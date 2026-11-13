"""模型判断页的真实浏览器回归；不提交真人反馈。需另安装Playwright。"""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[1]


def wait_idle(page):
    expect(page.get_by_test_id("stApp")).to_have_attribute("data-test-script-state", "notRunning", timeout=60000)


def open_judgment(page, url, standalone=False):
    page.goto(url)
    if not standalone:
        radio = page.get_by_role("radio", name="模型判断", exact=True)
        radio.wait_for(state="attached")
        radio.focus()
        radio.press("Space")
    expect(page.get_by_role("heading", name="模型判断", exact=True)).to_be_visible(timeout=60000)
    wait_idle(page)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8517")
    parser.add_argument("--standalone", action="store_true", help="直接进入同学测试独立页")
    args = parser.parse_args()
    out = ROOT / "reports" / "model_judgment" / ("ui_linux" if args.standalone else "ui_v1")
    out.mkdir(parents=True, exist_ok=True)
    checks, errors = {}, []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1050})
        page.on("pageerror", lambda error: errors.append(str(error)))
        open_judgment(page, args.url, args.standalone)
        plot = page.get_by_test_id("stVegaLiteChart").first
        expect(plot.locator("svg")).to_be_visible()
        expect(plot).to_contain_text("饮水量（自动填充）")
        checks["baseline_and_training_scope"] = "93.12%" in page.inner_text("body") and "1270" in page.inner_text("body")
        # 命中透明交互条：包含零值行，避免仅检查下拉框。
        hit = plot.locator('g.mark-rect.role-mark').last.locator("path")
        if hit.count() == 0:
            hit = plot.locator('g.mark-rect.role-mark').last.locator("rect")
        assert hit.count() == 5, f"交互行数量异常：{hit.count()}"
        hit.nth(4).click(force=True)
        expect(page.get_by_role("heading", name="输入证据：饮水量（自动填充）", exact=True)).to_be_visible()
        wait_idle(page)
        checks["click_zero_importance_row"] = True
        expect(page.get_by_text("这列在当前验证输入中全为训练中位数", exact=False)).to_be_visible()
        plot.screenshot(path=str(out / "importance_chart.png"))
        page.get_by_role("heading", name="输入证据：饮水量（自动填充）", exact=True).scroll_into_view_if_needed()
        page.screenshot(path=str(out / "constant_feature.png"))
        plot.scroll_into_view_if_needed()
        hit.nth(2).click(force=True)
        expect(page.get_by_role("heading", name="输入证据：年龄", exact=True)).to_be_visible()
        wait_idle(page)
        checks["switch_chart_selection_updates_feature"] = True
        checks["correct_and_error_cases"] = page.get_by_text("预测正确的记录", exact=True).count() == 1 and page.get_by_text("预测错误的记录", exact=True).count() == 1
        assert page.get_by_text("选中输入 年龄：", exact=False).count() == 2
        checks["no_local_or_causal_claim"] = "本页没有计算局部归因，也不能判断个人患病原因" in page.inner_text("body")
        page.get_by_role("heading", name="模型判断", exact=True).scroll_into_view_if_needed()
        page.screenshot(path=str(out / "page_top.png"))
        page.get_by_role("heading", name="一条判对、一条判错：对照实际输入", exact=True).scroll_into_view_if_needed()
        page.screenshot(path=str(out / "cases.png"))
        if args.standalone:
            page.get_by_label("匿名编号（如 J01）", exact=True).fill("自动检查，不计真人")
            page.get_by_label("任务1：指出打乱哪项输入后，模型表现下降最多；写出图中证据。", exact=True).fill("体重，平均下降最多")
            page.get_by_label("任务2：这张图能否用于判断个人患病原因？请说明理由。", exact=True).fill("不能，整批依赖实验不是个人病因或局部解释")
            page.get_by_role("button", name="保存首次回答", exact=True).click()
            wait_idle(page)
            with page.expect_download() as download_info:
                page.get_by_role("button", name="下载本次回答（JSON）", exact=True).click()
            response = json.loads(Path(download_info.value.path()).read_text(encoding="utf-8"))
            summary = json.loads((ROOT / "reports/model_judgment/summary.json").read_text(encoding="utf-8"))
            checks["first_response_json_download"] = (
                response["participant"] == "自动检查，不计真人"
                and response["page_version"] == "model-judgment-v1"
                and response["experiment_model_sha256"] == summary["model_sha256"]
            )
        mobile = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        mobile.on("pageerror", lambda error: errors.append(str(error)))
        open_judgment(mobile, args.url, args.standalone)
        if not args.standalone:
            mobile.get_by_test_id("stSidebarCollapseButton").get_by_role("button").click()
            expect(mobile.get_by_test_id("stSidebar")).not_to_be_visible()
        checks["mobile_no_page_overflow"] = mobile.evaluate("document.documentElement.scrollWidth <= innerWidth")
        mobile.get_by_test_id("stVegaLiteChart").first.scroll_into_view_if_needed()
        mobile.screenshot(path=str(out / "mobile.png"))
        checks["no_browser_errors"] = not errors
        record = {"kind": "自动化浏览器回归，非真人用户测试", "page_version": "model-judgment-v1",
                  "entry": "standalone" if args.standalone else "main",
                  "browser": browser.version, "checks": checks, "page_errors": errors}
        (out / "browser_checks.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        browser.close()
    assert all(checks.values()), checks
    print(json.dumps(record, ensure_ascii=False))


if __name__ == "__main__":
    main()
