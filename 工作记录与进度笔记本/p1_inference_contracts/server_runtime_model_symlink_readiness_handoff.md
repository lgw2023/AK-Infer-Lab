# P1.8 Model Symlink Readiness Server Handoff

任务 ID：`runtime_model_symlink_readiness_2026_0706_p1_007`

目标：在不加载模型、不实例化 tokenizer、不运行推理、不安装或修复推理框架的前提下，复核 P1.7 中 `models/` 目录 metadata 为 0 的真实原因，跟随 `models/` 顶层 symlink 到 `/data/node0_disk1/Public/...` 只读解析模型 metadata，并给出是否可以进入独立小模型加载 smoke 的候选路径。

## 背景

P1.7 `runtime_small_model_readiness_2026_0706_p1_006` 已完成：

- 服务器执行 commit：`7c2e3ff`
- `tests/inference_contracts`：`11 passed in 0.20s`
- `models_dir=/data/node0_disk1/liguowei/AK-Infer-Lab/models`
- `models_dir_exists=1`
- `model_candidate_count=0`
- `metadata_file_count=0`
- `readiness_status=blocked_no_readable_model_metadata`
- `torch_npu_visible=1`
- `transformers_entry_visible=1`
- `vllm_entry_visible=1`

邮件补充观察说明：`models/` 下存在 10 个顶层条目，其中 9 个模型目录是 symlink，指向 `../../../Public/<name>`；P1.7 脚本没有跟随 symlink，所以只扫描到 `README.md`。服务器人工 `ls` 已确认 `/data/node0_disk1/Public/Qwen3.5-4B` 含 `config.json`、`tokenizer_config.json`、`model.safetensors.index.json` 等 metadata。

因此下一步不是直接加载模型，而是先用 symlink-aware 只读扫描把模型候选清单做实。

## 本轮必须回答

1. `models/` 顶层目录项哪些是 symlink，分别解析到哪个真实路径？
2. symlink 目标是否存在、是否可读、是否位于 `/data/node0_disk1/Public/`？
3. 跟随 symlink 后能否读取 `config.json`、tokenizer metadata、`*.safetensors.index.json` 等小型 metadata？
4. 哪些候选是生成式 causal LM，哪些只是 embedding、reranker 或 NER/keyword 模型？
5. 是否存在一个最适合下一轮独立小模型加载 smoke 的候选路径？
6. 如果仍不能进入加载 smoke，阻塞原因是 symlink 目标不可读、metadata 缺失、候选不是生成模型，还是需要人工选择模型？

## 执行边界

允许：

- `git pull --ff-only`
- `python -m pytest tests/inference_contracts -q`
- 对 `models/` 顶层和 symlink 目标做只读 `stat` / `readlink` / metadata 文件解析
- 对 metadata JSON 做小文件读取
- 对权重文件只做 `stat`，不读取内容
- 输出候选模型 ranking 和下一轮加载 smoke 建议

禁止：

- 不加载模型权重，不实例化模型，不实例化 tokenizer
- 不运行 `generate`、`serve`、benchmark、小模型 smoke 或 P000-P012 workload
- 不复制、移动、删除或改名 `models/` 或 `/data/node0_disk1/Public/` 里的任何文件
- 不安装、升级、卸载或修复 `transformers`、`vllm`、`vllm_ascend`、`mindie`、`mindspore` 或其他推理框架包
- 不修改 driver、CANN、apt、dpkg、NPU runtime 或 vLLM/vLLM-Ascend 源码
- 不在服务器上修改、提交或 push 项目代码
- 不发送 `.env`、SMTP 授权码、代理凭据、服务器账号、私钥、Cookie 或任何敏感信息

## 成功口径

最低成功：

- pytest 通过或给出明确失败日志
- `models_symlink_map.tsv` 显示顶层 symlink 与真实目标
- `model_metadata_inventory.jsonl` 至少覆盖可读 symlink 目标的 metadata 或明确说明为何不可读
- `readiness_conclusion.txt` 给出新的 readiness 状态

强成功：

- 明确找到至少一个生成式 causal LM 候选，例如 `Qwen3.5-4B`
- 给出下一轮独立小模型加载 smoke 的候选路径和推荐加载入口
- 明确仍只能把 P1.6 `torch_profiler_trace` 标注为 candidate bridge，不能声称 CANN device timeline pairing
