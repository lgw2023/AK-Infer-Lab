# 开发机 → Ascend 服务器：继续 P6.3C-R3D attempt02

更新日期：2026-08-07

科学任务 ID：`p6_3c_r3d_persistent_prefill_pressure_2026_0807_run01`

本次执行：`attempt_02_runtime_compatibility_completion`

任务性质：`NPU / same scientific contract / task-local runtime compatibility repair`

`result_transfer_authorized: true`

这是当前 P6 工作流的唯一活跃交接。它继续原 R3D，不覆盖 attempt01，也不改写 R3C、R3B、R3A、F4 或原始 P6.3C blocked 审计。不要创建 R3D-F1，也不要为了自动评分改变科学问题。

## 1. 任务目标

R3D 要验证的不是“Chunked Prefill 开关是否存在”，而是一个更具体的调度策略问题：八个请求已经处于 Decode 时，12281-token 长 Prompt 从 waiting 转入 running 后，如果持续限制它的后续 Prefill chunk，是否能把 resident Decode 的尾部干扰显著拉回，同时保留 injected TTFT 与 aggregate TPS 的可接受水平。

直接父任务是 `p6_3c_r3c_adaptive_budget_2026_0805_run01`：它证明 waiting-only one-shot cap 可运行，但没有证明 running unfinished Prefill 的持续限额。R3D 保留该结论并继续新的状态机问题。

共同平台继续冻结为：

```text
model=/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
served_model_name=deepseek-v4-flash-w8a8-mtp
vllm=0.22.1+empty
vllm_ascend=0.22.1rc1
TP=8; EP=true; MTP speculative tokens=1
graph=FULL_DECODE_ONLY; block_size=128; async_scheduling=true
prefix_cache=false
max_model_len=12288
max_num_batched_tokens=12288
max_num_seqs=9
profiler=disabled
request_retry_count=0
```

策略仍为六个：

| config | Chunked Prefill | pressure scope | target |
| --- | --- | --- | ---: |
| `off_b12288` | Off | none | — |
| `admission_on_t4096` | On | waiting only | 4096 |
| `persistent_on_t128` | On | waiting + running unfinished | 128 |
| `persistent_on_t256` | On | waiting + running unfinished | 256 |
| `persistent_on_t512` | On | waiting + running unfinished | 512 |
| `persistent_on_t1024` | On | waiting + running unfinished | 1024 |

不允许在同一 task ID 内改变 target、pressure scope、decode quantum、CLI budget、请求长度、到达 gate、cell、trial 数、指标、配对、SLO threshold 或 Pareto 目标。若确有科学理由改变其中任一项，建立新 variant 并精确报告 delta；不要把它表述成原 R3D attempt02。

## 2. attempt01 的真实结论

attempt01 保留为独立运行时失败记录：

- Git、16 项资产 SHA 和零 NPU audit 通过；
- 请求体生成成功，`body_record_count=22`，所有 body SHA 精确，跨 policy 生命周期字节复用成立；
- 正式入口尝试了 `mechanism_01`，但模型未 ready；
- `0/1286` EngineCore request，`0/243` HTTP request，后续 16 个 lifecycle 未运行；
- 没有 scheduler chunk sequence、TTFT、P99 TBT、stall 或 TPS 数据；
- 因此 attempt01 对 persistent Prefill policy 没有正向或负向科学证据。

首错不是 `request_body_manifest.json` 缺失。该 manifest 已成功生成，只是未包含在最早列出的 4 文件候选范围中。真实首错为旧 vLLM exact-type manager map 没有同步 Ascend MLA subclass：两个 Ascend 精确键均未注册，两个 manager alias 均仍指向旧类，deferred hybrid-KV loader 因而在模型启动前 fail closed。

最终资源状态也不是 2 个 marker。收到的最终 `resource_recovery_summary.json` 为 16/16 marker、`keep_alive_restored_exact=true`、port 7000 空、vLLM residual 0、tracked-clean。2 marker 是恢复过程中的中间观测。

## 3. 本次已发布的实质修复

开发机已把 R3C 服务器现场经验转为三个正式、可复用的 task-local 资产。

### 3.1 Ascend exact-type manager 对齐

`tools/inference_contracts/p6_3c_r3d_hybrid_kv_runtime_patch.py` 在 Ascend public spec 完成替换后：

1. 从原 MLA 与 sliding-window MLA key 取得已冻结的 manager class；
2. 保留旧 key，避免破坏已有解析；
3. 为 `AscendMLAAttentionSpec` 与 `AscendSlidingWindowMLASpec` 增加精确 key；
4. 将 manager module 的两个 alias 同步到 Ascend class；
5. 再运行四项解析自检并把 alignment provenance 写入 diagnostic。

历史 P6.3B-R2 loader 保持原 SHA，不被改写。R3D wrapper 显式选择新 loader，overlay builder 仍将它发布为 frozen Ascend bootstrap 所需的历史模块名，因此不修改 site-packages 或 vLLM-Ascend bootstrap。

### 3.2 ACL graph backend 能力兼容

`vllm_ascend_v0221rc1_acl_graph_update_params_compat.patch` 将无条件调用改为 capability guard：只有 backend class 真正实现 `update_graph_params` 才调用。它不改变 graph mode、capture sizes、模型、请求或 scheduler policy。输入文件 SHA 必须为官方 0.22.1rc1 的 `3b054c...e83`；应用后 SHA 必须为 `f81b08...b0ad`。

### 3.3 停卡前真实导入顺序 smoke

`smoke_p6_3c_runtime_overlay.py` 在 formal server-task 进入 keep-alive stop 之前，以正式 overlay `PYTHONPATH`、CANN/ATB 环境和插件集合执行：

- 导入 Ascend KV interface，触发 deferred loader；
- 验证 hybrid-KV patch 已安装；
- 验证四项 Ascend manager resolution 全部为 true；
- 导入 task-local ACL graph module；
- 验证 ACL graph 输出 SHA 与 capability guard。

这个 smoke 不加载模型、不发送请求、不执行 NPU 工作。失败时 formal task 必须在停卡前退出。成功证据写入 `runtime_overlay_preflight_smoke.json` 并复制到正式结果目录。

## 4. 与其他会话隔离

不要改共享 checkout，不要 checkout/stash/reset/clean 其他会话文件，不要复用或覆盖 attempt01 的 worktree/result。服务器不得 push 远程 `main`。

```bash
SHARED_REPO=/data/node0_disk1/liguowei/AK-Infer-Lab
WORKTREE=/data/node0_disk1/liguowei/server_worktrees/p6_3c_r3d_2026_0807_attempt02
ATTEMPT_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3d_2026_0807_attempt_02
RESULT_DIR=${ATTEMPT_ROOT}/p6_3c_r3d_persistent_prefill_pressure_2026_0807_run01

git -C "${SHARED_REPO}" fetch origin main
git -C "${SHARED_REPO}" status --short --branch
git -C "${SHARED_REPO}" rev-parse origin/main
test ! -e "${WORKTREE}"
git -C "${SHARED_REPO}" worktree add --detach "${WORKTREE}" origin/main
git -C "${WORKTREE}" status --short --branch
git -C "${WORKTREE}" rev-list --left-right --count HEAD...origin/main
test ! -e "${RESULT_DIR}"
```

如果建议路径已被同一任务的未完成会话占用，先检查 PID、日志、owner 和结果状态。不要删除；为本次新建带时间戳后缀的独立 worktree。若 `RESULT_DIR` 已存在，则不得覆盖；先判断是否已经有完整 attempt02。只有确需兼容重试时，使用新的外层 attempt 目录，同时保持内层 task basename 不变并记录 attempt history。

在触卡前做全局互斥检查：NPU 0–7 全部 Health=OK、AICore 空闲、无其他用户/会话的 vLLM/P6/P8/profiler 任务、port 7000 无监听。发现冲突时不终止别人的任务、不抢卡；报告 PID、用户、卡号、端口和任务名，等待资源空闲。

## 5. 发布资产 SHA-256

在任何 NPU 操作前逐项验证。这里的 SHA 是本轮发布事实，不是禁止服务器 AI 处理现场兼容问题；若不一致，先确认是否未同步最新 `origin/main`。同步后仍不一致才报告实际 SHA 与 diff。

```text
benchmarks/deepseek_v4_flash/workloads/p6_3c_r3d_persistent_prefill_pressure.yaml=fd9ff4cfcabcb195946d68c86e6fcdfe21136200125bc1ab5a3d5353624c1cbf
benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_acl_graph_update_params_compat.patch=777f6d87fa741c6c900ee251ddef79071b66017f17b192069468bfe349ed50d8
tools/inference_contracts/p6_3c_r3d_persistent_scheduler.py=de40ae8329025159759f3ba1c2f11e5dee1f261765c160d3d0d23c0715b63107
tools/inference_contracts/p6_3c_r3d_sitecustomize.py=a2100f168fd3a158ec709e45f4b10bacb60b3171051cc359ebe225c81a4ab370
tools/inference_contracts/p6_3c_r3d_hybrid_kv_runtime_patch.py=8a040d89d3e004038137f8da882b4873dad77eabc23552b290b0920f2d64b83c
tools/inference_contracts/smoke_p6_3c_runtime_overlay.py=ad38f9b948c62e13637b2f1f56a9fb66728565e337f436bb155e8eac3f4abdd7
tools/inference_contracts/prepare_p6_3c_runtime_overlay.py=5b8a95fbe2fc8ec81ea4a2243afea5d1093ee90fc6d8571691655b68de9162b0
tools/inference_contracts/run_deepseek_p6_3c_r3d_persistent_prefill.py=03aa2b129869bc9bbc1a8a85ee5cdcff942ae536060059906bdd4fe007d68bdb
tools/inference_contracts/run_deepseek_p6_3c_r3d_mode.sh=2fb95d16693275b1f0a22fa06873357f59b933b18c60c7e373b2d9cec6bf8e5b
tools/inference_contracts/run_deepseek_p6_3c_r3d_experiment.sh=2ebd8c3bd0c52e2c198ae32a122d3cef238c185437c78566bdc64211ee9c88a3
tools/inference_contracts/run_deepseek_p6_3c_r3d_server_task.sh=ccb3d86027ce24cb5f89c2ccebe15d8bcfc5f8d3112b9b6a07e4f5d67581968a
tools/inference_contracts/run_deepseek_p6_3c_r1_mode.sh=0b063b37e1580553769a7e47032668eea555a4e1d54d0a7bf6032907d1aa0e30
tools/inference_contracts/run_deepseek_p6_3c_r2_server_task.sh=86bd3567b4e3315c69b67276e88609fef0794a3adb387168323511dcf8d1966b
tools/inference_contracts/p6_3b_r1_hybrid_kv_runtime_patch.py=6be8eaf168279a6daba1aff891a289b19becb157d794adde0028457bb9821f6c
tools/inference_contracts/p6_3b_r2_hybrid_kv_runtime_patch.py=9d720389f520918642ddecf288d0ac3922f61873251760129ba34ba203d02631
benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_hybrid_kv_eagle_manager_overlay.patch=cac1e77ca08781fbaaf483d903733f9e2875091e6e8f9b33467e4da9c124390e
benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_hybrid_kv_deferred_install_overlay.patch=ad845854461605ae28ae7000f24ada0cb07c5c17f3b0c23ee1485ec537a7a85b
tools/inference_contracts/p6_3c_r3_decode_resident_observer.py=9c2147a7eb1e703da100bcff6cc31481f9c0ba7fe17bdf2375b9383ad71e9a15
docs/SERVER_ADAPTIVE_EXECUTION_POLICY.md=7dff584b742bfba91df332a8671c7430675d7dfacb9c3a15144dae1b3034fe0e
```

核验命令：

```bash
cd "${WORKTREE}"
while IFS='=' read -r path expected; do
  test -f "${path}" || { echo "missing:${path}"; exit 2; }
  actual=$(sha256sum "${path}" | awk '{print $1}')
  test "${actual}" = "${expected}" || {
    echo "sha_mismatch:${path}:expected=${expected}:actual=${actual}"
    exit 2
  }
done <<'EOF'
benchmarks/deepseek_v4_flash/workloads/p6_3c_r3d_persistent_prefill_pressure.yaml=fd9ff4cfcabcb195946d68c86e6fcdfe21136200125bc1ab5a3d5353624c1cbf
benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_acl_graph_update_params_compat.patch=777f6d87fa741c6c900ee251ddef79071b66017f17b192069468bfe349ed50d8
tools/inference_contracts/p6_3c_r3d_persistent_scheduler.py=de40ae8329025159759f3ba1c2f11e5dee1f261765c160d3d0d23c0715b63107
tools/inference_contracts/p6_3c_r3d_sitecustomize.py=a2100f168fd3a158ec709e45f4b10bacb60b3171051cc359ebe225c81a4ab370
tools/inference_contracts/p6_3c_r3d_hybrid_kv_runtime_patch.py=8a040d89d3e004038137f8da882b4873dad77eabc23552b290b0920f2d64b83c
tools/inference_contracts/smoke_p6_3c_runtime_overlay.py=ad38f9b948c62e13637b2f1f56a9fb66728565e337f436bb155e8eac3f4abdd7
tools/inference_contracts/prepare_p6_3c_runtime_overlay.py=5b8a95fbe2fc8ec81ea4a2243afea5d1093ee90fc6d8571691655b68de9162b0
tools/inference_contracts/run_deepseek_p6_3c_r3d_persistent_prefill.py=03aa2b129869bc9bbc1a8a85ee5cdcff942ae536060059906bdd4fe007d68bdb
tools/inference_contracts/run_deepseek_p6_3c_r3d_mode.sh=2fb95d16693275b1f0a22fa06873357f59b933b18c60c7e373b2d9cec6bf8e5b
tools/inference_contracts/run_deepseek_p6_3c_r3d_experiment.sh=2ebd8c3bd0c52e2c198ae32a122d3cef238c185437c78566bdc64211ee9c88a3
tools/inference_contracts/run_deepseek_p6_3c_r3d_server_task.sh=ccb3d86027ce24cb5f89c2ccebe15d8bcfc5f8d3112b9b6a07e4f5d67581968a
tools/inference_contracts/run_deepseek_p6_3c_r1_mode.sh=0b063b37e1580553769a7e47032668eea555a4e1d54d0a7bf6032907d1aa0e30
tools/inference_contracts/run_deepseek_p6_3c_r2_server_task.sh=86bd3567b4e3315c69b67276e88609fef0794a3adb387168323511dcf8d1966b
tools/inference_contracts/p6_3b_r1_hybrid_kv_runtime_patch.py=6be8eaf168279a6daba1aff891a289b19becb157d794adde0028457bb9821f6c
tools/inference_contracts/p6_3b_r2_hybrid_kv_runtime_patch.py=9d720389f520918642ddecf288d0ac3922f61873251760129ba34ba203d02631
benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_hybrid_kv_eagle_manager_overlay.patch=cac1e77ca08781fbaaf483d903733f9e2875091e6e8f9b33467e4da9c124390e
benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_hybrid_kv_deferred_install_overlay.patch=ad845854461605ae28ae7000f24ada0cb07c5c17f3b0c23ee1485ec537a7a85b
tools/inference_contracts/p6_3c_r3_decode_resident_observer.py=9c2147a7eb1e703da100bcff6cc31481f9c0ba7fe17bdf2375b9383ad71e9a15
docs/SERVER_ADAPTIVE_EXECUTION_POLICY.md=7dff584b742bfba91df332a8671c7430675d7dfacb9c3a15144dae1b3034fe0e
EOF
```

服务器 frozen source 还应包括：

```text
vllm/v1/core/single_type_kv_cache_manager.py=d57ad1c8e3d32db4a9d929ee201ab169305ef703b5bda9eb933d0f2f2a2299a1
vllm/v1/core/kv_cache_coordinator.py=a5f0683483508fcfd0b2e3477940825bae5953eec715a4f704becec805484b89
vllm_ascend/patch/platform/patch_kv_cache_coordinator.py=dc65ed2adbb05ea52d9e891f648b62a5391eb41b2a6b262b71d40efe31effe20
vllm_ascend/patch/platform/patch_kv_cache_interface.py=a4969e2c1b2ebde9a3c5a4d02df5175879fb56ea43322869871a3868ec1981b2
vllm_ascend/compilation/acl_graph.py=3b054c10af75cbc34cd0134b9f25203e81b7bf0d3a3df0a4972792bf9017de83
vllm_ascend/spec_decode/llm_base_proposer.py=0e58f5b5e97a4d34d31e66dedd026013ad637e27eccad75acdc39368e5dd05cb
vllm_ascend/distributed/kv_transfer/__init__.py=dc693fd52eb44921e731b69021388ecc186f4e5fa5eca3b28fc1963661e355d1
vllm/v1/core/sched/scheduler.py=41ff2e524c90d9aa72b72cd77492eb62ee2a729a773bd8233e970f39abbb5983
```

## 6. 零 NPU audit

先在 detached worktree 内执行：

```bash
cd "${WORKTREE}"
REPO_ROOT="${WORKTREE}" \
P6_3C_SHARED_REPO_ROOT="${SHARED_REPO}" \
P6_3C_SERVER_TASK_AUDIT_ONLY=1 \
bash tools/inference_contracts/run_deepseek_p6_3c_r3d_server_task.sh \
  /audit/p6_3c_r3d_attempt02
```

必须仍显示：17 lifecycle、1286 EngineCore request、243 HTTP request、0 retry、六个原策略、所有 CLI `max_num_batched_tokens=12288`，并且每个 mode 显示 `acl_graph_compat=1`。audit 不停 keep-alive、不启 vLLM、不触 NPU。

## 7. 自适应执行权限

按 `docs/SERVER_ADAPTIVE_EXECUTION_POLICY.md` 执行。服务器 AI 可以且应当处理真实环境中的路径、editable/site-packages layout、overlay、import order、CANN/ATB 环境、plugin load、loopback proxy、warmup、trace、cleanup 和分析器字段问题。不要因为历史文件里的“禁止改码/禁止重试”停止。

服务器 AI 有权并有责任在不改变科学合同的前提下完成这些现场适配；本任务不自动进入 R3E/P7/P8/P9。

本轮优先使用已发布修复，不再要求服务器先从旧 R3C 结果树手工找 patch。服务器仍可把已保留的 R3C 成功 loader SHA `c863eed6bf187909d0a402bfae57e5b6d22838834feedd9e9c479c2fc5b73f45` 与新实现做语义对照，但不得直接把 server-retained 文件写回共享 checkout。

若发布 smoke 仍因现场差异失败，可以在本任务独立 worktree/overlay 内做最小兼容修复并证据驱动重试，必须保存：

```text
attempt_id
failure_before
changed_paths
before_sha256
after_sha256
unified_diff
why_needed_on_this_server
scientific_impact=none | changed
validation_after
cleanup_and_resource_recovery
```

只要修复不改变科学变量，可继续同一 task ID 的新 attempt。若修复改变 policy、target、请求、cell、样本或指标，必须新建 variant。服务器不得向远程 main push；把 patch 和证据返回开发机审查。

## 8. keep-alive 与正式入口

本任务使用 NPU 0–7。正式 server-task 会先解析真实布局、物化 overlay 并执行导入 smoke；只有这些步骤通过后，基础 runner 才允许停止 keep-alive。

```bash
# 只停止本任务使用的卡。
bash /data/node0_disk1/Public/npu_stop.sh 0 1 2 3 4 5 6 7

# 无论成功、失败、中断或早停，都恢复完全相同的卡集合。
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
```

正式入口：

```bash
cd "${WORKTREE}"
mkdir -p "${ATTEMPT_ROOT}"
REPO_ROOT="${WORKTREE}" \
P6_3C_SHARED_REPO_ROOT="${SHARED_REPO}" \
bash tools/inference_contracts/run_deepseek_p6_3c_r3d_server_task.sh \
  "${RESULT_DIR}"
```

不要手工预生成或复制 `request_body_manifest.json`；driver 的 `prepare` 会在新结果目录内生成并验证它。任务内所有 HTTP 必须直连 `127.0.0.1:7000`，使用 `curl --noproxy '*' --proxy ''`，并保证 `NO_PROXY` 与 `no_proxy` 都含 `127.0.0.1,localhost,::1`。

结束后独立核对：

```text
stopped_card_ids=0,1,2,3,4,5,6,7
restored_card_ids=0,1,2,3,4,5,6,7
keep_alive_marker_count=16
keep_alive_restored_exact=true
port_7000_listener_count=0
vllm_residual_process_count=0
tracked_worktree_clean=true
```

资源恢复看最终 JSON，不要把恢复过程中的中间 marker 数写成最终状态。

## 9. 科学证据要求

全任务仍是 `17 fresh-model lifecycle`、`1286 EngineCore request`、`243 local HTTP request`。机制轨道 5 个 lifecycle，observer 开启、profiler 关闭；其结构化总门命名为 `full_prefill_sequence_gate_complete`。必须直接回答：

1. admission-only T4096 是否在首块后回到 full budget；
2. persistent T128/T256/T512/T1024 是否在 `waiting=0` 且 `running_unfinished_prefill_count>0` 时继续 pressure-capped；
3. 每个 target 的完整 chunk size sequence、chunk count 与 token sum；
4. 每个 pressure step 的 selected budget 是否等于实际 Decode scheduled token 加 target；
5. resident 结束后是否正确恢复 full budget；
6. preemption 是否为 0。

机制证据完整后才进入 12 个 performance lifecycle。顺序仍为：

```text
round_1: off, admission4096, persistent128, persistent256, persistent512, persistent1024
round_2: persistent1024, persistent512, persistent256, persistent128, admission4096, off
```

每个 config-cell 12 个 measured trial。报告 injected TTFT、resident interference-window P99 TBT、maximum adjacent-token stall、aggregate output TPS 和 resident TBT SLO attainment 的 absolute median；给出相对同 mirror round Off 的 paired median effect、seed 633 的 10000 次 descriptive bootstrap CI，以及两个 mirror round 的方向和量级。

项目内部联合边界仍为 TTFT 至少下降 20%、resident P99 TBT 增加不超过 10%、TPS 下降不超过 5%。无配置进入边界仍是有效科学结果；不要改阈值追求绿色。自动 grade 只作诊断，最终解释以结构化机制与性能证据为准。

## 10. 返回报告格式

报告开头使用：

```text
P6_3C_R3D_ATTEMPT02_SERVER_REPORT_BEGIN
task_id=
attempt_id=
head=
origin_main=
ahead_behind=
worktree=
shared_checkout_modified=
asset_sha_gate=
zero_npu_audit_exit=
runtime_overlay_import_smoke_complete=
ascend_manager_resolution=
acl_graph_input_sha256=
acl_graph_output_sha256=
scientific_contract_changed=
adaptive_attempt_count=
adaptive_patch_paths=
formal_experiment_started=
lifecycles=
engine_requests=
http_requests=
mechanism_complete=
performance_complete=
scientific_outcome=
cleanup_status=
stopped_card_ids=
restored_card_ids=
keep_alive_restored_exact=
port_7000_listener_count=
vllm_residual_process_count=
tracked_worktree_clean=
result_dir=
candidate_manifest=
candidate_total_bytes=
transfer_method_selected=false
P6_3C_R3D_ATTEMPT02_SERVER_REPORT_END
```

随后用自然语言回答第 9 节的六个机制问题，并给出每个 policy 的指标表、相对 Off 效应、mirror-round 解释和声明边界。若仍失败，报告第一处真实错误、发生在停卡前还是后、已执行到哪个 lifecycle，以及为什么该结果不能支持或否定 R3D 假设；不要只回红/绿标签。

## 11. 小包与传输边界

raw scheduler trace、token timestamps、request bodies、server log 与完整结果树留在服务器。候选包整体不超过 71680 bytes，且每个文件也不超过 70KB。候选至少包括：

```text
result_summary.md
environment_and_hashes.json
payload_identity_summary.json
lifecycle_summary.tsv
runtime_overlay_preflight_smoke.json
r3d_mechanism_sequence_summary.json
r3d_mechanism_sequence_cells.tsv
r3d_policy_summary.tsv
r3d_policy_paired_effects.tsv
r3d_policy_uncertainty.json
r3d_pareto_frontier.json
r3d_controller_summary.json
scientific_outcome.json
grading_inputs.json
startup_resource_summary.tsv
resource_recovery_summary.json
cleanup_status.txt
first_failure_excerpt.txt
```

任务完成后先报告 result-summary 路径、完整候选清单、逐文件 bytes/SHA-256/sensitivity、总大小、可用 `email` / `upload-api` / `server-local` 和一个推荐方法。`result_transfer_authorized:true` 只表示该有界包可被选择，不表示自动发送；在用户明确选择一种方法前不要传输，也不要先发状态邮件。
