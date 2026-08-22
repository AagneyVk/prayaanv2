from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .simulation import simulation

app = FastAPI(title="PRAYAAN V2 Urban Intelligence API", version="2.0.0")

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
    }


@app.get("/api/v2/state")
def state():
    return simulation.step(1.0)


@app.post("/api/v2/step")
def step(payload: StepRequest):
    seconds = max(0.1, min(payload.seconds, 10.0))
    return simulation.step(seconds)


@app.get("/api/v2/explain/{asset_id}")
def explain(asset_id: str):
    matching = [ev for ev in simulation.latest_events if ev.get("asset_id") == asset_id]
    if not matching:
        return {
            "asset_id": asset_id,
            "available": False,
            "reason": "No observation has reached this asset yet in the current demo run.",
        }
    latest = matching[0]
    severity = latest["severity"]
    confidence = latest["fused_confidence"]
    persistence = latest["persistence_ticks"]
    observations = latest["observations"]
    exposure_factor = 0.65 + min(observations, 5) * 0.06
    priority = min(100.0, 100 * (0.45 * severity + 0.35 * confidence + 0.20 * exposure_factor))
    return {
        "asset_id": asset_id,
        "available": True,
        "priority_score": round(priority, 1),
        "reasoning": {
            "severity": severity,
            "fused_confidence": confidence,
            "observations": observations,
            "persistence_ticks": persistence,
            "exposure_factor": round(exposure_factor, 3),
        },
        "formula": "100 × (0.45·severity + 0.35·confidence + 0.20·exposure_factor)",
        "recommendation": "PRIORITY REVIEW" if priority >= 75 else "MONITOR / SCHEDULE",
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
    }
