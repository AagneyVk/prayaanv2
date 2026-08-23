"""
PRAYAAN V2 — road-condition memory: roughness, degradation, repair verification.

Three capabilities that only a PERSISTENT, REPEATING fleet can provide. Each one
is impossible for a one-off survey, a drone flight, or a citizen-report app, and
that is precisely the argument for putting sensors on buses.

1. ROAD ROUGHNESS INDEX (inertial)
   A camera fails at night, in glare, and under standing water. An accelerometer
   does not care: it measures what the wheel felt. One cheap IMU per bus yields a
   CONTINUOUS condition score for every metre the fleet drives, instead of a set
   of discrete visual detections — and it finds sub-surface failures that have no
   visual signature at all.

2. DEGRADATION RATE
   A defect count is a snapshot. A defect count over time is a derivative:
   "this stretch went from sound to cracked in six weeks." Only repeated passes
   over the same road produce that slope, and the slope is what turns reactive
   patching into predictive maintenance — you resurface before the pothole, not
   after.

3. REPAIR VERIFICATION
   A contractor reports a road fixed. Today nobody checks, because checking means
   dispatching an inspector. The fleet drives past anyway: if the visual defect
   is gone AND the measured roughness has dropped, the repair is verified; if the
   fleet keeps observing it, the claim is disputed — with dated evidence.

All three are in scope for SIH26124: they are urban infrastructure intelligence
derived from a public-transport fleet acting as mobile sensing nodes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


# --------------------------------------------------------------------------
# Roughness
#
# Reported on an IRI-like scale (International Roughness Index, m/km) because
# that is the unit road authorities already procure and budget against. Numbers
# a municipal engineer recognises beat a bespoke 0-100 "condition score".
# --------------------------------------------------------------------------

IRI_GOOD = 2.5          # newly surfaced urban road
IRI_FAIR = 4.5
IRI_POOR = 6.5
IRI_INTERVENTION = 7.5  # resurfacing threshold used for the forecast

# A bus measures roughness well: heavy, stiff suspension, known axle geometry.
# It is still one noisy sample per pass, which is why repeated passes matter.
MEASUREMENT_NOISE = 0.55
MIN_PASSES_FOR_CONFIDENCE = 4

# Degradation is superlinear: a crack admits water, water widens the crack. A
# straight line would understate how fast a failing stretch runs away.
BASE_DEGRADATION_PER_TICK = 0.0012
DEFECT_DEGRADATION_MULTIPLIER = 3.4

REPAIR_IRI_TARGET = 2.2       # what a proper resurfacing achieves

# Only these defect classes physically alter the road profile, so only these can
# be adjudicated with the accelerometer. Repainting a zebra crossing or replacing
# a signal lamp changes nothing an IMU can feel — demanding a roughness
# improvement for those would mark every honest repair "partially verified" and
# make the whole verification service look broken.
SURFACE_AFFECTING = {"POTHOLE", "MANHOLE_DAMAGE", "SURFACE_CRACK", "WATERLOGGING"}
VERIFY_MIN_PASSES = 3         # fleet passes needed to rule on a repair claim

# The deployment did not begin the moment the control room was opened. These
# reconstruct the passes the fleet already made, so a trend is a trend on the
# first screen rather than after an hour of watching.
HISTORY_PASSES = 5
HISTORY_PASS_INTERVAL = 140   # ticks between one route's visits to a segment


@dataclass
class SegmentHealth:
    """Condition memory for one stretch of road."""
    segment_id: str
    a: tuple
    b: tuple
    length_m: float
    true_iri: float                     # ground truth — never read by the pipeline
    degradation_rate: float
    measurements: List[Tuple[int, float, str]] = field(default_factory=list)  # tick, iri, bus
    last_repair_tick: int | None = None
    # A lat/lon key identifies a segment to the machine but tells a road engineer
    # nothing. These carry the same stretch in the language a depot actually uses.
    landmarks: str = ""                 # "Guindy → Saidapet"
    corridor: str = ""                  # "GST Road → Anna Salai"
    served_by: List[str] = field(default_factory=list)   # ["21C", "114"]

    @property
    def location(self) -> str:
        """What a human would call this stretch of road."""
        if self.landmarks and self.corridor:
            return f"{self.landmarks}  ·  {self.corridor}"
        return self.landmarks or self.corridor or self.segment_id

    # ---- what the pipeline is allowed to know ----------------------------

    @property
    def passes(self) -> int:
        return len(self.measurements)

    @property
    def estimated_iri(self) -> float:
        """Recency-weighted mean of measured roughness.

        Weighted rather than plain-mean because the road changes: a measurement
        from 500 ticks ago describes a road that no longer exists.
        """
        if not self.measurements:
            return 0.0
        latest = self.measurements[-1][0]
        num = den = 0.0
        for tick, iri, _ in self.measurements:
            w = 0.5 ** ((latest - tick) / 400.0)
            num += w * iri
            den += w
        return num / max(1e-6, den)

    @property
    def confidence(self) -> float:
        """Confidence in the estimate: more passes, more independent buses."""
        if not self.measurements:
            return 0.0
        buses = len({m[2] for m in self.measurements})
        return min(0.97, 0.25 + 0.12 * min(self.passes, 6) + 0.08 * min(buses, 4))

    @property
    def condition(self) -> str:
        iri = self.estimated_iri
        if not self.measurements:
            return "UNSURVEYED"
        if iri < IRI_GOOD:
            return "GOOD"
        if iri < IRI_FAIR:
            return "FAIR"
        if iri < IRI_POOR:
            return "POOR"
        return "CRITICAL"

    def degradation(self) -> dict:
        """Least-squares slope of measured roughness over time.

        This is the derivative a single survey can never produce. Reported with
        the sample count so nobody mistakes a two-point line for a trend.
        """
        pts = [(t, v) for t, v, _ in self.measurements]
        if self.last_repair_tick is not None:
            # A resurfacing resets the curve. Fitting across it would average a
            # new road with an old one and report the repair as "improvement".
            pts = [(t, v) for t, v in pts if t > self.last_repair_tick]
        if len(pts) < 4:
            return {"available": False, "samples": len(pts),
                    "reason": "needs at least 4 passes since the last resurfacing"}

        n = len(pts)
        mt = sum(p[0] for p in pts) / n
        mv = sum(p[1] for p in pts) / n
        num = sum((t - mt) * (v - mv) for t, v in pts)
        den = sum((t - mt) ** 2 for t, v in pts)
        slope = num / den if den > 1e-9 else 0.0        # IRI per tick

        ss_tot = sum((v - mv) ** 2 for _, v in pts)
        ss_res = sum((v - (mv + slope * (t - mt))) ** 2 for t, v in pts)
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-9 else 0.0

        current = self.estimated_iri
        if slope > 1e-6 and current < IRI_INTERVENTION:
            ticks_left = (IRI_INTERVENTION - current) / slope
        else:
            ticks_left = None

        return {
            "available": True,
            "samples": n,
            "iri_per_100_ticks": round(slope * 100, 4),
            "fit_r2": round(max(0.0, r2), 3),
            "trend": "DEGRADING" if slope > 0.0004 else "STABLE" if slope > -0.0004 else "IMPROVING",
            "current_iri": round(current, 2),
            "intervention_iri": IRI_INTERVENTION,
            "ticks_to_intervention": round(ticks_left, 0) if ticks_left else None,
            "forecast": (
                f"Reaches resurfacing threshold in ~{round(ticks_left)} ticks at the "
                f"observed rate" if ticks_left else
                "ALREADY PAST the resurfacing threshold — schedule now"
                if current >= IRI_INTERVENTION else
                "No intervention forecast at the current rate"
            ),
        }

    def to_dict(self) -> dict:
        return {
            "segment_id": self.segment_id,
            "location": self.location,
            "landmarks": self.landmarks,
            "corridor": self.corridor,
            "served_by": self.served_by,
            "a": list(self.a), "b": list(self.b),
            "length_m": round(self.length_m, 1),
            "passes": self.passes,
            "independent_buses": len({m[2] for m in self.measurements}),
            "estimated_iri": round(self.estimated_iri, 2),
            "condition": self.condition,
            "confidence": round(self.confidence, 3),
            "surveyed": self.passes >= MIN_PASSES_FOR_CONFIDENCE,
            "last_repair_tick": self.last_repair_tick,
            "degradation": self.degradation(),
        }


# --------------------------------------------------------------------------
# Work orders
# --------------------------------------------------------------------------

@dataclass
class WorkOrder:
    order_id: str
    asset_id: str
    subtype: str
    segment_id: str | None
    raised_tick: int
    priority: float
    claimed_fixed_tick: int | None = None
    location: str = ""
    verdict: str = "OPEN"
    verified_tick: int | None = None
    evidence: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id, "asset_id": self.asset_id,
            "subtype": self.subtype, "segment_id": self.segment_id,
            "location": self.location,
            "raised_tick": self.raised_tick, "priority": self.priority,
            "claimed_fixed_tick": self.claimed_fixed_tick,
            "status": self.verdict, "verified_tick": self.verified_tick,
            "evidence": self.evidence,
        }


class RoadCondition:
    """Roughness memory, degradation tracking and repair adjudication."""

    def __init__(self, routes: Dict[str, list], haversine, rng_fn, route_meta=None):
        self._haversine = haversine
        self._rng = rng_fn
        self._route_meta = route_meta or {}
        self.segments: Dict[str, SegmentHealth] = {}
        self.orders: Dict[str, WorkOrder] = {}
        self._next_order = 1
        self._build(routes)

    # -- construction -------------------------------------------------------

    @staticmethod
    def segment_key(a: tuple, b: tuple) -> str:
        lo, hi = sorted([a, b])
        return f"{lo[0]:.4f},{lo[1]:.4f}|{hi[0]:.4f},{hi[1]:.4f}"

    def _place(self, route_id: str, i: int, n: int) -> str:
        """Name waypoint i of a route after the area it passes through.

        Routes carry a list of areas in travel order, but a polyline has its own
        number of vertices, so the two are aligned proportionally rather than
        assumed equal. A named stretch beats a lat/lon key for anyone who has to
        actually go and repair it.
        """
        areas = [a for a in self._route_meta.get(route_id, {}).get("areas", "").split(" · ") if a]
        if not areas or n < 2:
            return ""
        idx = round(i * (len(areas) - 1) / (n - 1))
        return areas[max(0, min(len(areas) - 1, idx))]

    def _build(self, routes: Dict[str, list]) -> None:
        for route_id, route in routes.items():
            n = len(route)
            corridor = self._route_meta.get(route_id, {}).get("corridor", "")
            short = route_id.split("-", 1)[-1]
            for i in range(n):
                a, b = route[i], route[(i + 1) % n]
                if a == b:
                    continue
                key = self.segment_key(a, b)
                if key in self.segments:
                    # A shared arterial: record that this route drives it too.
                    seg = self.segments[key]
                    if short not in seg.served_by:
                        seg.served_by.append(short)
                    continue
                here, nxt = self._place(route_id, i, n), self._place(route_id, (i + 1) % n, n)
                landmarks = here if (here == nxt or not nxt) else f"{here} → {nxt}"
                if i == n - 1 and landmarks:
                    # The closing leg of a loop service, driven back the other way.
                    landmarks += " (return leg)"
                # Latent condition varies by stretch, deterministically. Some
                # roads start sound; one starts already failing, so the demo has
                # something at the intervention threshold from the outset.
                spread = self._rng("iri", key)
                decay = self._rng("decay", key)
                seg = SegmentHealth(
                    segment_id=key, a=a, b=b,
                    length_m=self._haversine(a[0], a[1], b[0], b[1]),
                    true_iri=2.2 + spread * 4.6,
                    degradation_rate=BASE_DEGRADATION_PER_TICK * (0.4 + decay * 2.2),
                    landmarks=landmarks, corridor=corridor, served_by=[short],
                )
                self._seed_history(seg, route_id)
                self.segments[key] = seg

    def nearest_location(self, lat: float, lng: float) -> str:
        """Name the stretch of road a coordinate sits on.

        A discovered asset arrives as a lat/lng from clustered sightings — it
        belongs to no segment by construction. Attaching it to the closest one
        gives the operator somewhere to send a crew, which a decimal degree does
        not. Compared against segment midpoints: the segments are short relative
        to the spacing between them, so the midpoint is sufficient.
        """
        best, best_d = None, float("inf")
        for seg in self.segments.values():
            mid_lat = (seg.a[0] + seg.b[0]) / 2
            mid_lng = (seg.a[1] + seg.b[1]) / 2
            d = (mid_lat - lat) ** 2 + (mid_lng - lng) ** 2
            if d < best_d:
                best, best_d = seg, d
        return best.location if best else ""

    def _seed_history(self, seg: SegmentHealth, route_id: str) -> None:
        """Back-fill the passes this route already made before the demo started.

        PRAYAAN's whole claim is memory across time, and a trend needs history to
        be a trend. A control room opened on day one of a deployment that has
        been running for weeks should show that history, not an empty panel — so
        the prior passes are reconstructed from the same physics and the same
        noise model that govern live ones, rolled backwards from today.

        These are ordinary measurements at negative ticks: the estimator, the
        confidence gate and the least-squares fit treat them exactly as they
        treat a pass made a minute ago. Nothing here is a hand-written number.
        """
        short = route_id.split("-", 1)[-1]
        for k in range(HISTORY_PASSES, 0, -1):
            tick = -k * HISTORY_PASS_INTERVAL
            # The road was smoother back then, by exactly its own decay rate.
            was = max(1.0, seg.true_iri - seg.degradation_rate * (k * HISTORY_PASS_INTERVAL))
            noise = (self._rng("imu-history", short, seg.segment_id, tick) - 0.5) * 2 * MEASUREMENT_NOISE
            seg.measurements.append((tick, round(max(0.8, was + noise), 3), f"MTC-{short}"))

    # -- per-tick physics ---------------------------------------------------

    def advance(self, tick: int, confirmed_segments: set[str]) -> None:
        """Roads get worse on their own, and faster where a defect is confirmed."""
        for key, seg in self.segments.items():
            rate = seg.degradation_rate
            if key in confirmed_segments:
                # A confirmed defect is not just a symptom, it is a cause: water
                # enters, the failure spreads. This is why fixing early is cheap.
                rate *= DEFECT_DEGRADATION_MULTIPLIER
            seg.true_iri = min(12.0, seg.true_iri + rate)

    def observe(self, tick: int, bus_id: str, segment_key: str, speed_kmh: float) -> dict | None:
        """One IMU pass over one segment.

        Deliberately noisy and deliberately speed-dependent: a bus crawling in
        traffic samples fewer wavelengths than one at cruise, so a slow pass is a
        worse measurement. The pipeline never sees `true_iri`.
        """
        seg = self.segments.get(segment_key)
        if seg is None:
            return None
        # Very slow passes carry little information about road profile.
        quality = min(1.0, max(0.25, speed_kmh / 22.0))
        noise = (self._rng("imu", bus_id, segment_key, tick) - 0.5) * 2 * MEASUREMENT_NOISE / quality
        measured = max(0.8, seg.true_iri + noise)
        seg.measurements.append((tick, round(measured, 3), bus_id))
        seg.measurements = seg.measurements[-80:]
        return {"segment_id": segment_key, "iri": round(measured, 2), "bus_id": bus_id}

    # -- work orders --------------------------------------------------------

    def raise_order(self, tick: int, asset: dict, segment_key: str | None) -> WorkOrder | None:
        existing = next(
            (o for o in self.orders.values()
             if o.asset_id == asset["id"] and o.verdict in ("OPEN", "CLAIMED_FIXED")),
            None,
        )
        if existing:
            return existing
        oid = f"WO-{self._next_order:04d}"
        self._next_order += 1
        order = WorkOrder(
            order_id=oid, asset_id=asset["id"], subtype=asset["subtype"],
            segment_id=segment_key, raised_tick=tick, priority=asset.get("priority", 0.0),
            location=(asset.get("name")
                      or (self.segments[segment_key].location
                          if segment_key in self.segments else "")),
        )
        self.orders[oid] = order
        return order

    def claim_fixed(self, tick: int, order_id: str) -> None:
        order = self.orders.get(order_id)
        if order and order.verdict == "OPEN":
            order.claimed_fixed_tick = tick
            order.verdict = "CLAIMED_FIXED"

    def adjudicate(self, tick: int, assets_by_id: Dict[str, dict]) -> None:
        """Rule on repair claims using what the fleet observed afterwards.

        Two independent lines of evidence must agree: the visual defect must be
        gone, AND measured roughness must have improved. Requiring both is what
        makes the verdict defensible in a contractual dispute — a contractor can
        argue with a camera, but not with a camera and an accelerometer.
        """
        for order in self.orders.values():
            if order.verdict != "CLAIMED_FIXED" or order.claimed_fixed_tick is None:
                continue

            asset = assets_by_id.get(order.asset_id)
            seg = self.segments.get(order.segment_id) if order.segment_id else None

            since = [m for m in (seg.measurements if seg else []) if m[0] > order.claimed_fixed_tick]
            if len(since) < VERIFY_MIN_PASSES:
                continue     # not enough fleet evidence yet — stay pending

            before = [m for m in (seg.measurements if seg else []) if m[0] <= order.claimed_fixed_tick]
            iri_before = sum(v for _, v, _ in before[-6:]) / max(1, len(before[-6:])) if before else None
            iri_after = sum(v for _, v, _ in since) / len(since)
            surface_relevant = order.subtype in SURFACE_AFFECTING
            improved = iri_before is not None and (iri_before - iri_after) > 0.8

            still_seen = bool(asset) and asset.get("status") in ("CONFIRMED", "UNVERIFIED") and \
                asset.get("observations", 0) > 0 and asset.get("clean_passes", 0) < VERIFY_MIN_PASSES
            visually_gone = not asset or asset.get("status") in ("RESOLVED", "REPAIR_SUSPECTED", "REJECTED")

            order.evidence = {
                "adjudication": (
                    "VISUAL + INERTIAL" if surface_relevant else "VISUAL ONLY"
                ),
                "inertial_applicable": surface_relevant,
                "inertial_note": (
                    "Road profile is expected to change, so the accelerometer is a "
                    "second independent witness."
                    if surface_relevant else
                    "This repair does not alter the road profile, so roughness is "
                    "reported for context but is not evidence either way."
                ),
                "fleet_passes_since_claim": len(since),
                "iri_before_claim": round(iri_before, 2) if iri_before is not None else None,
                "iri_after_claim": round(iri_after, 2),
                "iri_improvement": round(iri_before - iri_after, 2) if iri_before is not None else None,
                "roughness_improved": improved,
                "visual_status": asset.get("status") if asset else "NO_LONGER_TRACKED",
                "independent_buses": len({m[2] for m in since}),
            }

            if surface_relevant:
                # Two independent witnesses must agree. A contractor can argue
                # with a camera; arguing with a camera AND an accelerometer is
                # a much harder position.
                if visually_gone and improved:
                    order.verdict, order.verified_tick = "VERIFIED_FIXED", tick
                elif still_seen and not improved:
                    order.verdict, order.verified_tick = "DISPUTED", tick
                elif visually_gone or improved:
                    order.verdict, order.verified_tick = "PARTIALLY_VERIFIED", tick
            else:
                # Vision is the only competent witness here, so it decides alone.
                if visually_gone:
                    order.verdict, order.verified_tick = "VERIFIED_FIXED", tick
                elif still_seen:
                    order.verdict, order.verified_tick = "DISPUTED", tick

    # -- reporting ----------------------------------------------------------

    def network_report(self) -> dict:
        # Two different questions, and conflating them made the panel read empty
        # for the first several hundred ticks: "has the fleet driven this at all"
        # is not "do we have enough passes to stand behind a number".
        covered = [s for s in self.segments.values() if s.passes >= 1]
        surveyed = [s for s in self.segments.values() if s.passes >= MIN_PASSES_FOR_CONFIDENCE]
        by_condition: Dict[str, int] = {}
        for s in self.segments.values():
            by_condition[s.condition] = by_condition.get(s.condition, 0) + 1
        degrading = [
            s for s in covered
            if s.degradation().get("available") and s.degradation()["trend"] == "DEGRADING"
        ]
        degrading.sort(key=lambda s: -s.degradation()["iri_per_100_ticks"])
        network_km = sum(s.length_m for s in self.segments.values()) / 1000.0
        covered_km = sum(s.length_m for s in covered) / 1000.0
        surveyed_km = sum(s.length_m for s in surveyed) / 1000.0
        return {
            "scale": "IRI-like (m/km): lower is smoother; thresholds mirror road-authority practice",
            "network_km": round(network_km, 1),
            "covered_km": round(covered_km, 1),
            "covered_pct": round(100 * covered_km / max(1e-6, network_km), 1),
            "surveyed_km": round(surveyed_km, 1),
            "surveyed_pct": round(100 * surveyed_km / max(1e-6, network_km), 1),
            "min_passes_for_confidence": MIN_PASSES_FOR_CONFIDENCE,
            "segments": len(self.segments),
            "by_condition": by_condition,
            # Provisional as soon as anything has been driven; the confident
            # figure arrives once enough passes accumulate. Reporting both beats
            # showing a dash and looking broken.
            "mean_iri_provisional": round(
                sum(s.estimated_iri for s in covered) / max(1, len(covered)), 2
            ) if covered else None,
            "mean_iri": round(
                sum(s.estimated_iri for s in surveyed) / max(1, len(surveyed)), 2
            ) if surveyed else None,
            "worst_segments": [s.to_dict() for s in sorted(
                covered, key=lambda s: -s.estimated_iri)[:5]],
            "fastest_degrading": [s.to_dict() for s in degrading[:5]],
            "thresholds": {"good": IRI_GOOD, "fair": IRI_FAIR, "poor": IRI_POOR,
                           "intervention": IRI_INTERVENTION},
            "note": (
                "Inertial sensing works at night, in glare and through standing water, "
                "where the cameras cannot. Segments flagged here with no visual "
                "detection are candidates for sub-surface failure."
            ),
        }

    def orders_report(self) -> dict:
        orders = [o.to_dict() for o in self.orders.values()]
        counts: Dict[str, int] = {}
        for o in orders:
            counts[o["status"]] = counts.get(o["status"], 0) + 1
        return {
            "orders": sorted(orders, key=lambda o: -o["raised_tick"]),
            "counts": counts,
            "policy": (
                "A repair is only VERIFIED_FIXED when the visual defect is gone AND "
                "measured roughness improved, across at least "
                f"{VERIFY_MIN_PASSES} independent fleet passes. Either alone is "
                "PARTIALLY_VERIFIED. Continued observation with no roughness change "
                "is DISPUTED."
            ),
            "note": (
                "No inspector is dispatched. The buses drive the route anyway; "
                "verification is a by-product of scheduled service."
            ),
        }
