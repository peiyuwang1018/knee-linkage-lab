/* Display-only analysis: no changes to the mechanical solver or scan limits. */
(function(root){
 'use strict';
 const EPS=1e-9;
 const finite=v=>typeof v==='number'&&Number.isFinite(v);
 const lerp=(a,b,u)=>a+(b-a)*u;
 function displayTime(t,T,mode){return mode==='oneway'?Math.max(0,Math.min(T,t<=T?t:2*T-t)):t;}
 function merge(intervals){
  const out=[];
  for(const [lo,hi] of intervals.map(([a,b])=>[Math.min(a,b),Math.max(a,b)]).sort((a,b)=>a[0]-b[0])){
   if(!out.length||lo>out[out.length-1][1]+EPS)out.push([lo,hi]);
   else out[out.length-1][1]=Math.max(out[out.length-1][1],hi);
  }
  return out;
 }
 function intersect(left,right){
  const out=[];let i=0,j=0;
  while(i<left.length&&j<right.length){
   const lo=Math.max(left[i][0],right[j][0]),hi=Math.min(left[i][1],right[j][1]);
   if(hi>=lo)out.push([lo,hi]);
   if(left[i][1]<right[j][1])i++;else j++;
  }
  return merge(out);
 }
 // Fraction of one linearly interpolated segment satisfying |torque| <= limit.
 function clip(a,b,limit){
  if(Math.abs(b-a)<EPS)return Math.abs(a)<=limit?[0,1]:null;
  const roots=[(-limit-a)/(b-a),(limit-a)/(b-a)].sort((x,y)=>x-y);
  const lo=Math.max(0,roots[0]),hi=Math.min(1,roots[1]);
  return hi>=lo?[lo,hi]:null;
 }
 function torqueCoverage(rows,T,limit,requestedStart,requestedEnd){
  if(!finite(limit)||limit<0)return null;
  const time=[[],[]],angles=[[],[]];
  for(let i=1;i<rows.length;i++){
   const a=rows[i-1],b=rows[i];
   if(!a.valid||!b.valid||!finite(a.tau_in)||!finite(b.tau_in)||b.t<=a.t)continue;
   const split=a.t<T&&b.t>T?[0,(T-a.t)/(b.t-a.t),1]:[0,1];
   for(let k=1;k<split.length;k++){
    const u=split[k-1],v=split[k],ta=lerp(a.t,b.t,u),tb=lerp(a.t,b.t,v);
    const range=clip(lerp(a.tau_in,b.tau_in,u),lerp(a.tau_in,b.tau_in,v),limit);
    if(!range)continue;
    const side=(ta+tb)/2<=T?0:1;
    const f0=lerp(u,v,range[0]),f1=lerp(u,v,range[1]);
    time[side].push([lerp(a.t,b.t,f0),lerp(a.t,b.t,f1)]);
    angles[side].push([lerp(a.q_deg,b.q_deg,f0),lerp(a.q_deg,b.q_deg,f1)]);
   }
  }
  const requested=[Math.min(requestedStart,requestedEnd),Math.max(requestedStart,requestedEnd)];
  const safeAngles=intersect(intersect(merge(angles[0]),merge(angles[1])),[requested]);
  const span=requested[1]-requested[0];
  const degrees=safeAngles.reduce((sum,[a,b])=>sum+b-a,0);
  const fixedSafe=rows.length>0&&rows.every(r=>r.valid&&finite(r.tau_in)&&Math.abs(r.tau_in)<=limit);
  const folded=intersect(merge(time[0]),merge(time[1].map(([a,b])=>[2*T-b,2*T-a])));
  return {percent:span>EPS?Math.min(100,100*degrees/span):(fixedSafe?100:0),
   degrees,span,fixed:span<=EPS,angles:safeAngles,oneway:folded,roundtrip:merge(time.flat())};
 }
 function curveBranches(rows,value,T,mode){
  const points=rows.map(r=>({t:r.t,v:value(r)}));
  if(mode!=='oneway')return [points];
  let turn=points.find(p=>Math.abs(p.t-T)<EPS);
  if(!turn){
   const i=points.findIndex(p=>p.t>T);
   if(i>0){const a=points[i-1],b=points[i];turn={t:T,v:finite(a.v)&&finite(b.v)?lerp(a.v,b.v,(T-a.t)/(b.t-a.t)):null};}
  }
  const out=points.filter(p=>p.t<T),back=points.filter(p=>p.t>T);
  if(turn){out.push(turn);back.unshift(turn);}
  const folded=back.map(p=>({t:2*T-p.t,v:p.v})).reverse();
  const identical=out.length===folded.length&&out.every((p,i)=>{
   const q=folded[i];return Math.abs(p.t-q.t)<1e-7&&((!finite(p.v)&&!finite(q.v))||
    (finite(p.v)&&finite(q.v)&&Math.abs(p.v-q.v)<1e-7*Math.max(1,Math.abs(p.v),Math.abs(q.v))));
  });
  return identical?[out]:[out,folded];
 }
 function nearestFrame(rows,target,T,mode,returning){
  let best=0,distance=Infinity;
  rows.forEach((r,i)=>{
   if(mode==='oneway'&&((returning&&r.t<T-EPS)||(!returning&&r.t>T+EPS)))return;
   const d=Math.abs(displayTime(r.t,T,mode)-target);
   if(d<distance){distance=d;best=i;}
  });
  return best;
 }
 const api={displayTime,torqueCoverage,curveBranches,nearestFrame};
 if(typeof module!=='undefined'&&module.exports)module.exports=api;
 else root.KneeAnalysis=api;
})(typeof globalThis!=='undefined'?globalThis:this);
