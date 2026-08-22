# PRAYAAN V2 — AI-Powered Mobile Urban Intelligence Platform

PRAYAAN V2 is a clean-room rebuild for SIH26124: **AI-Powered Mobile Urban Intelligence Platform Using Public Transport Fleet**.

The core idea is to treat public transport buses as **mobile urban sensing nodes**. In demo mode, a simulated fleet produces GPS, traffic and urban-hazard observations; the software pipeline then performs event processing, confidence scoring, geospatial fusion, prioritisation and city-level visualisation.

## V2 goals

- Judge-facing **urban command centre** rather than a CRUD dashboard.
- Animated city/fleet simulation with explicit **DEMO / simulated input provenance**.
- Evidence-first events: source bus, camera, GPS, timestamp, confidence and reasoning.
- Cross-bus confirmation and spatiotemporal event fusion.
- Urban memory for persistent infrastructure defects.
- Explainable maintenance priority scoring.
- Mobility Intelligence side module for congestion propagation and digital-twin what-if analysis.
- Architecture that can later swap simulated inputs for real bus cameras and edge AI.

## Architecture

```text
Simulated / real bus inputs
        |
        v
Edge event generation
        |
        v
FastAPI urban intelligence backend
        |
        +--> event fusion / confidence
        +--> corridor analytics
        +--> maintenance prioritisation
        +--> mobility intelligence
        |
        v
React command-centre frontend
```

## Run locally

### Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

## Demo truthfulness

The V2 demo intentionally distinguishes between:

- **SIMULATED INPUT** — virtual buses/camera observations because we do not own an instrumented public bus fleet.
- **LIVE SOFTWARE** — backend event processing, geospatial logic, fusion, prioritisation, analytics, persistence and UI are executed by the application.

This distinction is deliberate so the project can be demonstrated honestly while still proving the software architecture.
