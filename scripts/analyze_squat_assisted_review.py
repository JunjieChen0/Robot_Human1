"""Report bounded errors from AI-assisted review; retain uncertainty and original sessions."""

import hashlib
import itertools
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.squat_evaluation import evaluate


def main():
    review_path = ROOT / "user_test/squat_synthetic_assisted_review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    reference = json.loads((ROOT / "user_test/squat_synthetic_human_reference.json").read_text(encoding="utf-8"))
    results = []
    for name, item in reference["videos"].items():
        events = [e for e in review["events"] if e["video"] == name]
        assert len(events) == 5 and len({e["event_id"] for e in events}) == 5
        assert [e["candidate_stand_ms"] for e in events] == [round(t * 1000) for t in item["stand_seconds"]]
        valid = [e for e in events if e["decision"] == "valid"]
        uncertain = [e for e in events if e["decision"] == "uncertain"]
        assert all(e["decision"] in {"valid", "invalid", "uncertain"} for e in events)
        for side in ("left", "right"):
            folder = name if side == "left" else f"{name}_right"
            session_path = ROOT / "reports/squat_counter/synthetic_v2" / folder / "session.json"
            session = json.loads(session_path.read_text(encoding="utf-8"))
            assert all(e["source_sha256"] == session["source"]["sha256"] for e in events)

            def score(selected):
                rows = [{"source_id": e["source_sha256"], "event_id": e["event_id"],
                         "condition": item["condition"], "time_ms": e["candidate_stand_ms"]} for e in selected]
                return evaluate(session, rows, tolerance_ms=1200)

            combinations = []
            for bits in itertools.product((False, True), repeat=len(uncertain)):
                included = [e for e, bit in zip(uncertain, bits) if bit]
                scored = score(valid + included)
                combinations.append({"uncertain_assumed_valid": [e["event_id"] for e in included],
                    "assumed_valid_count": scored["ground_truth_count"],
                    "matched_count": scored["matched_count"], "false_count": scored["false_count"],
                    "missed_count": scored["missed_count"]})
            certain = score(valid)
            results.append({"video": name, "side": side, "condition": item["condition"],
                "session_sha256": hashlib.sha256(session_path.read_bytes()).hexdigest(),
                "review_valid_count": len(valid), "review_invalid_count": sum(e["decision"] == "invalid" for e in events),
                "review_uncertain_count": len(uncertain), "raw_automatic_count": len(session["auto_events"]),
                "false_count_range": [min(c["false_count"] for c in combinations), max(c["false_count"] for c in combinations)],
                "missed_count_range": [min(c["missed_count"] for c in combinations), max(c["missed_count"] for c in combinations)],
                "valid_review_event_matches": certain["matches"],
                "valid_review_event_feedback_samples": certain["feedback_delay_samples"],
                "valid_review_event_feedback_median_ms": certain["feedback_delay_median_ms"],
                "valid_review_event_feedback_p95_ms": certain["feedback_delay_p95_ms"],
                "negative_feedback_samples": certain["negative_delay_samples"],
                "all_uncertain_assignments": combinations})
    output = {"kind": "用户人工候选参照与AI辅助有效性复核的误差范围；不是独立人工真值评分",
        "client_date": "2026-11-21", "page_version": "squat-counter-v2", "new_model_inference": False,
        "new_human_participants": 0, "human_rule_adjudication_added": False,
        "review_sha256": hashlib.sha256(review_path.read_bytes()).hexdigest(),
        "matching_tolerance_ms": 1200, "formal_recognition_metrics": None, "results": results,
        "limitations": ["范围穷举每项不确定动作的有效/无效组合，固定本次AI辅助明确项；不是置信区间。",
            "AI视觉筛查没有独立人工量角，不确定项不强行定性；明确项仍是AI辅助判断。",
            "延迟只列暂定有效且匹配的事件，使用用户原站立起点；时间精度未另确认，非光电屏幕实测。",
            "材料为AI生成及后期处理视频，不支持真实场景泛化结论；未增加同学或真人改后测试。"]}
    path = ROOT / "reports/squat_counter/submission_20261121/assisted_review_metrics.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps([{k: r[k] for k in ("video", "side", "false_count_range", "missed_count_range",
        "valid_review_event_feedback_samples", "valid_review_event_feedback_median_ms")} for r in results], ensure_ascii=False))


if __name__ == "__main__":
    main()
