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
    # Run long enough for deterministic routes to encounter event sites repeatedly.
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
