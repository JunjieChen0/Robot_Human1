"""Browser acceptance checks. Blank frames use the real CPU model; pose fixtures test UI only."""

import argparse
import json
from pathlib import Path
import subprocess

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
MOCK_WORKER = r"""
self.onmessage=({data:d})=>{
  if(d.kind==='init'){self.postMessage({kind:'ready',inference_mode:'mock_landmarks'});return;}
  const t=d.frameTimeMs;
  const angle=(t>=1000&&t<2200)||(t>=5000&&t<6000)?85:170;
  const a=angle*Math.PI/180;
  const p=Array.from({length:33},()=>({x:.5,y:.5,visibility:1,presence:1}));
  p[11]={x:.45,y:.25,visibility:1};p[25]={x:.45,y:.6,visibility:1};
  p[23]={x:.45+Math.sin(a)*80/d.width,y:.6+Math.cos(a)*80/d.height,visibility:1};
  p[27]={x:.45,y:.6+80/d.height,visibility:1};
  d.bitmap.close();
  self.postMessage({kind:'result',epoch:d.epoch,frameTimeMs:t,captureWallMs:d.captureWallMs,
    width:d.width,height:d.height,landmarks:t>=3500&&t<4200?[]:[p]});
};
"""


def open_component(page, url):
    page.goto(url)
    page.get_by_role("heading", level=1).first.wait_for(state="visible",timeout=60000)
    if not page.get_by_role("heading", name="深蹲计数", exact=True).count():
        radio = page.get_by_role("radio", name="深蹲计数", exact=True)
        radio.wait_for(state="attached")
        radio.focus()
        radio.press("Space")
        expect(page.get_by_role("heading", name="深蹲计数", exact=True)).to_be_visible(timeout=60000)
    frame = page.frame_locator('iframe[title*="squat_counter"]')
    expect(frame.locator("#feedback")).to_be_visible(timeout=60000)
    return frame


def download(page, frame):
    with page.expect_download() as event:
        frame.locator("#download").click()
    return json.loads(Path(event.value.path()).read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8521")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/squat_counter/ui_v1")
    parser.add_argument("--blank-video", type=Path, default=ROOT / "commit/squat_qa/blank.webm")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if not args.blank_video.exists():
        args.blank_video.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=white:s=640x480:r=15",
                        "-t", "8", "-c:v", "libvpx", "-an", str(args.blank_video)], check=True)
    checks, errors = {}, []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True,
                                    args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"])
        page = browser.new_page(viewport={"width":1440,"height":1100})
        page.on("pageerror", lambda error: errors.append(str(error)))
        frame = open_component(page,args.url)
        expect(frame.locator("#file")).to_be_disabled()
        checks["consent_before_input"] = True
        page.screenshot(path=str(args.output/"initial.png"),full_page=True)
        frame.locator("#consent").check()
        frame.locator("#file").set_input_files(str(args.blank_video))
        expect(frame.locator("#sourceInfo")).to_contain_text("已载入",timeout=30000)
        frame.locator("#start").click()
        expect(frame.locator("#modelStatus")).to_have_text("模型：CPU已就绪",timeout=90000)
        expect(frame.locator("#feedback")).to_contain_text("看不清",timeout=30000)
        frame.locator("#feedback").scroll_into_view_if_needed()
        page.screenshot(path=str(args.output/"unclear_real_model.png"),full_page=True)
        frame.locator("#pause").click()
        blank = download(page,frame)
        assert blank["automatic_count"] == 0 and blank["frame_trace"]
        assert blank["model"]["inference_mode"] == "mediapipe"
        assert not any(row["valid"] for row in blank["frame_trace"])
        checks["real_cpu_model_blank_abstains"] = True

        frame.locator("#end").click()
        frame.locator("#sourceMode").select_option("camera")
        expect(frame.locator("#sourceInfo")).to_have_text("请打开摄像头，侧身完整入镜后开始。")
        iframe = next(f for f in page.frames if "squat_counter" in f.url)
        iframe.evaluate("""() => {
          window.nativeCamera=navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
          navigator.mediaDevices.getUserMedia=async options=>{
            const stream=await window.nativeCamera(options);window.pendingTracks=stream.getTracks();
            await new Promise(resolve=>window.releaseCamera=resolve);return stream;
          };
        }""")
        frame.locator("#openCamera").click()
        expect(frame.locator("#openCamera")).to_be_disabled()
        iframe.wait_for_function("window.pendingTracks?.length")
        frame.locator("#consent").uncheck()
        iframe.evaluate("window.releaseCamera()")
        iframe.wait_for_function("window.pendingTracks.every(t=>t.readyState==='ended')")
        expect(frame.locator("#cameraStatus")).to_have_text("摄像头：关闭")
        checks["cancelled_camera_request_releases_late_tracks"]=True
        iframe.evaluate("() => { navigator.mediaDevices.getUserMedia=window.nativeCamera; }")
        frame.locator("#consent").check()
        frame.locator("#openCamera").click()
        expect(frame.locator("#cameraStatus")).to_contain_text("开启",timeout=30000)
        iframe = next(f for f in page.frames if "squat_counter" in f.url)
        iframe.evaluate("window.testTracks=[...document.getElementById('video').srcObject.getTracks()]")
        frame.locator("#start").click()
        expect(frame.locator("#pause")).to_be_enabled(timeout=90000)
        frame.locator("#pause").click()
        expect(frame.locator("#cameraStatus")).to_contain_text("识别已暂停")
        assert iframe.evaluate("window.testTracks.every(t=>t.readyState==='live')")
        frame.locator("#resume").click()
        expect(frame.locator("#pause")).to_be_enabled(timeout=30000)
        frame.locator("#end").click()
        assert iframe.evaluate("window.testTracks.every(t=>t.readyState==='ended')")
        camera=download(page,frame)
        assert camera["model"]["inference_mode"]=="mediapipe"
        checks["camera_pause_resume_end_and_preserved_model_metadata"]=True
        frame.locator("#openCamera").click()
        expect(frame.locator("#cameraStatus")).to_contain_text("开启",timeout=30000)
        iframe.evaluate("window.testTracks=[...document.getElementById('video').srcObject.getTracks()]")
        frame.locator("#closeCamera").click()
        assert iframe.evaluate("window.testTracks.every(t=>t.readyState==='ended')")
        expect(frame.locator("#cameraStatus")).to_have_text("摄像头：关闭")
        checks["camera_close_releases_tracks"] = True
        if page.get_by_role("radio",name="模型判断",exact=True).count():
            frame.locator("#openCamera").click()
            expect(frame.locator("#cameraStatus")).to_contain_text("开启",timeout=30000)
            page.evaluate("window.squatTracks=[...document.querySelector('iframe[title*=squat_counter]').contentWindow.document.getElementById('video').srcObject.getTracks()]")
            radio=page.get_by_role("radio",name="模型判断",exact=True)
            radio.focus();radio.press("Space")
            expect(page.get_by_role("heading",name="模型判断",exact=True)).to_be_visible()
            assert page.evaluate("window.squatTracks.every(t=>t.readyState==='ended')")
            checks["navigation_releases_camera"]=True

        mocked = browser.new_page(viewport={"width":1440,"height":1100})
        mocked.on("pageerror",lambda error:errors.append(str(error)))
        mocked.route("**/pose_worker.mjs",lambda route:route.fulfill(body=MOCK_WORKER,content_type="text/javascript"))
        frame = open_component(mocked,args.url)
        frame.locator("#consent").check();frame.locator("#file").set_input_files(str(args.blank_video))
        expect(frame.locator("#sourceInfo")).to_contain_text("已载入",timeout=30000)
        frame.locator("#start").click()
        expect(frame.locator("#autoCount")).to_have_text("1",timeout=30000)
        frame.locator("#pause").click()
        frame.locator("#retract").click();expect(frame.locator("#correctedCount")).to_have_text("0")
        frame.locator("#add").click();expect(frame.locator("#correctedCount")).to_have_text("1")
        frame.locator("#undoCorrection").click();expect(frame.locator("#correctedCount")).to_have_text("0")
        frame.locator("#undoCorrection").click();expect(frame.locator("#correctedCount")).to_have_text("1")
        checks["corrections_keep_raw_events_and_are_reversible"] = True
        frame.locator("#review").evaluate("el=>{el.value=1.5;el.dispatchEvent(new Event('input',{bubbles:true}));}")
        expect(frame.locator("#autoCount")).to_have_text("1")
        frame.locator("#resume").click()
        expect(frame.locator("#autoCount")).to_have_text("2",timeout=30000)
        expect(frame.locator("#feedback")).to_contain_text("已结束",timeout=15000)
        checks["review_resume_and_end_without_duplicate_counts"] = True
        frame.locator(".record-panel details summary").click()
        frame.locator("#participant").fill("自动检查，非同学")
        frame.locator("#taskCompleted").select_option(label="已完成")
        frame.locator("#noticedError").fill("模拟关键点，仅检查纠错控件，不评价真实识别。")
        frame.locator("#correctionAnswer").fill("撤销、补记与撤销修正均已操作。")
        frame.locator("#saveAnswers").click()
        expect(frame.locator("#participant")).to_be_disabled()
        data=download(mocked,frame)
        assert data["automatic_count"]==2 and data["corrected_count"]==2
        assert len(data["corrections"])==4
        assert data["participant_answers"]["hints"] is None
        assert data["model"]["inference_mode"]=="mock_landmarks"
        checks["export_model_source_trace_and_locked_feedback"] = True
        mocked.screenshot(path=str(args.output/"mock_controls.png"),full_page=True)

        mobile=browser.new_page(viewport={"width":390,"height":844},is_mobile=True,has_touch=True)
        frame=open_component(mobile,args.url)
        if mobile.get_by_test_id("stSidebarCollapseButton").count():
            mobile.get_by_test_id("stSidebarCollapseButton").get_by_role("button").click()
        iframe=next(f for f in mobile.frames if "squat_counter" in f.url)
        checks["mobile_no_component_overflow"]=iframe.evaluate("document.documentElement.scrollWidth<=innerWidth")
        mobile.screenshot(path=str(args.output/"mobile.png"),full_page=True)
        checks["no_uncaught_browser_errors"]=not errors
        result={"kind":"自动浏览器检查；空画面用真实CPU模型，动作与纠错使用明确标记的模拟关键点；无真人测试",
                "page_version":"squat-counter-v1","browser":browser.version,"checks":checks,"page_errors":errors,
                "real_blank_trace_frames":len(blank["frame_trace"]),"human_recognition_metrics":None}
        result["camera_input"]="Chromium synthetic camera; no human imagery"
        (args.output/"browser_checks.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        browser.close()
    assert all(checks.values()),checks
    print(json.dumps(result,ensure_ascii=False))


if __name__=="__main__":
    main()
