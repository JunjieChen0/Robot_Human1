"""Match raw automatic squat events to manual annotations; never score corrected totals."""

import argparse
import csv
import json
import math
from pathlib import Path
import statistics


CONDITIONS = {"normal", "light_change", "occlusion"}


def match_events(truth, predicted, tolerance_ms):
    """Ordered one-to-one match: maximize matches, then minimize total timestamp error."""
    n, m = len(truth), len(predicted)
    scores = [[(0, 0.0) for _ in range(m + 1)] for _ in range(n + 1)]
    choices = {}
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            candidates = [(scores[i + 1][j], "skip_truth"), (scores[i][j + 1], "skip_predicted")]
            delta = abs(truth[i]["time_ms"] - predicted[j]["time_ms"])
            if delta <= tolerance_ms:
                count, cost = scores[i + 1][j + 1]
                candidates.append(((count + 1, cost - delta), "match"))
            scores[i][j], choices[i, j] = max(candidates, key=lambda item: item[0])
    i = j = 0
    pairs = []
    while i < n and j < m:
        choice = choices[i, j]
        if choice == "match":
            pairs.append((i, j))
            i += 1
            j += 1
        elif choice == "skip_truth":
            i += 1
        else:
            j += 1
    return pairs


def percentile(values, p):
    ordered = sorted(values)
    position = (len(ordered) - 1) * p
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def evaluate(session, annotations, tolerance_ms=1200):
    if not math.isfinite(tolerance_ms) or tolerance_ms < 0:
        raise ValueError("匹配窗口必须是非负有限毫秒数")
    if session["model"].get("inference_mode") != "mediapipe":
        raise ValueError("模拟关键点不能计入真实识别效果；仅用真实MediaPipe会话进行此评价")
    if not session["session"].get("ended_at"):
        raise ValueError("会话尚未结束，请先结束并重新导出")
    if any(row["kind"] in {"pause", "resume"} for row in session["actions"]):
        raise ValueError("性能测试需连续处理，不能包含手动暂停/继续；用户操作测试请单独记录")
    if session["source"].get("kind") == "video" and not any(row["kind"] == "video_finished" for row in session["actions"]):
        raise ValueError("视频未完整处理；性能测试请使用完整片段，局部测试应先剪成独立视频")
    expected_source = session["source"].get("sha256") or session["session"]["id"]
    if not annotations:
        raise ValueError("人工标注为空；空模板不是已完成测试")
    if any(row["source_id"] != expected_source for row in annotations):
        raise ValueError("标注source_id与视频SHA256/摄像头会话ID不一致")
    conditions = {row["condition"] for row in annotations}
    if len(conditions) != 1 or not conditions.issubset(CONDITIONS):
        raise ValueError("每次评价只接受一个条件：normal、light_change或occlusion")
    truth = [{**row, "time_ms": float(row["time_ms"])} for row in annotations]
    predicted = session["auto_events"]
    for rows, id_key in ((truth, "event_id"), (predicted, "id")):
        if len({row[id_key] for row in rows}) != len(rows):
            raise ValueError("事件ID重复，不能重复计入")
        if any(not math.isfinite(row["time_ms"]) or row["time_ms"] < 0 for row in rows):
            raise ValueError("事件时间必须是非负有限毫秒数")
    truth = sorted(truth, key=lambda row: row["time_ms"])
    predicted = sorted(predicted, key=lambda row: row["time_ms"])
    pairs = match_events(truth, predicted, tolerance_ms)
    matched_truth = {i for i, _ in pairs}
    matched_predicted = {j for _, j in pairs}
    matches, delays = [], []
    for i, j in pairs:
        feedback = predicted[j].get("feedback_time_ms")
        delay = None if feedback is None else feedback - truth[i]["time_ms"]
        if delay is not None:
            if not math.isfinite(delay):
                raise ValueError("反馈时间不是有限数值")
            delays.append(delay)
        matches.append({"truth_id": truth[i]["event_id"], "auto_id": predicted[j]["id"],
                        "truth_time_ms": truth[i]["time_ms"], "auto_time_ms": predicted[j]["time_ms"],
                        "feedback_delay_ms": delay})
    return {
        "kind": "真实模型会话与人工事件标注的逐次匹配；非用户操作评分",
        "source_id": expected_source, "condition": next(iter(conditions)), "page_version": session["page_version"],
        "tolerance_ms": tolerance_ms, "matching": "maximum one-to-one matches, then minimum timestamp difference",
        "ground_truth_count": len(truth), "raw_automatic_count": len(predicted),
        "corrected_count_not_used_for_scoring": session["corrected_count"], "matched_count": len(pairs),
        "false_count": len(predicted) - len(pairs), "missed_count": len(truth) - len(pairs),
        "unmatched_truth": [row for i, row in enumerate(truth) if i not in matched_truth],
        "unmatched_auto": [row for j, row in enumerate(predicted) if j not in matched_predicted],
        "matches": matches, "feedback_delay_samples": len(delays),
        "feedback_delay_median_ms": statistics.median(delays) if delays else None,
        "feedback_delay_p95_ms": percentile(delays, .95) if delays else None,
        "negative_delay_samples": sum(value < 0 for value in delays),
        "timing_note": "1倍速源时间轴加帧处理至后续渲染回调的耗时估计；包含300毫秒稳定确认的事件偏移；非光电屏幕实测。缺失延迟不填0，负值保留供复核。",
        "invalid_frame_count": sum(not row["valid"] for row in session["frame_trace"]),
        "limitation": "匹配窗口需测试前固定；超窗延迟可能同时记为未匹配误计与漏计，需连同原片段复核。遮挡导致的漏计不因系统暂停而删除。"
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", required=True, type=Path)
    parser.add_argument("--annotations", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--tolerance-ms", type=float, default=1200)
    args = parser.parse_args()
    session = json.loads(args.session.read_text(encoding="utf-8"))
    with args.annotations.open(encoding="utf-8-sig", newline="") as source:
        annotations = list(csv.DictReader(source))
    result = evaluate(session, annotations, args.tolerance_ms)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("ground_truth_count", "raw_automatic_count", "false_count", "missed_count", "feedback_delay_median_ms")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
