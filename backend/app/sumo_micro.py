from __future__ import annotations

import hashlib
import os
import random
import shutil
import subprocess
import tempfile
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
    return {
        "sumo": bool(sumo),
        "netconvert": bool(netconvert),
        "engine": "SUMO microscopic traffic" if sumo and netconvert else "unavailable",
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
        ("car", 4.5, 1.8, 2.6, 4.5, "passenger"),
        ("bike", 2.1, 0.8, 3.4, 5.0, "motorcycle"),
        ("auto", 2.8, 1.4, 2.4, 4.5, "passenger"),
        ("bus", 11.8, 2.5, 1.5, 3.5, "bus"),
        ("truck", 9.5, 2.5, 1.2, 3.0, "truck"),
        ("van", 5.2, 2.0, 2.0, 4.0, "delivery"),
    ]
    lines = ["<routes>"]
    for name, length, width, accel, decel, vclass in vtypes:
        lines.append(
            f'  <vType id="{name}" vClass="{vclass}" length="{length}" width="{width}" '
            f'accel="{accel}" decel="{decel}" minGap="1.2" sigma="0.35" carFollowModel="IDM" '
            f'lcStrategic="1.0" lcCooperative="0.7" lcSpeedGain="1.0" lcKeepRight="0.6"/>'
        )
    lines.append('  <route id="corridor" edges="e0 e1 e2"/>')
    ego_id = f"ego_{bus_id.replace('-', '_')}"
    lines.append(
        f'  <vehicle id="{ego_id}" type="bus" route="corridor" depart="0" '
        f'departLane="1" departSpeed="9.0"><param key="prayaan" value="ego"/></vehicle>'
    )

    kinds = ["car", "bike", "auto", "car", "van", "bike", "truck", "car", "auto", "bus"]
    for i in range(64):
        kind = rng.choice(kinds)
        depart = round(0.6 + i * rng.uniform(0.72, 1.12), 1)
        lane = rng.randrange(3)
        speed = round(rng.uniform(5.5, 13.5), 1)
        lines.append(
            f'  <vehicle id="{kind}_{i}" type="{kind}" route="corridor" depart="{depart}" '
            f'departLane="{lane}" departSpeed="{speed}"/>'
        )
    lines.append("</routes>")
    routes.write_text("\n".join(lines), encoding="utf-8")

    netconvert = _binary("netconvert")
    if not netconvert:
        raise RuntimeError("netconvert unavailable")
    subprocess.run(
        [netconvert, "--node-files", str(nodes), "--edge-files", str(edges), "--output-file", str(net), "--no-turnarounds", "true"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    cfg.write_text(
        "<configuration>\n"
        "  <input><net-file value=\"micro.net.xml\"/><route-files value=\"micro.rou.xml\"/></input>\n"
        "  <time><begin value=\"0\"/><end value=\"70\"/><step-length value=\"0.25\"/></time>\n"
        "  <processing><time-to-teleport value=\"-1\"/></processing>\n"
        "</configuration>\n",
        encoding="utf-8",
    )
    return cfg, ego_id


@lru_cache(maxsize=32)
def generate_bus_twin(bus_id: str) -> dict:
    sumo = _binary("sumo")
    if not sumo:
        return {
            "available": False,
            "bus_id": bus_id,
            "engine": "SUMO",
            "reason": "SUMO runtime unavailable. Reinstall backend requirements.",
        }

    try:
        import traci
    except Exception as exc:
        return {"available": False, "bus_id": bus_id, "engine": "SUMO", "reason": f"TraCI unavailable: {exc}"}

    seed = _seed(bus_id)
    with tempfile.TemporaryDirectory(prefix="prayaan_sumo_") as tmp:
        root = Path(tmp)
        try:
            cfg, ego_id = _write_scenario(root, bus_id, seed)
        except Exception as exc:
            return {"available": False, "bus_id": bus_id, "engine": "SUMO", "reason": str(exc)}

        label = f"prayaan_{seed}_{os.getpid()}"
        frames: list[dict] = []
        try:
            traci.start(
                [sumo, "-c", str(cfg), "--seed", str(seed % 100000), "--no-step-log", "true", "--duration-log.disable", "true"],
                label=label,
            )
            conn = traci.getConnection(label)
            for step in range(280):
                conn.simulationStep()
                if step % 2:
                    continue
                vehicles = []
                for vid in conn.vehicle.getIDList():
                    try:
                        kind = conn.vehicle.getTypeID(vid)
                        x, y = conn.vehicle.getPosition(vid)
                        speed = conn.vehicle.getSpeed(vid)
                        angle = conn.vehicle.getAngle(vid)
                        lane = conn.vehicle.getLaneIndex(vid)
                        vehicles.append({
                            "id": vid,
                            "kind": kind,
                            "x": round(x, 2),
                            "y": round(y, 2),
                            "speed": round(speed, 2),
                            "angle": round(angle, 1),
                            "lane": lane,
                            "ego": vid == ego_id,
                        })
                    except Exception:
                        pass
                ego = next((v for v in vehicles if v["ego"]), None)
                local = vehicles if not ego else [v for v in vehicles if abs(v["x"] - ego["x"]) <= 95]
                frames.append({"t": round(step * 0.25, 2), "vehicles": local, "ego": ego})
            conn.close()
        except Exception as exc:
            try:
                traci.getConnection(label).close()
            except Exception:
                pass
            return {"available": False, "bus_id": bus_id, "engine": "SUMO", "reason": f"SUMO run failed: {exc}"}

    moving = [v for frame in frames for v in frame["vehicles"] if v.get("speed", 0) > 0.5]
    mean_speed = sum(v["speed"] for v in moving) / max(1, len(moving))
    kinds_seen = sorted({v["kind"] for frame in frames for v in frame["vehicles"]})
    return {
        "available": True,
        "bus_id": bus_id,
        "engine": "SUMO",
        "physics": {"car_following": "IDM", "lane_change": "SUMO lane-change model"},
        "seed": seed % 100000,
        "step_seconds": 0.5,
        "road_length_m": 660,
        "lanes": 3,
        "frames": frames,
        "summary": {
            "frames": len(frames),
            "vehicle_types": kinds_seen,
            "mean_speed_kmh": round(mean_speed * 3.6, 1),
            "source": "LIVE SUMO TRAJECTORIES",
        },
    }
