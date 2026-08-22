# PRAYAAN V2 — Judge Demo Flow

## 1. Open with the city, not with a model

Start on **City Ops**. Explain that buses are simulated inputs because the team does not own an instrumented public-transport fleet, while the event pipeline, fusion, scoring, analytics and visualisation are running live.

Point to the provenance banner:

- `INPUT: SIMULATED_FLEET`
- `PIPELINE: LIVE_SOFTWARE`
- `RAW VIDEO: NOT UPLOADED`

This distinction is intentional and should remain visible during judging.

## 2. Show the moving sensing network

Point out:

- moving bus nodes;
- sensing coverage halos;
- observed route traces;
- coverage percentage and kilometres observed;
- event pulses appearing as buses traverse known demonstration sites.

Core line: **one bus sees a road; a fleet builds urban memory.**

## 3. Drill into one bus

Click a bus and open **Bus Edge**.

Explain the four simulated camera streams and the edge-compute status. The current camera visualisation is a synthetic perception scene; it demonstrates how the operator sees detections without claiming real MTC camera footage.

Important architectural point: only compact events are sent centrally. Raw continuous video is not required for normal analytics.

## 4. Follow one event end-to-end

Click a road defect in the evidence stream.

Show:

- detector confidence;
- bus and camera source;
- GPS and timestamp;
- number of observations;
- number of independent buses;
- fused confidence;
- current status (`UNVERIFIED` or `CONFIRMED`);
- explainable priority score.

The fusion logic weights detections from independent buses more strongly than repeated detections by the same bus.

## 5. Show cross-bus confirmation

Wait until another independent bus observes the same asset. The event changes to `CONFIRMED` only after unique-bus consensus and a confidence threshold are both satisfied.

This demonstrates **spatiotemporal fleet consensus** rather than a single-frame alert.

## 6. Show Urban Memory

Open **Urban Memory** and explain that persistent assets accumulate observations across repeated fleet passes.

Current prototype stores observation history and persistence. Future deployment can add clean-pass logic to automatically suggest that an infrastructure defect may have been repaired.

## 7. Show Mobility Intelligence as a side module

Open a corridor or **Mobility Lab**.

Explain that traffic control is not the core product. PRAYAAN uses fleet-observed speed and density as an extra urban-intelligence layer.

The module shows:

- observed vs normal speed;
- congestion index;
- estimated delay;
- affected corridor length;
- worsening/improving trend;
- downstream propagation flag;
- deterministic what-if comparison.

The current what-if engine is explicitly labelled `DETERMINISTIC WHAT-IF MODEL`. It is decision support, not a claim of live signal control.

## 8. Answer “is it real?” clearly

Recommended answer:

> We do not have access to a camera-equipped public bus fleet, so the fleet and camera observations are simulated. We intentionally expose that in the UI. The software after ingestion is live: buses generate events, the backend performs unique-bus fusion, persistence tracking, explainable priority scoring, corridor analytics and the command centre updates from those API results. The architecture is designed so real bus telemetry can replace the simulator without changing the central pipeline.

## 9. Reproducibility

The simulator uses a fixed seed. The backend exposes `/api/v2/reset` so the same demonstration can be replayed from the same starting state.

Run the smoke tests before a judging session:

```bash
cd backend
pytest -q
```

## 10. Core technical phrases

Use naturally:

- mobile urban sensing;
- edge inference;
- event-first architecture;
- spatiotemporal fusion;
- cross-bus consensus;
- confidence-aware evidence;
- temporal persistence / urban memory;
- explainable prioritisation;
- congestion propagation;
- decision-support digital twin;
- provenance-aware simulation.
