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

// The asset lifecycle is the story this map tells, so each state gets a colour
// that means something: red = the fleet stands behind it, amber = candidate,
// blue = we think it was repaired, green = closed, grey = discarded clutter.
const SITE_COLOURS = {
  CONFIRMED:        { stroke: '#ff5d6c', fill: '#ff3348' },
  UNVERIFIED:       { stroke: '#ffb547', fill: '#ffb547' },
  REPAIR_SUSPECTED: { stroke: '#5db8ff', fill: '#2a7fd4' },
  RESOLVED:         { stroke: '#34d399', fill: '#0f6b52' },
  REJECTED:         { stroke: '#3b5065', fill: '#16222e' },
  UNSEEN:           { stroke: '#41607a', fill: '#1d3346' },
}

const RADIUS = {
  CONFIRMED: 9, UNVERIFIED: 6, REPAIR_SUSPECTED: 7, RESOLVED: 6, REJECTED: 3, UNSEEN: 4,
}

// A glyph per defect class. An operator scanning the map should be able to tell a
// dark signal from a broken crossing without opening anything — colour alone
// encodes lifecycle, so shape has to carry the type.
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
        const c = SITE_COLOURS[site.status] || SITE_COLOURS.UNSEEN
        const confirmed = site.status === 'CONFIRMED'
        return (
          <CircleMarker
            key={site.id}
            center={[site.lat, site.lng]}
            radius={RADIUS[site.status] ?? 5}
            className={confirmed ? 'site-confirmed-pulse' : undefined}
            pathOptions={{
              color: c.stroke,
              fillColor: c.fill,
              fillOpacity: site.status === 'REJECTED' ? 0.2 : confirmed ? 0.8 : 0.6,
              weight: confirmed ? 2.5 : 1.5,
              dashArray: site.status === 'REJECTED' ? '2 4' : undefined,
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
              {site.status} · {Math.round((site.fused_confidence ?? 0) * 100)}% fused
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
