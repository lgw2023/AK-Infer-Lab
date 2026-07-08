# Developer to Server

## 当前任务：P0/P3 hardware ceiling sweep

- 任务 ID：`hardware_ceiling_sweep_2026_0708_p0_007`
- 上一轮依据：P1.28 `runtime_vllm_api_msprof_larger_controlled_replay_2026_0708_p1_028`
- 详细 handoff：`工作记录与进度笔记本/p0_hardware_ceiling/server_hardware_ceiling_sweep_handoff.md`
- 请先 `git pull --ff-only`，然后按详细 handoff 中 `建议执行命令` 的完整 bash 代码块执行。

## 为什么进入本任务

P1.28 附件已确认小 prompt 推理链路观测闭环强成功：

- 附件目录：`/Users/liguowei/Downloads/akp1_28vllmapimsproflargercontrolledreplay`
- `git_pull_exit_code=0`、`pytest_exit_code=0`
- `msprof_prefix_cache_on_exit_code=0`
- `msprof_prefix_cache_off_exit_code=0`
- `request_device_aggregate_fast_exit_code=0`
- `controlled_readout_exit_code=0`
- on/off 两轮均 `request_count=32`、`success_case_count=32`、`failed_case_count=0`
- on/off 两轮均固定 64 tokens，`generated_token_count_mismatch_count=0`
- final analysis `overall_status=success`
- readout `overall_status=success`、`missing_files=[]`
- readout 输出 12 行 mode/group、8 行 prefix-pair、23 行 top-op、21 行 AI Core metric 小摘要

但 P0-P4 不能直接收尾。当前 P0.5 `obs_2026_0705_atlas800t_a2_006` 只证明服务器环境和轻量 microbench 可测；它不是系统化 hardware ceiling sweep，不能声称已经把 H2D/D2H、AI Core/GEMM、DRAM、SSD 等硬件上限打满。下一步必须补 P0/P3 独立硬件 microbench，而不是继续扩大 P1 推理 workload、启动 P5 或启动 DeepSeek-V4-Flash 服务器任务。

## 通信前置要求

- 昇腾服务器每次邮件正文和每个附件都按不超过 70KB 处理。
- 不要通过邮件发送 raw 大日志、实验目录或大文件。
- 大 CSV/log 如超过 70KB，留在服务器本地，邮件只写路径、文件大小和关键行数。
- 邮件只回传任务状态、精简摘要、小 CSV/JSON/txt、70KB 内附件和服务器侧路径。

## 服务器需要做什么

1. 在 `/data/node0_disk1/liguowei/AK-Infer-Lab` 执行详细 handoff 的完整 bash 块。
2. 执行 `git pull --ff-only`。
3. 运行本地测试：`tests/observability_profile/test_hardware_ceiling.py` 和 `tests/observability_profile/test_microbench.py`。
4. 运行 `tools.observability_profile.hardware_ceiling collect`。
5. 只做硬件 microbench：
   - H2D/D2H copy sweep
   - sync/async 与 pinned 尝试
   - AI Core matmul shape sweep
   - CPU/DRAM 大块读/拷贝
   - SSD fio 多 block size / queue depth / rw mode
6. 生成 `hardware_ceiling_result.json`、`summary.txt`、四类 CSV 和 `mail_attachment_candidates.tsv`。

## 成功口径

强成功：

- `git_pull_exit_code=0`
- `pytest_exit_code=0`
- `hardware_ceiling_exit_code=0`
- `hardware_ceiling_result.json` 中 `overall_status=success`
- `npu_copy_sweep.csv` 至少有 H2D 和 D2H 的 measurable 行，且覆盖 MB/GB 级 size
- `npu_matmul_sweep.csv` 至少有 `1024/2048/4096` 的 `float16` measurable 行
- `cpu_dram_sweep.csv` 至少有 `256M` 和 `1G` measurable 行
- `ssd_fio_sweep.csv` 至少有 read/write/randread/randwrite 的 measurable 行
- 生成 `mail_attachment_candidates.tsv`

最低完成：

- 即使任何一类 sweep 失败，也必须回传 `server_run_context.txt`、`mail_summary.txt`、`hardware_ceiling_result.json`（如已生成）、`mail_attachment_candidates.tsv`、失败日志尾部和服务器侧路径。
- 不允许把失败项静默删除；必须在对应 CSV 中写 blocked/error，或在正文列出缺失文件与失败原因。

## 执行边界

允许：

- `git pull --ff-only`。
- 使用当前 conda 环境运行本地 Python 脚本和指定 pytest。
- source CANN 环境。
- 使用当前已有 `torch` / `torch_npu`、`numpy`、`fio`、`perf`、`numactl`。
- 默认使用 `ASCEND_RT_VISIBLE_DEVICES=6` 与 `--npu-device npu:0`。
- 使用 `/data/ak-trace/hardware_ceiling_scratch` 作为 fio scratch。
- 输出 70KB 内的小摘要、CSV、JSON、文件清单和小日志。

禁止：

- 不安装、升级、卸载或修复任何包。
- 不创建新 conda 环境。
- 不改 driver、CANN、apt、dpkg、NPU runtime、vLLM 或 vLLM-Ascend 源码。
- 不加载任何模型权重。
- 不启动 vLLM server，不发送 `/v1/completions` 请求。
- 不运行 msprof，不读取或生成 profiler raw trace。
- 不切换 Docker 推理栈。
- 不在服务器上修改、提交或 push 项目代码。
- 不回传 `.env`、SMTP 授权码、代理凭据、服务器账号、私钥、Cookie 或任何敏感信息。
- 不回传超过 70KB 的邮件正文或附件。
- 不输出模型 benchmark、生产吞吐结论、scheduler 效率结论、prefix cache 命中率结论、瓶颈归因或优化建议。

## 回传要求

邮件正文请包含：

```text
P0/P3 hardware ceiling sweep 已完成/失败。

run_id: hardware_ceiling_sweep_2026_0708_p0_007
commit: <git rev-parse HEAD>
artifact_dir: 工作记录与进度笔记本/hardware_ceiling_runs/hardware_ceiling_sweep_2026_0708_p0_007
git_pull_exit_code: <...>
pytest_exit_code: <...>
hardware_ceiling_exit_code: <...>
overall_status: <...>

peak_readout:
- h2d_best_gbps=<...>
- d2h_best_gbps=<...>
- matmul_best_tflops=<...>
- dram_read_best_gbps=<...>
- dram_copy_best_gbps=<...>
- fio_read_best_mib_s=<...>
- fio_write_best_mib_s=<...>

row_counts:
- npu_copy_sweep=<...>
- npu_matmul_sweep=<...>
- cpu_dram_sweep=<...>
- ssd_fio_sweep=<...>

边界：本轮只做独立硬件 microbench；未加载模型，未启动 vLLM，未运行 msprof，未安装或修复包，未输出模型 benchmark/吞吐/scheduler/prefix-cache/瓶颈归因结论。
```

附件只允许包含 `mail_attachment_candidates.tsv` 中 `mail_ok=true` 且不超过 70KB 的小文件。优先回传：

- `mail_summary.txt`
- `summary.txt`
- `server_run_context.txt`
- `run_context.json`
- `hardware_ceiling_result.json`
- `npu_copy_sweep.csv`
- `npu_matmul_sweep.csv`
- `cpu_dram_sweep.csv`
- `ssd_fio_sweep.csv`
- `mail_attachment_candidates.tsv`

如果任何 CSV、JSON 或 log 超过 70KB，不要压缩或拆分回传；正文只写服务器路径、文件大小和关键行数。
