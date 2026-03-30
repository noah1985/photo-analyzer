# Technical Notes

这个文件夹用于记录当前项目的技术状态，重点覆盖：

- 模型选项与当前使用情况
- 最近遇到的技术问题与结论
- 当前项目的整体架构

文件说明：

- [MODELS.md](MODELS.md)
  当前可选模型、定位、优缺点、当前默认与推荐使用方式。
- [ISSUES.md](ISSUES.md)
  最近一轮开发里遇到的关键技术问题、原因、当前处理结果。
- [ARCHITECTURE.md](ARCHITECTURE.md)
  Python CLI、Swift App、taxonomy 和输出链路的整体结构。
- [EVAL_MULTI_ROUND_GIT_LARGE.md](EVAL_MULTI_ROUND_GIT_LARGE.md)
  固定样本 + `git_large` 多轮实测、逐轮校正、落盘约定与接手步骤（给其他 agent 用）；附录含 **五轮随机 5 张** 脚本 `scripts/run_eval_five_rounds_random.py`（默认产物在 `var/eval_runs/`，已 gitignore）。

当前结论摘要：

- 默认稳态模型仍然是 `balanced`
- `photo` 使用 `Salesforce/blip2-opt-2.7b`；`git_large` 使用 `Salesforce/blip2-opt-6.7b`（v1.2.1 起替换原 GIT COCO，预设 key 未改）
- 小型结构化多模态模型实验已经停止，不再作为主实现
- 当前主流程是：`图片 -> caption -> taxonomy 映射 -> 分组标签 -> 中文总结`
