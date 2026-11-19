// The browser and Node tests use this same counting rule. No image inference here.
export const VERSION = "squat-counter-v2";
export const RULES = Object.freeze({standAngle: 160, downAngle: 100, stableMs: 300,
  maxGapMs: 500, minVisibility: 0.65});

export function kneeObservation(landmarks, width, height, side = "left") {
  const indices = side === "left" ? [11, 23, 25, 27] : [12, 24, 26, 28];
  const points = indices.map(index => landmarks?.[index]);
  if (!points.every(Boolean)) return {valid: false, reason: "no_pose"};
  const visibility = Math.min(...points.map(p => Math.min(p.visibility ?? 0, p.presence ?? p.visibility ?? 0)));
  if (!Number.isFinite(visibility) || visibility < RULES.minVisibility)
    return {valid: false, reason: "low_visibility", visibility};
  if (!points.every(p => Number.isFinite(p.x) && Number.isFinite(p.y) && p.x > .02 && p.x < .98 && p.y > .02 && p.y < .98))
    return {valid: false, reason: "out_of_frame", visibility};
  const [, hip, knee, ankle] = points;
  // Normalized x and y have different scales: restore the frame aspect ratio.
  const a = [(hip.x - knee.x) * width, (hip.y - knee.y) * height];
  const b = [(ankle.x - knee.x) * width, (ankle.y - knee.y) * height];
  const norm = Math.hypot(...a) * Math.hypot(...b);
  if (!Number.isFinite(norm) || norm < 1e-6) return {valid: false, reason: "degenerate", visibility};
  const angle = Math.acos(Math.max(-1, Math.min(1, (a[0]*b[0] + a[1]*b[1])/norm))) * 180 / Math.PI;
  return {valid: true, angle, visibility, points: points.map(p => ({x: p.x, y: p.y}))};
}

export class SquatCounter {
  constructor() {
    this.events = [];
    this.corrections = [];
    this.invalidate("initial");
  }
  invalidate(reason) {
    this.phase = "need_stand";
    this.candidate = null;
    this.lastMs = null;
    this.reason = reason;
  }
  observe({angle, timeMs, valid = true, reason = "unclear"}) {
    if (!valid || !Number.isFinite(angle) || !Number.isFinite(timeMs)) {
      this.invalidate(reason);
      return {phase: this.phase, reason, event: null};
    }
    if (this.lastMs !== null && (timeMs <= this.lastMs || timeMs - this.lastMs > RULES.maxGapMs))
      this.invalidate("time_gap");
    this.lastMs = timeMs;
    const zone = angle >= RULES.standAngle ? "stand" : angle <= RULES.downAngle ? "down" : "between";
    if (!this.candidate || this.candidate.zone !== zone) this.candidate = {zone, since: timeMs};
    let event = null;
    // Browser timestamp conversion can represent exactly 300ms as 299.999999999998ms.
    if (timeMs - this.candidate.since + 1e-6 >= RULES.stableMs) {
      if (this.phase === "need_stand" && zone === "stand") {
        this.phase = "ready";
        this.reason = "";
      } else if (this.phase === "ready" && zone === "down") {
        this.phase = "down";
      } else if (this.phase === "down" && zone === "stand") {
        event = {id: `auto-${this.events.length + 1}`, time_ms: timeMs, angle};
        this.events.push(event);
        this.phase = "ready";
        this.candidate = null;
      }
    }
    return {phase: this.phase, zone, reason: this.reason, event};
  }
  get activeCorrections() {
    const cancelled = new Set(this.corrections.filter(c => c.kind === "cancel_correction").map(c => c.target_id));
    return this.corrections.filter(c => c.kind !== "cancel_correction" && !cancelled.has(c.id));
  }
  isRetracted(id) { return this.activeCorrections.some(c => c.kind === "retract_auto" && c.target_id === id); }
  get correctedTotal() {
    return this.events.length + this.activeCorrections.reduce((n, c) => n + c.delta, 0);
  }
  correct(kind, timeMs, targetId = null) {
    if (!Number.isFinite(timeMs)) throw new Error("修正时间无效");
    if (kind === "retract_auto" && (!this.events.some(e => e.id === targetId) || this.isRetracted(targetId)))
      throw new Error("请选择尚未撤销的自动记录");
    if (!["add_manual", "retract_auto"].includes(kind)) throw new Error("未知修正操作");
    const item = {id: `correction-${this.corrections.length + 1}`, kind, time_ms: timeMs,
      target_id: targetId, delta: kind === "add_manual" ? 1 : -1};
    this.corrections.push(item);
    return item;
  }
  undoCorrection(timeMs) {
    const item = this.activeCorrections.at(-1);
    if (!item) return null;
    const undo = {id: `correction-${this.corrections.length + 1}`, kind: "cancel_correction",
      time_ms: timeMs, target_id: item.id, delta: -item.delta};
    this.corrections.push(undo);
    return undo;
  }
}
