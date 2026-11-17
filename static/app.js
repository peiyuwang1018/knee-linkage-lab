'use strict';
const $=id=>document.getElementById(id),NS='http://www.w3.org/2000/svg';
let defaults,config,result,scanResult,scanRequest,frame=0,playing=false,playTime=0,lastTick=0,pending=0,seq=0,bounds,chartMap;
const dash=['','7 4','2 3'];
// Stable visual identities. This display preference never enters the solver.
const palette={R1:'#3F82AD',R2:'#BD7952',R3:'#4D9478',thigh:'#B3973F',shank:'#9672AC',input:'#547F9C',knee:'#9672AC',ground:'#568B7B'};
let colorMode='muted';
const selectedRods=new Set(),contextOpacity=.55;
let motionDirection=1;
const defaultAnalysis=()=>({plotMode:'oneway',mirror:false,ratedTorque:55,ratio:1,efficiency:100});
let analysis=defaultAnalysis();
function restoreAnalysis(value={}){
 const next=defaultAnalysis();
 if(value&&typeof value==='object'){
  if(['oneway','roundtrip'].includes(value.plotMode))next.plotMode=value.plotMode;
  next.mirror=value.mirror===true;
  for(const key of ['ratedTorque','ratio','efficiency'])if(typeof value[key]==='number'&&Number.isFinite(value[key])&&value[key]>=(key==='ratedTorque'?0:.01)&&(key!=='efficiency'||value[key]<=100))next[key]=value[key];
 }
 return next;
}
try{analysis=restoreAnalysis(JSON.parse(localStorage.getItem('kneelab-analysis-v1')));}catch{}
function saveAnalysis(){try{localStorage.setItem('kneelab-analysis-v1',JSON.stringify(analysis));}catch{}}
function syncAnalysisControls(){
 const group=$('cycleModeSwitch');
 group.querySelectorAll('button').forEach((button,i)=>{const active=button.dataset.value===analysis.plotMode;button.setAttribute('aria-checked',String(active));button.tabIndex=active?0:-1;if(active)group.style.setProperty('--selected-index',i);});
 for(const key of ['ratedTorque','ratio','efficiency'])$(key).value=analysis[key];
}
try{if(localStorage.getItem('kneelab-color-mode')==='mono')colorMode='mono';}catch{}
function colorFor(key){return colorMode==='mono'?'#333333':(palette[key]||'#547F9C');}
function ink(key,attribute='stroke'){return {'data-color-key':key,style:`${attribute}:${colorFor(key)}`};}
function mechanismLegend(svg,w,h){
 const items=[{key:'thigh',name:'Thigh'},{key:'shank',name:'Shank'}];
 const columns=Math.max(1,Math.floor((w-50)/68)),rows=Math.ceil(items.length/columns),top=h-13-14*(rows-1);
 items.forEach((item,i)=>{const x=25+(i%columns)*68,y=top+Math.floor(i/columns)*14;line(svg,[x,y-3],[x+19,y-3],{...ink(item.key),'stroke-width':1.8,'stroke-dasharray':item.pattern||''});text(svg,[x+23,y],item.name,{'font-size':10});});
 return top-13;
}
const fields={
 geometry:[['n','Rod groups','',1,3,1,[1,2,3]],['spacing_deg','Phase spacing α','deg',1,179,1],['center_mm','Axis distance d','mm',50,1000,5],['input_radius_mm','Input radius rᵢ','mm',2,200,1],['output_radius_mm','Output radius rₒ','mm',2,200,1],['rod_mm','Coupler length L','mm',10,1500,5],['shank_mm','Shank length s','mm',50,1000,5],['clocking_deg','Output clocking δ','deg',-360,360,1],['branch','Assembly','',0,0,0,['open','crossed']]],
 motion:[['q_start_deg','Start knee angle','deg',-175,175,1],['q_end_deg','End knee angle','deg',-175,175,1],['half_cycle_s','One-way duration','s',.1,30,.1],['dead_center_tol_deg','Dead-center margin','deg',.1,30,.5]],
 load:[['mass_kg','Total robot mass','kg',.1,1000,1],['share','This leg share','',.01,1,.05],['load_mode','Load model','',0,0,0,['constant','trajectory']],['load_factor','Load factor κ','',.01,5,.1]],
 stiffness:[['stiffness_n_mm','Rod 1 stiffness k₁','N/mm',1,1e7,1000],['k2_ratio','Rod 2 / rod 1','',.01,100,.1],['k3_ratio','Rod 3 / rod 1','',.01,100,.1]],
 numeric:[['samples','Cycle samples','',21,1001,20]]
};
const labels={n:'Rod groups',input_radius_mm:'Radius r',spacing_deg:'Spacing α',center_mm:'Axis distance d',shank_mm:'Shank s',clocking_deg:'Clocking δ',max_rod_n:'Rod load',max_input_nm:'Input torque',max_speed_rad_s:'Input speed',max_twist_deg:'Elastic twist',min_top_height_mm:'Min. top height',max_bottom_height_mm:'Max. low height'};
function el(tag,attrs={},text){const n=document.createElementNS(NS,tag);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,v));if(text!==undefined)n.textContent=text;return n;}
function line(svg,a,b,attrs={}){svg.append(el('line',{x1:a[0],y1:a[1],x2:b[0],y2:b[1],...attrs}));}
function text(svg,p,value,attrs={}){svg.append(el('text',{x:p[0],y:p[1],...attrs},value));}
function fmt(v,d=1){return v==null?'—':Number(v).toFixed(d);}
function notice(message){$('notice').textContent=message;$('notice').hidden=!message;}
const api=(path,body)=>KneeRuntime.request(path,body);
function buildFields(){
 for(const [section,definitions] of Object.entries(fields)){
  const container=$(section+'Fields');
  for(const [key,label,unit,min,max,step,options] of definitions){
   const row=document.createElement('div');row.className='field';
   const lab=document.createElement('label');lab.htmlFor=key;lab.textContent=label;
   if(key==='n'){
    const hidden=document.createElement('input');hidden.type='hidden';hidden.id=key;
    const group=document.createElement('div');group.id='rodCount';group.className='count-segments';group.setAttribute('role','radiogroup');group.setAttribute('aria-label','Rod groups');
    for(let count=1;count<=3;count++){
     const button=document.createElement('button');button.type='button';button.textContent=count;button.dataset.count=count;button.setAttribute('role','radio');button.setAttribute('aria-label',`${count} rod group${count===1?'':'s'}`);
     button.onclick=()=>{stop();config.n=count;normalize();queueSolve();};
     button.onkeydown=e=>{if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End'].includes(e.key))return;e.preventDefault();const next=e.key==='Home'?1:e.key==='End'?3:Math.max(1,Math.min(3,count+(['ArrowRight','ArrowDown'].includes(e.key)?1:-1)));group.querySelector(`[data-count="${next}"]`).click();group.querySelector(`[data-count="${next}"]`).focus();};
     group.append(button);
    }
    lab.removeAttribute('for');row.append(lab,hidden,group);container.append(row);continue;
   }
   const input=document.createElement(options?'select':'input');input.id=key;
   if(options){for(const v of options){const op=document.createElement('option');op.value=v;op.textContent=key==='load_mode'?({constant:'Constant κ',trajectory:'COM trajectory'}[v]):v;input.append(op);}}
   else{input.type='number';input.min=min;input.max=max;input.step=step;}
   const read=()=>options&&typeof options[0]==='string'?input.value:Number(input.value);
   input.addEventListener('input',()=>{++seq;clearTimeout(pending);stop();if(input.value==='')return;config[key]=read();if(key==='q_start_deg'||key==='q_end_deg')syncAngleRange(false);syncGeometrySliders();queueSolve();});
   input.addEventListener('change',()=>{config[key]=read();normalize();queueSolve();});
   const u=document.createElement('span');u.className='unit';u.textContent=unit;row.append(lab,input,u);container.append(row);
   if(key==='spacing_deg'||key==='clocking_deg'){
    const strip=document.createElement('div');strip.className='parameter-slider';
    strip.innerHTML=`<input type="range" id="${key}Slider" min="${min}" max="${max}" step="${step}" aria-label="${label} slider"><div class="angle-scale"><span data-min></span><span data-max></span></div>`;
    strip.querySelector('input').oninput=e=>{stop();config[key]=Number(e.target.value);input.value=config[key];syncGeometrySliders();queueSolve();};
    container.append(strip);
   }
  }
 }
 buildAngleRange();
}
function syncGeometrySliders(){
 for(const key of ['spacing_deg','clocking_deg']){
  const slider=$(key+'Slider');if(!slider)continue;
  const min=key==='spacing_deg'?(config.n===3?60:1):-360,max=key==='spacing_deg'?(config.n===3?120:179):360;
  slider.min=min;slider.max=max;slider.value=config[key];slider.disabled=key==='spacing_deg'&&config.n===1;
  slider.setAttribute('aria-valuetext',`${config[key]} degrees`);
  slider.parentElement.querySelector('[data-min]').textContent=min+'°';slider.parentElement.querySelector('[data-max]').textContent=max+'°';
 }
}
function buildAngleRange(){
 const node=document.createElement('div');node.className='angle-range';
 node.innerHTML='<div class="angle-range-heading"><span>Knee angle range</span><output id="angleRangeValue"></output></div><div id="angleTrack" class="angle-track"><div class="angle-track-base"></div><div id="angleRangeFill" class="angle-track-fill"></div><i class="angle-zero" aria-hidden="true"></i><input id="angleLower" type="range" min="-175" max="175" step="1" aria-label="Lower knee angle"><input id="angleUpper" type="range" min="-175" max="175" step="1" aria-label="Upper knee angle"></div><div class="angle-scale"><span>−175°</span><span>0°</span><span>175°</span></div>';
 $('motionFields').prepend(node);
 const mirror=document.createElement('button');mirror.type='button';mirror.id='mirrorAngles';mirror.textContent='Mirror about 0°';mirror.setAttribute('aria-pressed','false');
 mirror.onclick=()=>{stop();analysis.mirror=!analysis.mirror;if(analysis.mirror)applyMirror(Math.max(Math.abs(config.q_start_deg),Math.abs(config.q_end_deg)));syncAngleRange();saveAnalysis();queueSolve();};
 const mirrorBar=document.createElement('div');mirrorBar.className='mirror-bar';mirrorBar.append(mirror);node.append(mirrorBar);
 const amplitude=document.createElement('div');amplitude.className='field';amplitude.id='mirrorAmplitudeField';
 amplitude.innerHTML='<label for="mirrorAmplitude">Half-range θ</label><input id="mirrorAmplitude" type="number" min="0" max="175" step="1"><span class="unit">deg</span>';
 node.after(amplitude);
 $('mirrorAmplitude').oninput=()=>{const input=$('mirrorAmplitude');if(input.value===''||!input.checkValidity())return;stop();applyMirror(Number(input.value));syncAngleRange();queueSolve();};
 for(const bound of ['Lower','Upper'])$('angle'+bound).addEventListener('input',()=>setAngleBound(bound,Number($('angle'+bound).value)));
 // Track clicks move the nearest handle; native handles retain keyboard/drag support.
 let activeBound=null;
 const track=$('angleTrack');
 const angleAt=e=>{const r=track.getBoundingClientRect();return Math.round(Math.max(-175,Math.min(175,-175+(e.clientX-r.left-7)/(r.width-14)*350)));};
 track.onpointerdown=e=>{if(e.button!==0||e.target.tagName==='INPUT')return;const angle=angleAt(e),lo=Math.min(config.q_start_deg,config.q_end_deg),hi=Math.max(config.q_start_deg,config.q_end_deg);activeBound=Math.abs(angle-lo)<Math.abs(angle-hi)?'Lower':'Upper';track.setPointerCapture(e.pointerId);$('angle'+activeBound).focus();setAngleBound(activeBound,angle);};
 track.onpointermove=e=>{if(activeBound&&track.hasPointerCapture(e.pointerId))setAngleBound(activeBound,angleAt(e));};
 track.onpointerup=track.onpointercancel=e=>{if(track.hasPointerCapture(e.pointerId))track.releasePointerCapture(e.pointerId);activeBound=null;};
}
function applyMirror(amplitude){const a=Math.max(0,Math.min(175,amplitude));config.q_start_deg=-motionDirection*a;config.q_end_deg=motionDirection*a;}
function setAngleBound(bound,value){
 if(analysis.mirror){stop();applyMirror(Math.abs(bound==='Lower'?Math.min(0,value):Math.max(0,value)));syncAngleRange();queueSolve();return;}
 const lo=Math.min(config.q_start_deg,config.q_end_deg),hi=Math.max(config.q_start_deg,config.q_end_deg);
 const lower=bound==='Lower';value=Math.max(-175,Math.min(175,lower?Math.min(value,hi):Math.max(value,lo)));
 const key=(lower===(motionDirection>0))?'q_start_deg':'q_end_deg';
 stop();config[key]=value;syncAngleRange();queueSolve();
}
function syncAngleRange(syncInputs=true){
 if(!$('angleLower'))return;
 const start=config.q_start_deg,end=config.q_end_deg;
 if(!Number.isFinite(start)||!Number.isFinite(end))return;
 if(start!==end)motionDirection=end>start?1:-1;
 $('mirrorAngles').setAttribute('aria-pressed',String(analysis.mirror));
 $('mirrorAmplitudeField').hidden=!analysis.mirror;
 $('mirrorAmplitude').value=Math.max(Math.abs(start),Math.abs(end));
 for(const id of ['q_start_deg','q_end_deg'])$(id).closest('.field').hidden=analysis.mirror;
 const lo=Math.min(start,end),hi=Math.max(start,end),left=(lo+175)/350*100,right=(hi+175)/350*100;
 $('angleLower').value=lo;$('angleUpper').value=hi;
 $('angleLower').setAttribute('aria-valuetext',`${lo} degrees`);$('angleUpper').setAttribute('aria-valuetext',`${hi} degrees`);
 $('angleLower').title=`Lower: ${lo}°`;$('angleUpper').title=`Upper: ${hi}°`;
 $('angleRangeValue').textContent=`${lo}° … ${hi}°`;
 $('angleRangeFill').style.left=`calc(7px + (100% - 14px) * ${left/100})`;
 $('angleRangeFill').style.width=`calc((100% - 14px) * ${(right-left)/100})`;
 $('angleLower').style.zIndex=lo===hi&&hi===175?'4':'';
 if(syncInputs){$('q_start_deg').value=start;$('q_end_deg').value=end;}
}
function syncParameterControls(){
 for(const b of $('rodCount').querySelectorAll('button')){const count=Number(b.dataset.count);b.classList.toggle('lit',count<=config.n);b.setAttribute('aria-checked',String(count===config.n));b.tabIndex=count===config.n?0:-1;}
 if(analysis.mirror&&Math.abs(config.q_start_deg+config.q_end_deg)>1e-8){analysis.mirror=false;saveAnalysis();}
 syncAngleRange();syncGeometrySliders();
}
function normalize(){$('preset').value='custom';if(config.n>1){config.output_radius_mm=config.input_radius_mm;config.rod_mm=config.center_mm;config.branch='open';}if(config.n===3)config.spacing_deg=Math.max(60,Math.min(120,config.spacing_deg));for(const defs of Object.values(fields))for(const [k] of defs)$(k).value=config[k];$('spacing_deg').disabled=config.n===1;$('spacing_deg').min=config.n===3?60:1;$('spacing_deg').max=config.n===3?120:179;$('dead_center_tol_deg').disabled=config.n!==1;$('output_radius_mm').disabled=config.n>1;$('rod_mm').disabled=config.n>1;$('branch').disabled=config.n>1;$('load_factor').disabled=config.load_mode!=='constant';$('k2_ratio').disabled=config.n<2;$('k3_ratio').disabled=config.n<3;$('geometryHint').textContent=config.n>1?`Linked geometry: L = d, rₒ = rᵢ. ${`Phases: ${Array.from({length:config.n},(_,i)=>fmt(i*config.spacing_deg,1)+'°').join(', ')}.`} Angle ratio = 1:1.`:'Single four-bar. Open / crossed selects the initial assembly branch.';syncParameterControls();syncRodSelection();}
function queueSolve(){++seq;clearTimeout(pending);$('status').textContent='Updating model…';pending=setTimeout(solve,120);}
async function solve(){const id=++seq;stop();$('status').textContent='Computing…';try{const data=await api('/api/cycle',{config});if(id!==seq)return;result=data;config=structuredClone(data.config);normalize();frame=Math.min(frame,data.rows.length-1);$('frame').max=data.rows.length-1;$('play').disabled=!data.motion.available;$('frame').disabled=!data.motion.available;showMotionRange();computeBounds();notice('');render();renderPeaks();renderRanges();drawChart();$('status').textContent=`${data.summary.complete?'Complete sampled cycle':data.motion.limited?'LIMITED MOTION · guarded preview':'INCOMPLETE CYCLE'} · ${data.summary.valid_samples}/${data.summary.samples} frames · closure ${data.summary.max_closure_m==null?'—':data.summary.max_closure_m.toExponential(1)} m · no collision / strength check`;try{localStorage.setItem('kneelab-config-v1',JSON.stringify(config));}catch{}}catch(e){if(id===seq){notice(e.message);$('status').textContent='Calculation not updated';}}}
function computeBounds(){const pts=result.rows.flatMap(r=>[r.hip,r.knee,r.foot,...r.A||[],...r.B||[]]);const xs=pts.map(p=>p[0]),ys=pts.map(p=>p[1]);bounds={xmin:Math.min(-.1,...xs)-.09,xmax:Math.max(.15,...xs)+.11,ymin:Math.min(0,...ys)-.08,ymax:Math.max(...ys)+.08};}
function transform(){const w=$('drawing').clientWidth,h=$('drawing').clientHeight,s=Math.min((w-90)/(bounds.xmax-bounds.xmin),(h-105-Math.max(0,selectedRods.size-1)*14)/(bounds.ymax-bounds.ymin));const cx=(bounds.xmax+bounds.xmin)/2,cy=(bounds.ymax+bounds.ymin)/2;return {s,w,h,pt:p=>[w/2+(p[0]-cx)*s,h/2-22.5-Math.max(0,selectedRods.size-1)*7-(p[1]-cy)*s]};}
function render(){if(!result)return;const r=result.rows[frame];updateRodButtons();$('frame').value=frame;$('time').textContent=fmt(r.t,2)+' s';drawMechanism(r);const pairs=[['Knee angle',fmt(r.q_deg,1)+'°'],['Hip height',fmt(r.hip_height_m*1000,0)+' mm'],['Foot Fz',fmt(r.fz,1)+' N'],['Knee torque',fmt(r.tau_out,1)+' N·m'],['Input torque',fmt(r.tau_in,1)+' N·m'],['Input speed',fmt(r.motor_speed,2)+' rad/s'],['Output / input torque',fmt(r.gain,2)],['Elastic twist',fmt(r.twist_deg,3)+'°']];fillDl($('instant'),pairs);$('rodTable').replaceChildren();for(let i=0;i<config.n;i++){const tr=document.createElement('tr'),f=r.forces?.[i];for(const v of [`R${i+1}`,f==null?'—':fmt(f,0)+' N',f==null?'—':Math.abs(f)<.05?'Zero':f>0?'Tension':'Compression']){const td=document.createElement('td');td.textContent=v;tr.append(td);}tr.firstElementChild.style.color=colorFor(`R${i+1}`);tr.firstElementChild.style.fontWeight='600';tr.firstElementChild.dataset.colorKey=`R${i+1}`;$('rodTable').append(tr);}updateCursor();}
function fillDl(node,pairs){node.replaceChildren();pairs.forEach(([a,b])=>{const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=a;dd.textContent=b;node.append(dt,dd);});}
function syncRodSelection(){
 for(const i of selectedRods)if(i>=config.n)selectedRods.delete(i);
 const node=$('rodSelector');node.replaceChildren();
 const label=document.createElement('span');label.className='selector-label';label.textContent='Forces';node.append(label);
 for(const [name,action] of [['All','all'],['Clear','clear']]){
  const button=document.createElement('button');button.textContent=name;button.dataset.action=action;
  button.title=action==='all'?'Show forces on every rod':'Clear force overlays';
  button.onclick=()=>{selectedRods.clear();if(action==='all')for(let i=0;i<config.n;i++)selectedRods.add(i);refreshRodSelection();};node.append(button);
 }
 for(let i=0;i<config.n;i++){
  const button=document.createElement('button');button.dataset.rod=i;button.title=`Toggle R${i+1} forces · multiple selection`;
  const sample=el('svg',{width:22,height:10,'aria-hidden':'true'});
  line(sample,[1,5],[21,5],{...ink(`R${i+1}`),'stroke-width':2,'stroke-dasharray':dash[i]});
  button.append(sample,document.createTextNode(`R${i+1}`));button.onclick=()=>selectRod(i);node.append(button);
 }
 updateRodButtons();
}
function selectRod(i,ensure=false){
 if(ensure||!selectedRods.has(i))selectedRods.add(i);else selectedRods.delete(i);
 refreshRodSelection();
}
function refreshRodSelection(){if(result){render();drawChart();}}
function rodOpacity(i){return !selectedRods.size||selectedRods.has(i)?1:contextOpacity;}
function updateRodButtons(){
 for(const row of $('forceRanges').querySelectorAll('tbody tr'))row.classList.toggle('selected',selectedRods.has(Number(row.dataset.rod)));
 for(const button of $('forceRanges').querySelectorAll('button[data-frame]'))button.classList.toggle('at-cursor',Number(button.dataset.frame)===frame&&selectedRods.has(Number(button.dataset.rod)));
 for(const b of $('rodSelector').querySelectorAll('button')){
  const active=b.dataset.action==='all'?selectedRods.size===config.n:b.dataset.action==='clear'?!selectedRods.size:selectedRods.has(Number(b.dataset.rod));
  b.classList.toggle('selected',active);b.setAttribute('aria-pressed',String(active));
 }
}
function showMotionRange(){
 const m=result.motion,node=$('motionRange');node.hidden=!m.limited&&m.available;
 node.textContent=!m.available?'No admissible motion at this margin. Change the geometry, range or assembly.':
  `Requested ${fmt(m.requested_start_deg,1)}° → ${fmt(m.requested_end_deg,1)}° · Preview ${fmt(m.start_deg,1)}° → ${fmt(m.end_deg,1)}° · ${fmt(config.dead_center_tol_deg,1)}° margin. Original range excluded from scan.`;
}
function forceArrow(svg,origin,vector,scale,key,end){
 const magnitude=Math.hypot(...vector);if(magnitude<1e-8)return;
 const delta=[vector[0]*scale,-vector[1]*scale],tip=[origin[0]+delta[0],origin[1]+delta[1]],u=[delta[0]/(magnitude*scale),delta[1]/(magnitude*scale)];
 const attrs={...ink(key),'stroke-width':2,'data-force-end':end};
 line(svg,origin,tip,attrs);
 const head=Math.min(7,magnitude*scale*.45),wing=head*.45;
 line(svg,tip,[tip[0]-head*u[0]+wing*u[1],tip[1]-head*u[1]-wing*u[0]],attrs);
 line(svg,tip,[tip[0]-head*u[0]-wing*u[1],tip[1]-head*u[1]+wing*u[0]],attrs);
}
function renderPeaks(){const s=result.summary;fillDl($('peaks'),[['Rod load',fmt(s.peak_rod_n,0)+' N'],['Input torque',fmt(s.peak_input_nm,1)+' N·m'],['Knee support',fmt(s.peak_knee_reaction_n,0)+' N'],['Input support',fmt(s.peak_input_reaction_n,0)+' N'],['Foot Fz range',fmt(s.min_fz_n,0)+'–'+fmt(s.max_fz_n,0)+' N']]);$('warnings').replaceChildren();[...result.errors.map(x=>'INVALID: '+x.replaceAll('_',' ')),...result.warnings].forEach(w=>{const p=document.createElement('p');p.textContent=w;$('warnings').append(p);});if(!s.complete)$('checks').open=true;}
function drawMechanism(r){const svg=$('mechanism');svg.replaceChildren();svg.style.height='';const {s,w,h,pt}=transform();svg.setAttribute('viewBox',`0 0 ${w} ${h}`);const defs=el('defs'),marker=el('marker',{id:'arrow',viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:6,markerHeight:6,orient:'auto-start-reverse'});marker.append(el('path',{d:'M 0 0 L 10 5 L 0 10',fill:'none',stroke:'#222','stroke-width':1.5}));defs.append(marker);svg.append(defs);if($('grid').checked){for(let x=Math.ceil(bounds.xmin/.05)*.05;x<bounds.xmax;x+=.05)line(svg,pt([x,bounds.ymin]),pt([x,bounds.ymax]),{class:'grid-line'});for(let y=Math.ceil(bounds.ymin/.05)*.05;y<bounds.ymax;y+=.05)line(svg,pt([bounds.xmin,y]),pt([bounds.xmax,y]),{class:'grid-line'});}
 const ground=pt([0,0])[1];line(svg,[25,ground],[w-25,ground],{stroke:'#555','stroke-width':1});for(let x=25;x<w-25;x+=15)line(svg,[x,ground],[x-7,ground+7],{stroke:'#ccc','stroke-width':1});text(svg,[32,ground-8],'Ground / fixed foot');line(svg,pt([0,0]),pt([0,bounds.ymax]),{class:'construction'});
 const O=pt(r.hip),K=pt(r.knee),F=pt(r.foot);line(svg,O,K,{class:'body-line',...ink('thigh'),style:`stroke:${colorFor('thigh')};stroke-width:2;opacity:${selectedRods.size?.7:1}`});line(svg,K,F,{class:'body-line',...ink('shank'),style:`stroke:${colorFor('shank')};stroke-width:2;opacity:${selectedRods.size?.7:1}`});for(const [p,rad] of [[O,config.input_radius_mm],[K,config.output_radius_mm]])svg.append(el('circle',{cx:p[0],cy:p[1],r:rad*s/1000,class:'construction'}));
 if(r.A)for(let i=0;i<config.n;i++){
  if(!r.A[i]||!r.B[i])continue;
  const A=pt(r.A[i]),B=pt(r.B[i]),group=el('g',{'data-rod-group':i,opacity:rodOpacity(i)});svg.append(group);
  line(group,O,A,{class:'body-line',...ink(`R${i+1}`)});line(group,K,B,{class:'body-line',...ink(`R${i+1}`)});
  line(group,A,B,{class:'rod',...ink(`R${i+1}`),'stroke-dasharray':dash[i],opacity:selectedRods.has(i)? .7 : 1});
  for(const p of [A,B])group.append(el('circle',{cx:p[0],cy:p[1],r:3.5,class:'joint',...ink(`R${i+1}`)}));
  const p=[A[0]*.6+B[0]*.4,A[1]*.6+B[1]*.4];text(group,[p[0]+5,p[1]-6],`R${i+1}`,{...ink(`R${i+1}`,'fill'),'font-weight':600,stroke:'white','stroke-width':3,'paint-order':'stroke'});
 }
 if(selectedRods.size&&r.A&&r.rod_end_forces){
  const peak=result.summary.peak_rod_n||1,scale=Math.min(52,w*.11)/peak,chosen=[...selectedRods].sort();
  chosen.forEach((i,slot)=>{
   const key=`R${i+1}`,vectors=r.rod_end_forces[i],force=r.forces[i];
   if(!vectors)return;
   forceArrow(svg,pt(r.A[i]),vectors.A,scale,key,'A');forceArrow(svg,pt(r.B[i]),vectors.B,scale,key,'B');
   text(svg,[25,h-47-14*(chosen.length-1-slot)],`${key}: ${fmt(force,1)} N · ${Math.abs(force)<.05?'Zero':force>0?'Tension':'Compression'}`,{...ink(key,'fill'),'font-size':10});
  });
  const scaleN=Math.pow(10,Math.floor(Math.log10(peak))),bar=scaleN*scale;
  line(svg,[25,h-33],[25+bar,h-33],{stroke:'#666','stroke-width':2});
  text(svg,[32+bar,h-29],`${fmt(scaleN,0)} N · forces ON rods`,{'font-size':10});
 }
 for(const [p,name,dx,dy] of [[O,'Input',-12,-10],[K,'K',10,20],[F,'F',10,17]]){svg.append(el('circle',{cx:p[0],cy:p[1],r:4.5,class:'joint'}));text(svg,[p[0]+dx,p[1]+dy],name,{'text-anchor':dx<0?'end':'start',stroke:'white','stroke-width':3,'paint-order':'stroke'});}
 const arrowX=F[0]-36;line(svg,[arrowX,F[1]-2],[arrowX,F[1]-(r.fz>0?65:-45)],{stroke:'#222','stroke-width':1.5,'marker-end':'url(#arrow)'});text(svg,[arrowX-10,F[1]-53],`Fz ${fmt(r.fz,0)} N`,{'text-anchor':'end'});
 if($('dimensions').checked){const xd=pt([bounds.xmin+.035,0])[0];line(svg,[xd,ground],[xd,O[1]],{class:'dim','marker-start':'url(#arrow)','marker-end':'url(#arrow)'});line(svg,[xd-5,O[1]],[O[0]-10,O[1]],{class:'construction'});text(svg,[xd-7,(ground+O[1])/2],`h ${fmt(r.hip_height_m*1000,0)}`,{transform:`rotate(-90 ${xd-7} ${(ground+O[1])/2})`,'text-anchor':'middle'});text(svg,[(O[0]+K[0])/2+9,(O[1]+K[1])/2+14],`d ${config.center_mm}`,{fill:'#666',stroke:'white','stroke-width':3,'paint-order':'stroke'});text(svg,[(F[0]+K[0])/2+9,(F[1]+K[1])/2],`s ${config.shank_mm}`,{fill:'#666',stroke:'white','stroke-width':3,'paint-order':'stroke'});}
 text(svg,[25,24],`n = ${config.n}    q = ${fmt(r.q_deg,1)}°    t = ${fmt(r.t,2)} s`);text(svg,[25,43],'Input/hip · K knee · F foot · nominal geometry',{'font-size':10,fill:'#777'});const warningY=mechanismLegend(svg,w,h);if(!r.valid)text(svg,[w/2,warningY],r.reasons.join(' / ').replaceAll('_',' '),{'text-anchor':'middle','font-weight':600});}
function series(){const kind=$('plotType').value;const norm=v=>v?Math.hypot(...v):null;switch(kind){case'forces':return Array.from({length:config.n},(_,i)=>({name:`R${i+1}`,key:`R${i+1}`,v:r=>r.forces?.[i]??null}));case'torque':return[{name:'Knee',key:'knee',v:r=>r.valid?r.tau_out:null},{name:'Input',key:'input',v:r=>r.tau_in}];case'reaction':return[{name:'Knee support',key:'knee',v:r=>norm(r.reaction_knee)},{name:'Input support',key:'input',v:r=>norm(r.reaction_input)}];case'grf':return[{name:'Foot Fz',key:'ground',v:r=>r.fz}];case'speed':return[{name:'Input speed',key:'input',v:r=>r.motor_speed}];case'height':return[{name:'Hip height',key:'thigh',v:r=>1000*r.hip_height_m}];default:return[{name:'Knee angle',key:'knee',v:r=>r.q_deg}];}}
function plotUnit(){return {forces:'N',torque:'N·m',reaction:'N',grf:'N',speed:'rad/s',height:'mm',angle:'deg'}[$('plotType').value];}
function signedValue(value){
 if(value==null||!Number.isFinite(value))return '—';
 if(Math.abs(value)<=1e-6)return '0.0';
 const a=Math.abs(value),digits=a<.01?a.toExponential(2):a.toFixed(a<1?3:1);
 return (value>0?'+':'−')+digits;
}
function renderRanges(){
 const tbody=$('forceRanges').querySelector('tbody');tbody.replaceChildren();
 $('rangeScope').textContent=result.motion.limited?'Guarded preview · valid samples':result.summary.complete?'Full cycle · sampled':'Partial cycle · valid samples';
 const names={min_positive:'minimum tension',max_positive:'maximum tension',min_negative:'strongest compression',max_negative:'compression closest to zero'};
 result.summary.rods.forEach((stats,i)=>{
  const tr=document.createElement('tr');tr.dataset.rod=i;tr.style.setProperty('--rod-color',colorFor(`R${i+1}`));
  const heading=document.createElement('th');heading.scope='row';
  const choose=document.createElement('button');choose.textContent=`R${i+1}`;choose.style.color=colorFor(`R${i+1}`);choose.title=`Toggle R${i+1} forces`;choose.onclick=()=>selectRod(i);heading.append(choose);tr.append(heading);
  for(const key of Object.keys(names)){
   const td=document.createElement('td'),event=stats.extrema[key];
   if(!event){td.textContent='—';td.title='No valid nonzero samples of this sign';}
   else{
    const button=document.createElement('button');button.textContent=signedValue(event.force_n);button.dataset.frame=event.frame;button.dataset.rod=i;
    const label=`R${i+1} ${names[key]}: ${signedValue(event.force_n)} N at ${fmt(event.t_s,3)} s, knee ${fmt(event.q_deg,2)} degrees`;
    button.title=label;button.setAttribute('aria-label',label);
    button.onclick=()=>{stop();frame=event.frame;$('plotType').value='forces';selectRod(i,true);};td.append(button);
   }
   tr.append(td);
  }
  tbody.append(tr);
 });
 updateRodButtons();
}
function capacityAnalysis(){
 const keys=['ratedTorque','ratio','efficiency'];
 if(keys.some(key=>!Number.isFinite(analysis[key]))||analysis.ratedTorque<0||analysis.ratio<=0||analysis.efficiency<=0||analysis.efficiency>100)return null;
 const limit=analysis.ratedTorque*analysis.ratio*analysis.efficiency/100;
 const coverage=KneeAnalysis.torqueCoverage(result.rows,result.config.half_cycle_s,limit,result.config.q_start_deg,result.config.q_end_deg);
 return coverage?{...coverage,limit}:null;
}
function renderCapacity(capacity){
 if(!capacity){$('torqueCoverage').textContent='Check the capacity inputs';$('torqueLimit').textContent='';$('coverageFill').style.width='0%';$('coverageDetail').textContent='Enter a nonnegative torque, a positive ratio, and efficiency from 0 to 100% (excluding 0).';return;}
 $('torqueCoverage').textContent=capacity.fixed?`${capacity.percent===100?'Within':'Outside'} limit · fixed pose`:`${fmt(capacity.percent,1)}% knee-angle coverage`;
 $('torqueLimit').textContent=`Input limit ±${fmt(capacity.limit,1)} N·m`;
 $('coverageFill').style.width=capacity.percent+'%';
 const partial=result.motion.limited?' · guarded preview':!result.summary.complete?' · incomplete cycle':'';
 $('coverageDetail').textContent=capacity.fixed?`Both directions checked${partial}.`:`${fmt(capacity.degrees,1)}° / ${fmt(capacity.span,1)}° requested range · both directions${partial}.`;
 $('coverageDetail').title=capacity.angles.length?'Within limit: '+capacity.angles.map(([a,b])=>`${fmt(a,1)}° to ${fmt(b,1)}°`).join('; '):'No valid angle interval within the limit.';
}
function drawChart(){
 if(!result)return;
 const svg=$('chart'),ss=series();svg.replaceChildren();
 const mode=analysis.plotMode,T=result.config.half_cycle_s,duration=mode==='oneway'?T:2*T;
 const torqueMode=$('plotType').value==='torque';$('motorPanel').hidden=!torqueMode;
 const capacity=torqueMode?capacityAnalysis():null;if(torqueMode)renderCapacity(capacity);
 const branches=ss.map(s=>KneeAnalysis.curveBranches(result.rows,s.v,T,mode));
 const hasReturn=mode==='oneway'&&branches.some(b=>b.length>1);
 $('cycleModeHint').textContent=mode==='roundtrip'?'Full outward + return cycle':hasReturn?'Return values dashed · cursor retraces':'Cursor retraces on return';
 const width=Math.max(250,svg.clientWidth),height=Math.max(160,svg.clientHeight),x0=48,x1=width-20,top=24,bottom=height-40;
 svg.setAttribute('viewBox',`0 0 ${width} ${height}`);svg.dataset.x0=x0;svg.dataset.span=x1-x0;
 const vals=ss.flatMap(s=>result.rows.map(s.v).filter(v=>v!==null&&Number.isFinite(v)));
 let lo=Math.min(0,...vals),hi=Math.max(0,...vals);if(hi-lo<1e-9){hi+=1;lo-=1;}
 const pad=(hi-lo)*.08;lo-=pad;hi+=pad;
 const x=t=>x0+(x1-x0)*t/duration,y=v=>bottom-(bottom-top)*(v-lo)/(hi-lo);
 chartMap={x,y,series:ss,duration};
 if(capacity)for(const [a,b] of capacity[mode]){
  const rect=el('rect',{x:x(a),y:top,width:Math.max(0,x(b)-x(a)),height:bottom-top,fill:colorMode==='mono'?'#e8eeea':'#e1f0e6','data-capacity-zone':'true'});
  rect.append(el('title',{},mode==='oneway'?'Input torque within the limit on both outward and return passes':'Input torque within the limit'));svg.append(rect);
 }
 for(let i=0;i<=4;i++){
  const v=lo+(hi-lo)*i/4,Y=y(v);line(svg,[x0,Y],[x1,Y],{stroke:'#e1e1e1','stroke-width':.7});
  text(svg,[x0-7,Y+4],fmt(v,Math.max(Math.abs(lo),Math.abs(hi))<10?1:0),{'text-anchor':'end','font-size':10});
 }
 line(svg,[x0,y(0)],[x1,y(0)],{stroke:'#777','stroke-width':.8});
 for(let i=0;i<=4;i++){const t=duration*i/4,X=x(t);line(svg,[X,top],[X,bottom],{stroke:'#eee','stroke-width':.7});text(svg,[X,height-20],fmt(t,1),{'text-anchor':'middle','font-size':10});}
 text(svg,[width-5,height-6],mode==='oneway'?'One-way t [s]':'Cycle t [s]',{'text-anchor':'end','font-size':10});
 if(capacity)for(const value of [...new Set([-capacity.limit,capacity.limit])])if(value>=lo&&value<=hi){line(svg,[x0,y(value)],[x1,y(value)],{stroke:'#6c9d80','stroke-width':1,'stroke-dasharray':'4 4','data-capacity-limit':value});text(svg,[x1-4,y(value)-4],`${value<0?'−':'+'}${fmt(Math.abs(value),1)}`,{'text-anchor':'end','font-size':9,fill:'#48765a'});}
 $('legend').replaceChildren();
 ss.forEach((s,i)=>{
  const selectable=/^R[123]$/.test(s.key),rod=selectable?Number(s.key.slice(1))-1:null;
  branches[i].forEach((points,branch)=>{
   let d='',active=false;
   for(const p of points){if(p.v===null||!Number.isFinite(p.v)){active=false;continue;}d+=(active?' L ':' M ')+x(p.t).toFixed(2)+' '+y(p.v).toFixed(2);active=true;}
   svg.append(el('path',{d,fill:'none',...ink(s.key),'stroke-width':1.6,'stroke-dasharray':branch?'3 4':dash[i],opacity:(selectable?rodOpacity(rod):1)*(branch?.7:1),'data-series-path':s.key,'data-pass':branch?'return':'outward'}));
  });
  const entry=document.createElement(selectable?'button':'span'),sample=el('svg',{width:21,height:9,'aria-hidden':'true'}),name=document.createElement('span'),value=document.createElement('strong');
  line(sample,[0,4],[21,4],{...ink(s.key),'stroke-width':1.6,'stroke-dasharray':dash[i]});
  entry.className='series-entry';entry.dataset.series=s.key;name.textContent=s.name;value.className='series-value';value.style.color=colorFor(s.key);entry.append(sample,name,value);
  if(selectable){entry.title=`Toggle ${s.name} forces; value is at the cursor`;entry.setAttribute('aria-pressed',String(selectedRods.has(rod)));entry.onclick=()=>selectRod(rod);}
  $('legend').append(entry);
 });
 svg.append(el('line',{id:'cursor',x1:65,y1:top,x2:65,y2:bottom,stroke:'#666','stroke-width':1,'stroke-dasharray':'3 3'}));
 svg.append(el('g',{id:'cursorPoints','aria-hidden':'true'}));updateCursor();
}
function updateCursor(){
 if(!$('cursor')||!result||!chartMap)return;
 const r=result.rows[frame],x=chartMap.x(KneeAnalysis.displayTime(r.t,config.half_cycle_s,analysis.plotMode)),points=$('cursorPoints');
 $('cursor').setAttribute('x1',x);$('cursor').setAttribute('x2',x);points.replaceChildren();
 $('cursorMeta').textContent=`${analysis.plotMode==='oneway'?(r.t>config.half_cycle_s?'← Return':'→ Outward')+' · ':''}t ${fmt(r.t,3)} s · q ${fmt(r.q_deg,2)}°${r.valid?'':' · invalid frame'}`;
 chartMap.series.forEach(s=>{
  const v=s.v(r),entry=$('legend').querySelector(`[data-series="${s.key}"]`),value=entry?.querySelector('.series-value');
  if(value)value.textContent=v==null?'—':`${signedValue(v)} ${plotUnit()}`;
  if(v==null||!Number.isFinite(v))return;
  const dot=el('circle',{cx:x,cy:chartMap.y(v),r:4.2,fill:'white',...ink(s.key),'stroke-width':1.8,'data-cursor-series':s.key});
  dot.append(el('title',{},`${s.name}: ${signedValue(v)} ${plotUnit()} at ${fmt(r.t,3)} s`));points.append(dot);
 });
}
function inspectChart(event){
 if(!result||!result.motion.available)return;
 const svg=$('chart'),rect=svg.getBoundingClientRect(),x=(event.clientX-rect.left)/rect.width*svg.viewBox.baseVal.width;
 const target=Math.max(0,Math.min(1,(x-Number(svg.dataset.x0))/Number(svg.dataset.span)))*chartMap.duration;
 frame=KneeAnalysis.nearestFrame(result.rows,target,config.half_cycle_s,analysis.plotMode,result.rows[frame].t>config.half_cycle_s);stop();render();
}
function stop(){playing=false;$('play').textContent='▶';$('play').setAttribute('aria-label','Play cycle');}
function animate(now){if(playing&&result){const dt=lastTick?(now-lastTick)/1000:0;playTime=(playTime+dt*Number($('playSpeed').value))%(2*config.half_cycle_s);frame=Math.round(playTime/(2*config.half_cycle_s)*(result.rows.length-1));render();}lastTick=now;requestAnimationFrame(animate);}
function download(data,name,type){const url=URL.createObjectURL(new Blob([data],{type}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1500);}
function view(name){$('modelView').hidden=name!=='model';$('scanView').hidden=name!=='scan';$('modelTab').classList.toggle('active',name==='model');$('scanTab').classList.toggle('active',name==='scan');$('showParameters').hidden=name==='scan';toggleParameters(false);stop();scheduleLayoutRender();}
function buildScanFields(){for(const [k,v] of Object.entries(defaults.grid)){const row=document.createElement('div');row.className='field';const l=document.createElement('label');l.textContent=labels[k];l.htmlFor='scan_'+k;const input=document.createElement('input');input.id='scan_'+k;input.value=v.join(', ');row.append(l,input);$('scanFields').append(row);}for(const [k,v] of Object.entries(defaults.limits)){const row=document.createElement('div');row.className='field';const l=document.createElement('label');l.textContent=labels[k];l.htmlFor='limit_'+k;const input=document.createElement('input');input.id='limit_'+k;input.type='number';input.min=0;input.value=v;const u=document.createElement('span');u.className='unit';u.textContent=k.endsWith('_mm')?'mm':k.endsWith('_nm')?'N·m':k.endsWith('_n')?'N':k.endsWith('_deg')?'deg':'rad/s';row.append(l,input,u);$('limitFields').append(row);}}
async function runScan(){stop();notice('');const grid={},limits={};try{for(const k of Object.keys(defaults.grid)){const raw=$('scan_'+k).value.split(',');if(raw.some(v=>!v.trim()))throw Error('Use comma-separated numbers without empty entries.');grid[k]=raw.map(Number);if(grid[k].some(v=>!Number.isFinite(v)))throw Error('Scan grid contains an invalid number.');}for(const k of Object.keys(defaults.limits))limits[k]=Number($('limit_'+k).value);scanRequest={config:structuredClone(config),grid,limits};$('runScan').disabled=true;$('scanStatus').textContent='Computing grid…';scanResult=await api('/api/scan',scanRequest);$('scanStatus').textContent=`${scanResult.feasible} feasible / ${scanResult.evaluated} candidates`;$('scanSummary').textContent='Rejected checks (a candidate may fail more than one): '+(Object.entries(scanResult.rejected).map(([k,v])=>`${k.replaceAll('_',' ')} ${v}`).join(' · ')||'none');const tbody=$('scanTable').querySelector('tbody');tbody.replaceChildren();scanResult.candidates.slice(0,200).forEach((r,i)=>{const c=r.config,tr=document.createElement('tr');for(const value of [i+1,c.n,c.input_radius_mm,c.spacing_deg,c.center_mm,c.shank_mm,c.clocking_deg,fmt(r.peak_rod_n,0),fmt(r.peak_input_nm,1),fmt(r.peak_knee_reaction_n,0),r.pareto?'Pareto':'']){const td=document.createElement('td');td.textContent=value;tr.append(td);}const td=document.createElement('td'),b=document.createElement('button');b.textContent='Load';b.addEventListener('click',()=>{config=structuredClone(c);normalize();view('model');frame=0;solve();});td.append(b);tr.append(td);tbody.append(tr);});$('scanExport').disabled=false;}catch(e){notice(e.message);$('scanStatus').textContent='Scan not completed';}finally{$('runScan').disabled=false;}}
async function boot(){try{syncAnalysisControls();defaults=await api('/api/defaults');config=structuredClone(defaults.config);try{const saved=JSON.parse(localStorage.getItem('kneelab-config-v1'));if(saved)config={...config,...saved};}catch{}buildFields();buildScanFields();normalize();await solve();}catch(e){notice(e.message);}}
$('modelTab').onclick=()=>view('model');$('scanTab').onclick=()=>view('scan');$('reset').onclick=()=>{config=structuredClone(defaults.config);analysis=defaultAnalysis();saveAnalysis();syncAnalysisControls();frame=0;normalize();solve();};$('preset').onchange=()=>{if($('preset').value==='custom')return;analysis.mirror=false;saveAnalysis();config=structuredClone(defaults.config);switch($('preset').value){case'three':config.n=3;config.spacing_deg=60;break;case'reverse':config.q_start_deg=-100;config.q_end_deg=100;break;case'single':config.n=1;config.q_start_deg=-100;config.q_end_deg=-15;config.clocking_deg=120;break;}frame=0;normalize();solve();};$('frame').oninput=()=>{stop();frame=Number($('frame').value);render();};$('play').onclick=()=>{if(!result)return;if(playing)stop();else{playing=true;playTime=result.rows[frame].t;lastTick=0;$('play').textContent='Ⅱ';$('play').setAttribute('aria-label','Pause cycle');}};$('dimensions').onchange=render;$('grid').onchange=render;$('fit').onclick=()=>{computeBounds();render();};$('plotType').onchange=drawChart;$('chart').onpointerdown=e=>{if(e.button!==0)return;$('chart').setPointerCapture(e.pointerId);inspectChart(e);};$('chart').onpointermove=e=>{if($('chart').hasPointerCapture(e.pointerId))inspectChart(e);};$('chart').onpointerup=e=>{if($('chart').hasPointerCapture(e.pointerId))$('chart').releasePointerCapture(e.pointerId);};$('chart').onkeydown=e=>{if(!result||!result.motion.available)return;let next=frame;
const returning=result.rows[frame].t>config.half_cycle_s,direction=analysis.plotMode==='oneway'&&returning?-1:1;
if(e.key==='ArrowLeft')next-=direction*(e.shiftKey?10:1);
else if(e.key==='ArrowRight')next+=direction*(e.shiftKey?10:1);
else if(e.key==='Home'||e.key==='End')next=KneeAnalysis.nearestFrame(result.rows,e.key==='Home'?0:chartMap.duration,config.half_cycle_s,analysis.plotMode,returning);
else return;e.preventDefault();stop();
if(analysis.plotMode==='oneway'){
const branchFrames=result.rows.map((r,i)=>({r,i})).filter(({r})=>returning?r.t>=config.half_cycle_s:r.t<=config.half_cycle_s);
next=Math.max(branchFrames[0].i,Math.min(branchFrames[branchFrames.length-1].i,next));
}
frame=Math.max(0,Math.min(result.rows.length-1,next));render();};$('saveConfig').onclick=()=>download(JSON.stringify({format:'knee-linkage-lab',version:2,config,analysis},null,2),'knee-config.json','application/json');$('loadConfig').onclick=()=>$('configFile').click();$('configFile').onchange=async()=>{try{const file=$('configFile').files[0];if(!file)return;const incoming=JSON.parse(await file.text());const checked=await api('/api/cycle',{config:incoming.config||incoming});config=checked.config;analysis=restoreAnalysis(incoming.analysis);syncAnalysisControls();saveAnalysis();frame=0;normalize();await solve();}catch(e){notice('Could not open config: '+e.message);}$('configFile').value='';};$('exportCsv').onclick=async()=>{try{download(await api('/api/cycle.csv',{config:config}),'knee-cycle.csv','text/csv');}catch(e){notice(e.message);}};$('exportSvg').onclick=()=>{const clone=$('mechanism').cloneNode(true),style=el('style');style.textContent='text{font-family:Arial,sans-serif;fill:#333;font-size:11px}.construction{stroke:#aaa;stroke-dasharray:5 4;fill:none;stroke-width:1}.grid-line{stroke:#eee;stroke-width:1}.dim{stroke:#888;stroke-width:.8;fill:none}.rod{stroke:#111;stroke-width:1.8;fill:none}.joint{fill:white;stroke:#111;stroke-width:1.2}.body-line{stroke:#555;stroke-width:1.4;fill:none}';clone.prepend(style);clone.setAttribute('xmlns',NS);download(new XMLSerializer().serializeToString(clone),'knee-frame.svg','image/svg+xml');};$('runScan').onclick=runScan;$('scanExport').onclick=()=>download(JSON.stringify({request:scanRequest,result:scanResult},null,2),'knee-scan.json','application/json');requestAnimationFrame(animate);boot();

$('showValues').onclick=()=>{$('readoutsPanel').open=!$('readoutsPanel').open;};
$('readoutsPanel').addEventListener('toggle',()=>{$('showValues').setAttribute('aria-expanded',String($('readoutsPanel').open));scheduleLayoutRender();});
function toggleParameters(open){
 document.body.classList.toggle('parameters-open',open);
 $('showParameters').setAttribute('aria-expanded',String(open));$('parameterBackdrop').hidden=!open;
}
$('showParameters').onclick=()=>toggleParameters(!document.body.classList.contains('parameters-open'));
$('parameterBackdrop').onclick=()=>toggleParameters(false);
document.addEventListener('keydown',event=>{if(event.key==='Escape')toggleParameters(false);});
let layoutFrame=0;
function scheduleLayoutRender(){
 if(layoutFrame)return;
 layoutFrame=requestAnimationFrame(()=>{
  layoutFrame=0;
  document.documentElement.style.setProperty('--app-header-height',document.querySelector('header').getBoundingClientRect().height+'px');
  if(window.innerWidth>760&&document.body.classList.contains('parameters-open'))toggleParameters(false);
  if(result&&!$('modelView').hidden&&$('drawing').clientWidth>0&&$('chart').clientWidth>0){render();drawChart();}
 });
}
const layoutObserver=new ResizeObserver(scheduleLayoutRender);
for(const element of [$('drawing'),$('chart'),document.querySelector('header')])layoutObserver.observe(element);
window.addEventListener('resize',scheduleLayoutRender);

$('colorMode').value=colorMode;syncModeSwitches();
$('colorMode').onchange=()=>{colorMode=$('colorMode').value;syncModeSwitches();try{localStorage.setItem('kneelab-color-mode',colorMode);}catch{}syncRodSelection();if(result){renderRanges();render();drawChart();}};




function syncModeSwitches(){
 for(const id of ['colorMode']){
  const group=$(id+'Switch'),buttons=[...group.querySelectorAll('button')],index=buttons.findIndex(b=>b.dataset.value===$(id).value);
  group.style.setProperty('--selected-index',index);
  buttons.forEach((button,i)=>{button.setAttribute('aria-checked',String(i===index));button.tabIndex=i===index?0:-1;});
 }
}
for(const id of ['colorMode']){
 const group=$(id+'Switch'),buttons=[...group.querySelectorAll('button')];
 buttons.forEach((button,index)=>{
  button.onclick=()=>{$(id).value=button.dataset.value;$(id).dispatchEvent(new Event('change'));};
  button.onkeydown=e=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();const next=e.key==='Home'?0:e.key==='End'?1:1-index;buttons[next].click();buttons[next].focus();};
 });
}

// Display and motor-capacity settings are saved separately from the solver config.
for(const button of $('cycleModeSwitch').querySelectorAll('button')){
 button.onclick=()=>{analysis.plotMode=button.dataset.value;syncAnalysisControls();saveAnalysis();drawChart();};
 button.onkeydown=e=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();const next=e.key==='Home'?'oneway':e.key==='End'?'roundtrip':analysis.plotMode==='oneway'?'roundtrip':'oneway';const target=$('cycleModeSwitch').querySelector(`[data-value="${next}"]`);target.click();target.focus();};
}
for(const key of ['ratedTorque','ratio','efficiency'])$(key).oninput=()=>{
 const input=$(key);analysis[key]=input.value!==''&&input.checkValidity()?Number(input.value):NaN;
 if(['ratedTorque','ratio','efficiency'].every(k=>Number.isFinite(analysis[k])))saveAnalysis();
 drawChart();
};
