# Developer to Server

## 当前任务：无新服务器执行任务

- 状态 ID：`no_active_server_task_after_p0_p4_closeout_2026_0708`
- 最近完成任务 1：P1.28 `runtime_vllm_api_msprof_larger_controlled_replay_2026_0708_p1_028`
- 最近完成任务 2：P0/P3 `hardware_ceiling_sweep_2026_0708_p0_007`

## 当前结论

P0-P4 当前阶段已经收尾。

三类阶段目标均已满足：

1. 服务器环境与硬件天花板基线：P0.5/006 加 P0/P3 `hardware_ceiling_sweep_2026_0708_p0_007`。
2. 小模型推理链路跑通：`transformers + torch_npu` 与 vLLM / vLLM-Ascend 小模型路径。
3. 小 prompt 推理链路观测：P1.23-P1.28 的 msprof、request-device 聚合和 readout 闭环。

## 最近完成结果摘要

### P1.28

- `git_pull_exit_code=0`
- `pytest_exit_code=0`
- `msprof_prefix_cache_on_exit_code=0`
- `msprof_prefix_cache_off_exit_code=0`
- `request_device_aggregate_fast_exit_code=0`
- `controlled_readout_exit_code=0`
- on/off 两轮均 32/32 成功，固定生成 64 tokens。
- readout `overall_status=success`、`missing_files=[]`。
- 边界：raw counter readout，不是 benchmark、吞吐、prefix cache 命中率验收或瓶颈归因。

### P0/P3 hardware ceiling sweep

- run_id：`hardware_ceiling_sweep_2026_0708_p0_007`
- commit：`7ce7493743a075a749a1c758079935ad159a448a`
- `git_pull_exit_code=0`
- `pytest_exit_code=0`
- `hardware_ceiling_exit_code=0`
- `overall_status=success`
- `npu_status=success`
- `dram_status=success`
- `fio_status=success`
- 行数：copy `64`、matmul `5`、DRAM `3`、fio `48`

peak readout：

- H2D best：`24.313915 GB/s`
- D2H best：`26.480714 GB/s`
- matmul best：`290.448949 TFLOPS`
- DRAM read best：`5.332057 GB/s`
- DRAM copy best：`2.963189 GB/s`
- fio read best：`394.721055 MiB/s`
- fio write best：`377.724455 MiB/s`

边界：这是独立硬件 microbench ceiling，不是模型推理 benchmark、生产吞吐或瓶颈归因。

## 请不要执行

- 不要重复执行 P1.28。
- 不要重复执行 P0/P3 hardware ceiling sweep。
- 不要启动 P5。
- 不要启动 DeepSeek-V4-Flash。
- 不要运行新的 benchmark、msprof、vLLM server 或模型加载任务。
- 不要安装、升级、卸载或修复任何包。

## 等待下一步

请等待开发侧重新整理全局计划或 DeepSeek-V4-Flash 专项实验卡片后，再根据新的 `developer-to-server.md` 执行下一轮任务。

在收到新任务前，服务器侧无需执行命令，也无需回传邮件。
