"""Run the same consented clip in frozen v1 and v2; technical checks, not a human retest."""

import argparse
import hashlib
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from check_squat_ui import download, open_component


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--phase", choices=["before", "after"], required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with args.video.open("rb") as source:
        source_hash = hashlib.file_digest(source, "sha256").hexdigest()
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width":1440,"height":1100})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        frame = open_component(page, args.url)
        frame.locator("#consent").check()
        frame.locator("#file").set_input_files(str(args.video.resolve()))
        expect(frame.locator("#sourceInfo")).to_contain_text("已载入", timeout=30000)
        frame.locator("#start").click()
        expect(frame.locator("#sessionState")).to_contain_text("已结束", timeout=120000)
        iframe = next(f for f in page.frames if "squat_counter" in f.url)
        iframe.wait_for_function("document.getElementById('video').readyState >= 2")
        end_position = iframe.evaluate("document.getElementById('video').currentTime")
        initial = download(page, frame)
        assert initial["source"]["sha256"] == source_hash
        assert initial["model"]["inference_mode"] == "mediapipe"
        version = "squat-counter-v1" if args.phase == "before" else "squat-counter-v2"
        assert initial["page_version"] == version
        duration = initial["source"]["duration_ms"]/1000
        frame.locator("#add").click()
        default = download(page, frame)
        assert default["automatic_count"] == initial["automatic_count"]
        assert default["corrected_count"] == initial["automatic_count"] + 1
        panel = frame.locator(".count-panel")
        panel.scroll_into_view_if_needed()
        box = panel.bounding_box()
        page.evaluate("y=>document.querySelector('[data-testid=stMain]').scrollBy(0,y-100)", box["y"])
        panel.screenshot(path=str(args.output/"default_correction.png"))
        frame.locator("#undoCorrection").click()
        frame.locator("#review").evaluate("el=>{el.value=5;el.dispatchEvent(new Event('input',{bubbles:true}));}")
        iframe.wait_for_function("!document.getElementById('video').seeking && Math.abs(document.getElementById('video').currentTime-5)<.001")
        frame.locator("#add").click()
        selected = download(page, frame)
        assert abs(selected["corrections"][-1]["time_ms"] - 5000) < 1
        checks = {"real_cpu_model":True, "same_source_hash":True,
                  "raw_events_preserved":selected["auto_events"] == initial["auto_events"],
                  "existing_review_selects_5_seconds":True}
        if args.phase == "after":
            assert abs(end_position-duration) < .01
            assert abs(default["corrections"][0]["time_ms"] - initial["source"]["duration_ms"]) < 1
            checks["end_position_preserved"] = True
            expect(frame.locator("#correctionTime")).to_have_value("5.000")
            frame.locator("#correctionTime").fill("15.000")
            frame.locator("#correctionTime").evaluate("el=>el.dispatchEvent(new Event('change',{bubbles:true}))")
            iframe.wait_for_function("!document.getElementById('video').seeking && Math.abs(document.getElementById('video').currentTime-15)<.001")
            frame.locator("#add").click()
            numeric = download(page, frame)
            assert numeric["corrections"][-1]["time_ms"] == 15000
            checks["precise_manual_time_preserved"] = True
            before_count = frame.locator("#correctedCount").inner_text()
            frame.locator("#correctionTime").fill(str(duration+1))
            frame.locator("#add").click()
            expect(frame.locator("#correctedCount")).to_have_text(before_count)
            expect(frame.locator("#correctionState")).to_contain_text("请输入")
            checks["out_of_range_correction_rejected"] = True
            frame.locator("#correctionTime").fill("15.000")
            (args.output/"numeric_session.json").write_text(json.dumps(numeric,ensure_ascii=False,indent=2),encoding="utf-8")
        else:
            assert end_position < .01 and default["corrections"][0]["time_ms"] == 0
            checks["v1_position_reset_reproduced"] = True
        for name, data in [("initial_session",initial),("default_session",default),("selected_session",selected)]:
            (args.output/f"{name}.json").write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
        result = {"kind":"自动技术复测，非同学复测；5秒/15秒仅测试输入控件，不是漏计真值",
                  "phase":args.phase,"page_version":version,"browser":browser.version,
                  "source_sha256":source_hash,"duration_seconds":duration,
                  "end_position_seconds":end_position,"default_correction_ms":default["corrections"][0]["time_ms"],
                  "raw_automatic_count":initial["automatic_count"],"checks":checks,"page_errors":errors,
                  "recognition_metrics":None,"human_retest_participants":0}
        assert not errors and all(checks.values()), result
        (args.output/"technical_retest.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        browser.close()
        print(json.dumps(result,ensure_ascii=False))


if __name__ == "__main__":
    main()
