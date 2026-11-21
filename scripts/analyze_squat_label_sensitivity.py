"""Compare explicit label assumptions; never convert unresolved candidates to confirmed truth."""

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.squat_evaluation import evaluate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT/"reports/squat_counter/submission_20261121/label_sensitivity.json")
    args = parser.parse_args()
    reference = json.loads((ROOT/"user_test/squat_synthetic_human_reference.json").read_text(encoding="utf-8"))
    experiments = ROOT/"reports/squat_counter/synthetic_v2"
    scenarios = [
        {"id": "all_candidates_valid", "assumption": "假设全部15个候选均满足既定动作规则；尚未人工确认。", "excluded": {}},
        {"id": "shallow_and_short_stand_invalid", "assumption": "假设正常前2次、光变前3次浅蹲均无效，遮挡第2次短站立无效；其他候选有效。这是敏感性假设，非人工判定。",
         "excluded": {"normal_light": [1, 2], "light_change": [1, 2, 3], "occlusion": [2]}},
    ]
    for scenario in scenarios:
        results = []
        for name, item in reference["videos"].items():
            for side in ("left", "right"):
                folder = name if side == "left" else f"{name}_right"
                session = json.loads((experiments/folder/"session.json").read_text(encoding="utf-8"))
                rows = [{"source_id": session["source"]["sha256"], "event_id": f"{name}-{n}",
                         "condition": item["condition"], "time_ms": round(t*1000)}
                        for n, t in enumerate(item["stand_seconds"], 1) if n not in scenario["excluded"].get(name, [])]
                score = evaluate(session, rows, tolerance_ms=1200)
                results.append({"video": name, "side": side, "source_sha256": session["source"]["sha256"],
                    "assumed_valid_count": score["ground_truth_count"], "raw_automatic_count": score["raw_automatic_count"],
                    "matched_count": score["matched_count"], "false_count_if_assumption_holds": score["false_count"],
                    "missed_count_if_assumption_holds": score["missed_count"],
                    "reference_to_feedback_median_ms": score["feedback_delay_median_ms"],
                    "reference_to_feedback_p95_ms": score["feedback_delay_p95_ms"],
                    "timing_samples": score["feedback_delay_samples"], "negative_timing_samples": score["negative_delay_samples"],
                    "unmatched_assumed_valid_events": score["unmatched_truth"], "unmatched_automatic_events": score["unmatched_auto"],
                    "matches_under_assumption": score["matches"]})
        scenario["results"] = results
    output = {"kind": "候选标签假设的敏感性分析；非正式识别评分", "client_date": "2026-11-21",
        "page_version": "squat-counter-v2", "new_model_inference": False, "human_decisions_applied": False,
        "matching_tolerance_ms": 1200, "scenarios": scenarios, "formal_recognition_metrics": None,
        "note": "两种假设下都重新匹配全部自动事件；不只减少漏计而忽略可能新增的误计。保留左右侧；没有新增同学样本。"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps([{ "scenario": s["id"], "right": [
        {k: r[k] for k in ("video", "assumed_valid_count", "raw_automatic_count", "false_count_if_assumption_holds", "missed_count_if_assumption_holds")}
        for r in s["results"] if r["side"] == "right"]} for s in scenarios], ensure_ascii=False))


if __name__ == "__main__":
    main()
