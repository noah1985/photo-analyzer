# Model Status

## Current Options

项目当前支持 5 个模型预设，定义在 [captioning.py](../photo_analyzer/captioning.py)：

| key | HF repo | 定位 | 当前判断 |
| --- | --- | --- | --- |
| `fast` | `Salesforce/blip-image-captioning-base` | 快速初筛 | 可用，但不适合最终结论 |
| `balanced` | `Salesforce/blip-image-captioning-large` | 默认主力 | 当前最稳，默认推荐 |
| `detailed` | `nlpconnect/vit-gpt2-image-captioning` | 自由描述更开放 | 可观察更多细节，但更容易发散 |
| `photo` | `Salesforce/blip2-opt-2.7b` | 高质量补充（BLIP-2） | 通常强于传统 BLIP，但更慢、更重；需自行用样片对比 `balanced` |
| `git_large` | `Salesforce/blip2-opt-6.7b` | 更强 BLIP-2（更大 OPT） | 能力上限更高，CPU 下很慢；建议有 GPU 时再依赖 |

- `fast`
  - 模型：`Salesforce/blip-image-captioning-base`
  - 定位：快速初筛
  - 特点：速度快，描述能力基础，可作为轻量预览
- `balanced`
  - 模型：`Salesforce/blip-image-captioning-large`
  - 定位：默认主力
  - 特点：当前最稳，主体和场景描述整体最好
- `detailed`
  - 模型：`nlpconnect/vit-gpt2-image-captioning`
  - 定位：自由描述更开放
  - 特点：可能给更多细节，但发散概率更高
- `photo`
  - 模型：`Salesforce/blip2-opt-2.7b`
  - 定位：BLIP-2 系列里较轻的一档，作高质量补充
  - 特点：仍走 `transformers` 的 `image-to-text` 管线；下载与内存明显高于 `balanced`
- `git_large`
  - 模型：`Salesforce/blip2-opt-6.7b`
  - 定位：同系列更大解码器，预设 key 仍为 `git_large` 以保持 CLI / 旧脚本兼容
  - 特点：磁盘与推理成本最高；国内可通过 `HF_ENDPOINT=https://hf-mirror.com` 与 `vend_hf_models.py` 拉取

## Current Recommendation

当前推荐使用顺序：

1. `balanced`
2. `photo`（需要更强 caption、能接受更慢/更大下载时尝试）
3. `git_large`（有 GPU 或能接受极慢 CPU 时再试）
4. `fast`
5. `detailed`

原因：

- `balanced` 目前是综合准确度与成本最均衡的选项
- BLIP-2 两档在多数题材上往往优于已移除的 GIT COCO，但仍需你用真实图验证是否值得成本
- `fast` 适合快速扫图，不适合作为最终分析依据
- `detailed` 可用于观察额外词汇，但不适合做默认结论

## Removed / Abandoned Attempts

以下模型方案已验证存在明显问题，当前不再作为主实现：

- `microsoft/git-base-coco` / `microsoft/git-large-coco`（GIT）
  - 问题：在真实样片上易出现胡言、物体混淆（如苹果/葡萄、书本/包装纸），已替换为 BLIP-2
- `HuggingFaceTB/SmolVLM2-2.2B-Instruct`
  - 问题：依赖链较重，当前环境缺 `torchvision` 时会直接失败
- `HuggingFaceTB/SmolVLM-500M-Instruct`
  - 问题：结构化 prompt 下经常返回模板化占位内容
- `HuggingFaceTB/SmolVLM-256M-Instruct`
  - 问题：虽然能跑，但摄影结构化输出不稳定，实际效果经常不如传统 caption

这些实验的结论是：

- 小体量 VLM 在本项目的“摄影题材/场景/构图/风格”任务上不稳定
- 继续堆结构化 prompt 收益不高
- 当前更可靠的路线仍然是传统 caption + taxonomy 映射

## Current Runtime Behavior

当前模型使用策略（v1.2.1+）：

- 推理时**只读取项目内** `models/hf/<子目录>/`（或环境变量 `PHOTO_ANALYZER_HF_VENDOR_ROOT`），**不在分析流程中联网下载**。
- 一次性填充：在项目根执行 `python3 scripts/vend_hf_models.py`，默认 `HF_ENDPOINT=https://hf-mirror.com`。
- 子目录名与预设对应关系见仓库内 `models/hf/README.md`。

## Next Candidate Direction

如果后续还要继续提升模型能力，建议优先考虑：

- 保持 `balanced` 为默认
- 对 `photo` / `git_large`（BLIP-2）与 `balanced` 做对比样本，确认是否在常见题材上值得额外耗时
- 如果未来要再尝试新模型，优先验证：
  - 是否能稳定加载
  - 是否能在真实图片上胜过 `balanced`
  - 是否不会显著拉高单张耗时
