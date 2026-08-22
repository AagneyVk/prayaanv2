import React, { useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import { Pause, Play, RotateCcw, X } from 'lucide-react'

const KIND_COLOR = {
  car: 0x4aa3ff,
  bike: 0xffd166,
  auto: 0x35d07f,
  bus: 0xff6b6b,
  truck: 0xb889ff,
  van: 0x66d9ef,
}

function makeVehicle(kind, ego = false) {
  const group = new THREE.Group()
  const dims = {
    car: [4.4, 1.75, 1.35],
    bike: [2.0, 0.7, 1.05],
    auto: [2.8, 1.35, 1.55],
    bus: [10.5, 2.45, 3.1],
    truck: [8.8, 2.4, 2.8],
    van: [5.1, 1.95, 2.15],
  }[kind] || [4.4, 1.75, 1.35]

  const body = new THREE.Mesh(
    new THREE.BoxGeometry(dims[0], dims[2], dims[1]),
    new THREE.MeshStandardMaterial({ color: ego ? 0x00e5ff : (KIND_COLOR[kind] || 0xffffff), metalness: 0.2, roughness: 0.55 })
  )
  body.position.y = dims[2] / 2
  group.add(body)

  if (kind !== 'bike') {
    const glass = new THREE.Mesh(
      new THREE.BoxGeometry(Math.max(1.0, dims[0] * 0.38), Math.max(0.35, dims[2] * 0.42), dims[1] * 0.86),
      new THREE.MeshStandardMaterial({ color: 0x07131d, roughness: 0.15, metalness: 0.15 })
    )
    glass.position.set(-dims[0] * 0.08, dims[2] * 0.72, 0)
    group.add(glass)
  } else {
    const rider = new THREE.Mesh(
      new THREE.CapsuleGeometry(0.22, 0.65, 4, 8),
      new THREE.MeshStandardMaterial({ color: 0xf2f4f8 })
    )
    rider.position.set(0.05, 1.25, 0)
    group.add(rider)
  }

  for (const z of [-dims[1] / 2 - 0.04, dims[1] / 2 + 0.04]) {
    for (const x of [-dims[0] * 0.30, dims[0] * 0.30]) {
      if (kind === 'bike' && x > 0) continue
      const wheel = new THREE.Mesh(
        new THREE.CylinderGeometry(kind === 'bike' ? 0.28 : 0.34, kind === 'bike' ? 0.28 : 0.34, 0.16, 16),
        new THREE.MeshStandardMaterial({ color: 0x050607 })
      )
      wheel.rotation.x = Math.PI / 2
      wheel.position.set(x, kind === 'bike' ? 0.32 : 0.34, z)
      group.add(wheel)
    }
  }

  if (ego) {
    const halo = new THREE.Mesh(
      new THREE.RingGeometry(2.6, 3.0, 48),
      new THREE.MeshBasicMaterial({ color: 0x00e5ff, transparent: true, opacity: 0.55, side: THREE.DoubleSide })
    )
    halo.rotation.x = -Math.PI / 2
    halo.position.y = 0.03
    group.add(halo)
  }

  group.userData.length = dims[0]
  return group
}

export default function BusMicroTwin({ bus, onClose }) {
  const mountRef = useRef(null)
  const rendererRef = useRef(null)
  const sceneRef = useRef(null)
  const cameraRef = useRef(null)
  const meshesRef = useRef(new Map())
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [playing, setPlaying] = useState(true)
  const [frameIndex, setFrameIndex] = useState(0)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetch(`/api/v2/sumo/bus/${bus.bus_id}`)
      .then(r => r.json())
      .then(payload => {
        if (cancelled) return
        if (!payload.available) throw new Error(payload.reason || 'SUMO unavailable')
        setData(payload)
        setFrameIndex(0)
        setLoading(false)
      })
      .catch(err => { if (!cancelled) { setError(err.message); setLoading(false) } })
    return () => { cancelled = true }
  }, [bus.bus_id])

  useEffect(() => {
    if (!data || !mountRef.current) return
    const mount = mountRef.current
    const scene = new THREE.Scene()
    scene.background = new THREE.Color(0x05070a)
    scene.fog = new THREE.Fog(0x05070a, 70, 240)
    const camera = new THREE.PerspectiveCamera(52, mount.clientWidth / mount.clientHeight, 0.1, 1000)
    camera.position.set(-28, 24, 28)
    camera.lookAt(0, 0, 0)

    const renderer = new THREE.WebGLRenderer({ antialias: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.setSize(mount.clientWidth, mount.clientHeight)
    renderer.shadowMap.enabled = true
    mount.appendChild(renderer.domElement)

    const ambient = new THREE.HemisphereLight(0x9fdcff, 0x101018, 1.5)
    scene.add(ambient)
    const key = new THREE.DirectionalLight(0xffffff, 2.1)
    key.position.set(-10, 30, 20)
    key.castShadow = true
    scene.add(key)

    const road = new THREE.Mesh(
      new THREE.BoxGeometry(220, 0.15, 12.5),
      new THREE.MeshStandardMaterial({ color: 0x171a20, roughness: 0.95 })
    )
    road.receiveShadow = true
    scene.add(road)
    for (const z of [-2.05, 2.05]) {
      for (let x = -108; x <= 108; x += 7) {
        const dash = new THREE.Mesh(
          new THREE.BoxGeometry(3.5, 0.03, 0.08),
          new THREE.MeshBasicMaterial({ color: 0xc9d0da })
        )
        dash.position.set(x, 0.1, z)
        scene.add(dash)
      }
    }
    for (const z of [-6.3, 6.3]) {
      const edge = new THREE.Mesh(new THREE.BoxGeometry(220, 0.08, 0.12), new THREE.MeshBasicMaterial({ color: 0x51606f }))
      edge.position.set(0, 0.08, z)
      scene.add(edge)
    }

    rendererRef.current = renderer
    sceneRef.current = scene
    cameraRef.current = camera

    let raf
    const render = () => {
      renderer.render(scene, camera)
      raf = requestAnimationFrame(render)
    }
    render()

    const resize = () => {
      if (!mountRef.current) return
      camera.aspect = mountRef.current.clientWidth / mountRef.current.clientHeight
      camera.updateProjectionMatrix()
      renderer.setSize(mountRef.current.clientWidth, mountRef.current.clientHeight)
    }
    window.addEventListener('resize', resize)
    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', resize)
      meshesRef.current.forEach(m => scene.remove(m))
      meshesRef.current.clear()
      renderer.dispose()
      if (renderer.domElement.parentNode === mount) mount.removeChild(renderer.domElement)
    }
  }, [data])

  useEffect(() => {
    if (!data?.frames?.length || !sceneRef.current) return
    const frame = data.frames[Math.min(frameIndex, data.frames.length - 1)]
    const active = new Set()
    const ego = frame.ego
    const egoX = ego?.x ?? 0

    frame.vehicles.forEach(v => {
      active.add(v.id)
      let mesh = meshesRef.current.get(v.id)
      if (!mesh) {
        mesh = makeVehicle(v.kind, v.ego)
        mesh.traverse(obj => { if (obj.isMesh) obj.castShadow = true })
        meshesRef.current.set(v.id, mesh)
        sceneRef.current.add(mesh)
      }
      const localX = v.x - egoX
      const laneZ = (v.lane - 1) * 4.1
      mesh.position.set(localX, 0.12, laneZ)
      mesh.rotation.y = Math.PI / 2
    })

    meshesRef.current.forEach((mesh, id) => {
      if (!active.has(id)) {
        sceneRef.current.remove(mesh)
        meshesRef.current.delete(id)
      }
    })

    if (cameraRef.current) {
      cameraRef.current.position.x = -28
      cameraRef.current.lookAt(8, 0, 0)
    }
  }, [data, frameIndex])

  useEffect(() => {
    if (!playing || !data?.frames?.length) return
    const timer = setInterval(() => setFrameIndex(i => (i + 1) % data.frames.length), 100)
    return () => clearInterval(timer)
  }, [playing, data])

  const frame = data?.frames?.[frameIndex]
  const ego = frame?.ego
  const nearby = frame?.vehicles?.length || 0
  const kindCounts = useMemo(() => {
    const out = {}
    for (const v of frame?.vehicles || []) out[v.kind] = (out[v.kind] || 0) + 1
    return out
  }, [frame])

  return (
    <div className="micro-twin-overlay">
      <div className="micro-twin-shell">
        <div className="micro-twin-head">
          <div><span>SUMO MICROSCOPIC DIGITAL TWIN</span><h2>{bus.bus_id} · Local Traffic World</h2></div>
          <div className="micro-actions">
            <button onClick={() => setPlaying(v => !v)}>{playing ? <Pause size={17}/> : <Play size={17}/>}</button>
            <button onClick={() => setFrameIndex(0)}><RotateCcw size={17}/></button>
            <button onClick={onClose}><X size={18}/></button>
          </div>
        </div>

        {loading && <div className="micro-loading">Generating SUMO physics for {bus.bus_id}… first run may take a few seconds.</div>}
        {error && <div className="micro-error"><b>SUMO micro twin unavailable</b><span>{error}</span><small>Run backend dependency installation again; PRAYAAN uses the official eclipse-sumo wheel.</small></div>}

        {data && <>
          <div ref={mountRef} className="micro-canvas" />
          <div className="micro-hud left">
            <span>PHYSICS SOURCE</span><b>{data.summary.source}</b>
            <small>IDM car following · SUMO lane changing</small>
          </div>
          <div className="micro-hud right">
            <span>EGO BUS</span><b>{ego ? `${(ego.speed * 3.6).toFixed(1)} km/h` : 'waiting to enter'}</b>
            <small>{nearby} nearby vehicles · frame {frameIndex + 1}/{data.frames.length}</small>
          </div>
          <div className="micro-types">
            {Object.entries(kindCounts).map(([kind, count]) => <span key={kind}>{kind.toUpperCase()} <b>{count}</b></span>)}
          </div>
          <div className="micro-timeline"><i style={{ width: `${((frameIndex + 1) / data.frames.length) * 100}%` }}/></div>
        </>}
      </div>
    </div>
  )
}
