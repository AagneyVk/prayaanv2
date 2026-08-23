import React, { useMemo } from 'react'
import { CircleMarker, Marker, Polygon, Polyline, Tooltip } from 'react-leaflet'
import L from 'leaflet'

/**
 * Animated map layer for the command centre.
 *
 * Everything drawn here is derived from data the backend actually sent. The one
 * deliberate exception is the "scan halo" around each bus, which is a fixed
 * pixel radius and is a UI affordance, not a sensing claim — the true sensor
 * footprint is the 55 m cone, drawn to real scale.
 */

const SENSOR_RANGE_M = 55
const FRONT_FOV_DEG = 62

// A glyph per defect class. Colour now carries operational impact, so shape has
// to carry type — an operator must be able to tell a dark signal from a broken
// crossing without opening anything.
const TYPE_GLYPH = {
  POTHOLE: '\u25c9',
  SURFACE_CRACK: '\u2307',
  FADED_MARKING: '\u2261',
  FADED_ZEBRA_CROSSING: '\u25a4',
  WATERLOGGING: '\u2248',
  MANHOLE_DAMAGE: '\u2b2d',
  TRAFFIC_SIGNAL_FAULT: '\u25d4',
  STREETLIGHT_OUTAGE: '\u2600',
  DAMAGED_SIGNAGE: '\u25c7',
  PEDESTRIAN_RISK: '\u25b3',
  ILLEGAL_DUMPING: '\u2612',
}

// Colour encodes OPERATIONAL IMPACT — "will this stop or damage a bus" — not
// lifecycle. The system exists to keep the fleet moving, so red has to mean
// "act now, this impedes driving". Colouring every confirmed asset red made a
// faded crossing shout as loudly as a sunken manhole, and once everything is
// urgent nothing is.
//
// Lifecycle is still visible, just carried by other channels: pulse for major,
// dashes for discarded, size for confidence.
const IMPACT_COLOURS = {
  major:     { stroke: '#ff5d6c', fill: '#ff3348' },  // impedes or damages vehicles
  confirmed: { stroke: '#ffb547', fill: '#f59e0b' },  // confirmed, not vehicle-impeding
  candidate: { stroke: '#c98f3e', fill: '#8a6222' },  // awaiting a second bus
  repair:    { stroke: '#5db8ff', fill: '#2a7fd4' },  // repair suspected
  resolved:  { stroke: '#34d399', fill: '#0f6b52' },  // fleet-verified fixed
  rejected:  { stroke: '#3b5065', fill: '#16222e' },  // discarded clutter
}

const RADIUS = {
  major: 10, confirmed: 7, candidate: 5, repair: 7, resolved: 6, rejected: 3,
}

// How much each defect class actually impedes a vehicle. Mirrors the routing
// weights deliberately: the map and the router must agree on what "major" means,
// or an operator sees red on the map and NO_ACTION from the router.
const BLOCKING_WEIGHT = {
  MANHOLE_DAMAGE: 1.45,
  WATERLOGGING: 1.35,
  POTHOLE: 1.00,
  SURFACE_CRACK: 0.45,
}

// Red requires all three: confirmed by independent buses, a class that actually
// impedes driving, and enough severity to matter. A shallow pothole two buses
// agree on is still amber.
const MAJOR_THRESHOLD = 0.70

function impactOf(site) {
  if (site.status === 'RESOLVED') return 'resolved'
  if (site.status === 'REJECTED') return 'rejected'
  if (site.status === 'REPAIR_SUSPECTED') return 'repair'
  if (site.status !== 'CONFIRMED') return 'candidate'
  const w = BLOCKING_WEIGHT[site.subtype] || 0
  const score = w * (site.severity ?? 0) * (site.fused_confidence ?? 0)
  return score >= MAJOR_THRESHOLD ? 'major' : 'confirmed'
}

/** Bus icon that actually points where the bus is going. */
function busIcon(heading, night) {
  return L.divIcon({
    className: 'bus-div-icon',
    iconSize: [26, 26],
    iconAnchor: [13, 13],
    html: `<div class="bus-glyph${night ? ' night' : ''}" style="transform:rotate(${heading}deg)">
             <span class="bus-arrow"></span>
             <span class="bus-beam"></span>
           </div>`,
  })
}

/** Offset a lat/lng by a distance and bearing, for the true-scale sensor cone. */
function project(lat, lng, metres, bearingDeg) {
  const rad = (bearingDeg * Math.PI) / 180
  const dLat = (metres * Math.cos(rad)) / 111320
  const dLng = (metres * Math.sin(rad)) / (111320 * Math.cos((lat * Math.PI) / 180))
  return [lat + dLat, lng + dLng]
}

function sensorCone(bus) {
  const half = FRONT_FOV_DEG / 2
  const pts = [[bus.lat, bus.lng]]
  for (let a = -half; a <= half; a += 6) {
    pts.push(project(bus.lat, bus.lng, SENSOR_RANGE_M, (bus.heading || 0) + a))
  }
  return pts
}

export default function LiveMap({
  fleet, trails, sites, events, pulses, sweep, advisory, showRejected, lighting,
  onSelectBus, onSelectEvent,
}) {
  const visibleSites = showRejected ? sites : sites.filter(s => s.status !== 'REJECTED')
  const night = (lighting?.ambient ?? 1) < 0.35

  // Headlight beams appear only after dark. Small touch, but it is the moment the
  // map stops being a diagram and starts reading as a city at night — and it is
  // driven by the same ambient value that governs what the cameras can detect.
  const icons = useMemo(
    () => new Map(fleet.map(b => [b.bus_id, busIcon(b.heading || 0, night)])),
    [fleet, night]
  )

  return (
    <>
      {/* Routing advisory: what the bus does today vs what the hazard-weighted
          router suggests. Drawn only when the engine actually advises a change,
          so the map never implies an action nobody recommended. */}
      {advisory?.action === 'ADVISE_REROUTE' && (
        <>
          <Polyline
            positions={advisory.baseline.path}
            pathOptions={{ color: '#7b8ea3', weight: 3, opacity: 0.5, dashArray: '4 7' }}
          />
          <Polyline
            positions={advisory.advised.path}
            pathOptions={{ color: '#ffb547', weight: 4, opacity: 0.95 }}
          />
        </>
      )}
      {/* Fading breadcrumb of where each bus has actually been sensing. */}
      {fleet.map(bus => {
        const trail = trails.get(bus.bus_id)
        if (!trail || trail.length < 2) return null
        return trail.slice(1).map((pt, i) => (
          <Polyline
            key={`${bus.bus_id}-tr-${i}`}
            positions={[trail[i], pt]}
            pathOptions={{
              color: '#22d3ee',
              weight: 1 + (i / trail.length) * 2.2,
              opacity: 0.06 + (i / trail.length) * 0.5,
            }}
          />
        ))
      })}

      {/* Known asset locations, coloured by consensus status. */}
      {visibleSites.map(site => {
        const impact = impactOf(site)
        const c = IMPACT_COLOURS[impact]
        // Only a major fault pulses. Motion is the loudest signal on a map, so
        // it is reserved for the thing that needs a crew today.
        const major = impact === 'major'
        return (
          <CircleMarker
            key={site.id}
            center={[site.lat, site.lng]}
            radius={RADIUS[impact] ?? 5}
            className={major ? 'site-confirmed-pulse' : undefined}
            pathOptions={{
              color: c.stroke,
              fillColor: c.fill,
              fillOpacity: impact === 'rejected' ? 0.2 : major ? 0.85 : 0.6,
              weight: major ? 2.6 : 1.5,
              dashArray: impact === 'rejected' ? '2 4' : undefined,
            }}
            eventHandlers={{
              click: () => {
                const ev = events.find(e => e.asset_id === site.id)
                if (ev) onSelectEvent(ev)
              },
            }}
          >
            <Tooltip direction="top">
              <b>{TYPE_GLYPH[site.subtype] || '\u25cf'} {site.id} · {site.subtype.replaceAll('_', ' ')}</b>
              <br />
              {impact === 'major' ? 'MAJOR · IMPEDES VEHICLES' : site.status} · {Math.round((site.fused_confidence ?? 0) * 100)}% fused
              <br />
              {site.observations} obs · {site.independent_buses} bus
              {site.independent_buses === 1 ? '' : 'es'} · {site.clean_passes} clean pass
              {site.clean_passes === 1 ? '' : 'es'}
              <br />
              ±{site.position_uncertainty_m} m · priority {site.priority}
            </Tooltip>
          </CircleMarker>
        )
      })}

      {/* Expanding ring the moment a detection lands. */}
      {pulses.map(p => (
        <CircleMarker
          key={p.id}
          center={[p.lat, p.lng]}
          radius={p.radius}
          interactive={false}
          pathOptions={{
            color: p.status === 'CONFIRMED' ? '#ff5d6c' : '#ffd166',
            fillColor: 'transparent',
            fillOpacity: 0,
            weight: 2,
            opacity: p.opacity,
          }}
        />
      ))}

      {fleet.map(bus => (
        <React.Fragment key={bus.bus_id}>
          {/* True-scale 55 m forward camera footprint. */}
          <Polygon
            positions={sensorCone(bus)}
            interactive={false}
            pathOptions={{ color: '#7ef0ff', fillColor: '#22d3ee', fillOpacity: 0.18, weight: 0.8, opacity: 0.5 }}
          />
          {/* Decorative scan halo — fixed pixels, breathing with the sim clock. */}
          <CircleMarker
            center={[bus.lat, bus.lng]}
            radius={14 + sweep * 8}
            interactive={false}
            pathOptions={{
              color: '#13d5ff',
              fillColor: '#13d5ff',
              fillOpacity: 0.05,
              weight: 1,
              opacity: 0.45 - sweep * 0.3,
            }}
          />
          <Marker
            position={[bus.lat, bus.lng]}
            icon={icons.get(bus.bus_id)}
            eventHandlers={{ click: () => onSelectBus(bus) }}
          >
            <Tooltip direction="top" offset={[0, -10]}>
              {bus.bus_id} · {Math.round(bus.speed_kmh)} km/h · hdg {Math.round(bus.heading)}°
            </Tooltip>
          </Marker>
        </React.Fragment>
      ))}
    </>
  )
}
