import { useEffect, useRef, useState } from 'react'

/**
 * The backend advances in discrete ticks (one poll every `duration` ms), so the
 * raw fleet array teleports. These hooks interpolate between the last two
 * server states on an animation frame, which is purely a presentation concern:
 * no position is invented, we only draw the straight line the bus was already
 * reported to have travelled along.
 */

const lerp = (a, b, t) => a + (b - a) * t

function shortestAngleLerp(a, b, t) {
  const delta = ((((b - a) % 360) + 540) % 360) - 180
  return a + delta * t
}

export function useAnimatedFleet(fleet, duration = 1400) {
  const [frame, setFrame] = useState(fleet)
  const fromRef = useRef(new Map())
  const toRef = useRef(new Map())
  const startRef = useRef(0)
  const rafRef = useRef(0)

  useEffect(() => {
    if (!fleet?.length) return
    // Snapshot where each bus currently *appears*, and where it must arrive.
    const current = new Map(frame?.map(b => [b.bus_id, b]) || [])
    fromRef.current = new Map(
      fleet.map(b => [b.bus_id, current.get(b.bus_id) || b])
    )
    toRef.current = new Map(fleet.map(b => [b.bus_id, b]))
    startRef.current = performance.now()

    const tick = now => {
      const t = Math.min(1, (now - startRef.current) / duration)
      // Ease-out keeps the motion from looking like a metronome.
      const e = 1 - Math.pow(1 - t, 2)
      setFrame(
        fleet.map(target => {
          const a = fromRef.current.get(target.bus_id) || target
          return {
            ...target,
            lat: lerp(a.lat, target.lat, e),
            lng: lerp(a.lng, target.lng, e),
            heading: shortestAngleLerp(a.heading ?? target.heading, target.heading, e),
            speed_kmh: lerp(a.speed_kmh ?? target.speed_kmh, target.speed_kmh, e),
          }
        })
      )
      if (t < 1) rafRef.current = requestAnimationFrame(tick)
    }
    rafRef.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(rafRef.current)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fleet, duration])

  return frame || fleet || []
}

/** Fading breadcrumb trail per bus, capped so memory stays bounded. */
export function useTrails(fleet, length = 22) {
  const trails = useRef(new Map())
  const [, force] = useState(0)

  useEffect(() => {
    if (!fleet?.length) return
    fleet.forEach(b => {
      const t = trails.current.get(b.bus_id) || []
      t.push([b.lat, b.lng])
      if (t.length > length) t.shift()
      trails.current.set(b.bus_id, t)
    })
    force(n => n + 1)
  }, [fleet, length])

  return trails.current
}

/**
 * Expanding rings for freshly detected events. Each ring lives for `life` ms and
 * then removes itself, so this never accumulates.
 */
export function useDetectionPulses(newEvents, life = 2600) {
  const [pulses, setPulses] = useState([])
  const seen = useRef(new Set())

  useEffect(() => {
    if (!newEvents?.length) return
    const fresh = newEvents.filter(e => !seen.current.has(e.event_id))
    if (!fresh.length) return
    fresh.forEach(e => seen.current.add(e.event_id))
    const born = performance.now()
    setPulses(p => [...p, ...fresh.map(e => ({ id: e.event_id, lat: e.lat, lng: e.lng, status: e.status, born }))])
    const timer = setTimeout(
      () => setPulses(p => p.filter(x => x.born !== born)),
      life
    )
    return () => clearTimeout(timer)
  }, [newEvents, life])

  const [, force] = useState(0)
  useEffect(() => {
    if (!pulses.length) return
    let raf
    const loop = () => { force(n => n + 1); raf = requestAnimationFrame(loop) }
    raf = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf)
  }, [pulses.length])

  const now = performance.now()
  return pulses.map(p => {
    const age = Math.min(1, (now - p.born) / life)
    return { ...p, radius: 8 + age * 46, opacity: (1 - age) * 0.85 }
  })
}

/** Tween a number so metric cards count up instead of snapping. */
export function useCountUp(value, duration = 700) {
  const [display, setDisplay] = useState(value ?? 0)
  const fromRef = useRef(value ?? 0)

  useEffect(() => {
    const target = Number(value) || 0
    const from = fromRef.current
    if (from === target) return
    const start = performance.now()
    let raf
    const step = now => {
      const t = Math.min(1, (now - start) / duration)
      const e = 1 - Math.pow(1 - t, 3)
      const next = from + (target - from) * e
      setDisplay(next)
      if (t < 1) raf = requestAnimationFrame(step)
      else fromRef.current = target
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [value, duration])

  return display
}
