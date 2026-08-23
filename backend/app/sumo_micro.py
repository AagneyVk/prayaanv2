"""
PRAYAAN V2 — microscopic bus twin on real SUMO trajectories.

What changed and why
--------------------
The previous version ran a genuine SUMO simulation and then ignored it. The
"detections" were three dictionaries with hardcoded positions and hardcoded
confidences:

    {"id": "SCN-RASH", "x": 315.0, "confidence": 0.88, ...}

RASH DRIVING was therefore the *same static marker* as the pothole — a label the
ego bus drove past at a fixed coordinate. Nothing was detected, nothing was
analysed, and the two events behaved identically because mechanically they were
identical. Meanwhile every vehicle type shared `sigma=0.35` and one set of
lane-change parameters, so all traffic moved as a uniform block.

This module now does three things properly:

1. **Heterogeneous drivers.** Per-type reaction time, imperfection, gap
   acceptance, lane-change aggression and a per-driver speed factor drawn from a
   distribution. Two cars of the same type no longer drive identically, because
   real ones do not.

2. **Sublane lateral dynamics.** With SL2015 and a lateral resolution, vehicles
   occupy continuous lateral positions instead of snapping to lane centres.
   Motorcycles filter between lanes. This matters beyond looks: lateral velocity
   is the strongest single cue for erratic driving, and without sublane there is
   no lateral velocity to measure.

3. **Events DERIVED from the trajectories.** Nothing is placed at a fixed x.
   Every vehicle is scored on measured kinematics — harsh braking, lane-change
   rate, lateral velocity, speed variance — and the worst-scoring track becomes
   the anomaly event, at the time and place it actually occurred, with a
   confidence computed from the magnitudes. Run it with a different seed and a
   different vehicle is flagged, somewhere else, because the analysis is real.

Road defects are still SYNTHETIC INPUT — we do not own a camera fleet — but
their detection is geometric: the ego bus must actually pass within sensor range
and within the camera cone, and confidence falls off with distance and speed.
"""

from __future__ import annotations

import hashlib
import math
import os
import random
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path


# --------------------------------------------------------------------------
# Runtime discovery
# --------------------------------------------------------------------------

def _binary(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    try:
        from sumolib import checkBinary
        candidate = checkBinary(name)
        return candidate if candidate and os.path.exists(candidate) else None
    except Exception:
        return None


def status() -> dict:
    sumo = _binary("sumo")
    netconvert = _binary("netconvert")
    try:
        import traci
        traci_ok, traci_path = True, getattr(traci, "__file__", None)
    except Exception:
        traci_ok, traci_path = False, None
    try:
        import sumolib
        sumolib_ok, sumolib_path = True, getattr(sumolib, "__file__", None)
    except Exception:
        sumolib_ok, sumolib_path = False, None
    ready = bool(sumo and netconvert)
    return {
        "sumo": bool(sumo), "netconvert": bool(netconvert),
        "traci": traci_ok, "sumolib": sumolib_ok,
        "sumo_binary": sumo, "netconvert_binary": netconvert,
        "traci_path": traci_path, "sumolib_path": sumolib_path,
        "ready": ready, "transport": "SUMO FCD subprocess export",
        "engine": "SUMO microscopic traffic" if ready else "incomplete",
    }


def _seed(bus_id: str) -> int:
    return int(hashlib.sha256(bus_id.encode()).hexdigest()[:8], 16)


# --------------------------------------------------------------------------
# Driver population
#
# The whole point of a microscopic model is that individuals differ. These are
# the parameters that make them differ, and each is a claim about behaviour a
# traffic engineer can argue with:
#
#   tau          reaction time / desired time headway (s)
#   sigma        driver imperfection — how sloppily speed is held
#   minGap       standstill gap accepted (m)
#   speedFactor  per-driver desired speed as a fraction of the limit, drawn from
#                a truncated normal so no two drivers want the same speed
#   lcSpeedGain  eagerness to change lane purely to go faster
#   lcAssertive  willingness to accept a tight gap
#   latAlignment lateral position within the lane
# --------------------------------------------------------------------------

VEHICLE_CLASSES = [
    # name     len   wid  accel decel vClass        vmax  tau   sigma minGap speedFactor                  lcGain lcAssert latAlign
    ("car",    4.5,  1.8, 2.6,  4.5,  "passenger",  16.7, 1.00, 0.45, 2.0,  "normc(1.0,0.13,0.75,1.35)",  1.2,  1.0, "center"),
    ("bike",   1.9,  0.8, 3.6,  6.0,  "motorcycle", 18.0, 0.55, 0.62, 0.5,  "normc(1.12,0.18,0.8,1.6)",   4.5,  3.0, "arbitrary"),
    ("auto",   2.8,  1.4, 2.2,  4.2,  "passenger",  13.5, 0.85, 0.58, 1.0,  "normc(0.95,0.15,0.7,1.3)",   2.4,  1.8, "arbitrary"),
    ("bus",   11.8,  2.5, 1.3,  3.2,  "bus",        13.0, 1.35, 0.22, 3.0,  "normc(0.95,0.06,0.85,1.05)", 0.4,  0.5, "center"),
    ("truck",  9.5,  2.5, 1.0,  2.8,  "truck",      11.0, 1.50, 0.20, 3.2,  "normc(0.9,0.07,0.75,1.05)",  0.3,  0.4, "center"),
    ("van",    5.2,  2.0, 2.0,  4.0,  "delivery",   15.0, 1.05, 0.42, 2.2,  "normc(1.0,0.11,0.8,1.25)",   1.0,  0.9, "center"),
    # A minority of genuinely aggressive drivers. They are NOT tagged in the data
    # the analytics reads — the detector has to find them from motion alone,
    # which is the entire point of the exercise.
    ("rash",   4.3,  1.8, 5.2,  7.5,  "passenger",  19.5, 0.35, 0.78, 0.6,  "normc(1.45,0.12,1.2,1.75)",  9.0,  5.0, "arbitrary"),
]

SIM_END = 170.0         # seconds of simulated corridor time
STEP_LENGTH = 0.25      # SUMO integration step
SAMPLE_EVERY = 0.5      # trajectory sampling sent to the browser
LOCAL_WINDOW_M = 110.0  # how much of the corridor travels with the ego bus

# Synthetic roadside / road-surface defects. These are DECLARED INPUT — we do not
# own a camera fleet — but detection of them below is geometric, not scripted.
DEFECT_LIBRARY = [
    ("SCN-POTHOLE", "ROAD_DEFECT",    "POTHOLE",              "HIGH",     0.86),
    ("SCN-ZEBRA",   "SAFETY",         "FADED_ZEBRA_CROSSING", "HIGH",     0.72),
    ("SCN-SIGNAL",  "INFRASTRUCTURE", "TRAFFIC_SIGNAL_FAULT", "CRITICAL", 0.88),
    ("SCN-MANHOLE", "ROAD_HAZARD",    "MANHOLE_DAMAGE",       "CRITICAL", 0.92),
    ("SCN-WATER",   "ROAD_HAZARD",    "WATERLOGGING",         "MEDIUM",   0.74),
    ("SCN-DUMP",    "SANITATION",     "ILLEGAL_DUMPING",      "LOW",      0.58),
]

EGO_SENSOR_RANGE_M = 60.0
MIN_STANDOFF_M = 9.0     # closer than this and the defect is out of the camera frame
EGO_FOV_DEG = 62.0


def _write_scenario(root: Path, bus_id: str, seed: int) -> tuple[Path, str, list[dict]]:
    nodes, edges, routes = root / "micro.nod.xml", root / "micro.edg.xml", root / "micro.rou.xml"
    net, cfg = root / "micro.net.xml", root / "micro.sumocfg"

    nodes.write_text(
        '<nodes>\n'
        '  <node id="n0" x="0" y="0" type="priority"/>\n'
        '  <node id="n1" x="260" y="0" type="priority"/>\n'
        '  <node id="n2" x="520" y="0" type="priority"/>\n'
        '  <node id="n3" x="820" y="0" type="priority"/>\n'
        '</nodes>\n', encoding="utf-8")

    # A speed drop on the middle edge creates a genuine bottleneck, so congestion
    # forms as a backward-propagating shockwave instead of being drawn on.
    edges.write_text(
        '<edges>\n'
        '  <edge id="e0" from="n0" to="n1" numLanes="3" speed="16.7"/>\n'
        '  <edge id="e1" from="n1" to="n2" numLanes="3" speed="10.5"/>\n'
        '  <edge id="e2" from="n2" to="n3" numLanes="3" speed="16.7"/>\n'
        '</edges>\n', encoding="utf-8")

    rng = random.Random(seed)
    lines = ["<routes>"]

    for (name, length, width, accel, decel, vclass, vmax,
         tau, sigma, min_gap, speed_factor, lc_gain, lc_assert, lat_align) in VEHICLE_CLASSES:
        lines.append(
            f'  <vType id="{name}" vClass="{vclass}" length="{length}" width="{width}"'
            f' accel="{accel}" decel="{decel}" emergencyDecel="{decel + 2.5:.1f}"'
            f' minGap="{min_gap}" sigma="{sigma}" tau="{tau}" maxSpeed="{vmax}"'
            f' speedFactor="{speed_factor}"'
            f' carFollowModel="IDM" laneChangeModel="SL2015"'
            f' lcStrategic="1.0" lcCooperative="{0.15 if name == "rash" else 0.7}"'
            f' lcSpeedGain="{lc_gain}" lcAssertive="{lc_assert}"'
            f' lcKeepRight="{0.05 if name in ("rash", "bike") else 0.6}"'
            f' lcSublane="{3.0 if lat_align == "arbitrary" else 1.0}"'
            f' lcImpatience="{1.0 if name == "rash" else 0.3}"'
            f' latAlignment="{lat_align}"/>'
        )

    lines.append('  <route id="corridor" edges="e0 e1 e2"/>')

    # Probabilistic inflow: arrivals vary run to run and through the run, rather
    # than the same fixed roster marching past on every replay.
    flow_mix = [("car", 0.30), ("bike", 0.26), ("auto", 0.16), ("van", 0.08),
                ("truck", 0.06), ("bus", 0.04)]
    for kind, prob in flow_mix:
        jitter = rng.uniform(0.82, 1.18)
        lines.append(
            f'  <flow id="fl_{kind}" type="{kind}" route="corridor" begin="0"'
            f' end="{SIM_END - 20:.0f}" probability="{prob * jitter:.3f}"'
            f' departLane="random" departSpeed="desired"/>'
        )

    # A surge partway through, so the corridor is never in steady state.
    lines.append(
        f'  <flow id="fl_surge" type="car" route="corridor" begin="{SIM_END * 0.35:.0f}"'
        f' end="{SIM_END * 0.55:.0f}" probability="0.42" departLane="random"'
        f' departSpeed="desired"/>'
    )

    # Explicit vehicles MUST be emitted in departure order. SUMO does not sort
    # them for you — it prints "Route file should be sorted by departure time"
    # and silently DROPS the offending vehicle. That is how the ego bus vanished
    # from the simulation while everything still reported success.
    explicit: list[tuple[float, str]] = []

    ego_id = f"ego_{bus_id.replace('-', '_')}"
    explicit.append((
        8.0,
        f'  <vehicle id="{ego_id}" type="bus" route="corridor" depart="8.0"'
        f' departLane="best" departSpeed="desired">'
        f'<param key="prayaan" value="ego"/></vehicle>'
    ))

    # Aggressive drivers enter at seed-dependent times. Where and when they
    # actually misbehave is NOT scripted — it emerges from their parameters
    # meeting the bottleneck, and the analytics has to find them.
    for i in range(3):
        depart = rng.uniform(14.0, 22.0) + i * rng.uniform(32.0, 46.0)
        explicit.append((
            depart,
            f'  <vehicle id="rash_{i}" type="rash" route="corridor"'
            f' depart="{depart:.1f}" departLane="{rng.randrange(3)}" departSpeed="max"/>'
        ))

    for _, xml in sorted(explicit, key=lambda e: e[0]):
        lines.append(xml)

    lines.append("</routes>")
    routes.write_text("\n".join(lines), encoding="utf-8")

    netconvert = _binary("netconvert")
    if not netconvert:
        raise RuntimeError("netconvert unavailable")
    converted = subprocess.run(
        [netconvert, "--node-files", str(nodes), "--edge-files", str(edges),
         "--output-file", str(net), "--no-turnarounds", "true"],
        capture_output=True, text=True, timeout=40)
    if converted.returncode != 0:
        raise RuntimeError(f"netconvert failed: {(converted.stderr or converted.stdout).strip()}")

    cfg.write_text(
        '<configuration>\n'
        '  <input><net-file value="micro.net.xml"/><route-files value="micro.rou.xml"/></input>\n'
        f'  <time><begin value="0"/><end value="{SIM_END:.0f}"/>'
        f'<step-length value="{STEP_LENGTH}"/></time>\n'
        '  <processing>\n'
        '    <time-to-teleport value="-1"/>\n'
        # Load the whole route file up front instead of streaming it. Without
        # this, SUMO demands departure-sorted input across flows AND explicit
        # vehicles, and silently DROPS anything out of order — which is exactly
        # how the ego bus and two aggressive drivers disappeared from a run that
        # still reported success.
        '    <route-steps value="-1"/>\n'
        # Sublane resolution gives continuous lateral positions, which is what
        # makes lateral-velocity analytics possible at all.
        '    <lateral-resolution value="0.64"/>\n'
        '    <collision.action value="warn"/>\n'
        '  </processing>\n'
        '</configuration>\n', encoding="utf-8")

    defects = []
    span = 700.0
    for i, (did, dtype, subtype, sev, base_conf) in enumerate(DEFECT_LIBRARY):
        defects.append({
            "id": did, "type": dtype, "subtype": subtype, "severity": sev,
            "base_confidence": base_conf,
            "x": round(80.0 + span * (i + 0.5) / len(DEFECT_LIBRARY) + rng.uniform(-16, 16), 1),
            "lane": rng.randrange(3),
            "source": "SYNTHETIC ROADSIDE INPUT",
        })
    return cfg, ego_id, defects


def _lane_index(lane_id) -> int:
    try:
        return int(str(lane_id).rsplit("_", 1)[1])
    except Exception:
        return 1


def _parse_fcd(path: Path, ego_id: str) -> tuple[list[dict], dict]:
    """Sample the FCD, and build per-vehicle tracks for the analytics pass."""
    frames: list[dict] = []
    tracks: dict[str, list[dict]] = {}
    ratio = SAMPLE_EVERY / STEP_LENGTH

    for _, elem in ET.iterparse(path, events=("end",)):
        if elem.tag != "timestep":
            continue
        t = float(elem.attrib.get("time", "0"))
        steps = t / STEP_LENGTH
        if abs(steps / ratio - round(steps / ratio)) > 1e-6:
            elem.clear()
            continue

        vehicles = []
        for node in elem.findall("vehicle"):
            vid = node.attrib.get("id", "")
            kind = node.attrib.get("type", "car")
            v = {
                "id": vid,
                # The analytics must not be able to read "this one is the rash
                # driver" off the vehicle type — that would be grading its own
                # homework. Aggressive drivers are reported as ordinary cars.
                "kind": "car" if kind == "rash" else kind,
                "x": round(float(node.attrib.get("x", "0")), 2),
                "y": round(float(node.attrib.get("y", "0")), 2),
                "speed": round(float(node.attrib.get("speed", "0")), 2),
                "angle": round(float(node.attrib.get("angle", "90")), 1),
                "lane": _lane_index(node.attrib.get("lane")),
                "ego": vid == ego_id,
            }
            vehicles.append(v)
            tracks.setdefault(vid, []).append({**v, "t": round(t, 2)})

        ego = next((v for v in vehicles if v["ego"]), None)
        local = vehicles if not ego else [
            v for v in vehicles if abs(v["x"] - ego["x"]) <= LOCAL_WINDOW_M
        ]
        frames.append({
            "t": round(t, 2),
            "vehicles": local,
            "ego": ego,
            "local_density": len(local),
            "stopped_vehicles": sum(1 for v in local if v["speed"] < 0.5),
        })
        elem.clear()

    return frames, tracks


# --------------------------------------------------------------------------
# Trajectory analytics — the part that used to be a hardcoded dictionary.
# --------------------------------------------------------------------------

def _score_track(track: list[dict]) -> dict | None:
    """Measure how erratically one vehicle actually drove.

    Every term comes from the trajectory. None of them knows the vehicle type.
    """
    if len(track) < 8:
        return None

    harsh_brakes = 0
    max_decel = 0.0
    lane_changes = 0
    max_lateral = 0.0
    lateral_sum = 0.0
    speeds: list[float] = []
    worst_t, worst_x, worst_lane = track[0]["t"], track[0]["x"], track[0]["lane"]
    worst_reason, worst_metric = "speed_variance", 0.0

    for a, b in zip(track, track[1:]):
        dt = max(1e-3, b["t"] - a["t"])
        accel = (b["speed"] - a["speed"]) / dt
        lateral = abs(b["y"] - a["y"]) / dt
        speeds.append(b["speed"])
        lateral_sum += lateral
        max_lateral = max(max_lateral, lateral)

        if accel < -3.0:
            harsh_brakes += 1
            max_decel = max(max_decel, -accel)
            if -accel > worst_metric:
                worst_metric = -accel
                worst_t, worst_x, worst_lane, worst_reason = b["t"], b["x"], b["lane"], "harsh_braking"
        if b["lane"] != a["lane"]:
            lane_changes += 1
            if lateral * 2.0 > worst_metric:
                worst_metric = lateral * 2.0
                worst_t, worst_x, worst_lane, worst_reason = b["t"], b["x"], b["lane"], "lane_change"

    duration = max(1e-3, track[-1]["t"] - track[0]["t"])
    mean_speed = sum(speeds) / max(1, len(speeds))
    speed_var = sum((s - mean_speed) ** 2 for s in speeds) / max(1, len(speeds))

    lc_rate = lane_changes / duration * 60.0     # lane changes per minute
    brake_rate = harsh_brakes / duration * 60.0
    mean_lateral = lateral_sum / max(1, len(track) - 1)

    terms = {
        "lane_change_rate_per_min": round(lc_rate, 2),
        "harsh_brake_rate_per_min": round(brake_rate, 2),
        "peak_deceleration_ms2": round(max_decel, 2),
        "peak_lateral_speed_ms": round(max_lateral, 2),
        "mean_lateral_speed_ms": round(mean_lateral, 3),
        "speed_variance": round(speed_var, 2),
        "mean_speed_kmh": round(mean_speed * 3.6, 1),
        "observed_seconds": round(duration, 1),
    }
    score = (
        0.30 * min(1.0, lc_rate / 12.0)
        + 0.24 * min(1.0, brake_rate / 8.0)
        + 0.18 * min(1.0, max_decel / 6.0)
        + 0.16 * min(1.0, max_lateral / 1.6)
        + 0.12 * min(1.0, speed_var / 14.0)
    )
    return {
        "vehicle_id": track[0]["id"],
        "score": round(score, 3),
        "terms": terms,
        "at_time": worst_t,
        "at_x": worst_x,
        "at_lane": worst_lane,
        "trigger": worst_reason,
    }


def _driving_anomalies(tracks: dict, ego_id: str, ego_track: list[dict]) -> list[dict]:
    """Flag the worst-driving vehicles the ego bus was actually close to."""
    scored = []
    for vid, track in tracks.items():
        if vid == ego_id:
            continue
        s = _score_track(track)
        if not s:
            continue
        # Only report what this bus could have witnessed. An anomaly 400 m away
        # is not its evidence, and claiming it would be dishonest.
        ego_at = next((e for e in ego_track if abs(e["t"] - s["at_time"]) < 1.0), None)
        if not ego_at or abs(ego_at["x"] - s["at_x"]) > 90.0:
            continue
        s["range_from_bus_m"] = round(abs(ego_at["x"] - s["at_x"]), 1)
        scored.append(s)

    scored.sort(key=lambda s: -s["score"])
    out = []
    for s in scored[:2]:
        if s["score"] < 0.28:
            continue
        severity = "CRITICAL" if s["score"] >= 0.55 else "HIGH" if s["score"] >= 0.40 else "MEDIUM"
        conf = min(0.96, 0.45 + 0.5 * s["score"]) * (1.0 - min(0.35, s["range_from_bus_m"] / 260.0))
        t = s["terms"]
        out.append({
            "id": f"ANOM-{s['vehicle_id']}",
            "type": "DRIVING_ANOMALY",
            "label": "ERRATIC DRIVING",
            "x": s["at_x"], "lane": s["at_lane"], "t": s["at_time"],
            "severity": severity,
            "confidence": round(conf, 3),
            "score": s["score"],
            "trigger": s["trigger"],
            "range_from_bus_m": s["range_from_bus_m"],
            "source": "DERIVED FROM SUMO TRAJECTORY",
            "pipeline": "LIVE TRAJECTORY ANALYTICS",
            "detail": (
                f"{t['lane_change_rate_per_min']} lane changes/min, "
                f"{t['harsh_brake_rate_per_min']} harsh brakes/min, peak decel "
                f"{t['peak_deceleration_ms2']} m/s², peak lateral "
                f"{t['peak_lateral_speed_ms']} m/s. Flagged on measured motion, "
                f"not on vehicle class."
            ),
            "evidence": t,
            "action": "Raise safety observation; corridor behaviour flagged for review.",
            # ANPR is deliberately out of scope. An invented plate would be the
            # one fabricated record in an otherwise honest demo, and plate capture
            # turns an infrastructure tool into a surveillance one.
            "identification": "ANONYMISED_TRACK",
            "track_ref": s["vehicle_id"],
            "anpr": "NOT PERFORMED — vehicle identification deliberately out of scope",
        })
    return out


def _defect_detections(defects: list[dict], ego_track: list[dict]) -> list[dict]:
    """Detect roadside defects the ego bus genuinely passed within range of."""
    out = []
    for d in defects:
        # A forward camera classifies a defect on APPROACH, not as the bus drives
        # over it — by then it is under the bumper and out of frame. Require a
        # minimum standoff and take the best-quality look, which lands detections
        # at a realistic 10-30 m rather than reporting a 1 m "observation" the
        # camera could never have made.
        best = None
        for p in ego_track:
            dx = d["x"] - p["x"]
            if dx < MIN_STANDOFF_M:
                continue                     # too close, or already passed
            lateral = abs((d["lane"] - p["lane"]) * 3.2)
            rng_m = math.hypot(dx, lateral)
            if rng_m > EGO_SENSOR_RANGE_M:
                continue
            bearing = abs(math.degrees(math.atan2(lateral, max(0.5, dx))))
            if bearing > EGO_FOV_DEG / 2:
                continue                     # outside the forward camera cone
            quality = (1.0 - (rng_m / EGO_SENSOR_RANGE_M) ** 1.5) * max(0.35, 1.0 - p["speed"] / 26.0)
            if best is None or quality > best[3]:
                best = (rng_m, p, bearing, quality)
        if not best:
            continue
        rng_m, p, bearing, _q = best
        range_q = 1.0 - (rng_m / EGO_SENSOR_RANGE_M) ** 1.5
        blur_q = max(0.35, 1.0 - p["speed"] / 26.0)
        conf = min(0.97, d["base_confidence"] * (0.55 + 0.45 * range_q) * (0.7 + 0.3 * blur_q))
        out.append({
            "id": d["id"], "type": d["type"],
            "label": d["subtype"].replace("_", " "),
            "subtype": d["subtype"],
            "x": d["x"], "lane": d["lane"], "t": p["t"],
            "severity": d["severity"], "confidence": round(conf, 3),
            "source": "SYNTHETIC ROADSIDE INPUT",
            "pipeline": "LIVE GEOMETRIC DETECTION",
            "detail": (
                f"Observed at {rng_m:.0f} m, {bearing:.0f}° off centreline, bus at "
                f"{p['speed'] * 3.6:.0f} km/h. Confidence follows the viewing geometry."
            ),
            "evidence": {
                "range_m": round(rng_m, 1),
                "bearing_deg": round(bearing, 1),
                "range_quality": round(range_q, 3),
                "motion_blur_quality": round(blur_q, 3),
                "bus_speed_kmh": round(p["speed"] * 3.6, 1),
            },
            "action": "Create geotagged observation; await independent-bus confirmation.",
        })
    return out


def _corridor_analytics(frames: list[dict]) -> dict:
    """Congestion measured from the trajectories, not asserted."""
    densities = [f["local_density"] for f in frames]
    stopped = [f["stopped_vehicles"] for f in frames]
    speeds = [v["speed"] for f in frames for v in f["vehicles"] if v["speed"] > 0.2]
    peak_i = max(range(len(densities)), key=lambda i: densities[i]) if densities else 0
    return {
        "mean_local_density": round(sum(densities) / max(1, len(densities)), 1),
        "peak_local_density": max(densities) if densities else 0,
        "peak_density_at_s": frames[peak_i]["t"] if frames else 0,
        "max_stopped_vehicles": max(stopped) if stopped else 0,
        "mean_speed_kmh": round(sum(speeds) / max(1, len(speeds)) * 3.6, 1),
        "note": (
            "The middle edge has a lower speed limit, so congestion forms as a "
            "backward-propagating shockwave rather than being drawn on."
        ),
    }


@lru_cache(maxsize=32)
def generate_bus_twin(bus_id: str) -> dict:
    components = status()
    if not components["sumo"] or not components["netconvert"]:
        return {"available": False, "bus_id": bus_id, "engine": "SUMO",
                "reason": "SUMO runtime incomplete. Re-run backend dependency installation.",
                "components": components}

    seed = _seed(bus_id)
    with tempfile.TemporaryDirectory(prefix="prayaan_sumo_") as tmp:
        root = Path(tmp)
        try:
            cfg, ego_id, defects = _write_scenario(root, bus_id, seed)
        except Exception as exc:
            return {"available": False, "bus_id": bus_id, "engine": "SUMO",
                    "reason": str(exc), "components": components}

        fcd = root / "micro.fcd.xml"
        command = [components["sumo_binary"], "-c", str(cfg), "--seed", str(seed % 100000),
                   "--no-step-log", "true", "--duration-log.disable", "true",
                   "--fcd-output", str(fcd)]
        try:
            run = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=120)
        except Exception as exc:
            return {"available": False, "bus_id": bus_id, "engine": "SUMO",
                    "reason": f"SUMO subprocess failed to launch: {exc}", "components": components}
        if run.returncode != 0:
            return {"available": False, "bus_id": bus_id, "engine": "SUMO",
                    "reason": f"SUMO scenario failed: {(run.stderr or run.stdout or 'no diagnostic').strip()}",
                    "components": components}
        if not fcd.exists():
            return {"available": False, "bus_id": bus_id, "engine": "SUMO",
                    "reason": "SUMO completed but did not create the FCD trajectory file.",
                    "components": components}
        try:
            frames, tracks = _parse_fcd(fcd, ego_id)
        except Exception as exc:
            return {"available": False, "bus_id": bus_id, "engine": "SUMO",
                    "reason": f"SUMO trajectory parse failed: {exc}", "components": components}

    if not frames:
        return {"available": False, "bus_id": bus_id, "engine": "SUMO",
                "reason": "SUMO produced no trajectory frames.", "components": components}

    ego_track = tracks.get(ego_id, [])
    anomalies = _driving_anomalies(tracks, ego_id, ego_track)
    detections = _defect_detections(defects, ego_track)
    scenarios = sorted(detections + anomalies, key=lambda s: s.get("t", 0))

    moving = [v for f in frames for v in f["vehicles"] if v.get("speed", 0) > 0.5]
    mean = sum(v["speed"] for v in moving) / max(1, len(moving))
    kinds = sorted({v["kind"] for f in frames for v in f["vehicles"]})

    return {
        "available": True, "bus_id": bus_id, "engine": "SUMO", "components": components,
        "physics": {
            "car_following": "IDM",
            "lane_change": "SL2015",
            "sublane": True,
            "lateral_resolution_m": 0.64,
            "heterogeneous_drivers": True,
            "note": (
                "Per-type reaction time, imperfection, gap acceptance and lane-change "
                "aggression, plus a per-driver speed factor drawn from a truncated "
                "normal. No two drivers share a desired speed."
            ),
        },
        "seed": seed % 100000,
        "step_seconds": SAMPLE_EVERY,
        "road_length_m": 820,
        "lanes": 3,
        "frames": frames,
        "scenarios": scenarios,
        "anomalies": anomalies,
        "corridor": _corridor_analytics(frames),
        "summary": {
            "frames": len(frames),
            "duration_s": SIM_END,
            "tracked_vehicles": len(tracks),
            "vehicle_types": kinds,
            "mean_speed_kmh": round(mean * 3.6, 1),
            "anomalies_detected": len(anomalies),
            "defects_observed": len(detections),
            "source": "LIVE SUMO FCD TRAJECTORIES",
            "transport": "subprocess export (no TraCI socket)",
            "scenario": "heterogeneous mixed traffic + bottleneck; events derived from trajectories",
        },
        "provenance": {
            "traffic_motion": "REAL SUMO MICROSCOPIC SIMULATION",
            "driving_anomalies": "DERIVED FROM SIMULATED TRAJECTORIES (live analytics)",
            "roadside_defects": "SYNTHETIC INPUT, GEOMETRIC DETECTION",
            "vehicle_identification": "NOT PERFORMED",
            "analytics_pipeline": "LIVE SOFTWARE",
        },
    }
