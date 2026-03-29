# Model Status

## Current Options

项目当前支持 4 个模型预设，定义在 [captioning.py](../photo_analyzer/captioning.py)：

| key | HF repo | 定位 | 当前判断 |
| --- | --- | --- | --- |
| `fast` | `Salesforce/blip-image-captioning-base` | 快速初筛 | 可用，但不适合最终结论 |
| `balanced` | `Salesforce/blip-image-captioning-large` | 默认主力 | 当前最稳，默认推荐 |
| `detailed` | `nlpconnect/vit-gpt2-image-captioning` | 自由描述更开放 | 可观察更多细节，但更容易发散 |
| `photo` | `microsoft/git-base-coco` | 摄影方向补充模型 | 可试，但目前仍未稳定压过 `balanced` |

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
  - 模型：`microsoft/git-base-coco`
  - 定位：摄影方向的补充模型
  - 特点：比此前实验模型更稳、更快，但目前仍未稳定压过 `balanced`

## Current Recommendation

当前推荐使用顺序：

1. `balanced`
2. `photo`
3. `fast`
4. `detailed`

原因：

- `balanced` 目前是综合准确度最稳的选项
- `photo` 已经从不稳定的结构化多模态实验，收敛为更稳的 caption 路线
- `fast` 适合快速扫图，不适合作为最终分析依据
- `detailed` 可用于观察额外词汇，但不适合做默认结论

## Removed / Abandoned Attempts

以下模型方案已验证存在明显问题，当前不再作为主实现：

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

当前模型下载与使用策略：

- 优先命中本地 Hugging Face 缓存
- 本地有缓存时，不再先去远端检查
- 只有本地没有缓存时，才会真正联网下载

缓存目录通常是：

- `~/.cache/huggingface/hub`（macOS / Linux 常见路径）

## Next Candidate Direction

如果后续还要继续提升模型能力，建议优先考虑：

- 保持 `balanced` 为默认
- 继续对 `photo` 做真实样本验证
- 如果未来要再尝试新模型，优先验证：
  - 是否能稳定加载
  - 是否能在真实图片上胜过 `balanced`
  - 是否不会显著拉高单张耗时
