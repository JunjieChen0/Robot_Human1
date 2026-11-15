import test from "node:test";
import assert from "node:assert/strict";
import {SquatCounter, kneeObservation} from "../src/squat_frontend/counter.mjs";

function sequence(counter) {
  let time = counter.lastMs === null ? 0 : counter.lastMs + 100;
  return (angle, duration = 400, valid = true) => {
    for (let elapsed=0; elapsed<duration; elapsed+=100) {
      counter.observe({angle,timeMs:time,valid});time+=100;
    }
  };
}

test("initial squat and 3-second holds cannot count without a completed cycle", () => {
  const c=new SquatCounter(), feed=sequence(c);
  feed(80,3000);assert.equal(c.events.length,0);
  feed(170,3000);assert.equal(c.events.length,0);
  feed(80,3000);assert.equal(c.events.length,0);
  feed(170,400);assert.equal(c.events.length,1);
  feed(170,3000);assert.equal(c.events.length,1);
  feed(80);feed(170);assert.equal(c.events.length,2);
});
test("half squats and threshold flicker do not trigger an extra cycle", () => {
  const c=new SquatCounter(),feed=sequence(c);feed(170);
  feed(120,1000);feed(170);assert.equal(c.events.length,0);
  feed(90);
  for(let i=0;i<10;i++){feed(161,100);feed(159,100);}
  assert.equal(c.events.length,0);
  feed(170);assert.equal(c.events.length,1);
});
test("lost visibility clears pending motion and requires standing again", () => {
  const c=new SquatCounter(),feed=sequence(c);feed(170);feed(80);
  feed(170,200);feed(170,100,false);feed(170,400);
  assert.equal(c.events.length,0);
  feed(80);feed(170);assert.equal(c.events.length,1);
});
test("pause and long frame gaps cannot bridge a squat into a count", () => {
  const c=new SquatCounter(),feed=sequence(c);feed(170);feed(80);
  c.invalidate("pause");const resumed=sequence(c);resumed(170);
  assert.equal(c.events.length,0);
  resumed(80);
  c.observe({angle:170,timeMs:10000});c.observe({angle:170,timeMs:10300});
  assert.equal(c.events.length,0);
});
test("an out-of-order clock cannot complete an old movement", () => {
  const c=new SquatCounter(),feed=sequence(c);feed(170);feed(80);
  c.observe({angle:170,timeMs:0});c.observe({angle:170,timeMs:300});
  assert.equal(c.events.length,0);
});
test("exact 160/100 degree boundaries and 300 milliseconds are inclusive", () => {
  const c=new SquatCounter();
  for(const [t,a] of [[0,160],[300,160],[400,100],[700,100],[800,160],[1100,160]])c.observe({angle:a,timeMs:t});
  assert.equal(c.events.length,1);assert.equal(c.events[0].time_ms,1100);
});
test("knee geometry restores image aspect ratio and rejects uncertain landmarks", () => {
  const points=Array.from({length:33},()=>({x:.5,y:.5,visibility:1,presence:1}));
  points[11]={x:.4,y:.2,visibility:1};points[23]={x:.4,y:.4,visibility:1};
  points[25]={x:.5,y:.5,visibility:1};points[27]={x:.6,y:.4,visibility:1};
  const observation=kneeObservation(points,200,100);
  assert.ok(Math.abs(observation.angle-126.86989764584402)<1e-8);
  points[25].visibility=.2;assert.equal(kneeObservation(points,200,100).valid,false);
  points[25].visibility=1;points[27].y=1.1;assert.equal(kneeObservation(points,200,100).reason,"out_of_frame");
  assert.equal(kneeObservation(null,200,100).reason,"no_pose");
});
test("manual corrections retain raw events, prevent double retract, and can be undone", () => {
  const c=new SquatCounter(),feed=sequence(c);feed(170);feed(80);feed(170);
  assert.equal(c.correctedTotal,1);
  c.correct("retract_auto",1300,"auto-1");assert.equal(c.correctedTotal,0);
  assert.throws(()=>c.correct("retract_auto",1300,"auto-1"));
  c.correct("add_manual",1400);assert.equal(c.correctedTotal,1);
  assert.equal(c.events.length,1);assert.equal(c.corrections.length,2);
  c.undoCorrection(1500);assert.equal(c.correctedTotal,0);
  c.undoCorrection(1600);assert.equal(c.correctedTotal,1);
  assert.equal(c.undoCorrection(1700),null);
  assert.equal(c.events.length,1);assert.equal(c.corrections.length,4);
});
