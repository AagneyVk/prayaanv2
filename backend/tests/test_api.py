from fastapi.testclient import TestClient

from app.main import app
from app.simulation import UrbanSimulation


client = TestClient(app)


def test_health_reports_provenance():
    response = client.get('/health')
    assert response.status_code == 200
    payload = response.json()
    assert payload['status'] == 'ok'
    assert payload['input_provenance'] == 'SIMULATED_FLEET'
    assert payload['pipeline'] == 'LIVE_SOFTWARE'
    assert 'sumo' in payload


def test_state_has_live_fleet_and_corridors():
    response = client.get('/api/v2/state')
    assert response.status_code == 200
    payload = response.json()
    assert payload['fleet']
    assert payload['corridors']
    assert 'city_health' in payload
    assert payload['metrics']['active_buses'] > 0


def test_simulation_is_reproducible_after_reset():
    sim = UrbanSimulation(seed=42)
    first = sim.step(1.0)
    initial_positions = [(b['bus_id'], b['lat'], b['lng']) for b in first['fleet']]
    sim.step(1.0)
    sim.reset()
    replay = sim.step(1.0)
    replay_positions = [(b['bus_id'], b['lat'], b['lng']) for b in replay['fleet']]
    assert initial_positions == replay_positions


def test_cross_bus_confirmation_requires_unique_buses():
    sim = UrbanSimulation(seed=42)
    for _ in range(450):
        state = sim.step(1.0)
    confirmed = [e for e in state['events'] if e['status'] == 'CONFIRMED']
    assert confirmed
    assert all(e['independent_buses'] >= 2 for e in confirmed)


def test_what_if_is_explicitly_decision_support():
    response = client.get('/api/v2/mobility/what-if/COR-OMR')
    assert response.status_code == 200
    payload = response.json()
    assert payload['available'] is True
    assert payload['source'] == 'DETERMINISTIC WHAT-IF MODEL'
    assert payload['same_initial_state'] is True
    assert 'disclaimer' in payload


def test_sumo_micro_twin_produces_fcd_trajectories():
    status = client.get('/api/v2/sumo/status').json()
    assert status['sumo'] is True
    assert status['netconvert'] is True
    assert status['transport'] == 'SUMO FCD subprocess export'

    response = client.get('/api/v2/sumo/bus/MTC-021')
    assert response.status_code == 200
    payload = response.json()
    assert payload['available'] is True, payload.get('reason')
    assert payload['engine'] == 'SUMO'
    assert payload['physics']['car_following'] == 'IDM'
    assert payload['physics']['lane_change'] == 'SL2015'
    assert payload['physics']['sublane'] is True
    assert payload['summary']['source'] == 'LIVE SUMO FCD TRAJECTORIES'
    assert len(payload['frames']) > 40
    vehicles = [v for frame in payload['frames'] for v in frame['vehicles']]
    assert vehicles
    assert any(v['ego'] for v in vehicles)
    assert any(v['kind'] == 'bike' for v in vehicles)
    assert any(v['kind'] == 'truck' for v in vehicles)
    assert all('x' in v and 'speed' in v and 'lane' in v for v in vehicles[:20])


# ---------------------------------------------------------------------------
# Discovery pipeline: the software must not be allowed to read the answer key.
# ---------------------------------------------------------------------------

def test_pipeline_discovers_assets_rather_than_looking_them_up():
    sim = UrbanSimulation(seed=42)
    for _ in range(400):
        state = sim.step(1.0)
    ids = {a['id'] for a in state['assets']}
    # Discovered assets are pipeline-generated identifiers, never ground-truth ids.
    assert ids, 'pipeline discovered nothing'
    assert all(i.startswith('UA-') for i in ids)
    assert not (ids & {'RD-1842', 'INF-220', 'HZ-091', 'SAFE-77'})


def test_false_positives_are_rejected_without_ground_truth():
    sim = UrbanSimulation(seed=42)
    for _ in range(600):
        state = sim.step(1.0)
    assert state['metrics']['candidates_rejected'] > 0, 'clutter was never rejected'
    rejected = [a for a in state['assets'] if a['status'] == 'REJECTED']
    # Nothing gets rejected while independent buses still back it.
    assert all(a['independent_buses'] < 2 for a in rejected)


def test_repaired_defects_resolve_from_clean_passes_alone():
    sim = UrbanSimulation(seed=42)
    for _ in range(900):
        state = sim.step(1.0)
    resolved = [a for a in state['assets'] if a['status'] == 'RESOLVED']
    assert resolved, 'no defect was ever verified as repaired'
    # A repair is only credited after repeated non-detections.
    assert all(a['clean_passes'] >= 4 for a in resolved)


def test_localisation_beats_raw_gps_noise():
    from app.simulation import GPS_NOISE_M
    sim = UrbanSimulation(seed=42)
    for _ in range(500):
        sim.step(1.0)
    diag = sim.diagnostics()
    # Averaging independent noisy reports should localise the asset better than
    # any single report could.
    assert diag['localisation_error_m'] < GPS_NOISE_M


def test_false_positives_do_not_persist_even_when_they_briefly_confirm():
    """A phantom CAN reach CONFIRMED, and the system must then take it back.

    If two buses happen to throw clutter at the same spot, cross-bus consensus is
    satisfied and a defect that does not exist gets confirmed. Asserting that
    never happens would be the dishonest test to write. What the pipeline must
    guarantee is that the mistake is *transient*: later buses drive past, see
    clean road, and accumulated evidence of absence retires it — with no access
    to ground truth at any point.
    """
    sim = UrbanSimulation(seed=42)
    for _ in range(500):
        sim.step(1.0)
    mid = sim.diagnostics()
    assert mid['confirmed_false_positives'] <= 1, 'clutter is confirming too easily'

    for _ in range(400):
        sim.step(1.0)
    late = sim.diagnostics()
    assert late['confirmed_false_positives'] == 0, 'a false positive was never retired'
    assert late['clusters_rejected'] > mid['clusters_rejected']


# ---------------------------------------------------------------------------
# Routing advisory
# ---------------------------------------------------------------------------

def test_unverified_candidates_never_influence_routing():
    from app import routing
    sim = UrbanSimulation(seed=42)
    for _ in range(400):
        state = sim.step(1.0)
    nodes, adj = routing.build_graph()
    penalties = routing.edge_penalties(state['assets'], nodes, adj)
    confirmed = {a['id'] for a in state['assets'] if a['status'] == 'CONFIRMED'}
    for edge in penalties.values():
        for cause in edge['causes']:
            assert cause['asset_id'] in confirmed


def test_routing_advisory_refuses_disproportionate_detours():
    from app import routing
    sim = UrbanSimulation(seed=42)
    for _ in range(400):
        state = sim.step(1.0)
    for bus_id in ['MTC-021', 'MTC-034', 'MTC-057', 'MTC-102', 'MTC-118', 'MTC-145']:
        adv = routing.advisory(bus_id, state['assets'], state['corridors'])
        assert adv['available'] is True
        assert adv['action'] in {
            'NO_ACTION', 'MONITOR', 'ADVISE_REROUTE', 'RECOMMEND_CLOSURE'
        }
        if adv['action'] == 'ADVISE_REROUTE':
            assert adv['detour_cost_pct'] <= routing.ADVISORY_MAX_DETOUR * 100
            assert adv['hazard_reduction_pct'] >= routing.ADVISORY_MIN_GAIN * 100


def test_hazard_layer_publishes_only_confirmed_assets():
    from app import routing
    sim = UrbanSimulation(seed=42)
    for _ in range(400):
        state = sim.step(1.0)
    layer = routing.hazard_layer(state['assets'])
    confirmed = [a for a in state['assets'] if a['status'] == 'CONFIRMED']
    assert len(layer['features']) == len(confirmed)
    assert layer['type'] == 'FeatureCollection'


def test_routing_endpoints_are_exposed():
    assert client.get('/api/v2/routing/advisory/MTC-021').status_code == 200
    assert client.get('/api/v2/routing/hazard-layer').status_code == 200
    graph = client.get('/api/v2/routing/graph').json()
    assert graph['nodes'] and graph['edges']
    diag = client.get('/api/v2/diagnostics').json()
    assert 'confirmed_false_positives' in diag


def test_read_endpoints_do_not_mutate_the_simulation():
    """Asking a question must not change the answer.

    Routing advisories, the hazard layer and explanations are reads. They
    previously called step(0.0), which still advanced the tick and recorded
    clean passes from a zero-length path — so merely opening a bus panel
    degraded the confidence of every asset near it.
    """
    sim = UrbanSimulation(seed=42)
    for _ in range(200):
        sim.step(1.0)
    tick = sim.tick
    clean = sum(len(c.clean_passes) for c in sim.clusters.values())
    observations = sum(c.observations for c in sim.clusters.values())

    for _ in range(5):
        sim.snapshot()
        for asset_id in list(sim.clusters)[:3]:
            sim.explain(asset_id)
            sim.asset_history(asset_id)

    assert sim.tick == tick
    assert sum(len(c.clean_passes) for c in sim.clusters.values()) == clean
    assert sum(c.observations for c in sim.clusters.values()) == observations



# ---------------------------------------------------------------------------
# Micro twin: the events must come OUT of the simulation, not be drawn on it.
# ---------------------------------------------------------------------------

def test_ego_bus_actually_exists_in_the_simulation():
    """The bus whose twin this is must appear in the trajectories.

    SUMO drops route entries that are not in departure order and only prints a
    warning, so the ego bus silently vanished while the endpoint still reported
    success and rendered 340 frames of traffic. Nothing else in the suite
    noticed, because everything else was still there.
    """
    from app.sumo_micro import generate_bus_twin
    twin = generate_bus_twin('MTC-021')
    assert twin['available'] is True, twin.get('reason')
    ego_frames = [f for f in twin['frames'] if f.get('ego')]
    assert len(ego_frames) > 50, 'ego bus missing from its own micro twin'
    xs = [f['ego']['x'] for f in ego_frames]
    assert max(xs) - min(xs) > 200, 'ego bus never travelled the corridor'


def test_driving_anomalies_are_derived_from_trajectories():
    """Anomalies must be measured, not placed.

    The previous implementation hardcoded {"x": 315.0, "confidence": 0.88}. A
    derived event carries the kinematics that produced it and lands wherever the
    behaviour actually happened.
    """
    from app.sumo_micro import generate_bus_twin
    twin = generate_bus_twin('MTC-118')
    anomalies = twin['anomalies']
    assert anomalies, 'no anomaly derived from a corridor containing aggressive drivers'
    for a in anomalies:
        assert a['source'] == 'DERIVED FROM SUMO TRAJECTORY'
        for term in ('lane_change_rate_per_min', 'harsh_brake_rate_per_min',
                     'peak_deceleration_ms2', 'peak_lateral_speed_ms'):
            assert term in a['evidence']
        # Confidence is computed, so it must not be one of the old constants.
        assert a['confidence'] not in (0.88, 0.91, 0.86)
        assert a['x'] not in (145.0, 315.0, 505.0)


def test_detector_cannot_read_the_vehicle_type():
    """Aggressive drivers must not be labelled as such in the analysed data.

    If the trajectory stream tagged them, the detector would be grading its own
    homework — it would 'find' exactly what was planted and nothing else.
    """
    from app.sumo_micro import generate_bus_twin
    twin = generate_bus_twin('MTC-021')
    kinds = {v['kind'] for f in twin['frames'] for v in f['vehicles']}
    assert 'rash' not in kinds


def test_anomaly_detection_is_not_limited_to_planted_vehicles():
    """Across buses, at least one ordinary flow vehicle should be flagged.

    Proof the scoring is measuring behaviour rather than recognising ids.
    """
    from app.sumo_micro import generate_bus_twin
    flagged = []
    for bus_id in ('MTC-021', 'MTC-057', 'MTC-118', 'MTC-102'):
        twin = generate_bus_twin(bus_id)
        flagged.extend(a['track_ref'] for a in twin.get('anomalies', []))
    assert flagged, 'nothing flagged at all'
    assert any(not ref.startswith('rash') for ref in flagged), (
        'only planted vehicles were ever flagged'
    )


def test_no_fabricated_vehicle_identity_is_published():
    """No invented number plate anywhere in the payload.

    A fabricated plate presented as evidence is the one dishonest artefact in an
    otherwise carefully provenance-labelled demo, and plate capture turns an
    infrastructure tool into a surveillance one.
    """
    import json
    from app.sumo_micro import generate_bus_twin
    blob = json.dumps(generate_bus_twin('MTC-021'))
    assert 'TN 09' not in blob
    assert 'plate_confidence' not in blob


def test_roadside_defects_are_detected_on_approach():
    """Detection geometry must be plausible for a forward camera."""
    from app.sumo_micro import generate_bus_twin, EGO_SENSOR_RANGE_M, MIN_STANDOFF_M
    twin = generate_bus_twin('MTC-021')
    defects = [s for s in twin['scenarios'] if s['type'] != 'DRIVING_ANOMALY']
    assert defects
    for d in defects:
        r = d['evidence']['range_m']
        # Never claim an observation from under the bumper, nor beyond range.
        assert MIN_STANDOFF_M - 1 <= r <= EGO_SENSOR_RANGE_M
        assert d['evidence']['bearing_deg'] <= 31.1


# ---------------------------------------------------------------------------
# Road condition: inertial roughness, degradation rate, repair verification.
# ---------------------------------------------------------------------------

def test_roughness_is_measured_not_looked_up():
    """The estimate must come from bus passes, never from the latent truth."""
    sim = UrbanSimulation(seed=42)
    for _ in range(400):
        state = sim.step(1.0)
    report = state['road_condition']
    assert report['segments'] > 0
    surveyed = [s for s in sim.road.segments.values() if s.passes > 0]
    assert surveyed, 'no segment was ever measured'
    for seg in surveyed[:8]:
        # A measured estimate lands near the truth but is not equal to it; if it
        # were identical, the pipeline would be reading the answer.
        assert abs(seg.estimated_iri - seg.true_iri) > 1e-9
        assert abs(seg.estimated_iri - seg.true_iri) < 2.5


def test_degradation_needs_enough_passes_and_resets_after_resurfacing():
    sim = UrbanSimulation(seed=42)
    for _ in range(700):
        sim.step(1.0)
    reported = [s.degradation() for s in sim.road.segments.values()]
    available = [d for d in reported if d.get('available')]
    assert available, 'no segment ever accumulated a trend'
    for d in available:
        assert d['samples'] >= 4          # never a trend from two points
        assert 'ticks_to_intervention' in d
    # Anything not yet surveyed enough must say so rather than guess.
    for d in reported:
        if not d.get('available'):
            assert 'reason' in d


def test_repairs_are_adjudicated_from_fleet_evidence():
    sim = UrbanSimulation(seed=42)
    for _ in range(900):
        state = sim.step(1.0)
    report = state['work_orders']
    assert report['orders'], 'no work order was ever raised'
    verdicts = {o['status'] for o in report['orders']}
    # Both outcomes must be reachable, or the verification claim is untestable.
    assert 'VERIFIED_FIXED' in verdicts
    assert 'DISPUTED' in verdicts
    for o in report['orders']:
        if o['status'] in ('VERIFIED_FIXED', 'DISPUTED', 'PARTIALLY_VERIFIED'):
            assert o['evidence']['fleet_passes_since_claim'] >= 3


def test_non_surface_repairs_are_not_judged_by_the_accelerometer():
    """Repainting a crossing changes no road profile.

    Requiring a roughness improvement for those marked every honest repair
    'partially verified' and made the whole service look broken.
    """
    from app.roadwork import SURFACE_AFFECTING
    sim = UrbanSimulation(seed=42)
    for _ in range(900):
        state = sim.step(1.0)
    judged = [o for o in state['work_orders']['orders'] if o['evidence']]
    assert judged
    for o in judged:
        expected = o['subtype'] in SURFACE_AFFECTING
        assert o['evidence']['inertial_applicable'] is expected
        assert o['evidence']['adjudication'] == ('VISUAL + INERTIAL' if expected else 'VISUAL ONLY')


def test_inertial_sensing_covers_what_cameras_cannot():
    """Roughness must be surveyed regardless of light, unlike the cameras."""
    sim = UrbanSimulation(seed=42)
    night_passes = 0
    for _ in range(600):
        state = sim.step(1.0)
        if state['lighting']['regime'] == 'NIGHT':
            night_passes += sum(1 for s in sim.road.segments.values()
                                if s.measurements and s.measurements[-1][0] == sim.tick)
    assert night_passes > 0, 'no road-condition data was gathered at night'
