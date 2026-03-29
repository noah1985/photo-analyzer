# v1.1.0 UI / Model Update

这次提交主要包含 4 类改动：

1. 模型切换
- App 顶部增加本地图像描述模型选择：
  - `快速`
  - `平衡`
  - `细节`
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

验证情况：

- `python3 -m unittest discover -s tests -v`
- `bash PhotoAnalyzerApp/build_app.sh`

本次提交只做本地 commit，不推送远程。
