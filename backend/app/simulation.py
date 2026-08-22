from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List


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
    {"id": "COR-OMR", "name": "OMR Corridor", "normal_speed": 34.0, "base_speed": 18.0, "lat": 12.9864, "lng": 80.2451},
    {"id": "COR-ANNA", "name": "Anna Salai", "normal_speed": 31.0, "base_speed": 14.0, "lat": 13.0604, "lng": 80.2496},
]


@dataclass
class Bus:
    bus_id: str
    route: List[tuple]
    route_index: int = 0
    progress: float = 0.0
    speed_kmh: float = 25.0
    heading: float = 0.0
    camera_status: Dict[str, str] = field(default_factory=lambda: {"front": "ACTIVE", "rear": "ACTIVE", "left": "ACTIVE", "right": "ACTIVE"})

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
            "lat": lat,
            "lng": lng,
            "speed_kmh": round(self.speed_kmh, 1),
            "heading": round(self.heading, 1),
            "route_name": f"Route {self.bus_id.split('-')[-1]}",
            "edge_fps": round(rng.uniform(23.5, 29.8), 1),
            "uplink_kbps": round(rng.uniform(5.0, 12.0), 1),
            "camera_status": self.camera_status,
        }


class UrbanSimulation:
    def __init__(self) -> None:
        self.rng = random.Random(42)
        self.tick = 0
        self.buses = {bus_id: Bus(bus_id, route) for bus_id, route in ROUTES.items()}
        self.observation_count: Dict[str, int] = {site["id"]: 0 for site in EVENT_SITES}
        self.first_seen: Dict[str, int] = {}
        self.latest_events: List[dict] = []

    @staticmethod
    def _distance(a_lat: float, a_lng: float, b_lat: float, b_lng: float) -> float:
        return math.hypot(a_lat - b_lat, a_lng - b_lng)

    def _event_for(self, bus: dict, site: dict) -> dict | None:
        distance = self._distance(bus["lat"], bus["lng"], site["lat"], site["lng"])
        if distance > 0.014:
            return None
        gate = (sum(ord(c) for c in bus["bus_id"]) + self.tick + sum(ord(c) for c in site["id"])) % 23
        if gate not in (0, 1):
            return None
        self.observation_count[site["id"]] += 1
        self.first_seen.setdefault(site["id"], self.tick)
        obs = self.observation_count[site["id"]]
        detector_conf = min(0.98, 0.62 + site["severity"] * 0.28 + self.rng.uniform(-0.05, 0.05))
        fused_conf = min(0.995, 1 - (1 - detector_conf) ** max(1, obs))
        persistence = max(1, self.tick - self.first_seen[site["id"]] + 1)
        status = "CONFIRMED" if obs >= 2 and fused_conf >= 0.86 else "UNVERIFIED"
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
            "observations": obs,
            "independent_buses": min(obs, len(self.buses)),
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
            },
        }

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

        corridors = []
        for corridor in CORRIDORS:
            wave = 4.5 * math.sin(self.tick / 13.0 + len(corridor["id"]))
            observed = max(7.0, corridor["base_speed"] + wave)
            congestion = max(0.0, min(1.0, 1.0 - observed / corridor["normal_speed"]))
            delay = max(0.0, (corridor["normal_speed"] / observed - 1.0) * 8.0)
            trend = "WORSENING" if math.cos(self.tick / 13.0 + len(corridor["id"])) < 0 else "IMPROVING"
            corridors.append({
                **corridor,
                "observed_speed": round(observed, 1),
                "congestion_index": round(congestion, 3),
                "estimated_delay_min": round(delay, 1),
                "trend": trend,
                "confidence": round(0.86 + 0.08 * abs(math.sin(self.tick / 15.0)), 3),
            })

        confirmed = sum(1 for site in EVENT_SITES if self.observation_count[site["id"]] >= 2)
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
            "metrics": {
                "active_buses": len(buses),
                "road_coverage_pct": round(coverage, 1),
                "road_observed_km": round(road_km, 1),
                "events_processed": sum(self.observation_count.values()),
                "confirmed_issues": confirmed,
                "edge_video_uploaded": False,
            },
        }


simulation = UrbanSimulation()
