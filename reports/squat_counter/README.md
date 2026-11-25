# 深蹲计数技术检查与待测清单

> 2026-11-25最终状态见[提交材料索引](submission_20261121/README.md)及[逐次判读与统计](submission_20261121/assisted_review.md)。以下为分阶段历史记录，保留当时的待办与原始结果。现已提供应用、三人操作记录、同片段改进复测、演示与三条件实验；识别评价使用用户人工候选及AI辅助判读，七项无法判断明确保留。作业允许导入测试视频，未限定真人实拍；生成及后期素材的结果只说明这些输入上的行为，不作真实场景泛化结论。

当前页面`squat-counter-v2`。初始v1技术检查整理于2026-11-14；[初始验证摘要](verification.json)保留该时点状态和结果，不随后来来稿改写。2026-11-18已收齐[三名同学的v1记录](../../user_test/squat_counter_v1_summary.md)，并据反馈完成v2修复及同片段技术前后检查；[本轮验证](verification_v2.json)与旧记录分开。

2026-11-18新增[S01同学操作核对](../../user_test/squat_counter_S01_review.md)及[机器摘要](S01_intake.json)，组织者确认本人独立完成，原答复“部分完成”。视频哈希一致，自动6次、4次补记后10次；原始事件保留。输入经过剪辑，原出处/剪辑明细待补，影像及含人物截图本地保存。

同日新增[S02核对](../../user_test/squat_counter_S02_review.md)及[机器摘要](S02_intake.json)。S02自报“已完成”，保留正式前清空重试与仅自动结束的边界；自动8次、补记2次后10次。素材说明为截取片段拼接两次，最低点及稀疏取样尚非完成事件真值。[S03核对](../../user_test/squat_counter_S03_review.md)和[摘要](S03_intake.json)保留“部分完成”、未知提示及“自动化会话”环境自述；组织者确认第三名同学本人执行。S03自动8、补记2后10，自报末次23.7秒超出23.458秒片段，不作已完成事件。

三份v1原件冻结，三人记录收齐不等于全部操作通过。v2修复视频位置归零、补记选时、站位/暂停/自动结束说明及300毫秒浮点边界，模型和阈值保持；[前后对照](../../user_test/squat_counter_before_after.md)分别展示同片段实际CPU运行和同保存轨迹的规则回放，没有真人改后效果结论。

2026-11-20补充[三条件合成素材连续测试](synthetic_v2/README.md)。AI生成与后期效果明确登记；用户另补人工候选时刻及边界说明。默认左侧三段均低可见度未计数，追加右侧分别5、5、2次；全部六次原导出、逐次匹配和图表保留。浅蹲深度/稳定时长及遮挡边界未全裁定，未匹配候选数不直接当正式漏计；不把合成素材写成真实学生或真实灯光/物体条件。另有本地合成素材演示，含实际CPU推理、纠错练习及明确标记的合成摄像头状态检查，单独保留、不公开原影像。

2026-11-21整理[提交材料与假设分析](submission_20261121/README.md)，提供待人工填写的动作有效性表和本地PDF/源码/影像证据包。新增两种标签假设的完整重新匹配，说明浅蹲若无效也可能产生误计；不据假设定稿正式指标。连续运行脚本改为Git信息可缺省，并在源码ZIP解压、无Git仓库上下文下通过实际CPU导出验证；应用、模型和旧会话未改。

## 任务对应材料

| 要求 | 已准备 | 尚待真实执行 |
| --- | --- | --- |
| 用户场景与成功条件 | [规则与验收条件](../../docs/squat_counter_spec.md)，大学生单人侧面深蹲 | 真实片段试录，固定正式测试版本 |
| 完整视觉交互 | [独立入口](../../squat_counter_app.py)、[主界面入口](../../app.py)、[浏览器实现](../../src/squat_frontend/app.mjs)，摄像头/视频、开始至结束、遮挡提示、纠错和原始记录 | 用真实动作验证可靠性 |
| 识别效果与使用效果分别评价 | [逐次匹配工具](../../src/squat_evaluation.py)、[标注空表](../../user_test/squat_annotations_template.csv)、[三份操作记录](../../user_test/squat_counter_records.csv)、[组织说明](../../user_test/squat_counter_test_guide.md) | 三种光照/遮挡条件下的连续误计、漏计、完整延迟；若声称使用效果提升需真人复测 |
| 一次失败改进与同条件复测 | [实际前后对照](../../user_test/squat_counter_before_after.md)，同S03视频保留结束位置，选时正确写入；数值边界有回归 | 已有技术复测，不计为同学复测或模型准确率提升 |
| 模型、影像来源与演示 | [来源及权限说明](../../docs/squat_model_sources.md)、[素材登记空表](../../user_test/squat_media_register.csv)、[运行说明](../../user_test/squat_counter_quickstart.md) | 获同意的实际影像与最终演示视频 |

## 自动检查的证据边界

Python回归包含原健康/公平性/模型判断测试以及新入口与评价工具；Node测试覆盖稳定阈值、保持、抖动、遮挡恢复、暂停、时间跳变、宽高比例和纠错历史。

浏览器验收用真实CPU模型处理纯色空视频，另用明确标记的`mock_landmarks`测试计数与控件。摄像头为Chromium合成设备。v2检查补充精确选时、负值拒绝、关闭摄像头后片段时钟保留、结束位置及回看条同步。真实授权S03视频的前后技术运行另外保存于[before](retest_v2/before.json)/[after](retest_v2/after.json)，两次连续实跑自动数均9，手工操作不覆盖原事件。所有技术检查不增加同学样本。

2026-11-14的Debian初始检查从无vendor或健康模型的源码启动，在含空格路径新建虚拟环境并下载校验资源，pip复用部分下载缓存。具体见[历史Linux记录](linux_startup.json)。本轮启动脚本、依赖和模型资源未改；Docker服务未运行，没有重新执行Debian启动，不把初始9项写成本轮结果。

| 入口 | 机器记录 | 截图 |
| --- | --- | --- |
| 独立页 | [浏览器检查](ui_v1/browser_checks.json) | [初始](ui_v1/initial.png)、[真实模型看不清](ui_v1/unclear_real_model.png)、[模拟流程反馈锁定](ui_v1/mock_controls.png)、[窄屏](ui_v1/mobile.png) |
| 主项目侧栏 | [浏览器检查](ui_integrated/browser_checks.json) | [初始](ui_integrated/initial.png)、[真实模型看不清](ui_integrated/unclear_real_model.png)、[模拟流程反馈锁定](ui_integrated/mock_controls.png)、[窄屏](ui_integrated/mobile.png) |
| v2独立页 | [15项检查](ui_v2/browser_checks.json) | [初始](ui_v2/initial.png)、[修正控件](ui_v2/correction_controls.png)、[窄屏](ui_v2/mobile.png) |
| v2主项目侧栏 | [16项检查](ui_v2_integrated/browser_checks.json) | [初始](ui_v2_integrated/initial.png)、[修正控件](ui_v2_integrated/correction_controls.png)、[窄屏](ui_v2_integrated/mobile.png) |

本轮Python81项通过（38.06秒）、Node9项通过。旧v1截图和检查保留为历史证据；新截图不覆盖旧版。

## 复现

运行完整项目已有依赖后执行Python回归。Node仅用于开发期规则检查，运行页面不需要Node或前端构建。

```text
python -B -m pytest tests -q -p no:cacheprovider --tb=short
node --test tests/test_squat_counter.mjs
python scripts/download_squat_assets.py --check-only
```

另装Playwright且可启动Chrome的Python可执行浏览器脚本；脚本需要ffmpeg生成空视频，也可用`--blank-video`传入程序生成的纯色8秒视频。

```text
python scripts/check_squat_ui.py --url http://127.0.0.1:8534 --output reports/squat_counter/ui_v2
python scripts/check_squat_ui.py --url http://127.0.0.1:8535 --output reports/squat_counter/ui_v2_integrated
```

识别性能评价必须使用获同意的真实视频、独立人工标注、连续运行及事先固定的匹配窗口。反馈延迟是1倍速源时间加处理至渲染回调的估计，含稳定确认偏移，不是光电实测。正式提交前按组织指南补齐真人证据；当前不宣称作业全部完成或识别准确率。
