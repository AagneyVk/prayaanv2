import React, { useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import { Pause, Play, RotateCcw, X, AlertTriangle, ScanLine } from 'lucide-react'

const COLORS={car:0x4aa3ff,bike:0xffd166,auto:0x35d07f,bus:0xff6b6b,truck:0xb889ff,van:0x66d9ef}
const mat=(c,r=.55)=>new THREE.MeshStandardMaterial({color:c,metalness:.18,roughness:r})
function wheel(r=.34,w=.18){const m=new THREE.Mesh(new THREE.CylinderGeometry(r,r,w,18),mat(0x050607,.9));m.rotation.x=Math.PI/2;return m}
function vehicle(kind,ego=false){
 const g=new THREE.Group(), c=ego?0x00e5ff:(COLORS[kind]||0xe8edf4)
 const dims=kind==='bus'?[10.6,2.65,2.45]:kind==='truck'?[8.8,2.35,2.35]:kind==='van'?[5.1,1.65,1.95]:kind==='auto'?[2.75,1.45,1.4]:kind==='bike'?[1.5,.75,.42]:[4.4,1.25,1.78]
 const body=new THREE.Mesh(new THREE.BoxGeometry(...dims),mat(c));body.position.y=dims[1]/2+.35;g.add(body)
 if(kind==='car'||kind==='van'){const cab=new THREE.Mesh(new THREE.BoxGeometry(dims[0]*.5,.6,dims[2]*.86),mat(0x091722,.2));cab.position.set(-.15,dims[1]+.25,0);g.add(cab)}
 if(kind==='auto'){const roof=new THREE.Mesh(new THREE.BoxGeometry(1.7,.55,1.35),mat(0x101813,.7));roof.position.set(-.3,1.65,0);g.add(roof)}
 if(kind==='bike'){const rider=new THREE.Mesh(new THREE.CapsuleGeometry(.18,.55,4,8),mat(0xe8edf4));rider.position.set(0,1.25,0);rider.rotation.z=-.2;g.add(rider);const head=new THREE.Mesh(new THREE.SphereGeometry(.18,12,12),mat(0x202a35));head.position.set(.15,1.72,0);g.add(head)}
 const axle=kind==='bus'?[-3.5,3.4]:kind==='truck'?[-2.7,2.5]:[-Math.max(.65,dims[0]*.3),Math.max(.65,dims[0]*.3)]
 for(const x of axle)for(const z of [-dims[2]/2-.04,dims[2]/2+.04]){const w=wheel(kind==='bus'||kind==='truck'?.46:.31);w.position.set(x,.38,z);g.add(w)}
 if(ego){const ring=new THREE.Mesh(new THREE.RingGeometry(3,3.4,54),new THREE.MeshBasicMaterial({color:0x00e5ff,transparent:true,opacity:.65,side:THREE.DoubleSide}));ring.rotation.x=-Math.PI/2;ring.position.y=.04;g.add(ring);const beam=new THREE.Mesh(new THREE.ConeGeometry(4,18,32,1,true),new THREE.MeshBasicMaterial({color:0x00e5ff,transparent:true,opacity:.045,side:THREE.DoubleSide}));beam.rotation.z=-Math.PI/2;beam.position.set(10,1.2,0);g.add(beam)}
 g.userData.target=new THREE.Vector3();return g
}
function pothole(){const g=new THREE.Group();const pit=new THREE.Mesh(new THREE.CylinderGeometry(1.15,.8,.13,22),mat(0x050505,1));pit.scale.z=.55;pit.position.y=.02;g.add(pit);const rim=new THREE.Mesh(new THREE.RingGeometry(.9,1.35,24),new THREE.MeshBasicMaterial({color:0x6d3f27,transparent:true,opacity:.8,side:THREE.DoubleSide}));rim.rotation.x=-Math.PI/2;rim.scale.y=.55;rim.position.y=.09;g.add(rim);return g}
function water(){const m=new THREE.Mesh(new THREE.CircleGeometry(2.4,30),new THREE.MeshStandardMaterial({color:0x246d89,transparent:true,opacity:.58,roughness:.18}));m.rotation.x=-Math.PI/2;m.scale.y=.48;m.position.y=.1;return m}

export default function BusMicroTwin({bus,onClose}){
 const mountRef=useRef(null), sceneRef=useRef(null), cameraRef=useRef(null), meshes=useRef(new Map()), scenery=useRef([]), hazards=useRef(new Map())
 const [data,setData]=useState(null),[loading,setLoading]=useState(true),[error,setError]=useState(null),[playing,setPlaying]=useState(true),[frameIndex,setFrameIndex]=useState(0),[cameraMode,setCameraMode]=useState('chase'),[activeEvent,setActiveEvent]=useState(null),[eventLog,setEventLog]=useState([])
 useEffect(()=>{let dead=false;setLoading(true);fetch(`/api/v2/sumo/bus/${bus.bus_id}`).then(r=>r.json()).then(p=>{if(dead)return;if(!p.available)throw Error(p.reason||'SUMO unavailable');setData(p);setFrameIndex(0);setLoading(false)}).catch(e=>{if(!dead){setError(e.message);setLoading(false)}});return()=>{dead=true}},[bus.bus_id])
 useEffect(()=>{if(!data||!mountRef.current)return;const mount=mountRef.current,scene=new THREE.Scene();scene.background=new THREE.Color(0x05070a);scene.fog=new THREE.Fog(0x05070a,90,260);const cam=new THREE.PerspectiveCamera(52,mount.clientWidth/mount.clientHeight,.1,1000);const renderer=new THREE.WebGLRenderer({antialias:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.setSize(mount.clientWidth,mount.clientHeight);renderer.shadowMap.enabled=true;renderer.outputColorSpace=THREE.SRGBColorSpace;mount.appendChild(renderer.domElement);scene.add(new THREE.HemisphereLight(0x9fdcff,0x101018,1.55));const sun=new THREE.DirectionalLight(0xffffff,2.1);sun.position.set(-10,30,20);scene.add(sun)
 const road=new THREE.Mesh(new THREE.BoxGeometry(250,.15,12.5),mat(0x171a20,.98));scene.add(road)
 for(const z of [-2.05,2.05])for(let x=-126;x<=126;x+=7){const d=new THREE.Mesh(new THREE.BoxGeometry(3.6,.03,.09),new THREE.MeshBasicMaterial({color:0xc9d0da}));d.position.set(x,.1,z);scene.add(d);scenery.current.push(d)}
 for(let x=-120;x<=120;x+=20)for(const z of [-8.5,8.5]){const pole=new THREE.Mesh(new THREE.CylinderGeometry(.08,.11,5.5,10),mat(0x26313c,.85));pole.position.set(x,2.75,z);scene.add(pole);scenery.current.push(pole)}
 for(const s of data.scenarios||[]){let h=s.type==='ROAD_DEFECT'?pothole():s.type==='ROAD_HAZARD'?water():null;if(h){scene.add(h);hazards.current.set(s.id,h)}}
 sceneRef.current=scene;cameraRef.current=cam;let raf;const render=()=>{meshes.current.forEach(m=>m.position.lerp(m.userData.target,.2));renderer.render(scene,cam);raf=requestAnimationFrame(render)};render();const resize=()=>{cam.aspect=mount.clientWidth/mount.clientHeight;cam.updateProjectionMatrix();renderer.setSize(mount.clientWidth,mount.clientHeight)};addEventListener('resize',resize);return()=>{cancelAnimationFrame(raf);removeEventListener('resize',resize);renderer.dispose();if(renderer.domElement.parentNode===mount)mount.removeChild(renderer.domElement);meshes.current.clear();scenery.current=[];hazards.current.clear()}},[data])
 useEffect(()=>{if(!data?.frames?.length||!sceneRef.current)return;const f=data.frames[Math.min(frameIndex,data.frames.length-1)],ego=f.ego,egoX=ego?.x||0,active=new Set();for(const v of f.vehicles){active.add(v.id);let m=meshes.current.get(v.id);if(!m){m=vehicle(v.kind,v.ego);meshes.current.set(v.id,m);sceneRef.current.add(m);m.position.set(v.x-egoX,.12,(v.lane-1)*4.1)}m.userData.target.set(v.x-egoX,.12,(v.lane-1)*4.1)}meshes.current.forEach((m,id)=>{if(!active.has(id)){sceneRef.current.remove(m);meshes.current.delete(id)}})
 // Scroll fixed road furniture against the ego vehicle so forward motion is visually obvious.
 scenery.current.forEach((o,i)=>{const base=-120+(i%13)*20; if(o.geometry?.type==='BoxGeometry')o.position.x=((base-egoX+125)%250)-125; else o.position.x=((base-egoX+125)%250)-125})
 for(const s of data.scenarios||[]){const h=hazards.current.get(s.id);if(h)h.position.set(s.x-egoX,.1,(s.lane-1)*4.1)}
 const approaching=(data.scenarios||[]).filter(s=>ego&&s.x-egoX<35&&s.x-egoX>-10);const newest=approaching[0]||null;if(newest&&activeEvent?.id!==newest.id){setActiveEvent(newest);setEventLog(log=>log.some(x=>x.id===newest.id)?log:[newest,...log].slice(0,4))}else if(!newest&&activeEvent)setActiveEvent(null)
 if(cameraRef.current){if(cameraMode==='top'){cameraRef.current.position.set(0,72,.01);cameraRef.current.lookAt(0,0,0)}else if(cameraMode==='pov'){cameraRef.current.position.set(-4.6,3.4,0);cameraRef.current.lookAt(32,1.2,0)}else{cameraRef.current.position.set(-29,19,24);cameraRef.current.lookAt(9,0,0)}}},[data,frameIndex,cameraMode])
 useEffect(()=>{if(!playing||!data?.frames?.length)return;const t=setInterval(()=>setFrameIndex(i=>(i+1)%data.frames.length),100);return()=>clearInterval(t)},[playing,data])
 const frame=data?.frames?.[frameIndex],ego=frame?.ego,counts=useMemo(()=>{const o={};for(const v of frame?.vehicles||[])o[v.kind]=(o[v.kind]||0)+1;return o},[frame])
 return <div className="micro-twin-overlay"><div className="micro-twin-shell">
  <div className="micro-twin-head"><div><span>PRAYAAN · SUMO URBAN INTELLIGENCE TWIN</span><h2>{bus.bus_id} · Live Mission Replay</h2></div><div className="micro-actions"><div className="micro-camera-switch">{['chase','pov','top'].map(m=><button key={m} className={cameraMode===m?'active':''} onClick={()=>setCameraMode(m)}>{m.toUpperCase()}</button>)}</div><button onClick={()=>setPlaying(x=>!x)}>{playing?<Pause size={17}/>:<Play size={17}/>}</button><button onClick={()=>{setFrameIndex(0);setEventLog([])}}><RotateCcw size={17}/></button><button onClick={onClose}><X size={18}/></button></div></div>
  {loading&&<div className="micro-loading">Generating SUMO physics + mission scenarios for {bus.bus_id}…</div>}{error&&<div className="micro-error"><b>SUMO micro twin unavailable</b><span>{error}</span></div>}
  {data&&<><div ref={mountRef} className="micro-canvas"/>
   <div className="micro-hud left"><span>PHYSICS</span><b>LIVE SUMO FCD</b><small>IDM · LC2013 · seed {data.seed}</small><small>Scenario input: SYNTHETIC · analytics: LIVE</small></div>
   <div className="micro-hud right"><span>EGO BUS</span><b>{ego?`${(ego.speed*3.6).toFixed(1)} km/h`:'entering corridor'}</b><small>{frame?.local_density||0} nearby · {frame?.stopped_vehicles||0} stopped</small><small>travelled {ego?ego.x.toFixed(0):0} / {data.road_length_m} m</small></div>
   <div className="micro-types">{Object.entries(counts).map(([k,n])=><span key={k}>{k.toUpperCase()} <b>{n}</b></span>)}</div>
   <div className="scenario-stack">{eventLog.map(e=><div className={`scenario-mini ${e.severity.toLowerCase()}`} key={e.id}><AlertTriangle size={13}/><div><b>{e.label}</b><small>{Math.round(e.confidence*100)}% · {e.pipeline}</small></div></div>)}</div>
   {activeEvent&&<div className={`scenario-alert ${activeEvent.severity.toLowerCase()}`}><div className="scenario-alert-top"><ScanLine size={19}/><span>EDGE AI EVENT</span><b>{activeEvent.label}</b></div><p>{activeEvent.detail}</p><div className="scenario-evidence"><span>CONFIDENCE <b>{Math.round(activeEvent.confidence*100)}%</b></span><span>SEVERITY <b>{activeEvent.severity}</b></span>{activeEvent.plate&&<span>ANPR <b>{activeEvent.plate}</b> · {Math.round(activeEvent.plate_confidence*100)}%</span>}</div><small>{activeEvent.action}</small></div>}
   <div className="scenario-route"><span className="scenario-marker p" style={{left:'22%'}}>POTHOLE</span><span className="scenario-marker r" style={{left:'48%'}}>RASH + ANPR</span><span className="scenario-marker w" style={{left:'76%'}}>WATERLOGGING</span></div>
   <div className="micro-timeline"><i style={{width:`${((frameIndex+1)/data.frames.length)*100}%`}}/></div>
  </>}</div></div>
}
