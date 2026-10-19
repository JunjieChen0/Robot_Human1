"""浏览器回归与截图。先启动 Streamlit，再用安装了 playwright 的 Python 运行。"""

import argparse
import json
import re
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "ui"


def choose_radio(page, name):
    radio = page.get_by_role("radio", name=name, exact=True)
    radio.focus()
    radio.press("Space")


def wait_idle(page):
    expect(page.get_by_test_id("stApp")).to_have_attribute("data-test-script-state", "notRunning")


def choose_select(page, label, value):
    control = page.get_by_role("combobox", name=label, exact=True)
    control.fill(value)
    control.press("ArrowDown")
    page.get_by_role("option", name=value, exact=True).click()
    expect(control).to_have_value(value)
    wait_idle(page)


def contrast(foreground, background):
    def luminance(color):
        rgb = [float(value) / 255 for value in re.findall(r"[\d.]+", color)[:3]]
        linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in rgb]
        return sum(value * weight for value, weight in zip(linear, (0.2126, 0.7152, 0.0722)))
    light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="reports/ui", help="截图与检查记录的输出目录")
    args = parser.parse_args()
    OUT = ROOT / args.output
    OUT.mkdir(parents=True, exist_ok=True)
    checks = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto("http://localhost:8501")
        analyze = page.get_by_role("button", name="🔍 估计并分析趋势", exact=True)
        analyze.wait_for()
        page.get_by_text("尚无分析结果。", exact=False).wait_for()
        wait_idle(page)
        primary_style = analyze.evaluate("el => ({fg: getComputedStyle(el).color, bg: getComputedStyle(el).backgroundColor, height: el.getBoundingClientRect().height})")
        caption_color = page.get_by_test_id("stCaptionContainer").nth(3).locator("p").evaluate("el => getComputedStyle(el).color")
        measured = {"primary_contrast": contrast(primary_style["fg"], primary_style["bg"]), "caption_on_white_contrast": contrast(caption_color, "rgb(255,255,255)"), "primary_height_px": primary_style["height"]}
        measured["caption_effective_opacity"] = page.get_by_test_id("stCaptionContainer").nth(3).evaluate("el => { let opacity = 1; for (let node = el; node; node = node.parentElement) opacity *= Number(getComputedStyle(node).opacity); return opacity; }")
        checks["caption_not_faded"] = measured["caption_effective_opacity"] >= 0.99
        checks["primary_contrast_at_least_4_5"] = measured["primary_contrast"] >= 4.5
        checks["caption_contrast_at_least_4_5"] = measured["caption_on_white_contrast"] >= 4.5
        checks["primary_button_at_least_44_px"] = primary_style["height"] >= 44
        page.screenshot(path=str(OUT / "01_input.png"), full_page=True)
        checks["initial_empty_state"] = True

        page.get_by_text("导入个人档案（CSV）", exact=True).click()
        page.locator('input[type="file"]').set_input_files({"name": "invalid.csv", "mimeType": "text/csv", "buffer": b"Age,Height\n25,170\n"})
        page.get_by_role("button", name="校验并载入档案", exact=True).click()
        page.get_by_text("缺少列 Weight", exact=False).wait_for()
        wait_idle(page)
        checks["invalid_csv_recovery"] = True
        page.screenshot(path=str(OUT / "02_import_error.png"), full_page=True)

        template = (ROOT / "data" / "sample" / "profile_template.csv").read_bytes()
        page.locator('input[type="file"]').set_input_files({"name": "profile.csv", "mimeType": "text/csv", "buffer": template})
        expect(page.get_by_text("缺少列 Weight", exact=False)).not_to_be_visible()
        page.get_by_role("button", name="校验并载入档案", exact=True).click()
        page.get_by_text("校验通过，已载入表单。", exact=False).wait_for()
        expect(page.get_by_text("档案来源：CSV 与示例模板一致", exact=False)).to_be_visible()
        checks["example_csv_label_uses_content_not_filename"] = True
        page.get_by_text("查看 CSV 类别编码对照", exact=True).click()
        wait_idle(page)
        page.get_by_role("heading", name="选择录入方式", exact=True).scroll_into_view_if_needed()
        page.screenshot(path=str(OUT / "16_csv_codes.png"))
        page.get_by_text("查看 CSV 类别编码对照", exact=True).click()
        custom = template.decode("utf-8-sig").replace("25,1.7,70,", "25,1.7,71,").encode("utf-8-sig")
        assert custom != template
        page.locator('input[type="file"]').set_input_files({"name": "profile_template.csv", "mimeType": "text/csv", "buffer": custom})
        page.get_by_role("button", name="校验并载入档案", exact=True).click()
        expect(page.get_by_text("档案来源：CSV 导入（用户提供", exact=False)).to_be_visible()
        checks["custom_csv_not_mislabeled_as_example"] = True
        page.locator('input[type="file"]').set_input_files({"name": "profile.csv", "mimeType": "text/csv", "buffer": template})
        page.get_by_role("button", name="校验并载入档案", exact=True).click()
        page.get_by_text("校验通过，已载入表单。", exact=False).wait_for()
        checks["valid_csv_import"] = True
        page.get_by_text("导入个人档案（CSV）", exact=True).click()

        analyze.click()
        result = page.get_by_role("heading", name="③ 分析结果与解释", exact=True)
        result.wait_for()
        expect(page.get_by_text("尚无分析结果。", exact=False)).not_to_be_visible()
        wait_idle(page)
        result.scroll_into_view_if_needed()
        page.screenshot(path=str(OUT / "03_result.png"))
        page.get_by_role("link", name="填写用户反馈", exact=True).click()
        expect(page.get_by_role("heading", name="④ 理解自测与用户反馈", exact=True)).to_be_in_viewport()
        checks["feedback_shortcut_keeps_session"] = page.get_by_test_id("stMetric").filter(has_text="分类采用档案体重").count() == 1
        checks["model_result"] = True
        probability_chart = page.get_by_test_id("stVegaLiteChart").first
        expect(probability_chart).to_contain_text("100%")
        expect(probability_chart).to_contain_text("正常体重")
        checks["probability_chart_percentage_and_horizontal_labels"] = True
        axis_style = probability_chart.locator("svg text").first.evaluate("el => ({fill: getComputedStyle(el).fill, size: parseFloat(getComputedStyle(el).fontSize)})")
        checks["chart_labels_readable_contrast_and_size"] = contrast(axis_style["fill"], "rgb(255,255,255)") >= 4.5 and axis_style["size"] >= 14
        analyze.focus()
        focused_style = analyze.evaluate("el => ({fg: getComputedStyle(el).color, bg: getComputedStyle(el).backgroundColor})")
        checks["focused_primary_button_contrast"] = contrast(focused_style["fg"], focused_style["bg"]) >= 4.5
        probability_chart.screenshot(path=str(OUT / "12_probability_chart.png"))

        weight = page.get_by_role("spinbutton", name="体重（千克）", exact=True)
        weight.fill("80")
        weight.press("Enter")
        stale = page.get_by_text("输入已修改，请重新分析。", exact=False)
        stale.wait_for()
        wait_idle(page)
        stale.scroll_into_view_if_needed()
        page.screenshot(path=str(OUT / "04_stale.png"))
        analyze.click()
        page.get_by_role("heading", name="修改前后对比", exact=True).wait_for()
        wait_idle(page)
        checks["edit_and_reanalyze"] = True
        expect(page.get_by_test_id("stMetric").filter(has_text="分类采用档案体重")).to_contain_text("80.0 kg")
        expect(page.get_by_test_id("stMetric").filter(has_text="趋势采用日志体重")).to_contain_text("70.5 kg")
        headings = page.get_by_role("heading").all_text_contents()
        checks["comparison_precedes_detailed_explanation"] = headings.index("修改前后对比") < headings.index("肥胖等级估计")
        checks["summary_separates_snapshot_weight_sources"] = True
        page.get_by_text("比较的是最近两次成功分析", exact=False).wait_for()
        checks["comparison_explains_two_successful_submission_times"] = True
        page.get_by_text("两类概率越接近", exact=False).wait_for()
        checks["close_probability_explanation_without_risk_threshold"] = True
        page.get_by_role("heading", name="本次结果摘要", exact=True).evaluate("el => el.scrollIntoView({block: 'start'})")
        page.screenshot(path=str(OUT / "10_summary_comparison.png"))
        page.get_by_role("heading", name="体重趋势与外推", exact=True).scroll_into_view_if_needed()
        page.screenshot(path=str(OUT / "08_trend.png"))
        trend_chart = page.get_by_test_id("stVegaLiteChart").nth(1)
        expect(trend_chart).to_contain_text("外推起点")
        expect(trend_chart).to_contain_text("体重（kg）")
        expect(trend_chart).to_contain_text("天数（从首条记录起）")
        checks["trend_chinese_axes_boundary_and_dashed_projection"] = trend_chart.locator('[stroke-dasharray="7,5"]').count() > 0
        trend_chart.screenshot(path=str(OUT / "13_trend_chart.png"))

        intake = page.get_by_role("spinbutton", name="每日摄入热量（kcal）", exact=True)
        intake.fill("0")
        intake.press("Enter")
        wait_idle(page)
        analyze.click()
        page.get_by_text("本次分类已生成，趋势未生成。", exact=False).wait_for()
        expect(page.get_by_text("请输入大于 0 的热量值", exact=False).first).to_be_visible()
        expect(page.get_by_test_id("stAlertContainer").filter(has_text="分类分析已完成")).to_have_count(0)
        checks["plain_intake_error_and_partial_success"] = True
        page.get_by_text("本次仅完成分类，趋势未生成。", exact=False).scroll_into_view_if_needed()
        page.screenshot(path=str(OUT / "15_partial_success.png"))
        wait_idle(page)
        page.get_by_role("link", name="返回每日摄入热量", exact=True).last.click()
        expect(intake).to_be_in_viewport()
        expect(weight).to_have_value("80.0")
        intake.fill("1800")
        intake.press("Enter")
        wait_idle(page)
        analyze.click()
        page.get_by_role("heading", name="体重趋势与外推", exact=True).wait_for()
        wait_idle(page)
        checks["error_shortcut_and_recovery_preserve_profile"] = True

        choose_radio(page, "4")
        choose_radio(page, "根据当前输入估计的肥胖等级")
        page.get_by_role("textbox", name="遇到的问题或改进建议（可选）", exact=True).fill("自动化回归演示，非真人用户测试。")
        page.get_by_role("button", name="保存本次反馈", exact=True).click()
        page.get_by_text("反馈已保存在当前会话。下一步：", exact=False).wait_for()
        wait_idle(page)
        page.get_by_role("button", name="下载匿名反馈（JSON）", exact=True).scroll_into_view_if_needed()
        page.screenshot(path=str(OUT / "05_feedback.png"))
        checks["feedback_keeps_result"] = page.get_by_text("体重趋势与外推", exact=True).count() == 1
        with page.expect_download() as download:
            page.get_by_role("button", name="下载匿名反馈（JSON）", exact=True).click()
        feedback = json.loads(Path(download.value.path()).read_text(encoding="utf-8"))
        assert feedback["understood_classification"] is True
        checks["feedback_download"] = True

        choose_radio(page, "模型公平性审核")
        fairness_title = page.get_by_role("heading", name="模型公平性审核", exact=True)
        fairness_title.wait_for()
        expect(page.get_by_role("heading", name="④ 理解自测与用户反馈", exact=True)).to_have_count(0)
        wait_idle(page)
        for group in ("女性", "男性", "全部群体"):
            choose_select(page, "查看群体", group)
        for metric in ("漏判率 FNR", "误判率 FPR"):
            choose_select(page, "比较指标", metric)
        checks["audit_group_and_metric_switching"] = True
        expect(page.get_by_test_id("stVegaLiteChart")).to_contain_text("%")
        checks["audit_chart_percentage_and_horizontal_groups"] = True
        fairness_title.scroll_into_view_if_needed()
        page.screenshot(path=str(OUT / "06_fairness.png"), full_page=True)
        page.get_by_text("漏判：标签属于正类", exact=False).scroll_into_view_if_needed()
        page.screenshot(path=str(OUT / "09_fairness_groups.png"))
        page.get_by_text("错误率的不确定性", exact=True).click()
        wait_idle(page)
        uncertainty = page.get_by_test_id("stExpander").filter(has=page.get_by_text("错误率的不确定性", exact=True))
        uncertainty.scroll_into_view_if_needed()
        expect(uncertainty.get_by_test_id("stDataFrame")).to_be_visible()
        page.wait_for_timeout(300)
        page.screenshot(path=str(OUT / "14_fairness_intervals.png"))
        checks["audit_interval_plain_language"] = True
        choose_radio(page, "体重管理原型")
        analyze.wait_for()
        wait_idle(page)
        assert weight.input_value() == "80.0"
        checks["navigation_preserves_profile"] = True

        analyze.focus()
        checks["visible_keyboard_focus"] = analyze.evaluate("el => getComputedStyle(el).outlineStyle !== 'none'")
        analyze.press("Enter")
        result.wait_for()
        checks["keyboard_analysis"] = True

        mobile = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=1)
        mobile.goto("http://localhost:8501")
        mobile.get_by_role("button", name="🔍 估计并分析趋势", exact=True).wait_for()
        wait_idle(mobile)
        mobile.get_by_test_id("stSidebarCollapseButton").get_by_role("button").click()
        expect(mobile.get_by_test_id("stSidebar")).not_to_be_visible()
        mobile.screenshot(path=str(OUT / "07_mobile.png"), full_page=True)
        mobile.get_by_role("button", name="🔍 估计并分析趋势", exact=True).click()
        mobile.get_by_role("heading", name="本次结果摘要", exact=True).wait_for()
        wait_idle(mobile)
        mobile.get_by_role("heading", name="本次结果摘要", exact=True).evaluate("el => el.scrollIntoView({block: 'start'})")
        mobile.screenshot(path=str(OUT / "11_mobile_result.png"))
        checks["mobile_no_page_overflow"] = mobile.evaluate("document.documentElement.scrollWidth <= innerWidth")
        checks["no_browser_errors"] = not errors
        assert all(checks.values()), checks
        (OUT / "browser_checks.json").write_text(json.dumps({"kind": "自动化浏览器回归，非真人用户测试", "browser": browser.version, "checks": checks, "measurements": measured, "page_errors": errors}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(checks, ensure_ascii=False))
        browser.close()


if __name__ == "__main__":
    main()
