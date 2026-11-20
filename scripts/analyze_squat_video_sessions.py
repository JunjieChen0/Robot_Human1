"""Summarize synthetic-video runs against human candidate times, retaining rule uncertainty."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.squat_evaluation import evaluate


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reference_matching(session, rows):
    result = evaluate(session, rows, tolerance_ms=1200)
    return {
        "kind": "人工候选时刻匹配，包含规则有效性待核动作；以下未匹配数不是正式误计/漏计",
        "candidate_event_count": result["ground_truth_count"],
        "matched_candidate_count": result["matched_count"],
        "unmatched_candidate_count": result["missed_count"],
        "unmatched_model_event_count": result["false_count"],
        "unmatched_candidates": result["unmatched_truth"],
        "unmatched_model_events": result["unmatched_auto"],
        "matches": [{"candidate_id": r["truth_id"], "candidate_time_ms": r["truth_time_ms"],
                     "auto_id": r["auto_id"], "auto_time_ms": r["auto_time_ms"],
                     "candidate_to_feedback_estimate_ms": r["feedback_delay_ms"]} for r in result["matches"]],
        "candidate_to_feedback_samples": result["feedback_delay_samples"],
        "candidate_to_feedback_median_ms": result["feedback_delay_median_ms"],
        "candidate_to_feedback_p95_ms": result["feedback_delay_p95_ms"],
        "negative_estimate_samples": result["negative_delay_samples"],
    }


def plot_traces(output, reference):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    from matplotlib.lines import Line2D
    font_path = Path("C:/Windows/Fonts/msyh.ttc")
    if font_path.exists():
        font_manager.fontManager.addfont(str(font_path))
        plt.rcParams["font.family"] = font_manager.FontProperties(fname=str(font_path)).get_name()
    plt.rcParams["axes.unicode_minus"] = False
    fig, axes = plt.subplots(3, 1, figsize=(12, 9.4), sharey=True)
    labels = {"normal_light": "正常光照", "light_change": "后期光线变化", "occlusion": "后期局部遮挡"}
    for ax, (name, item) in zip(axes, reference["videos"].items()):
        s = json.loads((output/f"{name}_right/session.json").read_text(encoding="utf-8"))
        frames = s["frame_trace"]
        ax.plot([r["time_ms"]/1000 for r in frames],
                [r["angle"] if r["valid"] else float("nan") for r in frames], color="#236793", lw=1.5)
        for a, b in zip(frames, frames[1:]):
            if not a["valid"]:
                ax.axvspan(a["time_ms"]/1000, b["time_ms"]/1000, color="#d46a6a", alpha=.17, lw=0)
        for time_s in item["stand_seconds"]:
            ax.axvline(time_s, color="#555555", ls="--", lw=1, alpha=.75)
        for event in s["auto_events"]:
            ax.axvline(event["time_ms"]/1000, color="#178865", lw=1.8)
        for threshold in (100, 160):
            ax.axhline(threshold, color="#999999", ls=":", lw=.9)
        ax.set(xlim=(0, s["source"]["duration_ms"]/1000), ylim=(35, 185), ylabel="模型估计膝角（度）",
               title=f"{labels[name]} · 身体右侧 · 自动 {s['automatic_count']} 次 / 人工候选 5 个")
        ax.grid(axis="y", alpha=.16)
        ax.spines[["top", "right"]].set_visible(False)
    axes[-1].set_xlabel("源视频时间（秒）")
    fig.suptitle("合成视频连续运行：模型轨迹与人工候选时刻", fontsize=17, y=.975)
    fig.legend(handles=[Line2D([], [], color="#236793", label="有效帧膝角"),
        Line2D([], [], color="#555555", ls="--", label="人工候选站立起点（有效性部分待核）"),
        Line2D([], [], color="#178865", lw=2, label="自动计数时刻"),
        Line2D([], [], color="#d46a6a", lw=8, alpha=.35, label="关键点不清，自动暂停计数")],
        loc="lower center", bbox_to_anchor=(.5, .045), ncol=2, frameon=False)
    fig.text(.5, .02, "虚构人物、剪辑及后期条件；非真实环境性能。100° / 160°为既定模型规则，模型角度不能反推人工真值。",
             ha="center", fontsize=9, color="#444444")
    fig.subplots_adjust(top=.91, bottom=.16, hspace=.43, left=.085, right=.98)
    fig.savefig(output/"right_side_traces.png", dpi=160)
    fig.savefig(output/"right_side_traces.svg")
    svg = output/"right_side_traces.svg"
    svg.write_text("\n".join(line.rstrip() for line in svg.read_text(encoding="utf-8").splitlines())+"\n", encoding="utf-8")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--media-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT/"reports/squat_counter/synthetic_v2")
    args = parser.parse_args()
    reference_path = ROOT/"user_test/squat_synthetic_human_reference.json"
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    original_path = ROOT/"user_test/squat_synthetic_annotations_received.json"
    original = json.loads(original_path.read_text(encoding="utf-8"))
    sources, runs = [], []
    for name, item in reference["videos"].items():
        video = args.media_dir/f"{name}.mp4"
        source_hash = sha256(video)
        probe = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate,avg_frame_rate,nb_frames,duration:format=duration",
            "-of", "json", str(video)], text=True))
        sources.append({"name": video.name, "sha256": source_hash, "size_bytes": video.stat().st_size,
                        "ffprobe": probe, "synthetic": True, "effects_and_splices": original["videos"][name]})
        rows = [{"source_id": source_hash, "event_id": f"{name}-{n}", "time_ms": int(round(t*1000)),
                 "condition": item["condition"]} for n, t in enumerate(item["stand_seconds"], 1)]
        for side in ("left", "right"):
            folder = name if side == "left" else f"{name}_right"
            session = json.loads((args.output/folder/"session.json").read_text(encoding="utf-8"))
            metadata = json.loads((args.output/folder/"run_metadata.json").read_text(encoding="utf-8"))
            assert session["source"]["sha256"] == source_hash and session["rules"]["side"] == side
            assert all(metadata["checks"].values()) and len(session["auto_events"]) == session["automatic_count"]
            assert all(0 <= row["time_ms"] <= session["source"]["duration_ms"] for row in rows)
            frames = session["frame_trace"]
            gaps = [b["time_ms"]-a["time_ms"] for a, b in zip(frames, frames[1:])]
            valid = [r for r in frames if r["valid"]]
            angles = [r["angle"] for r in valid]
            result = {"name": name, "condition": item["condition"], "side": side,
                "session_file": f"{folder}/session.json", "metadata_file": f"{folder}/run_metadata.json",
                "session_sha256": sha256(args.output/folder/"session.json"),
                "raw_automatic_count": session["automatic_count"], "auto_event_times_ms": [e["time_ms"] for e in session["auto_events"]],
                "processed_frames": len(frames), "valid_frames": len(valid), "invalid_frames": len(frames)-len(valid),
                "invalid_reasons": dict(Counter(r["reason"] for r in frames if not r["valid"])),
                "first_frame_ms": frames[0]["time_ms"], "last_frame_ms": frames[-1]["time_ms"],
                "maximum_frame_gap_ms": max(gaps), "gaps_above_500ms": sum(g > 500 for g in gaps),
                "median_frame_gap_ms": statistics.median(gaps),
                "min_observed_valid_angle": min(angles) if angles else None,
                "max_observed_valid_angle": max(angles) if angles else None,
                "reference_matching": reference_matching(session, rows),
                "rule_validity_review_event_numbers": item["review_event_numbers"],
                "rule_validity_review_note": item["review_note"],
                "formal_recognition_metrics": None,
            }
            if name == "occlusion":
                result["sensitivity_excluding_candidate_2"] = reference_matching(session, [r for r in rows if r["event_id"] != "occlusion-2"])
                result["sensitivity_note"] = "仅展示若人工最终判定第2次不满足站立300毫秒时的匹配变化，不静默删事件，不确认其余事件有效。"
            runs.append(result)
    summary = {"kind": "合成视频三条件、左右侧完整连续运行及人工候选时刻匹配；非真实环境性能结论",
        "received_date_client": "2026-11-20", "page_version": "squat-counter-v2", "tolerance_ms_fixed_before_run": 1200,
        "annotation_status": reference["formal_metrics_status"], "formal_recognition_metrics": None,
        "sources": sources, "runs": runs,
        "provenance_sha256": {p.name: sha256(p) for p in (reference_path, original_path,
            ROOT/"user_test/squat_synthetic_human_reference.txt")},
        "limitations": ["三段均为AI生成人物及剪辑输入；调光和遮挡为后期效果，不是独立真人样本或真实环境干预。",
            "默认左侧先运行，发现关键点低可见度后补做全部右侧，保留全部六次，不将较好一侧冒充预先固定的唯一结果。",
            "人工补充15个候选时刻与疑点；浅蹲角度/确认时长、遮挡估计及短站立边界尚未逐次裁定。",
            "候选到反馈时间含稳定确认及处理至后续渲染回调估计；不是光电屏幕实测，负值保留；不等同正式反馈延迟。",
            "三段基础动作及剪辑不同，条件间差异不能单独归因于亮度或遮挡；帧有效率也不是识别准确率。",
            "本轮自动运行不增加同学数量，无真人改后复测；素材及联系图仅本地保存，公开原图来源和许可未提供。"]}
    (args.output/"summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    plot_traces(args.output, reference)
    print(json.dumps([{k: r[k] for k in ("name", "side", "raw_automatic_count", "valid_frames", "processed_frames")} for r in runs], ensure_ascii=False))


if __name__ == "__main__":
    main()
