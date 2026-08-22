from __future__ import annotations

import hashlib
import os
import random
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path


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
        traci_ok = True
        traci_path = getattr(traci, "__file__", None)
    except Exception:
        traci_ok = False
        traci_path = None
    try:
        import sumolib
        sumolib_ok = True
        sumolib_path = getattr(sumolib, "__file__", None)
    except Exception:
        sumolib_ok = False
        sumolib_path = None

    ready = bool(sumo and netconvert)
    return {
        "sumo": bool(sumo),
        "netconvert": bool(netconvert),
        "traci": traci_ok,
        "sumolib": sumolib_ok,
        "sumo_binary": sumo,
        "netconvert_binary": netconvert,
        "traci_path": traci_path,
        "sumolib_path": sumolib_path,
        "ready": ready,
        "transport": "SUMO FCD subprocess export",
        "engine": "SUMO microscopic traffic" if ready else "incomplete",
    }


def _seed(bus_id: str) -> int:
    return int(hashlib.sha256(bus_id.encode()).hexdigest()[:8], 16)


def _write_scenario(root: Path, bus_id: str, seed: int) -> tuple[Path, str]:
    nodes = root / "micro.nod.xml"
    edges = root / "micro.edg.xml"
    routes = root / "micro.rou.xml"
    net = root / "micro.net.xml"
    cfg = root / "micro.sumocfg"

    nodes.write_text(
        "<nodes>\n"
        "  <node id=\"n0\" x=\"0\" y=\"0\" type=\"priority\"/>\n"
        "  <node id=\"n1\" x=\"220\" y=\"0\" type=\"priority\"/>\n"
        "  <node id=\"n2\" x=\"440\" y=\"0\" type=\"priority\"/>\n"
        "  <node id=\"n3\" x=\"660\" y=\"0\" type=\"priority\"/>\n"
        "</nodes>\n",
        encoding="utf-8",
    )
    edges.write_text(
        "<edges>\n"
        "  <edge id=\"e0\" from=\"n0\" to=\"n1\" numLanes=\"3\" speed=\"16.7\"/>\n"
        "  <edge id=\"e1\" from=\"n1\" to=\"n2\" numLanes=\"3\" speed=\"13.9\"/>\n"
        "  <edge id=\"e2\" from=\"n2\" to=\"n3\" numLanes=\"3\" speed=\"16.7\"/>\n"
        "</edges>\n",
        encoding="utf-8",
    )

    rng = random.Random(seed)
    vtypes = [
        ("car", 4.5, 1.8, 2.6, 4.5, "passenger", 16.7),
        ("bike", 2.1, 0.8, 3.4, 5.0, "motorcycle", 18.0),
        ("auto", 2.8, 1.4, 2.4, 4.5, "passenger", 13.5),
        ("bus", 11.8, 2.5, 1.5, 3.5, "bus", 13.0),
        ("truck", 9.5, 2.5, 1.2, 3.0, "truck", 11.0),
        ("van", 5.2, 2.0, 2.0, 4.0, "delivery", 15.0),
        ("slowTruck", 10.5, 2.5, 0.9, 2.8, "truck", 7.5),
    ]
    max_speeds = {name: max_speed for name, _, _, _, _, _, max_speed in vtypes}
    lines = ["<routes>"]
    for name, length, width, accel, decel, vclass, max_speed in vtypes:
        lines.append(
            f'  <vType id="{name}" vClass="{vclass}" length="{length}" width="{width}" '
            f'accel="{accel}" decel="{decel}" minGap="1.2" sigma="0.35" carFollowModel="IDM" '
            f'laneChangeModel="LC2013" lcStrategic="1.0" lcCooperative="0.7" lcSpeedGain="1.0" '
            f'lcKeepRight="0.55" maxSpeed="{max_speed}"/>'
        )
    lines.append('  <route id="corridor" edges="e0 e1 e2"/>')

    lead_specs = [
        ("lead_car_0", "car", 0.0, 0, 10.5),
        ("lead_bike_0", "bike", 0.0, 2, 12.5),
        ("lead_auto_0", "auto", 0.4, 0, 9.5),
        ("lead_slow_truck", "slowTruck", 0.6, 1, 6.8),
        ("lead_van_0", "van", 1.2, 2, 10.0),
        ("lead_bus_0", "bus", 1.8, 0, 8.8),
        ("lead_car_1", "car", 2.3, 1, 9.2),
    ]
    for vid, kind, depart, lane, speed in lead_specs:
        safe_speed = min(speed, max_speeds[kind] * 0.95)
        lines.append(
            f'  <vehicle id="{vid}" type="{kind}" route="corridor" depart="{depart}" '
            f'departLane="{lane}" departSpeed="{safe_speed:.1f}"/>'
        )

    ego_id = f"ego_{bus_id.replace('-', '_')}"
    ego_speed = min(11.0, max_speeds["bus"] * 0.95)
    lines.append(
        f'  <vehicle id="{ego_id}" type="bus" route="corridor" depart="3.0" '
        f'departLane="1" departSpeed="{ego_speed:.1f}"><param key="prayaan" value="ego"/></vehicle>'
    )

    kinds = ["car", "bike", "auto", "car", "van", "bike", "truck", "car", "auto", "bus"]
    t = 3.35
    for i in range(72):
        t += rng.uniform(0.42, 0.88)
        kind = rng.choice(kinds)
        lane = rng.randrange(3)
        speed_ceiling = min(13.5, max_speeds[kind] * 0.90)
        speed_floor = min(5.5, speed_ceiling * 0.70)
        speed = rng.uniform(speed_floor, speed_ceiling)
        lines.append(
            f'  <vehicle id="{kind}_{i}" type="{kind}" route="corridor" depart="{t:.2f}" '
            f'departLane="{lane}" departSpeed="{speed:.1f}"/>'
        )
    lines.append("</routes>")
    routes.write_text("\n".join(lines), encoding="utf-8")

    netconvert = _binary("netconvert")
    if not netconvert:
        raise RuntimeError("netconvert unavailable")
    converted = subprocess.run(
        [netconvert, "--node-files", str(nodes), "--edge-files", str(edges), "--output-file", str(net), "--no-turnarounds", "true"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if converted.returncode != 0:
        detail = (converted.stderr or converted.stdout or "unknown netconvert error").strip()
        raise RuntimeError(f"netconvert failed: {detail}")

    cfg.write_text(
        "<configuration>\n"
        "  <input><net-file value=\"micro.net.xml\"/><route-files value=\"micro.rou.xml\"/></input>\n"
        "  <time><begin value=\"0\"/><end value=\"80\"/><step-length value=\"0.25\"/></time>\n"
        "  <processing><time-to-teleport value=\"-1\"/></processing>\n"
        "</configuration>\n",
        encoding="utf-8",
    )
    return cfg, ego_id


def _lane_index(lane_id: str | None) -> int:
    if not lane_id:
        return 1
    try:
        return int(lane_id.rsplit("_", 1)[1])
    except Exception:
        return 1


def _parse_fcd(fcd_path: Path, ego_id: str) -> list[dict]:
    frames: list[dict] = []
    for _, elem in ET.iterparse(fcd_path, events=("end",)):
        if elem.tag != "timestep":
            continue
        t = float(elem.attrib.get("time", "0"))
        if round((t * 100) % 50, 6) != 0:
            elem.clear()
            continue

        vehicles = []
        for node in elem.findall("vehicle"):
            vid = node.attrib.get("id", "")
            kind = node.attrib.get("type", "car")
            if kind == "slowTruck":
                kind = "truck"
            vehicles.append({
                "id": vid,
                "kind": kind,
                "x": round(float(node.attrib.get("x", "0")), 2),
                "y": round(float(node.attrib.get("y", "0")), 2),
                "speed": round(float(node.attrib.get("speed", "0")), 2),
                "angle": round(float(node.attrib.get("angle", "90")), 1),
                "lane": _lane_index(node.attrib.get("lane")),
                "ego": vid == ego_id,
            })

        ego = next((v for v in vehicles if v["ego"]), None)
        local = vehicles if not ego else [v for v in vehicles if abs(v["x"] - ego["x"]) <= 105]
        frames.append({
            "t": round(t, 2),
            "vehicles": local,
            "ego": ego,
            "local_density": len(local),
            "stopped_vehicles": sum(1 for v in local if v["speed"] < 0.5),
        })
        elem.clear()
    return frames


@lru_cache(maxsize=32)
def generate_bus_twin(bus_id: str) -> dict:
    components = status()
    if not components["sumo"] or not components["netconvert"]:
        return {
            "available": False,
            "bus_id": bus_id,
            "engine": "SUMO",
            "reason": "SUMO runtime incomplete. Re-run backend dependency installation.",
            "components": components,
        }

    seed = _seed(bus_id)
    with tempfile.TemporaryDirectory(prefix="prayaan_sumo_") as tmp:
        root = Path(tmp)
        try:
            cfg, ego_id = _write_scenario(root, bus_id, seed)
        except Exception as exc:
            return {"available": False, "bus_id": bus_id, "engine": "SUMO", "reason": str(exc), "components": components}

        fcd_path = root / "micro.fcd.xml"
        command = [
            components["sumo_binary"],
            "-c", str(cfg),
            "--seed", str(seed % 100000),
            "--no-step-log", "true",
            "--duration-log.disable", "true",
            "--fcd-output", str(fcd_path),
        ]
        try:
            run = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=45)
        except Exception as exc:
            return {
                "available": False,
                "bus_id": bus_id,
                "engine": "SUMO",
                "reason": f"SUMO subprocess failed to launch: {exc}",
                "components": components,
            }

        if run.returncode != 0:
            detail = (run.stderr or run.stdout or "SUMO exited without diagnostic output").strip()
            return {
                "available": False,
                "bus_id": bus_id,
                "engine": "SUMO",
                "reason": f"SUMO scenario failed: {detail}",
                "components": components,
                "command": command,
            }
        if not fcd_path.exists():
            return {
                "available": False,
                "bus_id": bus_id,
                "engine": "SUMO",
                "reason": "SUMO completed but did not create the FCD trajectory file.",
                "components": components,
            }

        try:
            frames = _parse_fcd(fcd_path, ego_id)
        except Exception as exc:
            return {
                "available": False,
                "bus_id": bus_id,
                "engine": "SUMO",
                "reason": f"SUMO trajectory parse failed: {exc}",
                "components": components,
            }

    if not frames:
        return {
            "available": False,
            "bus_id": bus_id,
            "engine": "SUMO",
            "reason": "SUMO produced no trajectory frames.",
            "components": components,
        }

    moving = [v for frame in frames for v in frame["vehicles"] if v.get("speed", 0) > 0.5]
    mean_speed = sum(v["speed"] for v in moving) / max(1, len(moving))
    kinds_seen = sorted({v["kind"] for frame in frames for v in frame["vehicles"]})
    return {
        "available": True,
        "bus_id": bus_id,
        "engine": "SUMO",
        "components": components,
        "physics": {"car_following": "IDM", "lane_change": "LC2013"},
        "seed": seed % 100000,
        "step_seconds": 0.5,
        "road_length_m": 660,
        "lanes": 3,
        "frames": frames,
        "summary": {
            "frames": len(frames),
            "vehicle_types": kinds_seen,
            "mean_speed_kmh": round(mean_speed * 3.6, 1),
            "source": "LIVE SUMO FCD TRAJECTORIES",
            "transport": "subprocess export (no TraCI socket)",
            "scenario": "mixed traffic with slow-moving lead traffic and seeded lane-change pressure",
        },
    }
