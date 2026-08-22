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

function material(color, roughness = 0.55) {
  return new THREE.MeshStandardMaterial({ color, metalness: 0.18, roughness })
}

function wheel(radius = 0.34, width = 0.18) {
  const mesh = new THREE.Mesh(new THREE.CylinderGeometry(radius, radius, width, 18), material(0x050607, 0.9))
  mesh.rotation.x = Math.PI / 2
  return mesh
}

function addCar(group, color) {
  const lower = new THREE.Mesh(new THREE.BoxGeometry(4.4, 0.75, 1.78), material(color))
  lower.position.y = 0.62
  group.add(lower)
  const cabin = new THREE.Mesh(new THREE.BoxGeometry(2.25, 0.72, 1.58), material(0x0a1822, 0.24))
  cabin.position.set(-0.2, 1.28, 0)
  group.add(cabin)
  for (const x of [-1.35, 1.35]) for (const z of [-0.91, 0.91]) {
    const w = wheel(); w.position.set(x, 0.38, z); group.add(w)
  }
}

function addVan(group, color) {
  const body = new THREE.Mesh(new THREE.BoxGeometry(5.1, 1.65, 1.95), material(color))
  body.position.y = 1.0
  group.add(body)
  const windshield = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.72, 1.68), material(0x07131d, 0.18))
  windshield.position.set(2.56, 1.35, 0)
  group.add(windshield)
  for (const x of [-1.55, 1.55]) for (const z of [-1.01, 1.01]) {
    const w = wheel(0.36); w.position.set(x, 0.4, z); group.add(w)
  }
}

function addBus(group, color) {
  const body = new THREE.Mesh(new THREE.BoxGeometry(10.6, 2.65, 2.45), material(color))
  body.position.y = 1.55
  group.add(body)
  for (let x = -3.8; x <= 3.8; x += 1.45) {
    for (const z of [-1.235, 1.235]) {
      const pane = new THREE.Mesh(new THREE.BoxGeometry(0.9, 0.62, 0.035), material(0x071923, 0.16))
      pane.position.set(x, 2.05, z)
      group.add(pane)
    }
  }
  const frontGlass = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.9, 2.05), material(0x071923, 0.16))
  frontGlass.position.set(5.31, 2.02, 0)
  group.add(frontGlass)
  for (const x of [-3.55, 3.45]) for (const z of [-1.26, 1.26]) {
    const w = wheel(0.48, 0.22); w.position.set(x, 0.5, z); group.add(w)
  }
}

function addTruck(group, color) {
  const cargo = new THREE.Mesh(new THREE.BoxGeometry(5.7, 2.3, 2.4), material(color, 0.7))
  cargo.position.set(-1.35, 1.52, 0)
  group.add(cargo)
  const cab = new THREE.Mesh(new THREE.BoxGeometry(2.55, 2.05, 2.3), material(0x8b67d9))
  cab.position.set(2.85, 1.35, 0)
  group.add(cab)
  const glass = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.72, 1.9), material(0x07131d, 0.18))
  glass.position.set(4.14, 1.72, 0)
  group.add(glass)
  for (const x of [-3.0, -0.2, 2.9]) for (const z of [-1.24, 1.24]) {
    const w = wheel(0.46, 0.22); w.position.set(x, 0.48, z); group.add(w)
  }
}

function addAuto(group, color) {
  const base = new THREE.Mesh(new THREE.BoxGeometry(2.75, 0.72, 1.4), material(color))
  base.position.y = 0.65
  group.add(base)
  const canopy = new THREE.Mesh(new THREE.BoxGeometry(1.85, 1.0, 1.38), material(0x121a15, 0.7))
  canopy.position.set(-0.32, 1.46, 0)
  group.add(canopy)
  const front = new THREE.Mesh(new THREE.BoxGeometry(0.75, 0.78, 1.24), material(0xf2c84b))
  front.position.set(1.02, 1.03, 0)
  group.add(front)
  const frontWheel = wheel(0.29); frontWheel.position.set(1.0, 0.32, 0); group.add(frontWheel)
  for (const z of [-0.73, 0.73]) { const w = wheel(0.31); w.position.set(-0.78, 0.34, z); group.add(w) }
}

function addBike(group, color) {
  const frame = new THREE.Mesh(new THREE.BoxGeometry(1.25, 0.18, 0.24), material(color))
  frame.position.y = 0.62
  group.add(frame)
  for (const x of [-0.72, 0.72]) {
    const w = wheel(0.31, 0.09)
    w.position.set(x, 0.31, 0)
    group.add(w)
  }
  const riderBody = new THREE.Mesh(new THREE.CapsuleGeometry(0.19, 0.55, 4, 8), material(0xe7edf4))
  riderBody.position.set(-0.05, 1.16, 0)
  riderBody.rotation.z = -0.18
  group.add(riderBody)
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.19, 12, 12), material(0x202a35))
  head.position.set(0.12, 1.68, 0)
  group.add(head)
  const handle = new THREE.Mesh(new THREE.BoxGeometry(0.07, 0.07, 0.75), material(0x3a4652))
  handle.position.set(0.55, 1.03, 0)
  group.add(handle)
}

function makeVehicle(kind, ego = false) {
  const group = new THREE.Group()
  const color = ego ? 0x00e5ff : (KIND_COLOR[kind] || 0xe8edf4)
  if (kind === 'bike') addBike(group, color)
  else if (kind === 'auto') addAuto(group, color)
  else if (kind === 'bus') addBus(group, color)
  else if (kind === 'truck') addTruck(group, color)
  else if (kind === 'van') addVan(group, color)
  else addCar(group, color)

  if (ego) {
    const halo = new THREE.Mesh(
      new THREE.RingGeometry(3.0, 3.35, 54),
      new THREE.MeshBasicMaterial({ color: 0x00e5ff, transparent: true, opacity: 0.62, side: THREE.DoubleSide })
    )
    halo.rotation.x = -Math.PI / 2
    halo.position.y = 0.04
    group.add(halo)
    const beam = new THREE.Mesh(
      new THREE.ConeGeometry(3.8, 15, 32, 1, true),
      new THREE.MeshBasicMaterial({ color: 0x00e5ff, transparent: true, opacity: 0.035, side: THREE.DoubleSide })
    )
    beam.rotation.z = -Math.PI / 2
    beam.position.set(9, 1.2, 0)
    group.add(beam)
  }
  group.userData.target = new THREE.Vector3()
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
  const [cameraMode, setCameraMode] = useState('chase')

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
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
    scene.fog = new THREE.Fog(0x05070a, 80, 250)
    const camera = new THREE.PerspectiveCamera(52, mount.clientWidth / mount.clientHeight, 0.1, 1000)
    camera.position.set(-30, 20, 25)
    camera.lookAt(8, 0, 0)

    const renderer = new THREE.WebGLRenderer({ antialias: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.setSize(mount.clientWidth, mount.clientHeight)
    renderer.shadowMap.enabled = true
    renderer.outputColorSpace = THREE.SRGBColorSpace
    mount.appendChild(renderer.domElement)

    scene.add(new THREE.HemisphereLight(0x9fdcff, 0x101018, 1.55))
    const key = new THREE.DirectionalLight(0xffffff, 2.15)
    key.position.set(-10, 30, 20)
    key.castShadow = true
    scene.add(key)

    const road = new THREE.Mesh(new THREE.BoxGeometry(230, 0.15, 12.5), material(0x171a20, 0.98))
    road.receiveShadow = true
    scene.add(road)
    for (const z of [-2.05, 2.05]) {
      for (let x = -112; x <= 112; x += 7) {
        const dash = new THREE.Mesh(new THREE.BoxGeometry(3.6, 0.03, 0.09), new THREE.MeshBasicMaterial({ color: 0xc9d0da }))
        dash.position.set(x, 0.1, z)
        scene.add(dash)
      }
    }
    for (const z of [-6.3, 6.3]) {
      const edge = new THREE.Mesh(new THREE.BoxGeometry(230, 0.08, 0.12), new THREE.MeshBasicMaterial({ color: 0x51606f }))
      edge.position.set(0, 0.08, z)
      scene.add(edge)
    }
    for (let x = -105; x <= 105; x += 21) {
      for (const z of [-8.6, 8.6]) {
        const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.11, 5.5, 10), material(0x26313c, 0.85))
        pole.position.set(x, 2.75, z)
        scene.add(pole)
        const lamp = new THREE.PointLight(0x6ecbff, 0.75, 17)
        lamp.position.set(x, 5.2, z)
        scene.add(lamp)
      }
    }

    rendererRef.current = renderer
    sceneRef.current = scene
    cameraRef.current = camera

    let raf
    const render = () => {
      meshesRef.current.forEach(mesh => mesh.position.lerp(mesh.userData.target, 0.18))
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
        const x = v.x - egoX
        const z = (v.lane - 1) * 4.1
        mesh.position.set(x, 0.12, z)
      }
      mesh.userData.target.set(v.x - egoX, 0.12, (v.lane - 1) * 4.1)
      mesh.rotation.y = 0
    })

    meshesRef.current.forEach((mesh, id) => {
      if (!active.has(id)) {
        sceneRef.current.remove(mesh)
        meshesRef.current.delete(id)
      }
    })

    if (cameraRef.current) {
      if (cameraMode === 'top') {
        cameraRef.current.position.set(0, 72, 0.01)
        cameraRef.current.lookAt(0, 0, 0)
      } else if (cameraMode === 'pov') {
        cameraRef.current.position.set(-4.8, 3.5, 0)
        cameraRef.current.lookAt(30, 1.2, 0)
      } else {
        cameraRef.current.position.set(-29, 19, 24)
        cameraRef.current.lookAt(9, 0, 0)
      }
    }
  }, [data, frameIndex, cameraMode])

  useEffect(() => {
    if (!playing || !data?.frames?.length) return
    const timer = setInterval(() => setFrameIndex(i => (i + 1) % data.frames.length), 100)
    return () => clearInterval(timer)
  }, [playing, data])

  const frame = data?.frames?.[frameIndex]
  const ego = frame?.ego
  const nearby = frame?.vehicles?.length || 0
  const stopped = frame?.stopped_vehicles || 0
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
            <div className="micro-camera-switch">
              {['chase','pov','top'].map(mode => <button key={mode} className={cameraMode === mode ? 'active' : ''} onClick={() => setCameraMode(mode)}>{mode.toUpperCase()}</button>)}
            </div>
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
            <small>IDM car following · LC2013 lane changing · seed {data.seed}</small>
          </div>
          <div className="micro-hud right">
            <span>EGO BUS</span><b>{ego ? `${(ego.speed * 3.6).toFixed(1)} km/h` : 'waiting to enter'}</b>
            <small>{nearby} nearby · {stopped} stopped · frame {frameIndex + 1}/{data.frames.length}</small>
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
