"""Capture an uninterrupted 1x CPU-model session; annotations are evaluated separately."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

from playwright.sync_api import expect, sync_playwright

from check_squat_ui import download, open_component


ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--side", choices=["left", "right"], default="left")
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        parser.error("输出目录必须为空，避免覆盖已保存的会话")
    args.output.mkdir(parents=True, exist_ok=True)
    source_hash = sha256(args.video)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        frame = open_component(page, args.url)
        expect(frame.locator("#pageVersion")).to_have_text("squat-counter-v2")
        frame.locator("#consent").check()
        frame.locator("#side").select_option(args.side)
        frame.locator("#file").set_input_files(str(args.video.resolve()))
        expect(frame.locator("#sourceInfo")).to_contain_text("已载入", timeout=30000)
        iframe = next(f for f in page.frames if "squat_counter" in f.url)
        duration = iframe.evaluate("document.getElementById('video').duration")
        started = time.monotonic()
        frame.locator("#start").click()
        expect(frame.locator("#sessionState")).to_contain_text("已结束", timeout=int(duration*1000+90000))
        iframe.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
        elapsed = time.monotonic()-started
        session = download(page, frame)
        checks = {
            "source_hash_matches": session["source"]["sha256"] == source_hash,
            "real_cpu_model": session["model"]["inference_mode"] == "mediapipe" and session["model"]["delegate"] == "CPU",
            "page_v2": session["page_version"] == "squat-counter-v2",
            "video_completed": session["session"].get("end_reason") == "video_finished",
            "no_manual_pause_or_correction": not session["corrections"] and [a["kind"] for a in session["actions"]] == ["start", "video_finished", "export"],
            "one_x_playback": iframe.evaluate("document.getElementById('video').playbackRate") == 1,
            "trace_present": bool(session["frame_trace"]),
            "no_page_errors": not errors,
        }
        commit = None
        if (ROOT/".git").exists() and shutil.which("git"):
            revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
            if revision.returncode == 0:
                commit = revision.stdout.strip()
        metadata = {
            "kind": "自动连续技术运行；非同学操作记录，不自动确认标注有效性",
            "code_commit": commit,
            "source_name": args.video.name, "source_sha256": source_hash,
            "duration_seconds": duration, "browser": browser.version,
            "headless": True, "side": args.side, "playback_rate": 1,
            "wall_seconds_including_model_load": elapsed,
            "checks": checks, "page_errors": errors,
            "permission_note": "自动勾选测试入口；素材来源及许可须另外登记，此勾选不构成许可证明。",
            "source_code_sha256": {name: sha256(ROOT/name) for name in (
                "src/squat_frontend/app.mjs", "src/squat_frontend/counter.mjs",
                "src/squat_frontend/pose_worker.mjs", "src/squat_frontend/asset_manifest.json")},
        }
        for name, data in (("session", session), ("run_metadata", metadata)):
            (args.output/f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        assert all(checks.values()), metadata
        browser.close()
        print(json.dumps({"source": args.video.name, "automatic_count": session["automatic_count"],
                          "frames": len(session["frame_trace"]), "checks": checks}, ensure_ascii=False))


if __name__ == "__main__":
    main()
