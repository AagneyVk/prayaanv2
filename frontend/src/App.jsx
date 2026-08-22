import React, { useEffect, useMemo, useState } from 'react'
import { MapContainer, TileLayer, CircleMarker, Polyline, Tooltip, useMap } from 'react-leaflet'
import {
  Activity, AlertTriangle, BusFront, Camera, CheckCircle2, ChevronRight, Clock3,
  Cpu, Crosshair, Gauge, Layers3, MapPinned, Radio, Route, ScanLine, ShieldCheck,
  Sparkles, TimerReset, TrafficCone, Video, Wifi, X, Zap, Orbit, Play
} from 'lucide-react'
import BusMicroTwin from './BusMicroTwin.jsx'

const API = '/api/v2'
const CHENNAI = [13.045, 80.235]

const ROUTE_LINES = [
  [[13.0827,80.2707],[13.0604,80.2496],[13.0402,80.2448],[13.0067,80.2570],[12.9864,80.2451]],
  [[13.1143,80.1548],[13.0878,80.1987],[13.0694,80.1948],[13.0501,80.2124],[13.0305,80.2302]],
  [[12.9249,80.1000],[12.9517,80.1413],[12.9756,80.2207],[13.0067,80.2570],[13.0402,80.2448]],
]

function FlyToSelection({ bus, event }) {
  const map = useMap()
  useEffect(() => {
    if (event) map.flyTo([event.lat, event.lng], 15, { duration: 0.8 })
    else if (bus) map.flyTo([bus.lat, bus.lng], 15, { duration: 0.8 })
  }, [bus, event, map])
  return null
}

function severityLabel(value = 0) {
  if (value >= 0.82) return 'CRITICAL'
  if (value >= 0.66) return 'HIGH'
  if (value >= 0.45) return 'MEDIUM'
  return 'LOW'
}

function eventIcon(type) {
  if (type === 'ROAD_DEFECT') return '◉'
  if (type === 'ROAD_HAZARD') return '≈'
  if (type === 'SAFETY') return '△'
  return '◇'
}

function LiveCameraTile({ label, variant = 0 }) {
  return (
    <div className="camera-tile">
      <div className="camera-head"><span>{label}</span><span className="camera-live">● LIVE SIM</span></div>
      <div className={`camera-scene camera-scene-${variant}`}>
        <div className="road-perspective" />
        <div className="vehicle-box vehicle-a"><span>CAR</span><b>0.96</b></div>
        {variant !== 2 && <div className="vehicle-box vehicle-b"><span>BIKE</span><b>0.91</b></div>}
        {variant === 0 && <div className="hazard-box"><span>POTHOLE</span><b>0.89</b></div>}
        {variant === 2 && <div className="person-box"><span>PERSON</span><b>0.94</b></div>}
        <ScanLine className="scanline-icon" size={18} />
      </div>
    </div>
  )
}

function ProvenanceBadge({ state }) {
  return (
    <div className="provenance-banner">
      <div className="provenance-primary"><Sparkles size={15}/> DEMONSTRATION MODE</div>
      <div className="provenance-item"><span>INPUT</span><b>{state?.input_provenance || 'SIMULATED_FLEET'}</b></div>
      <div className="provenance-item"><span>PIPELINE</span><b>{state?.pipeline || 'LIVE_SOFTWARE'}</b></div>
      <div className="provenance-item"><span>RAW VIDEO</span><b>NOT UPLOADED</b></div>
    </div>
  )
}

function App() {
  const [state, setState] = useState(null)
  const [offline, setOffline] = useState(false)
  const [selectedBus, setSelectedBus] = useState(null)
  const [selectedEvent, setSelectedEvent] = useState(null)
  const [activeView, setActiveView] = useState('city')
  const [explanation, setExplanation] = useState(null)
  const [whatIf, setWhatIf] = useState(null)
  const [tickSpeed, setTickSpeed] = useState(1400)
  const [microTwinBus, setMicroTwinBus] = useState(null)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const res = await fetch(`${API}/state`)
        if (!res.ok) throw new Error('backend unavailable')
        const payload = await res.json()
        if (!cancelled) {
          setState(payload)
          setOffline(false)
          if (selectedBus) {
            const next = payload.fleet.find(b => b.bus_id === selectedBus.bus_id)
            if (next) setSelectedBus(next)
          }
        }
      } catch (e) {
        if (!cancelled) setOffline(true)
      }
    }
    load()
    const timer = setInterval(load, tickSpeed)
    return () => { cancelled = true; clearInterval(timer) }
  }, [tickSpeed])

  const metrics = state?.metrics || {}
  const fleet = state?.fleet || []
  const events = state?.events || []
  const corridors = state?.corridors || []
  const latestConfirmed = useMemo(() => events.filter(e => e.status === 'CONFIRMED').slice(0, 5), [events])

  async function openEvent(event) {
    setSelectedEvent(event)
    setActiveView('event')
    try {
      const res = await fetch(`${API}/explain/${event.asset_id}`)
      setExplanation(await res.json())
    } catch { setExplanation(null) }
  }

  async function runWhatIf(corridor) {
    setActiveView('mobility')
    setWhatIf(null)
    try {
      const res = await fetch(`${API}/mobility/what-if/${corridor.id}`)
      setWhatIf(await res.json())
    } catch { setWhatIf(null) }
  }

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand-mark"><div className="brand-glyph">P</div><div><h1>PRAYAAN <span>V2</span></h1><p>URBAN INTELLIGENCE COMMAND CENTER</p></div></div>
        <div className="top-status">
          <span className={`status-dot ${offline ? 'bad' : ''}`} />
          <span>{offline ? 'BACKEND OFFLINE' : 'PIPELINE ONLINE'}</span>
          <div className="top-chip"><Clock3 size={14}/>{state?.timestamp ? new Date(state.timestamp).toLocaleTimeString() : '--:--:--'}</div>
          <div className="top-chip strong">SIH26124</div>
        </div>
      </header>

      <ProvenanceBadge state={state} />

      <div className="workspace">
        <nav className="rail">
          {[
            ['city', MapPinned, 'City Ops'],
            ['bus', BusFront, 'Bus Edge'],
            ['memory', TimerReset, 'Urban Memory'],
            ['mobility', Route, 'Mobility Lab'],
          ].map(([id, Icon, label]) => (
            <button key={id} className={activeView === id ? 'active' : ''} onClick={() => setActiveView(id)}>
              <Icon size={19}/><span>{label}</span>
            </button>
          ))}
        </nav>

        <aside className="left-column">
          <section className="section-heading"><div><span className="eyebrow">CITY STATUS</span><h2>Chennai Fleet</h2></div><Activity size={18}/></section>
          <div className="metric-grid">
            <div className="metric-card"><BusFront/><b>{metrics.active_buses ?? 0}</b><span>ACTIVE BUSES</span></div>
            <div className="metric-card"><Layers3/><b>{metrics.road_coverage_pct ?? 0}%</b><span>ROAD COVERAGE</span></div>
            <div className="metric-card"><Radio/><b>{metrics.events_processed ?? 0}</b><span>OBSERVATIONS</span></div>
            <div className="metric-card"><CheckCircle2/><b>{metrics.confirmed_issues ?? 0}</b><span>CONFIRMED</span></div>
          </div>

          <section className="panel compact">
            <div className="panel-title"><span>FLEET INTELLIGENCE</span><small>{fleet.length} nodes</small></div>
            <div className="bus-list">
              {fleet.map(bus => (
                <button key={bus.bus_id} onClick={() => { setSelectedBus(bus); setSelectedEvent(null); setActiveView('bus') }} className={selectedBus?.bus_id === bus.bus_id ? 'selected' : ''}>
                  <span className="bus-pulse"/><div><b>{bus.bus_id}</b><small>{bus.route_name}</small></div><div className="bus-side"><strong>{bus.speed_kmh}</strong><small>km/h</small></div>
                </button>
              ))}
            </div>
          </section>

          <section className="coverage-card">
            <div className="coverage-top"><span>NETWORK OBSERVED TODAY</span><b>{metrics.road_observed_km ?? 0} km</b></div>
            <div className="coverage-bar"><i style={{ width: `${Math.min(metrics.road_coverage_pct || 0, 100)}%` }}/></div>
            <p>Each bus paints a moving sensing footprint. Repeated passes raise confidence and create persistent urban memory.</p>
          </section>
        </aside>

        <main className="main-stage">
          {offline && <div className="offline-card"><AlertTriangle size={22}/><div><b>Backend not running</b><span>Start FastAPI on port 8000. The UI is intentionally not showing fake fallback results.</span></div></div>}

          <div className="map-frame">
            <MapContainer center={CHENNAI} zoom={11} zoomControl={false} attributionControl={false} className="map">
              <TileLayer url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png" />
              {ROUTE_LINES.map((line, idx) => <Polyline key={idx} positions={line} pathOptions={{ color: '#2a79ff', weight: 2, opacity: 0.35, dashArray: '5 8' }} />)}
              {fleet.map(bus => (
                <React.Fragment key={bus.bus_id}>
                  <CircleMarker center={[bus.lat,bus.lng]} radius={18} pathOptions={{ color: '#13d5ff', fillColor: '#13d5ff', fillOpacity: 0.07, weight: 1 }} />
                  <CircleMarker center={[bus.lat,bus.lng]} radius={6} pathOptions={{ color: '#d7f8ff', fillColor: '#13d5ff', fillOpacity: 1, weight: 2 }} eventHandlers={{ click: () => { setSelectedBus(bus); setActiveView('bus') } }}>
                    <Tooltip direction="top" offset={[0,-4]}>{bus.bus_id} · {bus.speed_kmh} km/h</Tooltip>
                  </CircleMarker>
                </React.Fragment>
              ))}
              {events.slice(0,20).map(event => (
                <CircleMarker key={event.event_id} center={[event.lat,event.lng]} radius={event.status === 'CONFIRMED' ? 8 : 5} pathOptions={{ color: event.status === 'CONFIRMED' ? '#ff5d6c' : '#ffb547', fillColor: event.status === 'CONFIRMED' ? '#ff3348' : '#ffb547', fillOpacity: 0.72, weight: 2 }} eventHandlers={{ click: () => openEvent(event) }}>
                  <Tooltip direction="top"><b>{event.subtype.replaceAll('_',' ')}</b><br/>{Math.round(event.fused_confidence*100)}% fused confidence</Tooltip>
                </CircleMarker>
              ))}
              <FlyToSelection bus={selectedBus} event={selectedEvent}/>
            </MapContainer>

            <div className="map-overlay-title"><span>LIVE CITY DIGITAL TWIN</span><b>FLEET SENSING COVERAGE</b></div>
            <div className="map-legend"><span><i className="legend-bus"/>BUS NODE</span><span><i className="legend-event"/>EVENT</span><span><i className="legend-route"/>OBSERVED ROUTE</span></div>
            <div className="sim-control"><span>SIM RATE</span><button className={tickSpeed === 1400 ? 'active' : ''} onClick={() => setTickSpeed(1400)}>1×</button><button className={tickSpeed === 650 ? 'active' : ''} onClick={() => setTickSpeed(650)}>2×</button></div>
          </div>

          <div className="bottom-strip">
            <div><span className="eyebrow">LIVE ANALYTICS</span><h3>Network pulse</h3></div>
            {corridors.map(c => (
              <button key={c.id} className="corridor-chip" onClick={() => runWhatIf(c)}>
                <div><b>{c.name}</b><span>{c.trend}</span></div><strong>{c.observed_speed} <small>km/h</small></strong><div className="mini-risk" style={{ '--risk': `${Math.round(c.congestion_index*100)}%` }} />
                <ChevronRight size={15}/>
              </button>
            ))}
          </div>
        </main>

        <aside className="right-column">
          <div className="section-heading"><div><span className="eyebrow">EVIDENCE STREAM</span><h2>Urban Events</h2></div><Radio size={17}/></div>
          <div className="event-stream">
            {events.slice(0,8).map(event => (
              <button key={event.event_id} onClick={() => openEvent(event)}>
                <div className={`event-symbol ${event.status === 'CONFIRMED' ? 'confirmed' : ''}`}>{eventIcon(event.type)}</div>
                <div className="event-copy"><div><b>{event.title}</b><span className={`severity ${severityLabel(event.severity).toLowerCase()}`}>{severityLabel(event.severity)}</span></div><p>{event.bus_id} · {event.camera.toUpperCase()} CAM · {event.status}</p><small>{Math.round(event.fused_confidence*100)}% fused · {event.observations} observation{event.observations === 1 ? '' : 's'}</small></div>
              </button>
            ))}
            {!events.length && <div className="empty-events"><Radio size={18}/><span>Waiting for fleet observations…</span></div>}
          </div>

          <section className="panel confirmed-panel">
            <div className="panel-title"><span>CROSS-BUS CONSENSUS</span><small>live</small></div>
            {latestConfirmed.length ? latestConfirmed.map(e => (
              <div className="consensus-row" key={`c-${e.event_id}`}><ShieldCheck size={16}/><div><b>{e.asset_id}</b><span>{e.independent_buses} buses · {Math.round(e.fused_confidence*100)}%</span></div></div>
            )) : <p className="panel-note">A defect turns from unverified to confirmed after repeated independent observations.</p>}
          </section>
        </aside>
      </div>

      {(activeView === 'bus' && selectedBus) && (
        <div className="drawer bus-drawer">
          <div className="drawer-head"><div><span className="eyebrow">EDGE NODE</span><h2>{selectedBus.bus_id} · Onboard Perception</h2></div><button onClick={() => setActiveView('city')}><X/></button></div>
          <div className="bus-meta-grid">
            <div><Gauge/><span>Speed</span><b>{selectedBus.speed_kmh} km/h</b></div><div><Cpu/><span>Edge inference</span><b>{selectedBus.edge_fps} FPS</b></div><div><Wifi/><span>Event uplink</span><b>{selectedBus.uplink_kbps} KB/s</b></div><div><Video/><span>Raw video cloud</span><b>OFF</b></div>
          </div>
          <div className="camera-grid"><LiveCameraTile label="FRONT CAMERA" variant={0}/><LiveCameraTile label="LEFT CAMERA" variant={1}/><LiveCameraTile label="RIGHT CAMERA" variant={2}/><LiveCameraTile label="REAR CAMERA" variant={3}/></div>
          <div className="micro-launch-card">
            <div><Orbit size={20}/><div><span>MICROSCOPIC TRAFFIC PHYSICS</span><b>Open this bus inside SUMO</b><small>IDM following · lane changes · mixed traffic · real TraCI coordinates</small></div></div>
            <button onClick={() => setMicroTwinBus(selectedBus)}><Play size={15}/> OPEN MICRO TWIN</button>
          </div>
          <div className="edge-foot"><ShieldCheck size={17}/><div><b>Privacy-preserving edge mode</b><span>Camera imagery is represented as simulated onboard inference. Only compact events, confidence, GPS and timestamps are sent to the command system.</span></div></div>
        </div>
      )}

      {(activeView === 'event' && selectedEvent) && (
        <div className="drawer event-drawer">
          <div className="drawer-head"><div><span className="eyebrow">EVIDENCE TRACE</span><h2>{selectedEvent.title}</h2></div><button onClick={() => setActiveView('city')}><X/></button></div>
          <div className="evidence-hero">
            <div className="evidence-visual"><Camera size={26}/><div className="bbox-demo"><span>{selectedEvent.subtype.replaceAll('_',' ')}</span><b>{Math.round(selectedEvent.detector_confidence*100)}%</b></div><small>SIMULATED CAMERA OBSERVATION</small></div>
            <div className="evidence-stats"><span>STATUS</span><b className={selectedEvent.status === 'CONFIRMED' ? 'good-text' : 'warn-text'}>{selectedEvent.status}</b><span>FUSED CONFIDENCE</span><strong>{Math.round(selectedEvent.fused_confidence*100)}%</strong><span>INDEPENDENT OBSERVATIONS</span><strong>{selectedEvent.observations}</strong><span>SOURCE</span><strong>{selectedEvent.bus_id} / {selectedEvent.camera.toUpperCase()}</strong></div>
          </div>
          <div className="memory-line"><div className="memory-node active"><i/><span>FIRST SEEN</span><b>Tick {Math.max(1, (state?.tick || 1) - selectedEvent.persistence_ticks + 1)}</b></div><div className="memory-node active"><i/><span>RE-OBSERVED</span><b>{selectedEvent.observations}×</b></div><div className={`memory-node ${selectedEvent.status === 'CONFIRMED' ? 'active' : ''}`}><i/><span>CONSENSUS</span><b>{selectedEvent.status}</b></div><div className="memory-node"><i/><span>REPAIR VERIFY</span><b>Future pass</b></div></div>
          {explanation?.available && <div className="why-card"><div><Zap/><span>WHY THIS PRIORITY?</span></div><strong>{explanation.priority_score}/100</strong><p>{explanation.formula}</p><div className="why-grid"><span>Severity <b>{explanation.reasoning.severity}</b></span><span>Fusion <b>{explanation.reasoning.fused_confidence}</b></span><span>Observations <b>{explanation.reasoning.observations}</b></span><span>Exposure <b>{explanation.reasoning.exposure_factor}</b></span></div></div>}
        </div>
      )}

      {activeView === 'memory' && (
        <div className="drawer memory-drawer">
          <div className="drawer-head"><div><span className="eyebrow">TEMPORAL PERSISTENCE</span><h2>Urban Memory</h2></div><button onClick={() => setActiveView('city')}><X/></button></div>
          <p className="drawer-intro">PRAYAAN remembers infrastructure issues across repeated fleet passes. Persistent observations raise confidence; disappearance after repeated clean passes can later become automatic repair verification.</p>
          <div className="asset-list">{events.filter((e,i,a) => a.findIndex(x => x.asset_id === e.asset_id) === i).map(e => <button key={e.asset_id} onClick={() => openEvent(e)}><div className="asset-code">{e.asset_id}</div><div><b>{e.title}</b><span>{e.observations} observations · {e.status}</span></div><strong>{Math.round(e.fused_confidence*100)}%</strong></button>)}</div>
        </div>
      )}

      {activeView === 'mobility' && (
        <div className="drawer mobility-drawer">
          <div className="drawer-head"><div><span className="eyebrow">SIDE MODULE · DECISION SUPPORT</span><h2>Mobility Digital Twin</h2></div><button onClick={() => setActiveView('city')}><X/></button></div>
          <p className="drawer-intro">Traffic is not the core product. PRAYAAN uses fleet-observed speed and density as a side intelligence layer to identify congestion propagation and test corridor interventions.</p>
          <div className="mobility-grid">{corridors.map(c => <button key={c.id} onClick={() => runWhatIf(c)} className="mobility-card"><div><TrafficCone/><b>{c.name}</b></div><strong>{c.observed_speed} km/h</strong><span>Normal {c.normal_speed} · Delay +{c.estimated_delay_min} min</span><div className="mobility-risk"><i style={{ width: `${Math.round(c.congestion_index*100)}%` }}/></div><small>{c.trend} · {Math.round(c.confidence*100)}% confidence</small></button>)}</div>
          {whatIf?.available && <div className="whatif"><div className="whatif-head"><Crosshair/><div><span>WHAT-IF EXPERIMENT</span><b>{whatIf.corridor_name}</b></div><small>SAME INITIAL STATE</small></div><div className="compare"><div><span>NO ACTION</span><strong>{whatIf.baseline.mean_speed_kmh} km/h</strong><p>Delay +{whatIf.baseline.estimated_delay_min} min</p><b>Spillback: {whatIf.baseline.spillback_risk}</b></div><div className="intervention"><span>FLOW MITIGATION</span><strong>{whatIf.intervention.mean_speed_kmh} km/h</strong><p>Delay +{whatIf.intervention.estimated_delay_min} min</p><b>Spillback: {whatIf.intervention.spillback_risk}</b></div></div><p className="model-note">Corridor what-if remains a decision-support model. For vehicle-level physics, open any bus and launch its SUMO Micro Twin.</p></div>}
        </div>
      )}

      {microTwinBus && <BusMicroTwin bus={microTwinBus} onClose={() => setMicroTwinBus(null)} />}
    </div>
  )
}

export default App
