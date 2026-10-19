"""003 的实际浏览器操作与取证；记录 AI 自动化过程，不代表真人测试。"""

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import time
import traceback
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
TZ = timezone(timedelta(hours=8))


def now():
    return datetime.now(TZ).isoformat(timespec="seconds")


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT).decode("utf-8")


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-python", required=True)
    args = parser.parse_args()
    if (OUT / "run.json").exists():
        raise FileExistsError("已有运行记录，停止以保留原始证据。")
    paths = git("ls-files", "--cached", "--others", "--exclude-standard", "-z").split("\0")
    before = {p: file_hash(ROOT / p) for p in paths if p and (ROOT / p).is_file()}
    manifest = {
        "participant": "003", "kind": "AI 实际浏览器操作，非真人测试",
        "started_at": now(), "prior_exposure": "已阅读指南、源码和既有反馈，不属于盲测或首次理解。",
        "git_head": git("rev-parse", "HEAD").strip(), "git_status_before": git("status", "--short"),
        "driver_python": sys.version, "platform": platform.platform(),
        "viewport": {"width": 1440, "height": 1000},
        "timing": "automation_seconds 仅为脚本执行、等待及取证耗时；真人用时未记录。",
        "tasks": {}, "page_errors": [], "completed": False,
        "existing_file_hashes_before": before,
    }
    metadata = subprocess.check_output([
        args.server_python, "-c",
        "import json,sys,streamlit,sklearn; print(json.dumps(dict(python=sys.version,streamlit=streamlit.__version__,sklearn=sklearn.__version__)))",
    ], cwd=ROOT)
    manifest["server_environment"] = json.loads(metadata)
    url = "http://127.0.0.1:8503"
    manifest["url"] = url
    server_log = (OUT / "server.log").open("w", encoding="utf-8")
    server = subprocess.Popen([
        args.server_python, "-m", "streamlit", "run", "app.py",
        "--server.address", "127.0.0.1", "--server.port", "8503",
        "--server.headless", "true", "--browser.gatherUsageStats", "false",
    ], cwd=ROOT, stdout=server_log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
    page = None
    try:
        for _ in range(60):
            if server.poll() is not None:
                raise RuntimeError("测试服务退出，请检查 server.log。")
            try:
                with urllib.request.urlopen(url + "/_stcore/health", timeout=1) as response:
                    if response.read() == b"ok":
                        break
            except OSError:
                time.sleep(0.5)
        else:
            raise TimeoutError("测试服务未就绪。")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            manifest["browser"] = "Google Chrome " + browser.version
            context = browser.new_context(viewport=manifest["viewport"], device_scale_factor=1, accept_downloads=True)
            page = context.new_page()
            page.on("pageerror", lambda error: manifest["page_errors"].append(str(error)))
            page.set_default_timeout(20000)

            def idle():
                expect(page.get_by_test_id("stApp")).to_have_attribute("data-test-script-state", "notRunning")

            def metrics():
                return page.get_by_test_id("stMetric").all_inner_texts()

            def capture(name, target=None, full=False):
                idle()
                if target is not None:
                    target.scroll_into_view_if_needed()
                page.screenshot(path=str(OUT / (name + ".png")), full_page=full)
                (OUT / (name + ".txt")).write_text(page.locator("body").inner_text(), encoding="utf-8")

            def radio(name):
                control = page.get_by_role("radio", name=name, exact=True)
                control.focus()
                control.press("Space")
                expect(control).to_be_checked()
                idle()

            def select(label, option):
                control = page.get_by_role("combobox", name=label, exact=True)
                control.click()
                page.get_by_role("option", name=option, exact=True).click()
                expect(control).to_contain_text(option)
                idle()

            def finish(task, started, **data):
                manifest["tasks"][task] = {"status": "完整", "automation_seconds": round(time.perf_counter() - started, 3), **data}
                (OUT / "run.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
                print(json.dumps({"task": task, **manifest["tasks"][task]}, ensure_ascii=False), flush=True)

            page.goto(url)
            analyze = page.get_by_role("button", name="🔍 估计并分析趋势", exact=True)
            analyze.wait_for()
            idle()
            assert page.get_by_text("尚无分析结果。", exact=False).is_visible()
            manifest["fresh_session"] = True

            started = time.perf_counter()
            page.get_by_text("导入个人档案（CSV）", exact=True).click()
            page.locator('input[type="file"]').set_input_files(str(ROOT / "data/sample/profile_template.csv"))
            page.get_by_role("button", name="校验并载入档案", exact=True).click()
            page.get_by_text("校验通过，已载入表单。", exact=False).wait_for()
            height = page.get_by_role("spinbutton", name="身高（米）", exact=True)
            weight = page.get_by_role("spinbutton", name="体重（千克）", exact=True)
            expect(height).to_have_value("1.70")
            expect(weight).to_have_value("70.0")
            capture("T1_import", page.get_by_role("heading", name="当前输入概览", exact=True))
            finish("T1", started, height=height.input_value(), weight=weight.input_value(), answer="身高单位米，体重单位千克；使用仓库示例 CSV，不是个人健康记录。")

            started = time.perf_counter()
            expect(page.get_by_role("checkbox", name="同时分析体重趋势（可选）", exact=True)).to_be_checked()
            intake = page.get_by_role("spinbutton", name="每日摄入热量（kcal）", exact=True)
            intake.fill("1800")
            intake.press("Enter")
            idle()
            analyze.click()
            result = page.get_by_role("heading", name="③ 分析结果与解释", exact=True)
            trend = page.get_by_role("heading", name="体重趋势与外推", exact=True)
            trend.wait_for()
            capture("T2_classification", result)
            capture("T2_trend", trend)
            baseline = metrics()
            finish("T2", started, metrics=baseline, answer="分类估计当前输入所属的肥胖等级；趋势采用独立的模拟体重日志，未来曲线是能量平衡外推。")

            started = time.perf_counter()
            explanation = page.get_by_role("heading", name="解释反馈", exact=True)
            capture("T3_explanation", explanation)
            scope = page.locator('details').filter(has=page.locator('summary', has_text="数据来源与适用范围"))
            scope.locator("summary").click()
            expect(scope).to_have_attribute("open", "")
            expect(scope).to_contain_text("SMOTE")
            capture("T3_scope", scope)
            finish("T3", started, answer="类别概率 80% 不等于个体患病风险或绝对正确率；页面说明尚未验证新群体适用性，不能推广为所有大学生的健康结论。", first_understanding_eligible=False)

            started = time.perf_counter()
            weight.fill("80")
            weight.press("Enter")
            stale = page.get_by_text("输入已修改，请重新分析。", exact=False)
            stale.wait_for()
            capture("T4_stale", stale)
            stale_metrics = metrics()
            analyze.click()
            comparison = page.get_by_role("heading", name="修改前后对比", exact=True)
            comparison.wait_for()
            idle()
            expect(stale).to_have_count(0)
            capture("T4_updated", result)
            capture("T4_comparison", comparison)
            capture("T4_trend", trend)
            updated = metrics()
            finish("T4", started, stale_metrics=stale_metrics, updated_metrics=updated, weight=weight.input_value())

            started = time.perf_counter()
            intake.fill("0")
            intake.press("Enter")
            idle()
            analyze.click()
            error = page.get_by_text("该次趋势未生成：", exact=False)
            error.wait_for()
            idle()
            expect(trend).to_have_count(0)
            expect(page.get_by_role("heading", name="肥胖等级估计", exact=True)).to_be_visible()
            capture("T5_error", error)
            invalid = metrics()
            intake.fill("1800")
            intake.press("Enter")
            idle()
            analyze.click()
            trend.wait_for()
            capture("T5_recovered", trend)
            expect(weight).to_have_value("80.0")
            recovered = metrics()
            finish("T5", started, invalid_metrics=invalid, recovered_metrics=recovered, prescribed_error=True)

            started = time.perf_counter()
            radio("3")
            radio("根据当前输入估计的肥胖等级")
            page.get_by_role("textbox", name="遇到的问题或改进建议（可选）", exact=True).fill("003：AI 实际浏览器操作。建议将档案体重、日志体重与修改前后对比集中显示；此评分为 AI 界面评估，不作为真人满意度。")
            page.get_by_role("button", name="保存本次反馈", exact=True).click()
            page.get_by_text("反馈已保存在当前会话，可下载留存。", exact=True).wait_for()
            download_button = page.get_by_role("button", name="下载匿名反馈（JSON）", exact=True)
            capture("T6_feedback", download_button)
            with page.expect_download() as downloaded:
                download_button.click()
            downloaded.value.save_as(str(OUT / "weighttrend_feedback.json"))
            feedback = json.loads((OUT / "weighttrend_feedback.json").read_text(encoding="utf-8"))
            assert feedback["ease_1_to_5"] == 3 and feedback["understood_classification"] is True
            radio("模型公平性审核")
            fairness = page.get_by_role("heading", name="模型公平性审核", exact=True)
            fairness.wait_for()
            for group in ("女性", "男性", "全部群体"):
                select("查看群体", group)
                capture("T6_group_" + {"女性": "female", "男性": "male", "全部群体": "all"}[group], page.get_by_role("combobox", name="查看群体", exact=True))
            for metric, name in (("漏判率 FNR", "fnr"), ("误判率 FPR", "fpr")):
                select("比较指标", metric)
                capture("T6_metric_" + name, page.get_by_role("combobox", name="比较指标", exact=True))
            uncertainty = page.locator('details').filter(has=page.locator('summary', has_text="错误率的不确定性"))
            uncertainty.locator("summary").click()
            expect(uncertainty).to_have_attribute("open", "")
            expect(uncertainty).to_contain_text("Wilson")
            capture("T6_uncertainty", uncertainty)
            group_download = page.get_by_role("button", name="下载分组测试结果", exact=True)
            with page.expect_download() as downloaded:
                group_download.click()
            downloaded.value.save_as(str(OUT / "fairness_group_metrics.csv"))
            fairness_metrics = metrics()
            radio("体重管理原型")
            trend.wait_for()
            expect(weight).to_have_value("80.0")
            expect(intake).to_have_value("1800")
            expect(download_button).to_be_visible()
            capture("T6_return", result)
            returned = metrics()
            assert returned == recovered
            finish("T6", started, feedback=feedback, fairness_metrics=fairness_metrics, groups=["女性", "男性", "全部群体"], metrics=["漏判率 FNR", "误判率 FPR"], returned_metrics=returned, fairness_answer="本次约束未改善整体 EO 差值；女性组本次零错误不能说明完全公平或未来无误判。", fairness_self_test_explanation_opened=False)
            manifest["completed"] = True
            browser.close()
    except Exception:
        manifest["failure"] = traceback.format_exc()
        if page is not None and not page.is_closed():
            page.screenshot(path=str(OUT / "failure.png")), (OUT / "failure.txt").write_text(page.locator("body").inner_text(), encoding="utf-8")
        raise
    finally:
        server.terminate()
        server.wait(timeout=15)
        server_log.close()
        after = {p: file_hash(ROOT / p) if (ROOT / p).is_file() else None for p in before}
        manifest["existing_file_hashes_after"] = after
        manifest["preexisting_files_unchanged"] = before == after
        manifest["finished_at"] = now()
        manifest["evidence_hashes"] = {p.name: file_hash(p) for p in sorted(OUT.iterdir()) if p.is_file() and p.name != "run.json"}
        (OUT / "run.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"completed": manifest["completed"], "page_errors": manifest["page_errors"], "preexisting_files_unchanged": manifest["preexisting_files_unchanged"]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
