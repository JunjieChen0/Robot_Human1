"""保留首次中断记录，在新会话重建状态后补做 T6。"""

import json
import time
import traceback

from playwright.sync_api import expect, sync_playwright

from walkthrough import OUT, ROOT, file_hash, now


def main():
    target = OUT / "t6_retry"
    target.mkdir(exist_ok=False)
    record = {
        "kind": "003 AI 实际浏览器补测，非真人测试", "started_at": now(),
        "reason": "首次 T6 选取女性选项时定位超时；反馈已下载，后续步骤未完成。",
        "session": "新会话重建 80 kg 档案与 1800 kcal 趋势，再重新执行完整 T6。",
        "timing": "仅记录补测 T6 自动化操作、等待与取证耗时，不含准备；不作真人用时。",
        "events": [], "page_errors": [], "completed": False,
    }
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        record["browser"] = browser.version
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
        page.on("pageerror", lambda error: record["page_errors"].append(str(error)))

        def idle():
            expect(page.get_by_test_id("stApp")).to_have_attribute("data-test-script-state", "notRunning")

        def radio(name):
            item = page.get_by_role("radio", name=name, exact=True)
            item.focus()
            item.press("Space")
            expect(item).to_be_checked()

        def capture(name, locator):
            idle()
            locator.scroll_into_view_if_needed()
            page.screenshot(path=str(target / (name + ".png")))
            (target / (name + ".txt")).write_text(page.locator("body").inner_text(), encoding="utf-8")
            record["events"].append({"step": name, "at": now()})

        def select(label, value):
            item = page.get_by_role("combobox", name=label, exact=True)
            item.fill(value)
            item.press("ArrowDown")
            option = page.get_by_role("option", name=value, exact=True)
            expect(option).to_be_visible()
            option.click()
            expect(item).to_have_value(value)
            expect(page.get_by_text("当前展示：" + (value if label == "查看群体" else "全部群体") + " ·", exact=False)).to_be_visible()
            idle()

        try:
            page.goto("http://127.0.0.1:8503")
            analyze = page.get_by_role("button", name="🔍 估计并分析趋势", exact=True)
            analyze.wait_for()
            idle()
            page.get_by_text("导入个人档案（CSV）", exact=True).click()
            page.locator('input[type="file"]').set_input_files(str(ROOT / "data/sample/profile_template.csv"))
            page.get_by_role("button", name="校验并载入档案", exact=True).click()
            page.get_by_text("校验通过，已载入表单。", exact=False).wait_for()
            weight = page.get_by_role("spinbutton", name="体重（千克）", exact=True)
            weight.fill("80")
            weight.press("Enter")
            idle()
            analyze.click()
            trend = page.get_by_role("heading", name="体重趋势与外推", exact=True)
            trend.wait_for()
            idle()
            before = page.get_by_test_id("stMetric").all_inner_texts()
            record["preparation_metrics"] = before
            started = time.perf_counter()
            radio("3")
            radio("根据当前输入估计的肥胖等级")
            page.get_by_role("textbox", name="遇到的问题或改进建议（可选）", exact=True).fill("003：AI 实际浏览器补测 T6。建议集中展示两种体重来源及前后对比；评分仅为 AI 界面评估。")
            page.get_by_role("button", name="保存本次反馈", exact=True).click()
            page.get_by_text("反馈已保存在当前会话，可下载留存。", exact=True).wait_for()
            feedback_download = page.get_by_role("button", name="下载匿名反馈（JSON）", exact=True)
            capture("01_feedback", feedback_download)
            with page.expect_download() as download:
                feedback_download.click()
            download.value.save_as(str(target / "weighttrend_feedback.json"))
            record["feedback"] = json.loads((target / "weighttrend_feedback.json").read_text(encoding="utf-8"))
            radio("模型公平性审核")
            page.get_by_role("heading", name="先看整体表现，再看群体差异", exact=True).wait_for()
            idle()
            for group, name in (("女性", "female"), ("男性", "male"), ("全部群体", "all")):
                select("查看群体", group)
                capture("02_group_" + name, page.get_by_role("combobox", name="查看群体", exact=True))
            for metric, name in (("漏判率 FNR", "fnr"), ("误判率 FPR", "fpr")):
                select("比较指标", metric)
                capture("03_metric_" + name, page.get_by_role("combobox", name="比较指标", exact=True))
            uncertainty = page.locator("details").filter(has=page.locator("summary", has_text="错误率的不确定性"))
            uncertainty.locator("summary").click()
            expect(uncertainty).to_have_attribute("open", "")
            expect(uncertainty).to_contain_text("Wilson")
            capture("04_uncertainty", uncertainty)
            record["fairness_metrics"] = page.get_by_test_id("stMetric").all_inner_texts()
            record["fairness_answer"] = "本次约束前后 EO 均为 0.0208，未改善；女性本次零错误不能说明完全公平或未来不会出错。"
            record["fairness_self_test_opened"] = False
            with page.expect_download() as download:
                page.get_by_role("button", name="下载分组测试结果", exact=True).click()
            download.value.save_as(str(target / "fairness_group_metrics.csv"))
            radio("体重管理原型")
            trend.wait_for()
            idle()
            expect(weight).to_have_value("80.0")
            expect(page.get_by_role("spinbutton", name="每日摄入热量（kcal）", exact=True)).to_have_value("1800")
            expect(feedback_download).to_be_visible()
            capture("05_return", page.get_by_role("heading", name="③ 分析结果与解释", exact=True))
            record["returned_metrics"] = page.get_by_test_id("stMetric").all_inner_texts()
            assert record["returned_metrics"] == before
            record["automation_seconds"] = round(time.perf_counter() - started, 3)
            record["completed"] = True
        except Exception:
            record["failure"] = traceback.format_exc()
            page.screenshot(path=str(target / "failure.png"))
            (target / "failure.txt").write_text(page.locator("body").aria_snapshot(), encoding="utf-8")
            raise
        finally:
            record["finished_at"] = now()
            browser.close()
            record["evidence_hashes"] = {p.name: file_hash(p) for p in sorted(target.iterdir()) if p.is_file()}
            (target / "run.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"completed": record["completed"], "automation_seconds": record["automation_seconds"], "page_errors": record["page_errors"]}), flush=True)


if __name__ == "__main__":
    main()
