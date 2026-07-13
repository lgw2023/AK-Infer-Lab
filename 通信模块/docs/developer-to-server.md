# Developer to Server

## 当前唯一服务器动作：同步 P6.1L-R1 green 收口并停止

~~~text
task_id: none
execution_mode: read_only_sync_and_wait_no_npu
source_result_task_id: p6_1l_deepseek_v4_flash_w8a8_mtp_decode_length_ladder_rerun1_2026_0713
source_execution_git_head: bef2d8be182973c8c7c6206b14fad91d906b8efc
accepted_grade: green_mtp_decode_length_ladder_revalidated
claim_boundary: mtp_4096_decode_length_stability_revalidation_only
next_task_authorized: false
~~~

P6.1L-R1 已由外部开发机验收完成。historical lineage audit v2、live metrics
preflight 和最终 hard-gate grading 均通过；一个 fresh lifecycle 内六个 slot 全部
首次成功，累计 generated=4608、draft/accepted=2304/2304，0 retry，cleanup=clean。
`result_summary.md` 把 22 项全 true hard checks 写成 `21/21`，这是非阻塞摘要计数
笔误，不要求服务器修改结果包或重跑实验。

本轮只要求同步远程 `main`、阅读已提交的 green 收口并确认停止状态。不得重新执行六个
slot，也不得进入 official context ladder、128K、完整 P6.1、profiler、P8.1 或性能
比较。

## 1. 同步并核对 main

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab

test -z "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=no)"
git -C "${REPO_ROOT}" fetch origin main
git -C "${REPO_ROOT}" merge --ff-only origin/main
test "$(git -C "${REPO_ROOT}" rev-parse HEAD)" = "$(git -C "${REPO_ROOT}" rev-parse origin/main)"
test "$(git -C "${REPO_ROOT}" branch --show-current)" = main
test -z "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=no)"

grep -F "server_result: green_mtp_decode_length_ladder_revalidated" \
  "${REPO_ROOT}/benchmarks/deepseek_v4_flash/workloads/p6_1l_mtp_decode_length_ladder_rerun1.yaml"
grep -F "next_task_authorized: false" \
  "${REPO_ROOT}/benchmarks/deepseek_v4_flash/workloads/p6_1l_mtp_decode_length_ladder_rerun1.yaml"
~~~

同步后只需阅读：

- `benchmarks/deepseek_v4_flash/workloads/p6_1l_mtp_decode_length_ladder_rerun1.yaml`
- `工作记录与进度笔记本/01_工作记录.md`
- `工作记录与进度笔记本/02_阶段计划.md`
- `工作记录与进度笔记本/05_下一步行动指导.md`
- `工作记录与进度笔记本/12_P5_P9_后续阶段重排计划.md`

## 2. 保留服务器原始证据

保留 raw server log、raw metrics 和计数文件。以下目录不改写、不删除、不重新分级：

~~~text
/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/p6_1l_deepseek_v4_flash_w8a8_mtp_decode_length_ladder_rerun1_2026_0713
~~~

不得运行 `通信模块/server_local_git_sync.sh`，不得修改服务器专属 worktree、主镜像
tracked 文件、base conda environment、site-packages、checkpoint 或既有 task-local
overlay。

## 3. 停止边界

- 不得启动 vLLM。
- 不得发送模型请求。
- 不得创建或修改 overlay。
- 不得重新执行六个 slot。
- 不得生成或传输新的结果包；本轮没有新的 email、upload-api 或 server-local 传输范围。
- 不得把诊断 wall time 写成 benchmark、优化收益或 no-MTP 性能比较。
- 同步并核对完成后停止，等待用户授权下一任务。
