# 深蹲计数技术检查与待测清单

页面版本`squat-counter-v1`，整理日期2026-11-14（组织者本地日期）。本轮按“先完成应用与测试说明”执行。应用、计数规则、导出、评价代码及空白表已准备；没有登记真人视频、同学结果或真实改进效果。

## 任务对应材料

| 要求 | 已准备 | 尚待真实执行 |
| --- | --- | --- |
| 用户场景与成功条件 | [规则与验收条件](../../docs/squat_counter_spec.md)，大学生单人侧面深蹲 | 真实片段试录，固定正式测试版本 |
| 完整视觉交互 | [独立入口](../../squat_counter_app.py)、[主界面入口](../../app.py)、[浏览器实现](../../src/squat_frontend/app.mjs)，摄像头/视频、开始至结束、遮挡提示、纠错和原始记录 | 用真实动作验证可靠性 |
| 识别效果与使用效果分别评价 | [逐次匹配工具](../../src/squat_evaluation.py)、[标注空表](../../user_test/squat_annotations_template.csv)、[操作空表](../../user_test/squat_counter_records.csv)、[组织说明](../../user_test/squat_counter_test_guide.md) | 三种光照/遮挡条件下的误计、漏计、延迟；3位同学独立操作 |
| 一次失败改进与同条件复测 | [前后对照模板](../../user_test/squat_counter_before_after.md)，记录模型、规则、提示三类原因 | 选真实失败、修改并用同片段/条件复测 |
| 模型、影像来源与演示 | [来源及权限说明](../../docs/squat_model_sources.md)、[素材登记空表](../../user_test/squat_media_register.csv)、[运行说明](../../user_test/squat_counter_quickstart.md) | 获同意的实际影像与最终演示视频 |

## 自动检查的证据边界

Python回归包含原健康/公平性/模型判断测试以及新入口与评价工具；Node测试覆盖稳定阈值、保持、抖动、遮挡恢复、暂停、时间跳变、宽高比例和纠错历史。

浏览器检查分两类：真实MediaPipe CPU模型处理程序生成的纯色空视频，确认看不清时不计数；另用明确标记为`mock_landmarks`的关键点测试计数与纠错控件。摄像头使用Chromium合成设备，未拍摄真人。模拟会话由评价工具拒绝，不能计入真实识别性能。检查涵盖授权等待时取消、暂停与结束、关闭及切页释放轨道、回看不重复计数、导出和移动端布局。

Debian检查从不含vendor缓存或健康模型的源码启动，在含空格路径中新建虚拟环境，安装页面依赖并从官方源下载资源。pip复用了部分下载缓存并联网下载其余依赖；不是完全冷网络下载。没有安装Python视觉/GPU或健康模型依赖。具体环境、检查项与汇总见[Linux记录](linux_startup.json)及[验证摘要](verification.json)。

| 入口 | 机器记录 | 截图 |
| --- | --- | --- |
| 独立页 | [浏览器检查](ui_v1/browser_checks.json) | [初始](ui_v1/initial.png)、[真实模型看不清](ui_v1/unclear_real_model.png)、[模拟流程反馈锁定](ui_v1/mock_controls.png)、[窄屏](ui_v1/mobile.png) |
| 主项目侧栏 | [浏览器检查](ui_integrated/browser_checks.json) | [初始](ui_integrated/initial.png)、[真实模型看不清](ui_integrated/unclear_real_model.png)、[模拟流程反馈锁定](ui_integrated/mock_controls.png)、[窄屏](ui_integrated/mobile.png) |

## 复现

运行完整项目已有依赖后执行Python回归。Node仅用于开发期规则检查，运行页面不需要Node或前端构建。

```text
python -B -m pytest tests -q -p no:cacheprovider --tb=short
node --test tests/test_squat_counter.mjs
python scripts/download_squat_assets.py --check-only
```

另装Playwright且可启动Chrome的Python可执行浏览器脚本；脚本需要ffmpeg生成空视频，也可用`--blank-video`传入程序生成的纯色8秒视频。

```text
python scripts/check_squat_ui.py --url http://127.0.0.1:8521 --output reports/squat_counter/ui_v1
python scripts/check_squat_ui.py --url http://127.0.0.1:8522 --output reports/squat_counter/ui_integrated
```

识别性能评价必须使用获同意的真实视频、独立人工标注、连续运行及事先固定的匹配窗口。反馈延迟是1倍速源时间加处理至渲染回调的估计，含稳定确认偏移，不是光电实测。正式提交前按组织指南补齐真人证据；当前不宣称作业全部完成或识别准确率。
