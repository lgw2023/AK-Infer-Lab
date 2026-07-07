# P1.23 vLLM API msprof Stats Pairing Handoff

任务 ID：`runtime_vllm_api_msprof_stats_pairing_2026_0707_p1_023`

目标：在 P1.22 已证明 `continuous16_mixed` 16 请求负载可以做 prefix-cache on/off 受控对照后，启动第一轮真实 vLLM API workload profiler 证据采集。服务器需要对同一 `continuous16_mixed` 负载分别运行 `msprof_prefix_cache_on` 与 `msprof_prefix_cache_off` 两个子任务，用 `msprof --msproftx=on` 包住现有 vLLM API concurrency 脚本，产出客户端 P1 trace、vLLM server stats、msprof host/device/sqlite 文件枚举、timebase 候选和选定 profiler 产物。

本轮是 profiler 覆盖与 stats pairing 证据采集，不是 benchmark、压测、吞吐比较、prefix cache 命中验收、调度效率结论、瓶颈归因或优化建议。

## P1.22 已有依据

P1.22 `runtime_vllm_api_prefix_cache_ab_2026_0707_p1_022` 已成功：

- `pytest_exit_code=0`
- `prefix_cache_on_exit_code=0`
- `prefix_cache_off_exit_code=0`
- `prefix_cache_ab_validation_exit_code=0`
- 两轮均为 `case_plan=continuous16_mixed`
- 两轮均 `request_count=16`、`success_case_count=16`、`failed_case_count=0`
- 两轮均 `client_overlap_candidate_count=120`
- 两轮均 `trace_validation_errors=0`
- `prefix_cache_on` 命令包含 `--enable-prefix-caching`
- `prefix_cache_off` 命令不包含 `--enable-prefix-caching`
- `prefix_cache_on`: `server_stats_sample_count=1`、`max_running=15`、`max_waiting=1`、`max_kv_cache_usage_pct=7.9`、`max_prefix_cache_hit_rate_pct=49.2`
- `prefix_cache_off`: `server_stats_sample_count=2`、`max_running=9`、`max_waiting=5`、`max_kv_cache_usage_pct=6.3`、`max_prefix_cache_hit_rate_pct=0.0`

因此下一轮可以进入 profiler 采集，不需要继续只做无 profiler 的小 smoke。

## 本轮必须回答

1. `msprof --msproftx=on` 能否包住 `tools/inference_contracts/run_vllm_api_concurrency_smoke.py` 及其 vLLM API server 子进程并正常退出？
2. `msprof_prefix_cache_on` 与 `msprof_prefix_cache_off` 是否仍然各自完成 16/16 请求、client overlap、P1 trace validator？
3. 两个子任务的 server command 是否保持 prefix-cache 开关分离？
4. 两个子任务是否都生成 vLLM `vllm_api_server_stats_summary.tsv`？
5. msprof 输出目录是否包含 `host`、`device_<id>`、`sqlite`、`time.db` 或其他可用于后续 pairing 的时间字段候选？
6. msprof 产物体积是否可控；如果原始 raw data 过大，是否已只回传 selected profiler 产物、文件列表和大小清单？
7. 是否能形成 `msprof_pairing_inventory.tsv`，把每个 mode 的请求成功数、P1 trace 校验、vLLM stats、msprof 文件数、sqlite 数、timebase 候选数放到一张表？

## 执行边界

允许：

- `git pull --ff-only`
- `python -m pytest tests/inference_contracts -q`
- 使用服务器当前 conda 环境
- source `/usr/local/Ascend/cann-9.0.0/set_env.sh`
- source `/usr/local/Ascend/nnal/atb/set_env.sh`
- 使用当前环境已有 `vllm`、`vllm_ascend`、`msprof`
- 使用 `/data/node0_disk1/Public/Qwen3.5-4B`
- 使用 `ASCEND_RT_VISIBLE_DEVICES`、`VLLM_USE_V1`、`VLLM_PLUGINS=ascend`、`VLLM_WORKER_MULTIPROC_METHOD`
- 用 ASCII `/tmp/<run_id>_<mode>_msprof` 作为 `msprof --output`
- 对 `prefix_cache_on` 与 `prefix_cache_off` 各运行一次 profiled `continuous16_mixed` 负载
- 只读枚举和解析 msprof 产物，复制 selected profiler 产物到项目 artifact

禁止：

- 不安装、升级、卸载或修复任何包
- 不创建新 conda 环境
- 不改 driver、CANN、apt、dpkg、NPU runtime、vLLM 或 vLLM-Ascend 源码
- 不静默降低 `max_model_len`、不删减 case、不降低输入 cap、不缩短 output token
- 不运行 full 16K/32K 或 full `P010=43216` tokens
- 不运行多 worker 压测、benchmark、长时间服务或吞吐压测
- 不切换 Docker 推理栈
- 不在服务器上修改、提交或 push 项目代码
- 不回传 `.env`、SMTP 授权码、代理凭据、服务器账号、私钥、Cookie 或任何敏感信息
- 不输出性能 benchmark、吞吐优劣、调度效率、prefix cache 命中率验收、瓶颈归因或优化建议

## 成功口径

强成功：

- `pytest_exit_code=0`
- `msprof_prefix_cache_on_exit_code=0`
- `msprof_prefix_cache_off_exit_code=0`
- 两个子任务均 `success_case_count=16`
- 两个子任务均 `failed_case_count=0`
- 两个子任务均 `client_overlap_candidate_count > 0`
- 两个子任务均 `trace_validation_errors=0`
- 两个子任务均生成 `vllm_api_server_stats_summary.tsv`
- 两个子任务均生成 msprof 输出目录文件枚举与 selected profiler 产物
- `msprof_pairing_inventory.tsv` 已生成，并列出 host/device/sqlite/timebase 候选数量

最低完成：

- 即使某个 msprof 子任务失败，也必须回传 `pytest`、已完成的 vLLM artifact、msprof log、输出目录文件列表、失败码和明确失败阶段。

无论成功或失败，本轮都只判断 profiler 覆盖和 pairing 证据是否可用，不做性能或瓶颈结论。
