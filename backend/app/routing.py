"""
PRAYAAN V2 — hazard-aware fleet routing advisory.

Why this module exists
----------------------
Until now nothing in PRAYAAN *acted* on a confirmed defect. The system found
one, scored it, and displayed it. Detection without action is a dashboard.

What it deliberately does NOT do
--------------------------------
It does not reroute the public. We do not own the navigation surface drivers
use, and diverting an arterial because one lane edge is broken is
disproportionate. Instead it advises the fleet the city already operates — the
same buses that carry the sensors, and the vehicles most damaged by road
defects — and exposes the hazard layer for emergency dispatch to consume.

How it decides
--------------
Not binary road closure. A confirmed defect adds a COST PENALTY to the road
segment it sits on:

    edge_cost = travel_time * (1 + penalty)
    penalty   = sum over confirmed defects on edge of
                    severity * fused_confidence * type_weight

Unverified candidates contribute NOTHING. That is the same discipline the alert
pipeline applies: the system does not act on evidence it would not stand behind.
A weighted router naturally avoids a bad road when a reasonable alternative
exists and still uses it when none does — no absurd detours, no hard closures.

An advisory is only surfaced when the alternative is genuinely worth taking,
which keeps the operator from being trained to ignore it.
"""

from __future__ import annotations

import heapq
import math
from typing import Dict, List, Tuple

from .simulation import CORRIDORS, ROUTES, _haversine_m, _closest_approach


# A defect's routing weight is not its maintenance severity. A pothole damages
# suspension; standing water of unknown depth can stop a bus outright; a faded
# marking is a safety concern but does not impede the vehicle at all.
TYPE_WEIGHT = {
    # Vehicle-impeding: these physically damage or stop a bus.
    "MANHOLE_DAMAGE": 1.45,       # a sunken cover can break an axle
    "WATERLOGGING": 1.35,         # unknown depth can stop a bus outright
    "POTHOLE": 1.00,              # suspension damage, the classic case
    "SURFACE_CRACK": 0.45,
    # Safety-relevant but not vehicle-impeding: these are urgent REPAIRS, and
    # routing a bus around them helps nobody — the pedestrians are still there.
    # Low weights here are deliberate; a high one would let the system "solve" a
    # dangerous crossing by sending buses down a different street.
    "TRAFFIC_SIGNAL_FAULT": 0.70,  # an unlit signal genuinely raises collision risk
    "PEDESTRIAN_RISK": 0.55,
    "FADED_ZEBRA_CROSSING": 0.40,
    "STREETLIGHT_OUTAGE": 0.30,
    "FADED_MARKING": 0.25,
    "ILLEGAL_DUMPING": 0.25,       # can narrow a lane, rarely blocks one
    "DAMAGED_SIGNAGE": 0.20,
}

EDGE_INFLUENCE_M = 45.0   # how close a defect must be to count against a segment
ADVISORY_MIN_GAIN = 0.06  # ignore detours that save less than 6% hazard-cost
ADVISORY_MAX_DETOUR = 0.18  # never advise a detour costing >18% extra time

# Closure is judged on the WORST SINGLE DEFECT, never on a sum. Three moderate
# potholes on one leg are three repair jobs; they are not a road closure. Summing
# them would let the system escalate to shutting a road because a street is
# generally shabby, which is exactly the disproportionate behaviour that makes
# an advisory system get switched off.
# Calibrated against the actual weight range, not guessed. The maximum a single
# defect can score is ~1.45 (a sunken manhole at full severity and confidence).
# At 0.95 a merely-bad waterlogging cleared the bar and the system recommended
# closing four of six arterials at once — advice no depot would follow twice, and
# the fastest way to get an advisory system switched off. At 1.25 only a
# near-maximal vehicle-impeding defect escalates, which is the intent: closure is
# for "this will break an axle", not "this road is in poor condition".
CRITICAL_SINGLE_PENALTY = 1.25

# Roads that exist but carry no bus route.
#
# The graph built from ROUTES alone is almost a set of disjoint chains, so
# between two adjacent stops there is usually no second path and the router can
# never advise anything. That is an artefact of using bus routes as a proxy for
# the road network, not a property of Chennai. These are the cross-streets a
# driver would actually use — the router may send a bus down them; the scheduled
# service still runs its published route.
CONNECTORS = [
    # Real cross-streets linking the arterials, so the router has somewhere to
    # send a bus. Without these the graph is six near-disjoint chains and no
    # alternative path exists between adjacent stops — the router could never
    # advise anything, which is a property of using bus routes as a proxy for the
    # road network, not of Chennai.
    ((13.0418, 80.2341), (13.0517, 80.2264)),   # T. Nagar ↔ Kodambakkam
    ((13.0418, 80.2341), (13.0569, 80.2425)),   # T. Nagar ↔ Nungambakkam
    ((13.0213, 80.2231), (13.0350, 80.2100)),   # Saidapet ↔ Ashok Nagar
    ((13.0569, 80.2425), (13.0546, 80.2640)),   # Nungambakkam ↔ Royapettah
    ((13.0500, 80.2824), (13.0330, 80.2680)),   # Marina ↔ Mylapore
    ((13.0475, 80.2489), (13.0517, 80.2264)),   # Gemini ↔ Kodambakkam
    ((12.9650, 80.2450), (12.9830, 80.2590)),   # Perungudi ↔ Thiruvanmiyur
    ((13.0517, 80.2264), (13.0350, 80.2100)),   # Kodambakkam ↔ Ashok Nagar
    ((13.0418, 80.2341), (13.0510, 80.2120)),   # T. Nagar ↔ Vadapalani
    ((13.0475, 80.2489), (13.0330, 80.2680)),   # Gemini ↔ Mylapore
    ((13.0827, 80.2707), (13.0546, 80.2640)),   # Central ↔ Royapettah
    ((12.9756, 80.2207), (13.0067, 80.2206)),   # Velachery ↔ Guindy
]


def _node_key(lat: float, lng: float) -> str:
    return f"{lat:.5f},{lng:.5f}"


def build_graph() -> Tuple[Dict[str, tuple], Dict[str, List[dict]]]:
    """Undirected road graph from the fleet's own route geometry.

    Real arterials are shared, so the six services already meet at Broadway,
    Central, Vadapalani, Kodambakkam, CMBT, Guindy, Chromepet, Tambaram and
    Royapettah. A connected graph therefore falls out of the route data with no
    OSM import and no extra dependency, and it is small enough (34 nodes) that
    Dijkstra is effectively free — which matters, since this runs on every poll.
    """
    nodes: Dict[str, tuple] = {}
    adj: Dict[str, List[dict]] = {}

    for route in ROUTES.values():
        for lat, lng in route:
            k = _node_key(lat, lng)
            nodes[k] = (lat, lng)
            adj.setdefault(k, [])

    for route in ROUTES.values():
        for i in range(len(route)):
            a = route[i]
            b = route[(i + 1) % len(route)]
            ka, kb = _node_key(*a), _node_key(*b)
            if ka == kb:
                continue
            length = _haversine_m(a[0], a[1], b[0], b[1])
            if not any(e["to"] == kb for e in adj[ka]):
                adj[ka].append({"to": kb, "length_m": length, "kind": "BUS_ROUTE"})
                adj[kb].append({"to": ka, "length_m": length, "kind": "BUS_ROUTE"})

    for a, b in CONNECTORS:
        ka, kb = _node_key(*a), _node_key(*b)
        if ka not in nodes or kb not in nodes:
            continue
        if any(e["to"] == kb for e in adj[ka]):
            continue
        length = _haversine_m(a[0], a[1], b[0], b[1])
        adj[ka].append({"to": kb, "length_m": length, "kind": "CONNECTOR"})
        adj[kb].append({"to": ka, "length_m": length, "kind": "CONNECTOR"})

    return nodes, adj


def _corridor_speed(lat: float, lng: float, corridors: List[dict]) -> float:
    """Fleet-observed speed near this point, falling back to an urban default.

    Travel time should reflect what the buses actually measured, not a constant.
    """
    if corridors:
        near = min(corridors, key=lambda c: _haversine_m(lat, lng, c["lat"], c["lng"]))
        if _haversine_m(lat, lng, near["lat"], near["lng"]) < near["length_km"] * 500:
            return max(6.0, near["observed_speed"])
    return 24.0


def edge_penalties(assets: List[dict], nodes: Dict[str, tuple], adj: Dict[str, List[dict]]) -> Dict[str, dict]:
    """Hazard penalty per undirected edge, with the defects that caused it.

    Only CONFIRMED assets contribute. An UNVERIFIED candidate — which may be a
    tar patch a single camera misread — must never move a bus.
    """
    out: Dict[str, dict] = {}
    confirmed = [a for a in assets if a.get("status") == "CONFIRMED"]

    for ka, edges in adj.items():
        for e in edges:
            kb = e["to"]
            key = "|".join(sorted([ka, kb]))
            if key in out:
                continue
            a, b = nodes[ka], nodes[kb]
            penalty = 0.0
            causes = []
            for asset in confirmed:
                d, _ = _closest_approach(asset["lat"], asset["lng"], a[0], a[1], b[0], b[1])
                if d > EDGE_INFLUENCE_M:
                    continue
                w = TYPE_WEIGHT.get(asset["subtype"], 0.5)
                contribution = asset["severity"] * asset["fused_confidence"] * w
                penalty += contribution
                causes.append({
                    "asset_id": asset["id"],
                    "subtype": asset["subtype"],
                    "severity": round(asset["severity"], 3),
                    "fused_confidence": round(asset["fused_confidence"], 3),
                    "type_weight": w,
                    "offset_from_centreline_m": round(d, 1),
                    "penalty_contribution": round(contribution, 3),
                })
            out[key] = {
                "penalty": round(penalty, 3),
                "causes": causes,
                "length_m": round(e["length_m"], 1),
            }
    return out


def _dijkstra(start: str, goal: str, nodes, adj, penalties, corridors, use_penalty: bool):
    """Shortest path by travel time, optionally inflated by hazard penalty."""
    dist = {start: 0.0}
    prev: Dict[str, str] = {}
    pq = [(0.0, start)]
    visited = set()

    while pq:
        d, node = heapq.heappop(pq)
        if node in visited:
            continue
        visited.add(node)
        if node == goal:
            break
        for e in adj.get(node, []):
            nxt = e["to"]
            if nxt in visited:
                continue
            lat, lng = nodes[node]
            speed = _corridor_speed(lat, lng, corridors)
            minutes = (e["length_m"] / 1000.0) / speed * 60.0
            if use_penalty:
                key = "|".join(sorted([node, nxt]))
                minutes *= 1.0 + penalties.get(key, {}).get("penalty", 0.0)
            nd = d + minutes
            if nd < dist.get(nxt, math.inf):
                dist[nxt] = nd
                prev[nxt] = node
                heapq.heappush(pq, (nd, nxt))

    if goal not in dist:
        return None, math.inf
    path = [goal]
    while path[-1] != start:
        path.append(prev[path[-1]])
    return list(reversed(path)), dist[goal]


def _path_metrics(path, nodes, adj, penalties, corridors):
    """True travel time and accumulated hazard exposure along a path."""
    minutes = 0.0
    hazard = 0.0
    hit: List[dict] = []
    for a, b in zip(path, path[1:]):
        edge = next((e for e in adj[a] if e["to"] == b), None)
        if not edge:
            continue
        lat, lng = nodes[a]
        minutes += (edge["length_m"] / 1000.0) / _corridor_speed(lat, lng, corridors) * 60.0
        info = penalties.get("|".join(sorted([a, b])), {})
        hazard += info.get("penalty", 0.0)
        hit.extend(info.get("causes", []))
    return minutes, hazard, hit


def advisory(bus_id: str, assets: List[dict], corridors: List[dict]) -> dict:
    """Should this bus's route be changed because of confirmed road defects?"""
    route = ROUTES.get(bus_id)
    if not route:
        return {"available": False, "reason": f"unknown bus {bus_id}"}

    nodes, adj = build_graph()
    penalties = edge_penalties(assets, nodes, adj)

    keys = [_node_key(*p) for p in route]
    legs: List[dict] = []
    total_base_min = total_alt_min = 0.0
    total_base_haz = total_alt_haz = 0.0
    baseline_path: List[str] = []
    advised_path: List[str] = []

    for a, b in zip(keys, keys[1:] + keys[:1]):
        if a == b:
            continue
        base_path, _ = _dijkstra(a, b, nodes, adj, penalties, corridors, use_penalty=False)
        alt_path, _ = _dijkstra(a, b, nodes, adj, penalties, corridors, use_penalty=True)
        if not base_path or not alt_path:
            continue

        b_min, b_haz, b_causes = _path_metrics(base_path, nodes, adj, penalties, corridors)
        a_min, a_haz, _ = _path_metrics(alt_path, nodes, adj, penalties, corridors)

        total_base_min += b_min
        total_alt_min += a_min
        total_base_haz += b_haz
        total_alt_haz += a_haz
        baseline_path.extend(base_path[:-1])
        advised_path.extend(alt_path[:-1])

        if b_haz > 0:
            legs.append({
                "from": nodes[a], "to": nodes[b],
                "baseline_minutes": round(b_min, 1),
                "hazard_penalty": round(b_haz, 3),
                "causes": b_causes,
                "diverted": alt_path != base_path,
            })

    baseline_path.append(keys[0])
    advised_path.append(keys[0])

    detour_ratio = (total_alt_min - total_base_min) / max(1e-6, total_base_min)
    hazard_reduction = (total_base_haz - total_alt_haz) / max(1e-6, total_base_haz) if total_base_haz else 0.0

    # Worst SINGLE defect, not the worst leg total — see CRITICAL_SINGLE_PENALTY.
    worst_single = max(
        (c["penalty_contribution"] for l in legs for c in l["causes"]),
        default=0.0,
    )

    if worst_single >= CRITICAL_SINGLE_PENALTY:
        action, reason = "RECOMMEND_CLOSURE", (
            f"A single confirmed defect scores {round(worst_single, 2)}, past the point where "
            "routing around it is the right answer. Escalate to the road authority and "
            "notify emergency dispatch rather than quietly diverting buses past it."
        )
    elif total_base_haz <= 0:
        action, reason = "NO_ACTION", "No confirmed defect lies on this route."
    elif hazard_reduction < ADVISORY_MIN_GAIN:
        action, reason = "NO_ACTION", (
            "Confirmed defects lie on this route, but no alternative meaningfully "
            "reduces exposure — the hazard is unavoidable given the network."
        )
    elif detour_ratio > ADVISORY_MAX_DETOUR:
        action, reason = "MONITOR", (
            f"An avoiding route exists but costs {round(detour_ratio * 100)}% extra running "
            f"time, above the {round(ADVISORY_MAX_DETOUR * 100)}% threshold. Repair is the "
            "cheaper intervention."
        )
    else:
        action, reason = "ADVISE_REROUTE", (
            f"Avoiding the confirmed defects cuts hazard exposure by "
            f"{round(hazard_reduction * 100)}% for {round(detour_ratio * 100)}% extra running time."
        )

    return {
        "available": True,
        "bus_id": bus_id,
        "action": action,
        "reason": reason,
        "source": "HAZARD-WEIGHTED SHORTEST PATH (DIJKSTRA)",
        "scope": "FLEET ADVISORY ONLY — this system does not reroute the public.",
        "baseline": {
            "minutes": round(total_base_min, 1),
            "hazard_exposure": round(total_base_haz, 3),
            "path": [nodes[k] for k in baseline_path],
        },
        "advised": {
            "minutes": round(total_alt_min, 1),
            "hazard_exposure": round(total_alt_haz, 3),
            "path": [nodes[k] for k in advised_path],
        },
        "worst_single_defect_penalty": round(worst_single, 3),
        "detour_cost_pct": round(detour_ratio * 100, 1),
        "hazard_reduction_pct": round(hazard_reduction * 100, 1),
        "affected_legs": legs,
        "policy": {
            "unverified_candidates_ignored": True,
            "note": (
                "Only CONFIRMED assets influence routing. A single-camera candidate "
                "never moves a bus."
            ),
            "min_hazard_gain_pct": ADVISORY_MIN_GAIN * 100,
            "max_detour_pct": ADVISORY_MAX_DETOUR * 100,
        },
    }


def hazard_layer(assets: List[dict]) -> dict:
    """Confirmed hazards as a feed for other systems to consume.

    The strategic position: PRAYAAN is the verified-hazard SOURCE, not a rival
    navigation app. Emergency dispatch, the city's own systems, or a mapping
    provider can ingest this without adopting anything else we built.
    """
    confirmed = [a for a in assets if a.get("status") == "CONFIRMED"]
    return {
        "type": "FeatureCollection",
        "source": "PRAYAAN V2 — fleet-confirmed urban hazards",
        "policy": "Only assets confirmed by independent buses are published.",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [a["lng"], a["lat"]]},
                "properties": {
                    "asset_id": a["id"],
                    "subtype": a["subtype"],
                    "severity": a["severity"],
                    "fused_confidence": a["fused_confidence"],
                    "independent_buses": a["independent_buses"],
                    "position_uncertainty_m": a.get("position_uncertainty_m"),
                    "routing_weight": TYPE_WEIGHT.get(a["subtype"], 0.5),
                },
            }
            for a in confirmed
        ],
    }
