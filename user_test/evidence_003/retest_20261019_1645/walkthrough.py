"""003 更新版 T1–T6 实际操作、计时和状态核对。"""

import hashlib
import json
import platform
import subprocess
import time
import traceback
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
PYTHON = r"C:\Users\Junjie\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"
URL = "http://127.0.0.1:8503"


def now():
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if (OUT / "run.json").exists():
        raise FileExistsError("保留已有记录，请使用新的取证目录。")
    names = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT).decode("utf-8").split("\0")
    before = {name: sha(ROOT / name) for name in names if name and (ROOT / name).is_file()}
    (OUT / "feedback_003_before.md").write_bytes((ROOT / "user_test/feedback_003.md").read_bytes())
    record = {
        "participant": "003", "kind": "AI 实际浏览器复测", "started_at": now(),
        "url": URL, "platform": platform.platform(), "viewport": {"width": 1440, "height": 1000},
        "prior_exposure": "参加过上一轮；本轮已阅读更新后的任务与源码。",
        "timing": "各任务从开始操作至截图及状态核对结束，不含资料阅读、分析和报告填写。",
        "error_rule": "点错控件、传错文件及非任务要求的错误提交计误操作；定位或系统异常单列。",
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip(),
        "git_status_before": subprocess.check_output(["git", "status", "--short"], cwd=ROOT).decode("utf-8"),
        "existing_hashes_before": before, "tasks": {}, "page_errors": [], "completed": False,
    }
    log = (OUT / "server.log").open("w", encoding="utf-8")
    server = subprocess.Popen([
        PYTHON, "-u", "-X", "utf8", "-m", "streamlit", "run", "app.py",
        "--server.port", "8503", "--server.address", "127.0.0.1",
        "--server.headless", "true", "--browser.gatherUsageStats", "false",
    ], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        for _ in range(60):
            if server.poll() is not None:
                raise RuntimeError("服务未启动，参见本轮日志。")
            try:
                with urllib.request.urlopen(URL + "/_stcore/health", timeout=1) as response:
                    if response.read() == b"ok":
                        break
            except OSError:
                time.sleep(0.5)
        else:
            raise TimeoutError("服务启动超时。")
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            record["browser"] = "Google Chrome " + browser.version
            page = browser.new_page(viewport=record["viewport"], accept_downloads=True)
            page.on("pageerror", lambda error: record["page_errors"].append(str(error)))
            page.set_default_timeout(20000)
            current = None

            def idle():
                expect(page.get_by_test_id("stApp")).to_have_attribute("data-test-script-state", "notRunning")

            def capture(name, locator):
                idle()
                locator.scroll_into_view_if_needed()
                page.screenshot(path=str(OUT / (name + ".png")))
                (OUT / (name + ".txt")).write_text(page.locator("body").inner_text(), encoding="utf-8")

            def metrics():
                return page.get_by_test_id("stMetric").all_inner_texts()

            def begin(task):
                nonlocal current
                current = task
                record["tasks"][task] = {"started_at": now(), "status": "执行中", "error_count": 0, "hints_count": 0, "interruptions": 0}
                return time.perf_counter()

            def finish(task, started, **data):
                record["tasks"][task].update(status="完整", finished_at=now(), time_seconds=round(time.perf_counter() - started, 3), **data)
                (OUT / "run.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
                print(json.dumps({"task": task, **record["tasks"][task]}, ensure_ascii=False), flush=True)

            def radio(name):
                control = page.get_by_role("radio", name=name, exact=True)
                control.focus()
                control.press("Space")
                expect(control).to_be_checked()

            def select(label, value):
                control = page.get_by_role("combobox", name=label, exact=True)
                control.fill(value)
                control.press("ArrowDown")
                page.get_by_role("option", name=value, exact=True).click()
                expect(control).to_have_value(value)
                idle()

            def expand(title):
                container = page.locator("details").filter(has=page.locator("summary", has_text=title))
                container.locator("summary").click()
                expect(container).to_have_attribute("open", "")
                return container

            try:
                page.goto(URL)
                analyze = page.get_by_role("button", name="🔍 估计并分析趋势", exact=True)
                analyze.wait_for()
                idle()
                expect(page.get_by_role("heading", name="本次结果摘要", exact=True)).to_have_count(0)
                record["fresh_session"] = True

                started = begin("T1")
                expect(page.get_by_role("heading", name="选择录入方式", exact=True)).to_be_visible()
                expect(page.get_by_text("填写示例：身高", exact=False)).to_contain_text("1.70 米")
                expand("导入个人档案（CSV）")
                page.locator('input[type="file"]').set_input_files(str(ROOT / "data/sample/profile_template.csv"))
                page.get_by_role("button", name="校验并载入档案", exact=True).click()
                page.get_by_text("校验通过，已载入表单。", exact=False).wait_for()
                height = page.get_by_role("spinbutton", name="身高（米）", exact=True)
                weight = page.get_by_role("spinbutton", name="体重（千克）", exact=True)
                expect(height).to_have_value("1.70")
                expect(weight).to_have_value("70.0")
                capture("T1_form", page.get_by_role("heading", name="① 身体与行为录入", exact=True))
                capture("T1_overview", page.get_by_role("heading", name="当前输入概览", exact=True))
                finish("T1", started, height=height.input_value(), weight=weight.input_value(), source="仓库 CSV 示例；身高米，体重千克。")

                started = begin("T2")
                expect(page.get_by_role("checkbox", name="同时分析体重趋势（可选）", exact=True)).to_be_checked()
                intake = page.get_by_role("spinbutton", name="每日摄入热量（kcal）", exact=True)
                intake.fill("1800")
                intake.press("Enter")
                idle()
                analyze.click()
                summary = page.get_by_role("heading", name="本次结果摘要", exact=True)
                trend = page.get_by_role("heading", name="体重趋势与外推", exact=True)
                trend.wait_for()
                capture("T2_summary", summary)
                capture("T2_probability", page.get_by_role("heading", name="肥胖等级估计", exact=True))
                capture("T2_trend", trend)
                finish("T2", started, metrics=metrics(), answer="分类估计当前输入的肥胖等级；日志用于描述记录变化，未来曲线按固定能量差外推。")

                started = begin("T3")
                explanation = page.get_by_role("heading", name="解释反馈", exact=True)
                expect(page.get_by_text("横断面调查：", exact=False)).to_be_visible()
                expect(page.get_by_text("中位数是将训练数值", exact=False)).to_be_visible()
                capture("T3_explanation", explanation)
                scope = expand("数据来源与适用范围")
                expect(scope).to_contain_text("SMOTE")
                capture("T3_scope", scope)
                finish("T3", started, answer="类别概率不是患病风险或绝对正确率；重要性不是个人原因，未验证新群体适用性。")

                started = begin("T4")
                weight.fill("80")
                weight.press("Enter")
                stale = page.get_by_text("输入已修改，请重新分析。", exact=False)
                stale.wait_for()
                expect(page.get_by_test_id("stMetric").filter(has_text="分类采用档案体重")).to_contain_text("70.0 kg")
                capture("T4_stale", stale)
                stale_metrics = metrics()
                analyze.click()
                comparison = page.get_by_role("heading", name="修改前后对比", exact=True)
                comparison.wait_for()
                expect(page.get_by_text("分类未改变：", exact=False)).to_be_visible()
                expect(page.get_by_test_id("stMetric").filter(has_text="分类采用档案体重")).to_contain_text("80.0 kg")
                expect(page.get_by_test_id("stMetric").filter(has_text="趋势采用日志体重")).to_contain_text("70.5 kg")
                headings = page.get_by_role("heading").all_text_contents()
                assert headings.index("本次结果摘要") < headings.index("修改前后对比") < headings.index("肥胖等级估计")
                capture("T4_summary", summary)
                capture("T4_comparison", comparison)
                finish("T4", started, stale_metrics=stale_metrics, updated_metrics=metrics(), comparison_precedes_details=True)

                started = begin("T5")
                intake.fill("0")
                intake.press("Enter")
                idle()
                analyze.click()
                error = page.get_by_text("本次分类已生成，趋势未生成。", exact=False)
                error.wait_for()
                expect(trend).to_have_count(0)
                capture("T5_error", summary)
                invalid = metrics()
                page.get_by_role("link", name="返回每日摄入热量", exact=True).last.click()
                expect(intake).to_be_in_viewport()
                expect(weight).to_have_value("80.0")
                capture("T5_error_shortcut", intake)
                intake.fill("1800")
                intake.press("Enter")
                idle()
                analyze.click()
                trend.wait_for()
                capture("T5_recovered", trend)
                recovered = metrics()
                finish("T5", started, invalid_metrics=invalid, recovered_metrics=recovered, return_to_intake_passed=True, prescribed_zero_is_not_misoperation=True)

                started = begin("T6")
                page.get_by_role("link", name="填写用户反馈", exact=True).click()
                expect(page.get_by_role("heading", name="④ 理解自测与用户反馈", exact=True)).to_be_in_viewport()
                radio("4")
                radio("根据当前输入估计的肥胖等级")
                page.get_by_role("textbox", name="遇到的问题或改进建议（可选）", exact=True).fill("003 更新后复测：摘要、两种体重来源、提前的对比和反馈跳转更方便；建议将审核页区间术语进一步中文化。")
                page.get_by_role("button", name="保存本次反馈", exact=True).click()
                page.get_by_text("反馈已保存在当前会话。下一步：", exact=False).wait_for()
                download_button = page.get_by_role("button", name="下载匿名反馈（JSON）", exact=True)
                capture("T6_feedback", download_button)
                with page.expect_download() as download:
                    download_button.click()
                download.value.save_as(str(OUT / "weighttrend_feedback.json"))
                feedback = json.loads((OUT / "weighttrend_feedback.json").read_text(encoding="utf-8"))
                assert feedback["ease_1_to_5"] == 4 and feedback["understood_classification"] is True
                radio("模型公平性审核")
                page.get_by_role("heading", name="先看整体表现，再看群体差异", exact=True).wait_for()
                idle()
                for group, name in (("女性", "female"), ("男性", "male"), ("全部群体", "all")):
                    select("查看群体", group)
                    expect(page.get_by_text("当前展示：" + group + " ·", exact=False)).to_be_visible()
                    capture("T6_group_" + name, page.get_by_role("combobox", name="查看群体", exact=True))
                for metric, name in (("漏判率 FNR", "fnr"), ("误判率 FPR", "fpr")):
                    select("比较指标", metric)
                    expect(page.get_by_text("全部群体 · " + metric, exact=False)).to_be_visible()
                    capture("T6_metric_" + name, page.get_by_role("combobox", name="比较指标", exact=True))
                detail = expand("详细分组指标")
                capture("T6_details", detail)
                uncertainty = expand("错误率的不确定性")
                expect(uncertainty).to_contain_text("Wilson")
                capture("T6_uncertainty", uncertainty)
                fairness_metrics = metrics()
                with page.expect_download() as download:
                    page.get_by_role("button", name="下载分组测试结果", exact=True).click()
                download.value.save_as(str(OUT / "fairness_group_metrics.csv"))
                radio("体重管理原型")
                trend.wait_for()
                idle()
                expect(weight).to_have_value("80.0")
                expect(intake).to_have_value("1800")
                expect(download_button).to_be_visible()
                returned = metrics()
                assert returned == recovered
                capture("T6_return", summary)
                finish("T6", started, feedback=feedback, fairness_metrics=fairness_metrics, returned_metrics=returned, shortcut_passed=True, state_preserved=True, fairness_answer="本次两方案 EO 相同，约束未改善差异；女性组零错误不代表完全公平或未来无错误。")
                record["completed"] = True
            except Exception:
                record["failure"] = traceback.format_exc()
                if current:
                    record["tasks"][current]["status"] = "中断"
                    record["tasks"][current]["interruptions"] += 1
                page.screenshot(path=str(OUT / "failure.png"))
                (OUT / "failure.txt").write_text(page.locator("body").aria_snapshot(), encoding="utf-8")
                raise
            finally:
                browser.close()
    finally:
        server.terminate()
        server.wait(timeout=15)
        log.close()
        record["finished_at"] = now()
        record["existing_hashes_after"] = {name: sha(ROOT / name) if (ROOT / name).is_file() else None for name in before}
        record["preexisting_files_unchanged"] = before == record["existing_hashes_after"]
        record["evidence_hashes"] = {path.name: sha(path) for path in sorted(OUT.iterdir()) if path.is_file() and path.name != "run.json"}
        (OUT / "run.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"completed": record["completed"], "page_errors": record["page_errors"], "preexisting_files_unchanged": record["preexisting_files_unchanged"]}), flush=True)


if __name__ == "__main__":
    main()
