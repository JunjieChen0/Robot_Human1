# WeightTrend（暂定名）

> **参加“模型判断”测试的同学：** 请先阅读[Linux下载与启动说明](user_test/model_judgment_remote_quickstart.md)，下载源码后运行 `bash start_model_judgment.sh`。首次自动安装页面依赖，无需训练模型；请先完成任务，再阅读下方实验结论。

**人机交互课程作业选题 2：减重趋势分析原型**

> **2026-10-19 全流程界面迭代：** 已补充单人 CSV 导入、中文选项、输入概览、待重算提示、提交快照、异常恢复、理解自测与匿名反馈下载。第三轮依据测评统一百分比和横向标签、区分趋势记录与外推、显示比较时间，并完善术语、来源和错误提示。
> 本地模型已生成时运行 `python -m streamlit run app.py` 即可使用；缺模型时按 §5 重建。
> 本轮提交索引见[交互设计与验证报告](reports/ui/交互设计与验证报告.md)，含用户场景、流程图、模型接口及截图。
> 用户测试见[填写模板](user_test/真人测试填写模板.md)、[汇总与迭代说明](user_test/interaction_iteration.md)和[原次记录表](user_test/interaction_records.csv)。当前纳入 [002](user_test/feedback_002_review.md)、[003](user_test/feedback_003_review.md)、[004](user_test/feedback_004_review.md) 三份任务记录，另有前两人的[更新后复测](user_test/retest_comparison_20261019.md)。002、003 修改前两项评分均值均为 3.50/5；第二轮界面的两人复测与 004 首测两项均为 4/5，仅作主观描述。第三轮已有 55 项自动测试和 32 项浏览器检查通过，最新截图见[第三轮验证](reports/ui/iteration_3/)。这些旧评分不作为第三轮修改后的用户评价。
> 002 原次六项用时合计 200.2 秒；003 为执行计时；004 的 T1 为 1.75 秒，T2–T6 为含阅读及工具开销的墙钟计时。各自口径、中断和恢复分别保留，不合并平均耗时或宣称首次独立完成。

> **受邀参加第二次作业测试的同学，请从这里开始：**
> [公平性页面测试指南](user_test/fairness_test_guide.md)包含启动方法、四项任务和报告提交要求。
> **请先将[个人测试报告模板](user_test/fairness_report_template.md)另存为副本再填写**，模板已附固定题干；完成后把 Markdown 文件发回邀请你测试的同学即可。
> 只测试该页面不需要下载数据或训练模型。请先按指南测试，再阅读下方实验结果，避免影响首次回答。

用户自报身高、体重记录、运动量和饮食，原型展示体重趋势、能量平衡估算和肥胖等级估计，并说明预测的适用范围与不确定性。

> **当前进度：原型和性别公平性审核页均已实现，第三轮自动测试 55 条通过。**
> 第一次作业三名同学的测试记录及提交文档保存在本地 `commit/`，不随 Git 克隆分发。第二次作业已收到三份真人评测来稿，参与性质由用户确认。P01已明确T1/T2未切换控件，按部分完成保留；手机秒表记录的T4包含自测，标准终点用时缺失。其核心理解回答已纳入，但已提前阅读源码和数据。002、003的限制仍保留，三人统一统计尚未完成。原文与核对材料保存在本地，`user_test/` 保留空白模板。
>
> 提交材料第 1 项「数据来源说明、可运行代码及运行说明」在本仓库内的载体即 §2（数据来源）、§3（模型与效果）与 §5（运行说明）。

## 1. 任务定义：目标用户、使用场景与输入输出

**目标用户**：本轮界面以课堂使用的大学生、特别是健康管理初学者为主要用户，另为课程管理和审核人员提供独立公平性页。原型定位为**教学演示与自测工具**，不作为医疗诊断依据；交互用户选择不代表模型已在该人群完成外部验证。

**使用场景**：用户在家庭或课堂环境中录入自身体重记录、运动量与饮食信息，原型回答三类问题：

1. 我目前的体重状态属于哪个肥胖等级？（分类预测）
2. 我的体重在记录期内变化趋势如何？（描述性分析）
3. 按当前能量平衡，未来体重大致会向哪个方向变化？（解析外推）

**输入数据**：性别、年龄、身高、体重、饮食习惯（蔬菜摄入评分 1–3、主餐次数、高热量饮食、加餐频率、饮酒频率）、运动频率评分 0–3、生活方式（出行方式、吸烟、家族超重史、是否记录热量摄入）——原型表单共采集 **14 个字段**。

**未采集字段的处理**：模型训练时包含「每日饮水量（CH2O）」与「电子设备使用时间（TUE）」两项，但原型不再向用户采集，以简化录入，预测时由模型按**训练集中位数**填充（CH2O = 2.0、TUE = 0.634），保证输入仍为完整的 19 维特征。经实测，7 个演示档案在该口径下仍全部判定正确；该取值口径已在界面使用说明与特征重要性表中披露。

**界面结构**：录入表单按语义分为「🧍 身体基本信息」「🥗 饮食习惯」「🏃 运动与生活方式」三张卡片，每行 4 列填满；蔬菜摄入量、高热量饮食与运动频率带问号详细说明；结果区采用概率表 + 柱状图双栏布局。

**输出**：7 类肥胖等级的概率分布、记录期体重趋势图、按 Mifflin-St Jeor 基础代谢 + 活动系数 TDEE 计算的每日能量差与 90 天体重外推。

交互流程：

```text
录入身高 / 体重记录 / 运动量 / 饮食
          ↓
校验字段、格式与合理范围
          ↓
体重趋势图 + 能量平衡估算（消耗 - 摄入）
          ↓
肥胖等级估计与解释、适用范围说明
          ↓
修改录入 → 重新计算 → 对比结果
```

体重趋势部分直接基于用户自己的多次记录，是描述性分析，不依赖训练数据；需要训练数据支撑的模型部分见下节数据源结论。

## 2. 数据来源与处理结论

### 2.1 公开数据调研结论（2026-10-05）

| 候选 | 类型 | 规模 | 字段覆盖 | 许可 | 结论 |
| --- | --- | --- | --- | --- | --- |
| [UCI 544 Estimation of obesity levels based on eating habits and physical condition](https://archive.ics.uci.edu/dataset/544/estimation+of+obesity+levels+based+on+eating+habits+and+physical+condition) | 横断面个体级 | 2111 × 17 | 身高、体重、饮食习惯（FAVC/FCVC/NCP/CH2O/SCC）、运动频率 FAF、肥胖等级标签 | CC BY 4.0 | **采用**：模型部分主数据，输入结构与原型录入项一致 |
| CDC BRFSS Nutrition, Physical Activity and Obesity | 横断面调查（聚合） | 大 | 饮食、运动、体重状态 | 本项目未核验 | 未采用 |
| NHANES（膳食 24h 回顾 + PAQ + 体格测量） | 横断面个体级 | 大 | 膳食、运动、身高体重 | 本项目未核验 | 未采用 |
| 纵向个人体重 + 饮食 + 运动日志 | 时间序列 | — | — | — | **未找到公开可用数据**；趋势部分改为用户自报记录的描述性分析 + 能量平衡模型外推 |

调研要点：

- 本项目未获得适合直接使用的个人纵向体重、饮食与运动数据，不能据此断言此类公开数据不存在；趋势模块使用自报记录与简化能量外推。
- UCI 544 的输入项（身高、体重、饮食行为、运动频率）与原型录入项一一对应，且带肥胖等级标签，可直接支撑作业要求的训练/验证/测试与模型比较。
- 能量平衡部分采用 Mifflin-St Jeor 静息能量估算、固定活动系数与线性外推；公式可直接计算，但个体预测误差仍需纵向数据评价。

### 2.2 数据质量与异常值处理

- 数据规模：原始 CSV 为 2111 行 × 17 列（16 个属性 + 1 个标签列），缺失 0，非有限值 0；MTRANS one-hot 展开为 4 个哑变量后，模型输入为 **19 维特征**。
- 完全重复行：33 行分属 9 个重复组，其中冗余 24 行（`data/processed/data_quality.json` 的 `duplicate_full_rows`）。**保留不删除**，划分时按组整体分配，避免完全重复行跨集合（实测 0 组跨划分）；该检查不能排除相近合成样本的影响。
- 异常值检测（`src/preprocess.py::detect_outliers`）：
  - **问卷字段**（FCVC/NCP/CH2O/FAF/TUE）取值本身是问卷语义（如 FAF 0–3 表示每周运动频率等级），只做领域边界校验，结果**无领域非法值**；
  - **连续字段**（Age/Height/Weight）额外报告 IQR 离群点（Age 168、Height 1、Weight 1），这些属于分布尾部而非数据错误，**保留全部样本**，不机械删除或截尾。
  - 完整报告见 `reports/tables/outlier_summary.json`。
- 数据局限（报告中需说明）：UCI 544 的问卷部分来自哥伦比亚/秘鲁/墨西哥人群，其余大部分为 SMOTE 合成扩充样本（据数据集论文），类别边界可能比真实人群干净，**0.94 量级的准确率存在一定乐观偏差**。

## 3. 模型与效果评价（2026-10-06 更新）

| 环节 | 结果 |
| --- | --- |
| 数据规模 | 原始 2111 × 17（编码后 19 维特征），缺失 0，重复 9 组 33 行 / 冗余 24 行（保留并按组划分，不机械删除） |
| 划分 | 按标签分层 60/20/20 = 1270 / 421 / 420；无受试者编号，不做用户分组；重复行按组整体划分，无跨划分泄漏 |
| 验证集比较 | RandomForest macro-F1 0.9569，LogisticRegression 0.8625，选中 RandomForest |
| 测试集评价 | Accuracy 0.9452，macro-F1 0.9438，错误样本 23 / 420 |
| 特征重要性 | Weight 0.326、Height 0.097、Age 0.095 居前（模型高度依赖体重/身高/年龄信号） |
| 自动测试 | `pytest -q` 54 通过（含公平性、CSV 导入与交互恢复扩展） |

按原型的中位数填充方式另行评价，同一测试集准确率为 93.10%、宏 F1 为 0.9293；完整特征评价仍为 94.52%、0.9438。结果见 `reports/tables/prototype_input_metrics.json`。

### 3.1 错误案例分析（`reports/tables/error_analysis.md`）

- 错误率 5.5%（23/420），错误最多的真实类别是**超重 I 级**（7 条）。
- 错误集中在**相邻 BMI 等级边界**（正常体重 ↔ 超重 I 级），符合类别边界样本预期。
- 错误样本平均体重比正确样本低约 8.8 kg；两组类别构成不同，不能把这一均值差直接解释为误判原因，也不能据此比较不同单位字段的重要性。
- 约 52% 的错误样本最高概率落在 40%–70% 区间，这只是错误子集的概率分布，不能据此推断所有样本的错误率。
- 可能原因：边界样本特征组合落在决策边界附近；数据含 SMOTE 合成样本，边界模式可能不完全反映真实人群；概率分布平坦时轻微特征变化即可改变预测。

### 3.2 趋势外推的验证口径

本项目未采用纵向训练数据，趋势模块不依赖分类训练集：记录期变化由用户自报体重记录直接计算，未来 90 天外推由**解析能量平衡模型**给出（7700 kcal 折合 1 kg，每日能量差恒定假设），曲线包含第 90 天终点。`tests/test_energy.py` 检查公式参考值、活动系数阈值、能量差方向和外推终点；这些测试不能替代真实预测误差评价。界面标注结果仅用于趋势参考，不作为医学诊断。

活动水平由运动频率字段 FAF（数据集取值 0–3）映射，档位阈值为 1/3/5，因此在当前录入范围内**「高度活动」不可达**，最高只能得到「中度活动」（1.55 系数），该映射为原型采用的简化假设，尚未验证个体误差。该口径已在界面 FAF 字段说明中披露；若要放开上限，需同时调整 `src/energy.py` 的档位阈值并重算外推数值。

## 4. 待决问题

- [x] 模型路线锁定：UCI 544 分类 + 能量平衡外推的混合路线。
- [x] 趋势外推的验证方式：公开纵向数据缺失，采用**解析自洽验证 + 界面明示示意性口径**（见 §3.2，迭代 3/5）。
- [x] 原型录入项与 UCI 544 字段的映射表（见 `src/config.py` 的 `FIELD_DESCRIPTIONS_ZH`）。
- [x] 异常值处理：检测 + 论证保留，报告见 `reports/tables/outlier_summary.json`（迭代 2）。
- [x] 错误案例分析：脚本 `src/error_analysis.py` 与报告 `reports/tables/error_analysis.md`（迭代 3）。
- [x] 已依据反馈完成界面修改，取得 002、003 更新后复测及 004 最新版反馈；任务记录、问题与前后差异见 `user_test/interaction_iteration.md`。

## 5. 运行说明

### 5.1 环境要求

| 项 | 要求 | 实测通过版本（2026-10-09） |
| --- | --- | --- |
| Python | 3.11 | 3.11.15 |
| 依赖 | 见 `requirements.txt`（范围约束，未提供 lock 文件） | streamlit 1.65.0、scikit-learn 1.9.0、pandas 2.3.3 |
| 网络 | **首次运行需要联网**访问 `archive.ics.uci.edu` 下载数据集；离线兜底见 §5.5 | — |

### 5.2 运行体重管理原型需要重建的产物

`.gitignore` 排除了三类可由脚本重建的本地产物。克隆后若要使用体重管理页面或复现实验，按 §5.3 重建；只参加公平性页面用户测试时，按[测试指南](user_test/fairness_test_guide.md)安装依赖并启动即可：

| 路径 | 内容 | 由哪一步生成 |
| --- | --- | --- |
| `data/raw/` | UCI 544 官方压缩包与原始 CSV | `python -m src.download_data` |
| `data/processed/` | `features.csv`（19 维编码 + `split` 列）、`data_quality.json` | `python -m src.preprocess` |
| `models/` | `final_model.joblib`、`model_metadata.json`、`raw_ranges.json` | `python -m src.train` |

已入库、无需重建的产物：`reports/tables/*`、`reports/figures/*`、`data/sample/demo_profiles.csv`。
缺少模型文件时 `app.py` 会打印缺失清单与重建命令后停止，不会崩溃。

### 5.3 运行步骤

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

python -m src.download_data   # 下载并解压 UCI 544        → data/raw/
python -m src.preprocess      # 编码、质量检查、异常值报告、分层划分 → data/processed/
python -m src.train           # LR vs RF 验证集比较，保存最终模型   → models/
python -m src.evaluate        # 测试集指标、混淆矩阵、演示档案      → reports/
python -m src.error_analysis  # 错误案例分析报告            → reports/tables/error_analysis.md
streamlit run app.py          # 启动交互原型（默认 http://localhost:8501）
pytest -q                     # 运行自动测试
```

步骤有先后依赖：`train` 读 `data/processed/features.csv`，`evaluate` 与 `error_analysis` 读 `models/final_model.joblib`，`error_analysis` 还读 `evaluate` 产出的 `reports/tables/test_predictions.csv`。完整自动测试和体重管理页面需要 `models/` 与 `data/sample/` 已就位；公平性审核页面只读取已入库的 `reports/fairness/`，无需这些模型文件。

### 5.4 成功判据

| 检查项 | 期望结果 |
| --- | --- |
| `pytest -q` | **34 passed**，退出码 0 |
| `python -m src.train` 标准输出 | RandomForest macro-F1 **0.9569** > LogisticRegression **0.8625**，最终模型为 RandomForest |
| `python -m src.evaluate` 标准输出 | accuracy **0.9452**、测试样本 **420**、错误 **23**（macro-F1 0.9438 见 `reports/tables/test_classification_report.csv`） |
| 原型服务 | `http://localhost:8501/_stcore/health` 返回 `ok` |
| 原型端到端（默认档案直接提交） | 正常体重 / 最高概率 47.0% / 差值 12.3% / 轻度活动 / 每日消耗 2037 kcal / 能量差 +237 kcal |

`RANDOM_STATE = 42`（`src/config.py`）固定了划分与训练随机性，按上述顺序重跑应复现同样的指标。

### 5.5 离线环境兜底

无网络时 `src.download_data` 会重试 3 次后失败，并在报错信息中给出手动步骤：

1. 从 §2.1 表中的 UCI 544 官方链接下载压缩包；
2. 保存为 `data/raw/uci544.zip`；
3. 重新运行 `python -m src.download_data`——脚本检测到有效压缩包后跳过下载，直接解压到 `data/raw/uci544/`；
4. 解压后必须存在 `data/raw/uci544/ObesityDataSet_raw_and_data_sinthetic.csv`；若压缩包内部结构不同，脚本会报错并打印该期望路径，按路径手动放置即可。

数据就位后，`src.preprocess` 及之后的所有步骤都是本地计算，不再需要网络。

---

迭代过程记录见 `CHANGELOG.md`（基线快照 → 正确性修复 → 数据处理规范性 → 效果评价补全 → 原型改进 → 文档汇总 → 精简录入项 → 界面重设计 → 提交路径修复 → 字段口径修正 → 运行说明补全 → 交付文档汇编 → 交付文档改本地件），每次迭代（含小版本修复）都会追加条目并同步文末「当前状态」表。

## 公平性扩展作业

参加用户测试请按[公平性页面测试指南](user_test/fairness_test_guide.md)操作，并返回[个人测试报告](user_test/fairness_report_template.md)。[记录者说明](user_test/fairness_facilitator_guide.md)含核对依据，由组织测试的同学使用。以下内容用于实验复现，不是测试者必须执行的步骤。

侧栏选择“模型公平性审核”可查看分组样本、基线与约束方案、漏判率与误判率、区间及解释。该实验将肥胖 I–III 型合并为正类，按原数据的性别分组；它是独立的二分类审核，不替代原七分类和能量外推。

```powershell
python -m src.fairness train
python -m src.fairness evaluate
python -m src.fairness_report
python -m pytest -q
python -m streamlit run app.py
```

先准备处理数据；若从 Git 克隆，按原流程下载、预处理，并为体重页面训练和评价原模型。新实验的 StandardScaler 和两种二分类模型仅在训练集拟合，验证集选择约束上限，测试集用于冻结后的评价。约束网格为 0.01、0.02、0.05、0.10、0.20；验证集平衡准确率和 F1 各允许最多下降 0.02，在合格方案中优先选 EO 差值较小者。

实测选中 eo_0.01；基线与约束方案在 420 条测试记录上逐条预测相同，平衡准确率均为 0.992650，F1 为 0.992288，EO 差值为 0.020833。女性本次零错误，男性漏判 2 次、误判 1 次。实验没有改善群体差异，报告说明了训练约束已满足等原因；不以高整体成绩或零性能损失宣称公平。

审核产物在 reports/fairness/，本地提交材料在 commit/公平性作业/。生成图表和 Markdown 正文用 src.fairness_report，PDF 是随包提供的排版版本。运行依赖新增 Fairlearn 0.13.0，其 SciPy 约束由 pip 解析。最新后续记录中，P01两项完整、两项部分完成，002和003各四项操作及主体回答完整覆盖，共10/12项、83.3%；这是操作完整完成比例，不是理解正确率或首次独立完成率。三人本轮均自报求助0次，但已有资料或页面接触。P01完整模块375秒含自测，标准T4精确用时缺失；002自报359秒，计时工具未记录；003新公平性报告自报手机分段计时330/495/385/500秒，共1710秒，从读题到保存首次回答，不含自测和安装。因计时范围及经验不同，不计算三人统一平均用时。003此前1270秒体重记录另存；新稿的平衡准确率名称、下方表格联动等偏差已列入核对，原话保留。CSV仍是空白转录模板，个人原文与补充只存本地。ZIP附最新报告和指南；审核页展示冻结结果，不提供测试集阈值或算法调参。

## 任务3扩展：模型判断

Linux同学从GitHub下载ZIP并解压后，运行 `bash start_model_judgment.sh` 即可直接进入本页；首次创建虚拟环境并安装 `requirements-judgment.txt` 中的四项展示依赖，后续复用环境。需要Python 3.11+；Debian 13自带的Python 3.13可用，缺venv时按[简明指南](user_test/model_judgment_remote_quickstart.md)安装系统venv组件。CPU运行，不需要独立显卡；通过SSH登录服务器的情况也附有端口转发方法。独立入口为 `model_judgment_app.py`，仅读取已入库结果，不依赖本地模型和训练数据。

启动 `python -m streamlit run app.py`，在侧栏选择“模型判断”。该页读取已入库的 `reports/model_judgment/`，只看页面不需要下载原始数据或训练模型。

页面展示五项预先选定的实际输入：体重（kg）、身高（m）、年龄（岁）、运动频率（FAF，0–3评分）、自动填充的饮水量（CH2O，1–3问卷评分，不是升数）。可展开查看全部19列及编码。BMI不是独立模型输入；运动评分没有“近期”时间窗，不能把评分大于0的记录称为近期参加活动的人数。

**实验口径**：原分类页的最终模型用训练加验证集重拟合，不能再拿这个模型在同一验证集上做未见数据评价。本扩展另用相同算法和参数的随机森林（300棵树、seed=42），仅拟合1270条训练记录，固定后在421条验证记录上评价；不使用测试集，不替换原分类页模型。验证输入按当前表单口径，将CH2O/TUE填为训练中位数。结论限定该实验模型，不直接解释最终重拟合的模型实例。

以七类召回率均值即平衡准确率为基线，每次从原始验证输入复制，仅打乱五项中的一列，每项重复30次，不重训模型。条形图显示“基线分数−打乱后分数”的均值，横线为均值±1标准差（ddof=0），单位为百分点；不是置信区间。零值和负值不截断、不移除，不将相对排名归一化成百分比。当前基线93.12%，体重的平均下降最大（59.446个百分点）；五项不等于全部输入排名。CH2O为常量，置换下降为0，不说明饮水对健康不重要。相关特征替代、打乱后的不常见组合和合成数据相关性均会限制解释。

点击图中条形或橙点，或用下拉框选择输入，可查看同批验证记录的分布、区间人数及比例，并核对未打乱时的一条正确和一条错误记录。默认各选原CSV行号最小的一条，含表头的行号可追溯，用户可换案例；并列展示全部输入、真实标签、预测标签与未经校准的最高类别概率。整批重要性不是单条预测的局部解释，不能证明个人患病原因。

重建实验（需先安装项目依赖）：

```powershell
python -m src.download_data
python -m src.preprocess
python -m src.model_judgment
python -m pytest tests -q
python -m streamlit run app.py
```

新增计算代码为 `src/model_judgment.py`，页面为 `src/model_judgment_ui.py`。产物包括静态PNG图、五项统计CSV、150次原始置换分数、验证输入及案例CSV、输入字典和记录模型/代码/数据哈希的JSON。实验模型保存在被Git忽略的 `models/judgment_model.joblib`，可重建；不会覆盖原模型或公平性结果。当前目录有本地提交包副本，pytest需明确指定 `tests`，避免收集到提交材料中的重复测试。

浏览器回归脚本为 `scripts/check_model_judgment_ui.py`，使用另装Playwright且已可启动Chrome的Python环境运行，服务默认端口8517，可用`--url`指定。它只做自动检查，不提交真人回答。

**三人v1首测已收齐，页面已更新为v2**：[J01](user_test/model_judgment_J01_review.md)、[002](user_test/model_judgment_002_review.md)、[本次重新提交的003](user_test/model_judgment_003_review.md)两项核心回答均符合要点，模型哈希、分数和案例与冻结结果一致。[J01原话](user_test/model_judgment_J01_record.json)、[002原话](user_test/model_judgment_002_record.json)、[本次003原话](user_test/model_judgment_003_record.json)与[三行CSV](user_test/model_judgment_records.csv)保留。行为、资料接触和0次提示按自报；002从图表提示读数的声明不改写为查表。缺失日期、用时和002环境留空；003“训练里约77%”按来源数据集比例澄清，不改原话。

组织者分别[确认三位同学亲自操作](user_test/model_judgment_actor_confirmation.json)。本次003仅纳入新来稿，撤回资料不恢复，旧页面同名编号不合并。v2在图上直接标均值、减少刻度，提前说明饮水常量及整批/个人边界，澄清行号和五项范围，增高输入表，取消默认选中特征，支持多行回答、即时锁定和背景自报字段。模型及实验数值未变。[修改前后对照](user_test/model_judgment_before_after.md)包含逐项依据、v1/v2截图及验证记录。**尚无v2真人复测**，不宣称误读消除或理解率提升；复测原话另存，详见[测试指南](user_test/model_judgment_test_guide.md)。

方法参考：[scikit-learn置换重要性](https://scikit-learn.org/stable/modules/permutation_importance.html)；图表选取接口参考[Streamlit Altair图表](https://docs.streamlit.io/develop/api-reference/charts/st.altair_chart)。
