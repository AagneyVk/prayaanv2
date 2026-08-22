from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Set


ROUTES = {
    "MTC-021": [(13.0827, 80.2707), (13.0604, 80.2496), (13.0402, 80.2448), (13.0067, 80.2570), (12.9864, 80.2451)],
    "MTC-034": [(13.1143, 80.1548), (13.0878, 80.1987), (13.0694, 80.1948), (13.0501, 80.2124), (13.0305, 80.2302)],
    "MTC-057": [(12.9249, 80.1000), (12.9517, 80.1413), (12.9756, 80.2207), (13.0067, 80.2570), (13.0402, 80.2448)],
    "MTC-102": [(13.0475, 80.2090), (13.0358, 80.2285), (13.0214, 80.2412), (13.0067, 80.2570), (12.9916, 80.2642)],
    "MTC-118": [(13.0901, 80.2144), (13.0744, 80.2299), (13.0604, 80.2496), (13.0475, 80.2592), (13.0337, 80.2688)],
    "MTC-145": [(12.9702, 80.2210), (12.9864, 80.2451), (13.0067, 80.2570), (13.0282, 80.2661), (13.0491, 80.2820)],
}

EVENT_SITES = [
    {"id": "RD-1842", "type": "ROAD_DEFECT", "subtype": "POTHOLE", "lat": 13.0402, "lng": 80.2448, "severity": 0.88, "title": "Deep lane-edge pothole"},
    {"id": "INF-220", "type": "INFRASTRUCTURE", "subtype": "DAMAGED_SIGNAGE", "lat": 13.0694, "lng": 80.1948, "severity": 0.63, "title": "Damaged directional sign"},
    {"id": "HZ-091", "type": "ROAD_HAZARD", "subtype": "WATERLOGGING", "lat": 12.9864, "lng": 80.2451, "severity": 0.78, "title": "Recurring waterlogging"},
    {"id": "SAFE-77", "type": "SAFETY", "subtype": "PEDESTRIAN_RISK", "lat": 13.0067, "lng": 80.2570, "severity": 0.72, "title": "Vulnerable pedestrian crossing"},
]

CORRIDORS = [
    {"id": "COR-OMR", "name": "OMR Corridor", "normal_speed": 34.0, "base_speed": 18.0, "lat": 12.9864, "lng": 80.2451, "length_km": 7.4},
    {"id": "COR-ANNA", "name": "Anna Salai", "normal_speed": 31.0, "base_speed": 14.0, "lat": 13.0604, "lng": 80.2496, "length_km": 5.8},
]


@dataclass
class Bus:
    bus_id: str
    route: List[tuple]
    route_index: int = 0
    progress: float = 0.0
    speed_kmh: float = 25.0
    heading: float = 0.0
    camera_status: Dict[str, str] = field(default_factory=lambda: {
        "front": "ACTIVE", "rear": "ACTIVE", "left": "ACTIVE", "right": "ACTIVE"
    })

    def step(self, dt: float, rng: random.Random) -> dict:
        start = self.route[self.route_index]
        end = self.route[(self.route_index + 1) % len(self.route)]
        self.speed_kmh = max(7.0, min(42.0, self.speed_kmh + rng.uniform(-2.2, 2.2)))
        self.progress += dt * (0.025 + self.speed_kmh / 1600.0)
        if self.progress >= 1.0:
            self.progress -= 1.0
            self.route_index = (self.route_index + 1) % len(self.route)
            start = self.route[self.route_index]
            end = self.route[(self.route_index + 1) % len(self.route)]
        lat = start[0] + (end[0] - start[0]) * self.progress
        lng = start[1] + (end[1] - start[1]) * self.progress
        self.heading = math.degrees(math.atan2(end[1] - start[1], end[0] - start[0]))
        return {
            "bus_id": self.bus_id,
            "lat": round(lat, 6),
            "lng": round(lng, 6),
            "speed_kmh": round(self.speed_kmh, 1),
            "heading": round(self.heading, 1),
            "route_name": f"Route {self.bus_id.split('-')[-1]}",
            "edge_fps": round(rng.uniform(23.5, 29.8), 1),
            "uplink_kbps": round(rng.uniform(5.0, 12.0), 1),
            "camera_status": self.camera_status,
        }


@dataclass
class AssetState:
    observations: int = 0
    seen_buses: Set[str] = field(default_factory=set)
    first_seen_tick: int | None = None
    last_seen_tick: int | None = None
    history: List[dict] = field(default_factory=list)


class UrbanSimulation:
    """
    Deterministic fleet demonstrator.

    The input layer is simulated because no instrumented public-transport fleet is
    available to the team. Everything after observation creation (event fusion,
    persistence, confidence, scoring and analytics) is executed by the software.
    """

    def __init__(self, seed: int = 42) -> None:
        self.seed = seed
        self.rng = random.Random(seed)
        self.tick = 0
        self.buses = {bus_id: Bus(bus_id, route) for bus_id, route in ROUTES.items()}
        self.assets: Dict[str, AssetState] = {site["id"]: AssetState() for site in EVENT_SITES}
        self.latest_events: List[dict] = []

    @staticmethod
    def _distance(a_lat: float, a_lng: float, b_lat: float, b_lng: float) -> float:
        return math.hypot(a_lat - b_lat, a_lng - b_lng)

    @staticmethod
    def _fused_confidence(detector_conf: float, independent_buses: int, observations: int) -> float:
        # Independent buses are deliberately weighted more than repeated sightings
        # by the same bus. This keeps the demo's "cross-bus consensus" claim honest.
        independent_gain = 1.0 - (1.0 - detector_conf) ** max(1, independent_buses)
        repeat_bonus = min(0.045, max(0, observations - independent_buses) * 0.008)
        return min(0.995, independent_gain + repeat_bonus)

    def _event_for(self, bus: dict, site: dict) -> dict | None:
        distance = self._distance(bus["lat"], bus["lng"], site["lat"], site["lng"])
        if distance > 0.014:
            return None

        # Deterministic gate: repeatable across runs with the same scenario.
        gate = (sum(ord(c) for c in bus["bus_id"]) + self.tick + sum(ord(c) for c in site["id"])) % 23
        if gate not in (0, 1):
            return None

        asset = self.assets[site["id"]]
        asset.observations += 1
        asset.seen_buses.add(bus["bus_id"])
        if asset.first_seen_tick is None:
            asset.first_seen_tick = self.tick
        asset.last_seen_tick = self.tick

        detector_conf = min(0.98, 0.62 + site["severity"] * 0.28 + self.rng.uniform(-0.05, 0.05))
        independent_buses = len(asset.seen_buses)
        fused_conf = self._fused_confidence(detector_conf, independent_buses, asset.observations)
        persistence = max(1, self.tick - (asset.first_seen_tick or self.tick) + 1)
        status = "CONFIRMED" if independent_buses >= 2 and fused_conf >= 0.86 else "UNVERIFIED"

        history_entry = {
            "tick": self.tick,
            "bus_id": bus["bus_id"],
            "detector_confidence": round(detector_conf, 3),
            "fused_confidence": round(fused_conf, 3),
            "status": status,
        }
        asset.history.insert(0, history_entry)
        asset.history = asset.history[:12]

        return {
            "event_id": f"{site['id']}-{self.tick}-{bus['bus_id']}",
            "asset_id": site["id"],
            "type": site["type"],
            "subtype": site["subtype"],
            "title": site["title"],
            "severity": site["severity"],
            "detector_confidence": round(detector_conf, 3),
            "fused_confidence": round(fused_conf, 3),
            "status": status,
            "observations": asset.observations,
            "independent_buses": independent_buses,
            "persistence_ticks": persistence,
            "bus_id": bus["bus_id"],
            "camera": "front" if site["type"] != "SAFETY" else "right",
            "lat": site["lat"],
            "lng": site["lng"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "evidence": {
                "source": "SIMULATED CAMERA OBSERVATION",
                "provenance": "SIMULATED_INPUT_LIVE_PIPELINE",
                "frame_ref": f"demo://{site['id']}/{self.tick}",
                "raw_video_uploaded": False,
            },
        }

    def _corridor_state(self) -> List[dict]:
        corridors = []
        for index, corridor in enumerate(CORRIDORS):
            # Offset waves create visible propagation rather than identical corridor motion.
            phase = self.tick / 13.0 + index * 0.85
            wave = 4.5 * math.sin(phase + len(corridor["id"]))
            observed = max(7.0, corridor["base_speed"] + wave)
            congestion = max(0.0, min(1.0, 1.0 - observed / corridor["normal_speed"]))
            delay = max(0.0, (corridor["normal_speed"] / observed - 1.0) * 8.0)
            derivative = math.cos(phase + len(corridor["id"]))
            trend = "WORSENING" if derivative < 0 else "IMPROVING"
            affected = corridor["length_km"] * min(1.0, 0.35 + congestion)
            propagation = "DOWNSTREAM" if derivative < -0.25 else "STABLE"
            corridors.append({
                **corridor,
                "observed_speed": round(observed, 1),
                "congestion_index": round(congestion, 3),
                "estimated_delay_min": round(delay, 1),
                "affected_length_km": round(affected, 1),
                "propagation": propagation,
                "trend": trend,
                "confidence": round(0.86 + 0.08 * abs(math.sin(self.tick / 15.0)), 3),
            })
        return corridors

    def _city_health(self, corridors: List[dict]) -> dict:
        confirmed_sites = [
            site for site in EVENT_SITES
            if len(self.assets[site["id"]].seen_buses) >= 2
        ]
        avg_congestion = sum(c["congestion_index"] for c in corridors) / max(1, len(corridors))
        defect_burden = sum(site["severity"] for site in confirmed_sites) / max(1, len(EVENT_SITES))
        road_health = max(0.0, 100.0 * (1.0 - 0.65 * defect_burden))
        mobility = max(0.0, 100.0 * (1.0 - avg_congestion))
        safety_confirmed = any(site["type"] == "SAFETY" and len(self.assets[site["id"]].seen_buses) >= 2 for site in EVENT_SITES)
        safety = 72.0 if safety_confirmed else 88.0
        overall = 0.42 * road_health + 0.38 * mobility + 0.20 * safety
        return {
            "overall": round(overall, 1),
            "road_health": round(road_health, 1),
            "mobility": round(mobility, 1),
            "safety": round(safety, 1),
        }

    def asset_history(self, asset_id: str) -> dict:
        site = next((s for s in EVENT_SITES if s["id"] == asset_id), None)
        asset = self.assets.get(asset_id)
        if not site or not asset:
            return {"available": False, "asset_id": asset_id}
        return {
            "available": True,
            "asset_id": asset_id,
            "title": site["title"],
            "subtype": site["subtype"],
            "observations": asset.observations,
            "independent_buses": len(asset.seen_buses),
            "first_seen_tick": asset.first_seen_tick,
            "last_seen_tick": asset.last_seen_tick,
            "history": asset.history,
        }

    def reset(self) -> dict:
        self.rng = random.Random(self.seed)
        self.tick = 0
        self.buses = {bus_id: Bus(bus_id, route) for bus_id, route in ROUTES.items()}
        self.assets = {site["id"]: AssetState() for site in EVENT_SITES}
        self.latest_events = []
        return {"status": "reset", "seed": self.seed}

    def step(self, dt: float = 1.0) -> dict:
        self.tick += 1
        buses = [bus.step(dt, self.rng) for bus in self.buses.values()]
        new_events: List[dict] = []
        for bus in buses:
            for site in EVENT_SITES:
                event = self._event_for(bus, site)
                if event:
                    new_events.append(event)
                    self.latest_events.insert(0, event)
        self.latest_events = self.latest_events[:40]

        corridors = self._corridor_state()
        confirmed = sum(1 for site in EVENT_SITES if len(self.assets[site["id"]].seen_buses) >= 2)
        coverage = min(92.0, 18.0 + self.tick * 0.75)
        road_km = 42.0 + self.tick * 1.8

        return {
            "mode": "DEMONSTRATION",
            "input_provenance": "SIMULATED_FLEET",
            "pipeline": "LIVE_SOFTWARE",
            "tick": self.tick,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "fleet": buses,
            "events": self.latest_events,
            "new_events": new_events,
            "corridors": corridors,
            "city_health": self._city_health(corridors),
            "metrics": {
                "active_buses": len(buses),
                "road_coverage_pct": round(coverage, 1),
                "road_observed_km": round(road_km, 1),
                "events_processed": sum(asset.observations for asset in self.assets.values()),
                "confirmed_issues": confirmed,
                "edge_video_uploaded": False,
                "unique_assets_seen": sum(1 for asset in self.assets.values() if asset.observations > 0),
            },
        }


simulation = UrbanSimulation()
