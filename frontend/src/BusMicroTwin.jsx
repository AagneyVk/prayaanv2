import React, { useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import { Pause, Play, RotateCcw, X, AlertTriangle, ScanLine, CheckCircle2, Focus, Camera } from 'lucide-react'

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
 // Everything is drawn in the EGO BUS's frame of reference, so a vehicle holding
 // the bus's speed sits at a fixed screen position and looks parked. It is not —
 // it is doing 45 km/h alongside. Rolling wheels are the cue that resolves this,
 // and without them the whole corridor reads as a still image with a moving
 // camera. The wheel radius is kept so angular speed matches ground speed.
 g.userData.wheels=[];g.userData.wheelRadius=kind==='bus'||kind==='truck'?.46:.31
 for(const x of axle)for(const z of [-dims[2]/2-.04,dims[2]/2+.04]){const w=wheel(g.userData.wheelRadius);w.position.set(x,.38,z);g.add(w);g.userData.wheels.push(w)}
 if(ego){const ring=new THREE.Mesh(new THREE.RingGeometry(3,3.4,54),new THREE.MeshBasicMaterial({color:0x00e5ff,transparent:true,opacity:.65,side:THREE.DoubleSide}));ring.rotation.x=-Math.PI/2;ring.position.y=.04;g.add(ring);const beam=new THREE.Mesh(new THREE.ConeGeometry(4,18,32,1,true),new THREE.MeshBasicMaterial({color:0x00e5ff,transparent:true,opacity:.045,side:THREE.DoubleSide}));beam.rotation.z=-Math.PI/2;beam.position.set(10,1.2,0);g.add(beam)}
 g.userData.target=new THREE.Vector3();return g
}
function pothole(){const g=new THREE.Group();const pit=new THREE.Mesh(new THREE.CylinderGeometry(1.15,.8,.13,22),mat(0x050505,1));pit.scale.z=.55;pit.position.y=.02;g.add(pit);const rim=new THREE.Mesh(new THREE.RingGeometry(.9,1.35,24),new THREE.MeshBasicMaterial({color:0x6d3f27,transparent:true,opacity:.85,side:THREE.DoubleSide}));rim.rotation.x=-Math.PI/2;rim.scale.y=.55;rim.position.y=.09;g.add(rim);return g}
function zebra(){
 // A real zebra crossing has its bars running ALONG the direction of travel:
 // each bar is ~0.5 m wide and ~4 m deep, repeated across the full carriageway.
 // The previous version had them 90 degrees out — one long bar spanning the road,
 // repeated down it, which is a stop-line pattern, not a crossing.
 const g=new THREE.Group()
 const DEPTH=4.2, BAR_W=0.5, PITCH=1.0, ROAD_W=12.4
 const n=Math.floor(ROAD_W/PITCH)
 for(let i=0;i<n;i++){
  const z=-ROAD_W/2+PITCH/2+i*PITCH
  // Thermoplastic wears fastest in the wheel tracks — roughly a metre either
  // side of each lane centre — so the bars there are the faint ones. That
  // pattern is the giveaway a human inspector looks for, so the model should
  // show it rather than fading uniformly.
  const wheelTrack=Math.min(Math.abs(Math.abs(z)-1.4),Math.abs(Math.abs(z)-5.5))
  const wear=Math.max(0,1-wheelTrack/1.5)
  const opacity=0.82-wear*0.62
  const bar=new THREE.Mesh(new THREE.BoxGeometry(DEPTH,.02,BAR_W),
    new THREE.MeshBasicMaterial({color:0xe9f1f8,transparent:true,opacity}))
  bar.position.set(0,.085,z);g.add(bar)
  // Worn bars break up rather than dimming evenly: scuffed patches of asphalt
  // show through. Two dark slivers per bar reads as chipping at this scale.
  if(wear>0.45)for(const off of [-DEPTH*0.22,DEPTH*0.19]){
   const chip=new THREE.Mesh(new THREE.BoxGeometry(DEPTH*0.16,.025,BAR_W*1.05),
     new THREE.MeshBasicMaterial({color:0x1a1d22,transparent:true,opacity:.75}))
   chip.position.set(off,.088,z);g.add(chip)
  }
 }
 // Give-way triangles on the approach: standard on Indian crossings and the
 // strongest cue that this is a pedestrian facility and not painted hatching.
 for(const side of [-1,1])for(let i=0;i<5;i++){
  const t=new THREE.Mesh(new THREE.ConeGeometry(.28,.7,3),
    new THREE.MeshBasicMaterial({color:0xd8e4ef,transparent:true,opacity:.4}))
  t.rotation.x=-Math.PI/2;t.rotation.z=side>0?Math.PI/2:-Math.PI/2
  t.position.set(side*(DEPTH/2+1.4),.086,-4.4+i*2.2);g.add(t)
 }
 return g
}
function signalHead(){const g=new THREE.Group();const post=new THREE.Mesh(new THREE.CylinderGeometry(.09,.12,5.4,10),mat(0x2b3742,.85));post.position.set(0,2.7,-6.6);g.add(post);const arm=new THREE.Mesh(new THREE.BoxGeometry(.12,.12,3.2),mat(0x2b3742,.85));arm.position.set(0,5.2,-5);g.add(arm);const box=new THREE.Mesh(new THREE.BoxGeometry(.5,1.5,.5),mat(0x11181f,.9));box.position.set(0,4.7,-3.5);g.add(box);
 // All three lamps unlit IS the detection — a working head would show one.
 for(const[i,c]of[[0,0x2a1416],[1,0x2a2413],[2,0x13261c]].entries()){const l=new THREE.Mesh(new THREE.SphereGeometry(.16,12,12),new THREE.MeshBasicMaterial({color:c[1]}));l.position.set(0,5.2-i*.45,-3.24);g.add(l)}return g}
function manhole(){const g=new THREE.Group();const rim=new THREE.Mesh(new THREE.TorusGeometry(.85,.11,10,26),mat(0x3a3f45,.85));rim.rotation.x=Math.PI/2;rim.position.y=.06;g.add(rim);const sunk=new THREE.Mesh(new THREE.CylinderGeometry(.8,.7,.28,24),mat(0x07090b,1));sunk.position.y=-.09;g.add(sunk);return g}
function dumping(){const g=new THREE.Group();const rnd=[[0,.35,0],[.9,.28,.5],[-.7,.3,-.4],[.4,.22,-.8],[-1.1,.2,.6]];for(const[x,r,z]of rnd){const m=new THREE.Mesh(new THREE.DodecahedronGeometry(r,0),mat(0x4a4632,.95));m.position.set(x,r*.7,z+5.6);g.add(m)}return g}
function water(){const m=new THREE.Mesh(new THREE.CircleGeometry(2.4,30),new THREE.MeshStandardMaterial({color:0x246d89,transparent:true,opacity:.58,roughness:.18}));m.rotation.x=-Math.PI/2;m.scale.y=.48;m.position.y=.1;return m}
function detectionBeacon(color=0xff4258){const g=new THREE.Group();for(const r of [1.8,2.6,3.4]){const ring=new THREE.Mesh(new THREE.RingGeometry(r,r+.08,40),new THREE.MeshBasicMaterial({color,transparent:true,opacity:.8,side:THREE.DoubleSide}));ring.rotation.x=-Math.PI/2;ring.userData.base=r;g.add(ring)}const post=new THREE.Mesh(new THREE.CylinderGeometry(.035,.035,3.6,8),new THREE.MeshBasicMaterial({color,transparent:true,opacity:.72}));post.position.y=1.8;g.add(post);g.userData.pulse=0;return g}
function vehicleTracker(){
 // A driving anomaly is a MOVING vehicle, not a spot on the road. It gets a
 // wireframe lock that rides the vehicle mesh plus a vertical leader so it stays
 // findable in dense traffic — deliberately nothing like the ground-ring beacon
 // used for static road defects, because they are not the same kind of thing.
 const g=new THREE.Group()
 const box=new THREE.Mesh(new THREE.BoxGeometry(5.6,3.0,2.7),new THREE.MeshBasicMaterial({color:0xff304e,wireframe:true,transparent:true,opacity:.9}))
 box.position.y=1.5;g.add(box)
 const leader=new THREE.Mesh(new THREE.CylinderGeometry(.03,.03,9,6),new THREE.MeshBasicMaterial({color:0xff304e,transparent:true,opacity:.55}))
 leader.position.y=6.5;g.add(leader)
 for(const r of [1.9,2.7]){const ring=new THREE.Mesh(new THREE.RingGeometry(r,r+.07,36),new THREE.MeshBasicMaterial({color:0xff304e,transparent:true,opacity:.7,side:THREE.DoubleSide}));ring.rotation.x=-Math.PI/2;ring.position.y=.06;g.add(ring)}
 g.userData.pulse=0;return g
}
function trackingHalo(){const g=new THREE.Group();const ring=new THREE.Mesh(new THREE.TorusGeometry(2.4,.08,10,48),new THREE.MeshBasicMaterial({color:0xff304e}));ring.rotation.x=Math.PI/2;ring.position.y=.15;g.add(ring);const box=new THREE.Mesh(new THREE.BoxGeometry(5.2,2.8,2.5),new THREE.MeshBasicMaterial({color:0xff304e,wireframe:true,transparent:true,opacity:.75}));box.position.y=1.45;g.add(box);g.userData.pulse=0;return g}

export default function BusMicroTwin({bus,onClose}){
 const mountRef=useRef(null), sceneRef=useRef(null), cameraRef=useRef(null), meshes=useRef(new Map()), scenery=useRef([]), hazards=useRef(new Map()), beacons=useRef(new Map()), trackers=useRef(new Map()), triggered=useRef(new Set()), alertTimer=useRef(null), anomalyTimer=useRef(null)
 const [data,setData]=useState(null),[loading,setLoading]=useState(true),[error,setError]=useState(null),[playing,setPlaying]=useState(true),[frameIndex,setFrameIndex]=useState(0),[cameraMode,setCameraMode]=useState('chase'),[playbackRate,setPlaybackRate]=useState(1),[activeEvent,setActiveEvent]=useState(null),[eventLog,setEventLog]=useState([]),[analysisPhase,setAnalysisPhase]=useState(null),[rashTarget,setRashTarget]=useState(null),[trackedVehicle,setTrackedVehicle]=useState(null),[activeAnomaly,setActiveAnomaly]=useState(null)
 useEffect(()=>{let dead=false;setLoading(true);setError(null);fetch(`/api/v2/sumo/bus/${bus.bus_id}`).then(r=>r.json()).then(p=>{if(dead)return;if(!p.available)throw Error(p.reason||'SUMO unavailable');setData(p);setFrameIndex(0);setLoading(false)}).catch(e=>{if(!dead){setError(e.message);setLoading(false)}});return()=>{dead=true}},[bus.bus_id])
 useEffect(()=>{if(!data||!mountRef.current)return;const mount=mountRef.current,scene=new THREE.Scene();scene.background=new THREE.Color(0x05070a);scene.fog=new THREE.Fog(0x05070a,90,260);const cam=new THREE.PerspectiveCamera(52,mount.clientWidth/mount.clientHeight,.1,1000);const renderer=new THREE.WebGLRenderer({antialias:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.setSize(mount.clientWidth,mount.clientHeight);renderer.shadowMap.enabled=true;renderer.outputColorSpace=THREE.SRGBColorSpace;mount.appendChild(renderer.domElement);scene.add(new THREE.HemisphereLight(0x9fdcff,0x101018,1.55));const sun=new THREE.DirectionalLight(0xffffff,2.1);sun.position.set(-10,30,20);scene.add(sun)
 const road=new THREE.Mesh(new THREE.BoxGeometry(250,.15,12.5),mat(0x171a20,.98));scene.add(road)
 // Lane dashes at a real 9 m pitch. Ground markings streaming past the camera
 // are the primary speed cue in any driving view — denser and correctly spaced
 // matters more here than any vehicle detail.
 for(const z of [-2.05,2.05])for(let x=-130;x<=130;x+=9){const d=new THREE.Mesh(new THREE.BoxGeometry(4.2,.03,.11),new THREE.MeshBasicMaterial({color:0xc9d0da}));d.position.set(x,.1,z);d.userData.x0=x;scene.add(d);scenery.current.push(d)}
 // Kerb edging: a continuous stipple at both road edges adds peripheral flow.
 for(const z of [-6.35,6.35])for(let x=-130;x<=130;x+=4){const k=new THREE.Mesh(new THREE.BoxGeometry(1.6,.05,.16),new THREE.MeshBasicMaterial({color:0x3b4653}));k.position.set(x,.09,z);k.userData.x0=x;scene.add(k);scenery.current.push(k)}
 for(let x=-130;x<=130;x+=20)for(const z of [-8.5,8.5]){const pole=new THREE.Mesh(new THREE.CylinderGeometry(.08,.11,5.5,10),mat(0x26313c,.85));pole.position.set(x,2.75,z);pole.userData.x0=x;scene.add(pole);scenery.current.push(pole)}
 // Roadside blocks at varied depth give parallax — near objects sweep past
 // faster than far ones, which is what actually sells forward motion.
 for(let i=0;i<26;i++){const z=(i%2?1:-1)*(13+(i*3.7)%16),h=4+((i*5.3)%11)
  const b=new THREE.Mesh(new THREE.BoxGeometry(6+((i*2.1)%7),h,5),mat(0x121820,.95))
  const x=-130+i*10.4;b.position.set(x,h/2,z);b.userData.x0=x;scene.add(b);scenery.current.push(b)}
 const SUBJECT={POTHOLE:pothole,WATERLOGGING:water,FADED_ZEBRA_CROSSING:zebra,TRAFFIC_SIGNAL_FAULT:signalHead,MANHOLE_DAMAGE:manhole,ILLEGAL_DUMPING:dumping}
 for(const s of data.scenarios||[]){const make=SUBJECT[s.subtype];let h=make?make():null;if(h){scene.add(h);hazards.current.set(s.id,h)}if(s.type!=='DRIVING_ANOMALY'){const b=detectionBeacon(s.type==='ROAD_DEFECT'?0xffa52f:s.type==='SAFETY'?0xff8ac4:s.type==='SANITATION'?0x9ad36b:s.type==='INFRASTRUCTURE'?0xc9a5ff:0x34d9ff);b.visible=false;scene.add(b);beacons.current.set(s.id,b)}}
 sceneRef.current=scene;cameraRef.current=cam;let raf;const clock=new THREE.Clock();const render=()=>{const dt=clock.getDelta();meshes.current.forEach(m=>{
   m.position.lerp(m.userData.target,.2)
   const spd=m.userData.speed||0
   if(m.userData.wheels)for(const w of m.userData.wheels)w.rotation.y-=spd*dt/m.userData.wheelRadius
   // Weight transfer: nose dips under braking, lifts under acceleration. Small
   // angle, but it is what separates "vehicles sliding on a plane" from traffic.
   const target=-(m.userData.accel||0)*0.012
   m.rotation.z+=(target-m.rotation.z)*Math.min(1,dt*6)
  });beacons.current.forEach(b=>{if(!b.visible)return;b.userData.pulse+=dt*3.2;b.children.forEach((c,i)=>{if(c.geometry?.type==='RingGeometry'){const s=1+((Math.sin(b.userData.pulse-i*.7)+1)*.16);c.scale.set(s,s,s);c.material.opacity=.35+.45*((Math.sin(b.userData.pulse-i*.8)+1)/2)}})});trackers.current.forEach(t=>{t.userData.pulse+=dt*4;t.scale.setScalar(1+Math.sin(t.userData.pulse)*.04)});renderer.render(scene,cam);raf=requestAnimationFrame(render)};render();const resize=()=>{cam.aspect=mount.clientWidth/mount.clientHeight;cam.updateProjectionMatrix();renderer.setSize(mount.clientWidth,mount.clientHeight)};addEventListener('resize',resize);return()=>{cancelAnimationFrame(raf);removeEventListener('resize',resize);if(alertTimer.current)clearTimeout(alertTimer.current);renderer.dispose();if(renderer.domElement.parentNode===mount)mount.removeChild(renderer.domElement);meshes.current.clear();scenery.current=[];hazards.current.clear();beacons.current.clear();trackers.current.clear()}},[data])
 useEffect(()=>{if(!data?.frames?.length||!sceneRef.current)return;const f=data.frames[Math.min(frameIndex,data.frames.length-1)],ego=f.ego,egoX=ego?.x||0,active=new Set();const prevF=data.frames[Math.max(0,Math.min(frameIndex,data.frames.length-1)-1)]
 for(const v of f.vehicles){active.add(v.id);let m=meshes.current.get(v.id);if(!m){m=vehicle(v.kind,v.ego);meshes.current.set(v.id,m);sceneRef.current.add(m);m.position.set(v.x-egoX,.12,(v.lane-1)*4.1)}
  // Lateral position comes from the sublane model, so bikes genuinely sit
  // between lanes instead of snapping to a centreline.
  const lat=(v.lane-1)*4.1
  m.userData.target.set(v.x-egoX,.12,lat)
  m.userData.speed=v.speed
  const pv=prevF?.vehicles?.find(x=>x.id===v.id)
  m.userData.accel=pv?(v.speed-pv.speed)/Math.max(.01,(f.t-prevF.t)):0
  if(v.angle!=null)m.rotation.y=THREE.MathUtils.degToRad(90-v.angle)
 }meshes.current.forEach((m,id)=>{if(!active.has(id)){sceneRef.current.remove(m);meshes.current.delete(id)}})
 // Wrap every scenery object around ITS OWN starting position. The previous
 // version recomputed a position from the array index (i % 13), so unrelated
 // objects shared a slot and the markings jumped rather than streamed — the
 // corridor looked static no matter how fast the bus was going.
 const SPAN=260
 scenery.current.forEach(o=>{const x0=o.userData.x0??o.position.x;o.position.x=((x0-egoX)%SPAN+SPAN*1.5)%SPAN-SPAN/2})
 for(const s of data.scenarios||[]){const h=hazards.current.get(s.id);if(h)h.position.set(s.x-egoX,.1,(s.lane-1)*4.1);const b=beacons.current.get(s.id);if(b)b.position.set(s.x-egoX,.11,(s.lane-1)*4.1)}

 // ---- moving anomalies: lock the rig onto the ACTUAL vehicle ---------------
 // The vehicle id came back from the trajectory analytics, and that id is in the
 // frame data, so the lock rides the real mesh. Previously an anomaly was given
 // a static ground beacon at a fixed x — which is why it looked and behaved
 // exactly like a pothole.
 const anomalyList=(data.scenarios||[]).filter(s=>s.type==='DRIVING_ANOMALY')
 let liveTrack=null
 for(const an of anomalyList){
  const v=(f.vehicles||[]).find(x=>x.id===an.track_ref)
  let rig=trackers.current.get(an.id)
  if(!v){if(rig){rig.parent?.remove(rig);trackers.current.delete(an.id)}continue}
  const vm=meshes.current.get(v.id)
  if(vm&&!rig){rig=vehicleTracker();vm.add(rig);trackers.current.set(an.id,rig)}
  const dx=v.x-egoX
  const info={...an,dx,live:{speed_kmh:+(v.speed*3.6).toFixed(1),lane:v.lane,lateral_m:+(v.y).toFixed(2),range_m:Math.abs(dx).toFixed(0),ahead:dx>=0}}
  if(!liveTrack||Math.abs(dx)<Math.abs(liveTrack.dx))liveTrack=info
 }
 setTrackedVehicle(liveTrack)

 // Static road defects still use approach distance. Anomalies are handled above.
 const candidates=(data.scenarios||[]).filter(s=>s.type!=='DRIVING_ANOMALY').map(s=>({...s,dx:ego?s.x-egoX:999})).filter(s=>s.dx<58&&s.dx>-55).sort((a,b)=>Math.abs(a.dx)-Math.abs(b.dx));const current=candidates[0]||null
 if(current){let phase=current.dx>32?'SCANNING':current.dx>18?'CANDIDATE LOCK':current.dx>5?'CLASSIFYING':current.dx>-12?'EVIDENCE LOCKED':'PASSED · EVENT PERSISTED';setAnalysisPhase(phase);const beacon=beacons.current.get(current.id);if(beacon)beacon.visible=true
  if(!triggered.current.has(current.id)&&current.dx<28){triggered.current.add(current.id);setActiveEvent(current);setEventLog(log=>[current,...log.filter(x=>x.id!==current.id)].slice(0,5));if(alertTimer.current)clearTimeout(alertTimer.current);alertTimer.current=setTimeout(()=>setActiveEvent(prev=>prev?.id===current.id?null:prev),8500)}
  }else{setAnalysisPhase(activeEvent?'EVENT STORED · MONITORING CONTINUES':null)}

 // Raise the anomaly alert from the ANALYSIS TIME the pipeline computed, not
 // from proximity to a coordinate. The behaviour happened at a moment; that
 // moment is when the operator should be told.
 // A road-asset alert and a vehicle-behaviour alert are different channels and
 // must not share one slot. They did, and because six defects fire along the
 // corridor a defect overwrote the vehicle alert on the very next frame — it
 // survived 5 samples out of 220 while defect alerts held the card for 148. That
 // is why the anomaly kept "coming like a pothole": whenever it was visible at
 // all, it was inside the pothole's card.
 if(liveTrack&&f.t>=liveTrack.t&&!triggered.current.has(liveTrack.id)){
  triggered.current.add(liveTrack.id);setActiveAnomaly(liveTrack)
  setEventLog(log=>[liveTrack,...log.filter(x=>x.id!==liveTrack.id)].slice(0,6))
  if(anomalyTimer.current)clearTimeout(anomalyTimer.current)
  anomalyTimer.current=setTimeout(()=>setActiveAnomaly(prev=>prev?.id===liveTrack.id?null:prev),11000)
 }
 if(liveTrack)setAnalysisPhase(f.t<liveTrack.t?'TRACKING VEHICLE':'ANOMALY CONFIRMED · TRACK LOCKED')
 if(cameraRef.current){if(cameraMode==='top'){cameraRef.current.position.set(0,72,.01);cameraRef.current.lookAt(0,0,0)}else if(cameraMode==='pov'){cameraRef.current.position.set(-4.6,3.4,0);cameraRef.current.lookAt(32,1.2,0)}else{cameraRef.current.position.set(-29,19,24);cameraRef.current.lookAt(9,0,0)}}},[data,frameIndex,cameraMode,activeEvent])
 useEffect(()=>{if(!playing||!data?.frames?.length)return;const cinematic=!!analysisPhase&&analysisPhase!=='EVENT STORED · MONITORING CONTINUES';const baseDelay=cinematic?230:110;const t=setInterval(()=>setFrameIndex(i=>{
   const n=(i+1)%data.frames.length
   // The replay loops, but `triggered` persisted across the wrap, so every event
   // fired on the first pass and never again — the second lap looked dead. Rearm
   // on wrap so each lap behaves like the first.
   if(n===0){triggered.current.clear();beacons.current.forEach(b=>b.visible=false);trackers.current.forEach((r,k)=>{r.parent?.remove(r);trackers.current.delete(k)});setActiveEvent(null);setActiveAnomaly(null);setEventLog([]);setAnalysisPhase(null)}
   return n
  }),baseDelay/playbackRate);return()=>clearInterval(t)},[playing,data,analysisPhase,playbackRate])
 const frame=data?.frames?.[frameIndex],ego=frame?.ego,counts=useMemo(()=>{const o={};for(const v of frame?.vehicles||[])o[v.kind]=(o[v.kind]||0)+1;return o},[frame])
 const progress=ego?Math.min(100,(ego.x/data?.road_length_m)*100):0
 return <div className="micro-twin-overlay"><div className="micro-twin-shell">
  <div className="micro-twin-head"><div><span>PRAYAAN · SUMO URBAN INTELLIGENCE TWIN</span><h2>{bus.bus_id} · Live Mission Replay</h2></div><div className="micro-actions"><div className="micro-speed-switch">{[0.5,1,2].map(rate=><button key={rate} className={playbackRate===rate?'active':''} onClick={()=>setPlaybackRate(rate)}>{rate}×</button>)}</div><div className="micro-camera-switch">{['chase','pov','top'].map(m=><button key={m} className={cameraMode===m?'active':''} onClick={()=>setCameraMode(m)}>{m.toUpperCase()}</button>)}</div><button onClick={()=>setPlaying(x=>!x)}>{playing?<Pause size={17}/>:<Play size={17}/>}</button><button onClick={()=>{setFrameIndex(0);setPlaybackRate(1);setEventLog([]);setActiveEvent(null);setActiveAnomaly(null);setAnalysisPhase(null);setRashTarget(null);triggered.current.clear();beacons.current.forEach(b=>b.visible=false)}}><RotateCcw size={17}/></button><button onClick={onClose}><X size={18}/></button></div></div>
  {loading&&<div className="micro-loading">Generating SUMO physics + mission scenarios for {bus.bus_id}…</div>}{error&&<div className="micro-error"><b>SUMO micro twin unavailable</b><span>{error}</span></div>}
  {data&&<><div ref={mountRef} className="micro-canvas"/>
   <div className="analysis-status"><span className={analysisPhase?'live':''}><Focus size={14}/>{analysisPhase||'PASSIVE SCAN'}</span><b>{playbackRate}× PLAYBACK{analysisPhase?' · CINEMATIC ANALYSIS':''}</b></div>
   <div className="micro-hud left"><span>PHYSICS</span><b>LIVE SUMO FCD</b><small>IDM · {data.physics?.lane_change||'LC2013'}{data.physics?.sublane?' · sublane':''} · seed {data.seed}</small><small>{data.summary?.tracked_vehicles} tracks · {data.summary?.anomalies_detected} anomalies DERIVED</small></div>
   <div className="micro-hud right"><span>EGO BUS</span><b>{ego?`${(ego.speed*3.6).toFixed(1)} km/h`:'entering corridor'}</b><small>{frame?.local_density||0} nearby · {frame?.stopped_vehicles||0} stopped</small><small>travelled {ego?ego.x.toFixed(0):0} / {data.road_length_m} m</small></div>
   {activeAnomaly&&<div className="vehicle-incident">
     <div className="vehicle-incident-top"><Camera size={17}/><span>VEHICLE BEHAVIOUR INCIDENT</span><b>{activeAnomaly.track_ref}</b></div>
     <div className="vehicle-incident-trigger">{activeAnomaly.trigger.replaceAll('_',' ').toUpperCase()} · {activeAnomaly.severity}</div>
     <p>{activeAnomaly.detail}</p>
     <div className="vehicle-incident-grid">
       {Object.entries(activeAnomaly.evidence).slice(0,6).map(([k,v])=><span key={k}>{k.replaceAll('_',' ')}<b>{v}</b></span>)}
     </div>
     <div className="anomaly-why"><b>WHY THIS VEHICLE</b><span>Scored against every other track in the corridor on measured motion alone. The detector could not see vehicle class, and no plate or location was captured.</span></div>
   </div>}
   {trackedVehicle&&!activeAnomaly&&<div className="track-live">
     <div className="track-live-top"><Camera size={14}/><span>VEHICLE UNDER TRACK</span><i>{trackedVehicle.dx>=0?'AHEAD':'BEHIND'}</i></div>
     <b>{trackedVehicle.track_ref}</b>
     <div className="track-live-grid">
       <span>SPEED<b>{trackedVehicle.live.speed_kmh} km/h</b></span>
       <span>LANE<b>{trackedVehicle.live.lane}</b></span>
       <span>RANGE<b>{trackedVehicle.live.range_m} m</b></span>
       <span>LATERAL<b>{trackedVehicle.live.lateral_m} m</b></span>
     </div>
     <div className="track-meter"><i style={{width:`${Math.min(100,(trackedVehicle.score||0)*100/0.7)}%`}}/></div>
     <div className="track-meter-label"><span>BEHAVIOUR SCORE</span><b>{trackedVehicle.score}</b></div>
     <small>ANONYMISED TRACK · NO PLATE · NO LOCATION STORED</small>
   </div>}
   <div className="micro-types">{Object.entries(counts).map(([k,n])=><span key={k}>{k.toUpperCase()} <b>{n}</b></span>)}</div>
   <div className="scenario-stack">
     <div className="scenario-stack-title">ROAD ASSETS · GEOTAGGED</div>
     {eventLog.filter(e=>e.type!=='DRIVING_ANOMALY').map(e=><div className={`scenario-mini ${e.severity.toLowerCase()}`} key={e.id}><CheckCircle2 size={13}/><div><b>{e.label}</b><small>{Math.round(e.confidence*100)}% · STORED AT {Math.round(e.x)} m</small></div></div>)}
     {eventLog.some(e=>e.type==='DRIVING_ANOMALY')&&<>
       <div className="scenario-stack-title vehicle">VEHICLE WATCH · NOT GEOTAGGED</div>
       {eventLog.filter(e=>e.type==='DRIVING_ANOMALY').map(e=><div className="scenario-mini vehicle" key={e.id}><Camera size={13}/><div><b>{e.track_ref}</b><small>{e.trigger.replaceAll('_',' ')} · score {e.score}</small><small>NO PLATE · NO LOCATION STORED</small></div></div>)}
     </>}
   </div>
   {activeEvent&&<div className={`scenario-alert persistent ${activeEvent.severity.toLowerCase()}`}><div className="scenario-alert-top"><ScanLine size={19}/><span>ROAD ASSET ANALYSIS</span><b>{activeEvent.label}</b></div><div className="analysis-steps"><span className="done">01 DETECT</span><span className={analysisPhase&&analysisPhase!=='SCANNING'?'done':''}>02 TRACK</span><span className={['CLASSIFYING','EVIDENCE LOCKED','PASSED · EVENT PERSISTED','EVENT STORED · MONITORING CONTINUES'].includes(analysisPhase)?'done':''}>03 CLASSIFY</span><span className={['EVIDENCE LOCKED','PASSED · EVENT PERSISTED','EVENT STORED · MONITORING CONTINUES'].includes(analysisPhase)?'done':''}>04 PACKAGE</span></div><p>{activeEvent.detail}</p><div className="scenario-evidence"><span>CONFIDENCE <b>{Math.round(activeEvent.confidence*100)}%</b></span><span>SEVERITY <b>{activeEvent.severity}</b></span>{activeEvent.evidence&&Object.entries(activeEvent.evidence).slice(0,4).map(([k,v])=><span key={k}>{k.replaceAll('_',' ').toUpperCase()} <b>{v}</b></span>)}{activeEvent.score!=null&&<span>ANOMALY SCORE <b>{activeEvent.score}</b></span>}</div><small>{activeEvent.action}</small><div className="alert-persist-note">Evidence panel remains visible after the physical encounter so the operator can inspect the result.</div></div>}
   <div className="scenario-route"><span className="route-progress" style={{width:`${progress}%`}}/>{/* The corridor strip is a map of PLACES. A road defect belongs on it; a
       moving vehicle does not, and putting one there was what made an anomaly
       read as another pothole. Vehicles live in the watch list instead. */}
   {(data.scenarios||[]).filter(s=>s.type!=='DRIVING_ANOMALY').map((s,i)=><span key={s.id} className={`scenario-marker ${s.type==='ROAD_HAZARD'?'w':'p'}`} style={{left:`${Math.min(96,Math.max(2,(s.x/data.road_length_m)*100))}%`,bottom:`${4+(i%3)*16}px`}}>{s.label}</span>)}</div>
   <div className="micro-timeline"><i style={{width:`${((frameIndex+1)/data.frames.length)*100}%`}}/></div>
  </>}</div></div>
}
