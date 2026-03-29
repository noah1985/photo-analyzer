# v1.1.0 UI / Model Update

这次提交主要包含 4 类改动：

1. 模型切换
- App 顶部增加本地图像描述模型选择：
  - `快速`
  - `平衡`
  - `细节`
  - `摄影`
- Python CLI 增加 `--model` 参数，`analyze`、`analyze-dir`、`sample-gallery` 全部支持。

2. 标签体系升级
- Python 分析结果改为 4 个固定大分类：
  - `subject_content`
  - `scene_lighting`
  - `composition_distance`
  - `style_impression`
- 每类最多输出 2 个标签。
- taxonomy 改成新的 4 组 schema，并补充了一轮标签触发词与规则优化。

3. 时间展示优化
- 将“模型初始化耗时”和“单张分析耗时”拆开。
- App 顶部展示：
  - 模型初始化耗时
  - 总照片数
  - 成功/失败数量
  - 本次总耗时
- 每张卡片单独展示该图片的分析耗时。

4. 桌面端与本地模型联动
- Swift App 改为消费 `tag_groups`、模型信息和耗时信息。
- 重新打包本地 `.app`。
- `build_app.sh` 改为使用 `xcrun swift build`，避免误用系统旧版 Swift。

5. 流式分析与首卡耗时（后续修订）
- **问题**：`analyze-dir --stream` 在首张 `progress` 发出时模型尚未加载，界面会误显示「正在分析第 1 张」；首张卡片「单张耗时」把 `torch` / `transformers` 的首次 import 算进分析时间，与第二张起不一致。
- **CLI**：在 `start` 之后、逐张循环之前增加 JSONL 事件：
  - `model_loading`（含 `caption_model`）
  - 调用 `preload_caption_pipeline` 预加载 caption pipeline
  - `model_ready`（含 `model_initialization_seconds`）
- **Python**：`captioning` 冷启动时把 `import torch` / `transformers` 与 `pipeline(...)` 放在同一段初始化计时内；新增 `preload_caption_pipeline` 供流式入口预加载。
- **App**：解析 `model_loading` / `model_ready`；加载阶段展示「正在加载本地模型……」，就绪后写入顶部汇总用的初始化秒数；首张 `progress` 仅在预加载之后发出。若连接旧版 CLI，仍可从首张带非零 `model_initialization_seconds` 的结果回填。

6. 真实样本纠偏（本次追加）
- 针对真实照片误判新增一层轻量纠偏：
  - 人物主体优先回拉到 `人像 / 单人肖像`
  - `woman / man / girl / boy` 等基础人物词重新纳入主触发词
  - 压低 `野生动物 / 饮品 / 静物` 盖过人物主体的情况
  - `helmet + kart / riding / racing` 这类组合优先推 `运动`
  - 黑白人物图优先补 `黑白倾向`
- 触发词匹配从“任意子串命中”改为“词边界命中”：
  - 避免 `sunglasses` 误命中 `glass`
  - 避免类似 `animal` 这样的宽泛词把人物图打成 `野生动物`
- taxonomy 继续扩充为更完整的摄影标签词表，便于后续基于真实样本继续收规则。

7. 摄影模型路线收敛（本次追加）
- 新增 `photo` 模型预设，作为摄影语义优先的更强本地模型。
- 最终收敛为更稳的传统 caption 路线，底层模型改为 `microsoft/git-base-coco`。
- 清理了此前为小型多模态指令模型试验加入的结构化摄影分析冗余代码：
  - 删除结构化 JSON 解析与占位描述兜底链路
  - 删除结构化摄影模型缓存与加载分支
  - `photo` 重新回到“caption -> taxonomy 映射”的主流程
- 相比实验版 `SmolVLM`，当前 `photo` 预设的特点是：
  - 描述更稳定
  - 首张初始化更轻
  - 单张 CPU 耗时显著下降到约 `4-12 秒`
- Swift App 模型选择器同步增加 `摄影` 选项。
- 对外定位也同步调整为：
  - 摄影方向的补充模型
  - 可试，但默认仍建议优先使用 `balanced`

7. 人物分类情境感知优化（本次追加）
- **问题**：`_refine_tag_groups` 检测到人物后无条件插入"人像"标签，导致弹钢琴、街拍路人、活动现场等照片全部归为人像。同时 `has_person` 缺少复数形式（girls / boys / women / men / children 等），很多含人物的照片检测不到人。
- **taxonomy.json 变更**：
  - 新增 `music_performance`（演奏）标签，trigger_terms 覆盖 piano / guitar / violin 等常见乐器词。
  - `portrait` 的 trigger_terms 收窄为 portrait / headshot / face / posing 等明确肖像词，不再包含泛化的 woman / man / girl / boy。
  - `children` 的 trigger_terms 补齐复数形式（girls / boys / kids / babies / toddlers）及 "young girl" 等短语。
  - `couple_portrait` / `group_portrait` 补充复数短语。
  - `event_scene` 补充 performing / stage / recital / show。
- **`_refine_tag_groups` 重构**：
  - `has_person` token 集合从 8 个扩展到 24 个（加入所有常见复数、child/kid/baby/dancer/singer/player 等），并用短语检测兜底。
  - 新增 `has_music`（乐器词 + 演奏短语）、`has_performance`（舞台/表演）、`is_portrait_like`（肖像特征短语或单人+无活动）、`is_street_context`、`is_child` 等情境信号。
  - 人物分类改为情境分流：
    - 有音乐信号 → 插入「演奏」
    - 有表演信号 → 插入「活动现场」
    - 街头 + 非肖像 → 插入「街拍」
    - 肖像特征 → 插入「人像」/「单人肖像」
    - 以上皆无但有人 → 保底插入「人像」
  - 儿童检测独立，不依赖肖像判定。
  - 构图强制（近景/竖幅/特写）仅在肖像情境下执行，非肖像照片不再被强制修改构图标签。
  - 音乐场景自动追加「室内」场景标签。

验证情况：

- `python3 -m unittest discover -s tests -v`（24 tests OK）
- `bash PhotoAnalyzerApp/build_app.sh`

## v1.1.0 发布标记

本迭代正式定为 **v1.1.0**，与下列位置一致：

- `photo_analyzer/core.py` → `ANALYSIS_VERSION`
- `pyproject.toml` → `version`
- `PhotoAnalyzerApp/Sources/AnalyzerService.swift` → `bundledUIVersion`
- `PhotoAnalyzerApp/build_app.sh` 生成的 `Info.plist` → `CFBundleShortVersionString`

技术说明目录：[technical_notes/](../../technical_notes/README.md)。

推送远程与 `git tag v1.1.0` 按需执行。
