from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .simulation import simulation
from .sumo_micro import generate_bus_twin, status as sumo_status
from . import routing

app = FastAPI(title="PRAYAAN V2 Urban Intelligence API", version="2.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class StepRequest(BaseModel):
    seconds: float = 1.0


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "PRAYAAN V2",
        "mode": "DEMONSTRATION",
        "input_provenance": "SIMULATED_FLEET",
        "pipeline": "LIVE_SOFTWARE",
        "seed": simulation.seed,
        "sumo": sumo_status(),
    }


@app.get("/api/v2/state")
def state():
    return simulation.step(1.0)


@app.post("/api/v2/step")
def step(payload: StepRequest):
    seconds = max(0.1, min(payload.seconds, 10.0))
    return simulation.step(seconds)


@app.post("/api/v2/reset")
def reset():
    return simulation.reset()


@app.get("/api/v2/assets/{asset_id}/history")
def asset_history(asset_id: str):
    return simulation.asset_history(asset_id)


@app.get("/api/v2/sumo/status")
def get_sumo_status():
    return sumo_status()


@app.get("/api/v2/sumo/bus/{bus_id}")
def bus_micro_twin(bus_id: str):
    return generate_bus_twin(bus_id)


@app.get("/api/v2/explain/{asset_id}")
def explain(asset_id: str):
    """Explainable maintenance priority for a DISCOVERED asset.

    The scoring used to live here, duplicated from the simulation and drifting
    from it. It now has one home, next to the evidence it scores.
    """
    return simulation.explain(asset_id)


@app.get("/api/v2/diagnostics")
def diagnostics():
    """Score the pipeline against ground truth it is never allowed to read.

    Deliberately its own endpoint: this is how we evaluate the system, not
    something the system consumes. In a deployment this is a survey crew.
    """
    return simulation.diagnostics()


@app.get("/api/v2/routing/advisory/{bus_id}")
def routing_advisory(bus_id: str):
    """Should this bus avoid a road because of a CONFIRMED defect?"""
    state = simulation.snapshot()
    return routing.advisory(bus_id, state["assets"], state["corridors"])


@app.get("/api/v2/routing/hazard-layer")
def hazard_layer():
    """Fleet-confirmed hazards as GeoJSON, for other systems to ingest."""
    state = simulation.snapshot()
    return routing.hazard_layer(state["assets"])


@app.get("/api/v2/routing/graph")
def routing_graph():
    """The road graph and its current hazard penalties, for inspection."""
    state = simulation.snapshot()
    nodes, adj = routing.build_graph()
    penalties = routing.edge_penalties(state["assets"], nodes, adj)
    return {
        "nodes": [{"key": k, "lat": v[0], "lng": v[1]} for k, v in nodes.items()],
        "edges": [
            {"key": k, **v} for k, v in sorted(penalties.items(), key=lambda kv: -kv[1]["penalty"])
        ],
        "note": "Only CONFIRMED assets contribute penalty. Unverified candidates never move a bus.",
    }


@app.get("/api/v2/mobility/what-if/{corridor_id}")
def mobility_what_if(corridor_id: str):
    state = simulation.step(0.4)
    corridor = next((c for c in state["corridors"] if c["id"] == corridor_id), None)
    if corridor is None:
        return {"available": False, "corridor_id": corridor_id}

    no_action_delay = corridor["estimated_delay_min"]
    mitigation_delay = max(0.0, no_action_delay * 0.58)
    no_action_speed = corridor["observed_speed"]
    mitigation_speed = min(corridor["normal_speed"], no_action_speed * 1.42)

    return {
        "available": True,
        "corridor_id": corridor_id,
        "corridor_name": corridor["name"],
        "source": "DETERMINISTIC WHAT-IF MODEL",
        "same_initial_state": True,
        "observed_input": {
            "speed_kmh": no_action_speed,
            "congestion_index": corridor["congestion_index"],
            "affected_length_km": corridor["affected_length_km"],
            "propagation": corridor["propagation"],
            "confidence": corridor["confidence"],
        },
        "baseline": {
            "policy": "NO ACTION",
            "mean_speed_kmh": round(no_action_speed, 1),
            "estimated_delay_min": round(no_action_delay, 1),
            "spillback_risk": "HIGH" if corridor["congestion_index"] > 0.55 else "MEDIUM",
        },
        "intervention": {
            "policy": "CORRIDOR FLOW MITIGATION",
            "mean_speed_kmh": round(mitigation_speed, 1),
            "estimated_delay_min": round(mitigation_delay, 1),
            "spillback_risk": "LOW" if mitigation_delay < 7 else "MEDIUM",
        },
        "disclaimer": "Decision-support scenario only. The current V2 mobility module is not a live traffic-signal controller.",
    }
