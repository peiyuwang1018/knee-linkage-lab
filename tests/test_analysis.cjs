const test = require('node:test');
const assert = require('node:assert/strict');
const {displayTime, torqueCoverage, curveBranches, nearestFrame} = require('../static/analysis.js');
const row = (t,q,torque,valid=true) => ({t,q_deg:q,tau_in:torque,valid});
const near = (a,b) => assert.ok(Math.abs(a-b)<1e-8, `${a} != ${b}`);

test('folded cursor retraces without changing cycle time', () => {
 assert.deepEqual([0,.5,1,1.5,2].map(t=>displayTime(t,1,'oneway')), [0,.5,1,.5,0]);
 assert.equal(displayTime(1.5,1,'roundtrip'),1.5);
});
test('positive and negative capacity crossings are interpolated', () => {
 const rows=[row(0,-100,-10),row(1,100,10),row(2,-100,-10)];
 const c=torqueCoverage(rows,1,5,-100,100);
 near(c.percent,50);assert.deepEqual(c.angles,[[-50,50]]);
 assert.deepEqual(c.oneway,[[.25,.75]]);
 assert.deepEqual(c.roundtrip,[[.25,.75],[1.25,1.75]]);
});
test('coverage weights angle, not time or sample count', () => {
 const rows=[row(0,0,0),row(.8,10,10),row(1,100,100),row(1.2,10,10),row(2,0,0)];
 const c=torqueCoverage(rows,1,10,0,100);
 near(c.percent,10);near(c.oneway[0][1],.8);
});
test('both passes must meet the torque limit', () => {
 const rows=[row(0,0,0),row(1,100,10),row(2,0,20)];
 const c=torqueCoverage(rows,1,12,0,100);
 near(c.percent,20);assert.deepEqual(c.angles,[[80,100]]);
});
test('invalid samples do not bridge a safe interval', () => {
 const rows=[row(0,0,1),row(.5,50,1,false),row(1,100,1),row(1.5,50,1),row(2,0,1)];
 const c=torqueCoverage(rows,1,100,0,100);
 near(c.percent,0);assert.deepEqual(c.oneway,[]);
});
test('guarded preview uses the complete requested range as denominator', () => {
 const rows=[row(0,-50,1),row(1,50,1),row(2,-50,1)];
 near(torqueCoverage(rows,1,10,-100,100).percent,50);
 near(torqueCoverage(rows,1,10,100,-100).percent,50);
});
test('fixed poses, zero torque and invalid capacity remain defined', () => {
 const rows=[row(0,30,0),row(1,30,0),row(2,30,0)];
 near(torqueCoverage(rows,1,0,30,30).percent,100);
 rows[1].valid=false;near(torqueCoverage(rows,1,10,30,30).percent,0);
 assert.equal(torqueCoverage(rows,1,NaN,0,100),null);
});
test('an even sample count can straddle the turn', () => {
 const rows=[row(0,0,0),row(.8,80,8),row(1.2,80,8),row(2,0,0)];
 const c=torqueCoverage(rows,1,4,0,100);
 near(c.percent,40);
 const branches=curveBranches(rows,r=>r.tau_in,1,'oneway');
 assert.equal(branches.length,1);assert.equal(branches[0].at(-1).t,1);
});
test('identical passes share one curve; opposite speeds retain both', () => {
 const rows=[row(0,0,0),row(.5,50,5),row(1,100,0),row(1.5,50,-5),row(2,0,0)];
 assert.equal(curveBranches(rows,r=>r.q_deg,1,'oneway').length,1);
 const speeds=curveBranches(rows,r=>r.tau_in,1,'oneway');
 assert.equal(speeds.length,2);assert.equal(speeds[1][1].v,-5);
 assert.equal(curveBranches(rows,r=>r.q_deg,1,'roundtrip')[0].length,5);
});
test('inspection stays on the current pass and supports equal timestamps at endpoints', () => {
 const rows=[0,.5,1,1.5,2].map(t=>row(t,0,0));
 assert.equal(nearestFrame(rows,.5,1,'oneway',false),1);
 assert.equal(nearestFrame(rows,.5,1,'oneway',true),3);
 assert.equal(nearestFrame(rows,0,1,'oneway',true),4);
 assert.equal(nearestFrame(rows,1.5,1,'roundtrip',false),3);
});
