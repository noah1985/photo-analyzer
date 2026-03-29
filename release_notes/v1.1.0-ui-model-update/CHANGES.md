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

验证情况：

- `python3 -m unittest discover -s tests -v`
- `bash PhotoAnalyzerApp/build_app.sh`

本次提交只做本地 commit，不推送远程。
