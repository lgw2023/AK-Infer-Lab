# Developer to Server

## 当前任务：恢复 CANN 生成的 ACL Python 路径，并有条件复跑四卡 base

任务 ID：

```text
p5_deepseek_v4_flash_4card_fp8_acl_path_probe_v0221rc1_2026_0711
```

设备授权：

```text
ACL 路径矩阵：ASCEND_RT_VISIBLE_DEVICES=4
有条件的四卡复跑：ASCEND_RT_VISIBLE_DEVICES=4,5,6,7
NPU 0-3 禁止使用、停止或影响
```

本轮只做两件事：

1. 用三个独立的新进程证明：ACL binding 由官方 CANN/ATB `set_env.sh` 生成的 Python 路径提供；source 后再清空该路径会复现上轮失败。
2. 路径门通过后，保留同一份 CANN/ATB 生成的 `PYTHONPATH`，复跑一次 TP4/EP `base_no_mtp` 与一个 `4096+64` 请求。

## 0. 上轮结论与本轮假设

上一轮 `p5_deepseek_v4_flash_4card_fp8_plugin_activation_probe_v0221rc1_2026_0711` 已确认：

- vLLM / vLLM-Ascend import root、目标 commit 与 6 个关键文件 SHA-256 全匹配。
- 完整官方插件白名单
  `ascend,ascend_kv_connector,ascend_model_loader,ascend_service_profiling,ascend_model`
  选择了 `vllm_ascend.models.deepseek_v4:AscendDeepseekV4ForCausalLM`，并使 NPU memory redirect 生效。
- allocator 断言计数为 0，CUDA attention assertion 计数为 0，Ascend model path 计数为 12，NVIDIA path 计数为 0。
- 四卡随后在 worker import 阶段失败：`vllm_ascend.device_allocator.camem` 顶层导入 `acl.rt.memcpy` 时出现 `ModuleNotFoundError: No module named 'acl'`；尚未开始权重加载、server ready 或请求。
- 上轮脚本在 source CANN/ATB 后执行了 `unset PYTHONPATH`；“acl 缺失”的确认命令也使用了 `env -u PYTHONPATH`。

高置信假设：不是 CANN/ACL 未安装，而是 handoff 为排除项目 overlay 时清除了 CANN 刚加入的 ACL Python binding 路径。vLLM-Ascend 的依赖表不把 `acl` 当普通 pip 包；本轮禁止安装它。

## 1. 完整同步远程 main

```bash
set -euo pipefail
cd /data/node0_disk1/liguowei/AK-Infer-Lab

if [ -x server_local/git_pull_remote_wins.sh ]; then
  server_local/git_pull_remote_wins.sh
else
  git fetch origin main
  git merge --ff-only origin/main
fi

git fetch origin main
printf 'local_head=%s\n' "$(git rev-parse HEAD)"
printf 'origin_main=%s\n' "$(git rev-parse origin/main)"
printf 'ahead_behind=%s\n' "$(git rev-list --left-right --count HEAD...origin/main)"
```

必须完整 fast-forward，满足 `HEAD == origin/main`、ahead/behind=`0 0`，再重新打开本文档。禁止 `cherry-pick`、detached checkout 或单文件覆盖。

## 2. 固定环境、对象与禁止项

```text
环境：
/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1

vLLM：
/data/node0_disk1/vllm-0.22.1
v0.22.1@0decac0d96c42b49572498019f0a0e3600f50398

vLLM-Ascend：
v0.22.1rc1@5f6faa0cb8830f667266f3b8121cd1383606f2a1

模型：
/data/node0_disk1/Public/DeepSeek-V4-Flash

退役 inventory（禁止启动）：
/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
```

禁止：

- 禁止 `conda create`、`pip install`、`pip uninstall`、升级、降级或重建；尤其禁止 pip 安装任意名为 `acl` 的包。
- 禁止修改 vLLM、vLLM-Ascend、site-packages、CANN、ATB、driver、firmware、apt 或系统 Python。
- 禁止 `sitecustomize.py`、项目 `PYTHONPATH`、user-site 或硬编码 ACL 路径注入。
- 禁止 `python -I`、`env -i`；它们会破坏本轮要验证的官方环境传播。
- 禁止在 CANN/ATB source 完成后再次清空 `PYTHONPATH`；四卡进程必须继承矩阵验证过的精确值。
- 禁止 NPU 0-3、W8A8、显式 `--quantization`、config 改写、offload、MTP、八卡、128K、msprof、P6 或其他 fallback。

## 3. 初始化、核心预检与资源门

```bash
set +e
set -uo pipefail
cd /data/node0_disk1/liguowei/AK-Infer-Lab

RUN_ID=p5_deepseek_v4_flash_4card_fp8_acl_path_probe_v0221rc1_2026_0711
ARTIFACT_DIR="工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}"
ENV_DIR=/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1
PYTHON_BIN="${ENV_DIR}/bin/python"
VLLM_BIN="${ENV_DIR}/bin/vllm"
VLLM_SRC=/data/node0_disk1/vllm-0.22.1
MODEL_PATH=/data/node0_disk1/Public/DeepSeek-V4-Flash
ACL_DIR="${ARTIFACT_DIR}/acl_path_probe"
OFFICIAL_ASCEND_PLUGINS=ascend,ascend_kv_connector,ascend_model_loader,ascend_service_profiling,ascend_model

mkdir -p "${ACL_DIR}" "${ARTIFACT_DIR}/base_no_mtp"
printf '%s\n' "$(git rev-parse HEAD)" > "${ARTIFACT_DIR}/git_head.txt"
npu-smi info > "${ARTIFACT_DIR}/npu_smi_before.txt" 2>&1 || true

PRECHECK_EXIT=0
[ -x "${PYTHON_BIN}" ] || PRECHECK_EXIT=10
[ -x "${VLLM_BIN}" ] || PRECHECK_EXIT=11
[ -d "${MODEL_PATH}" ] || PRECHECK_EXIT=12
[ "$(git -C "${VLLM_SRC}" rev-parse HEAD 2>/dev/null)" = "0decac0d96c42b49572498019f0a0e3600f50398" ] || PRECHECK_EXIT=13
[ -z "$(git -C "${VLLM_SRC}" status --short 2>/dev/null)" ] || PRECHECK_EXIT=14

unset PYTHONPATH
set +u
source /usr/local/Ascend/ascend-toolkit/set_env.sh
source /usr/local/Ascend/nnal/atb/set_env.sh
set -u
export PATH="${ENV_DIR}/bin:${PATH}"
export PYTHONNOUSERSITE=1
CANN_GENERATED_PYTHONPATH="${PYTHONPATH:-}"
export CANN_GENERATED_PYTHONPATH
printf '%s\n' "${CANN_GENERATED_PYTHONPATH}" > "${ACL_DIR}/cann_generated_pythonpath.txt"

case ":${CANN_GENERATED_PYTHONPATH}:" in
  *:/data/node0_disk1/liguowei/AK-Infer-Lab:*|*sitecustomize*) PRECHECK_EXIT=15 ;;
esac

ASCEND_RT_VISIBLE_DEVICES=4,5,6,7 VLLM_PLUGINS="${OFFICIAL_ASCEND_PLUGINS}" \
  "${PYTHON_BIN}" - "${ARTIFACT_DIR}/preflight.json" <<'PY'
import json
import sys
from importlib.metadata import version
from pathlib import Path

import torch
import torch_npu
import vllm
import vllm_ascend

result = {
    "python": sys.version.split()[0],
    "torch": torch.__version__,
    "torch_npu": version("torch-npu"),
    "vllm": vllm.__version__,
    "vllm_ascend": version("vllm-ascend"),
    "vllm_root": str(Path(vllm.__file__).resolve().parent),
    "vllm_ascend_root": str(Path(vllm_ascend.__file__).resolve().parent),
    "npu_available": bool(torch.npu.is_available()),
    "visible_device_count": int(torch.npu.device_count()),
}
Path(sys.argv[1]).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
ok = (
    result["torch"].startswith("2.10.0")
    and result["torch_npu"] == "2.10.0"
    and result["vllm"].startswith("0.22.1")
    and result["vllm_ascend"] == "0.22.1rc1"
    and result["vllm_root"] == "/data/node0_disk1/vllm-0.22.1/vllm"
    and result["npu_available"] is True
    and result["visible_device_count"] == 4
)
sys.exit(0 if ok else 3)
PY
PY_PREFLIGHT_EXIT=$?
if [ "${PY_PREFLIGHT_EXIT}" -ne 0 ] && [ "${PRECHECK_EXIT}" -eq 0 ]; then PRECHECK_EXIT=16; fi

"${PYTHON_BIN}" -m pytest tests/inference_contracts -q > "${ARTIFACT_DIR}/pytest.log" 2>&1
PYTEST_EXIT=$?
if [ "${PYTEST_EXIT}" -ne 0 ] && [ "${PRECHECK_EXIT}" -eq 0 ]; then PRECHECK_EXIT=17; fi

printf '%s\n' "${PRECHECK_EXIT}" > "${ARTIFACT_DIR}/precheck_exit_code.txt"
if [ "${PRECHECK_EXIT}" -ne 0 ]; then
  printf '%s\n' blocked_preflight > "${ARTIFACT_DIR}/probe_status.txt"
  exit "${PRECHECK_EXIT}"
fi
```

人工核对：

- NPU 4-7 健康、空闲且无其他用户进程；否则 `blocked_resource`。
- `cann_generated_pythonpath.txt` 中用于 ACL 的条目必须来自 `/usr/local/Ascend/...`，不得出现项目目录、上轮 artifact/overlay、`sitecustomize` 或用户目录。
- NPU 0-3 只观察，不干预。

## 4. NPU 4 三模式 fresh-process ACL 路径矩阵

每种 mode 必须使用独立 shell 与独立 Python，避免 import cache。JSON 只记录路径组件、module origin、import root 和结果，不 dump 全环境。

### Mode A：未 source 的干净对照

```bash
env -u PYTHONPATH ASCEND_RT_VISIBLE_DEVICES=4 PYTHONNOUSERSITE=1 \
  "${PYTHON_BIN}" -c 'import acl; from acl.rt import memcpy' \
  > "${ACL_DIR}/mode_a_clean_no_source.log" 2>&1
MODE_A_EXIT=$?
printf '%s\n' "${MODE_A_EXIT}" > "${ACL_DIR}/mode_a_clean_no_source.exit_code.txt"
```

预期失败；它只证明 conda 自身不提供 ACL，不用于证明 CANN 缺装。

### Mode B：先清理，再 source，保留官方生成路径

```bash
cat > "${ACL_DIR}/acl_spawn_probe.py" <<'PY'
import importlib.util
import json
import multiprocessing as mp
import os
import sys
from pathlib import Path

def inspect_imports():
    spec = importlib.util.find_spec("acl")
    if spec is None:
        raise ModuleNotFoundError("No module named 'acl'")
    import acl
    from acl.rt import memcpy
    import vllm
    import vllm_ascend
    import vllm_ascend.device_allocator.camem as camem
    import vllm_ascend.worker.worker as worker
    origin = spec.origin or getattr(acl, "__file__", "") or ""
    resolved = str(Path(origin).resolve()) if origin else ""
    return {
        "pythonpath_components": os.environ.get("PYTHONPATH", "").split(":"),
        "acl_origin": origin,
        "acl_origin_resolved": resolved,
        "acl_origin_under_usr_local_Ascend": resolved.startswith("/usr/local/Ascend/"),
        "acl_rt_memcpy_imported": memcpy is not None,
        "camem_module": camem.__name__,
        "worker_module": worker.__name__,
        "vllm_root": str(Path(vllm.__file__).resolve().parent),
        "vllm_ascend_root": str(Path(vllm_ascend.__file__).resolve().parent),
    }

def child(output_path):
    result = inspect_imports()
    Path(output_path).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

if __name__ == "__main__":
    root = Path(sys.argv[1])
    parent = inspect_imports()
    child_path = root / "mode_b_spawn_child.json"
    ctx = mp.get_context("spawn")
    proc = ctx.Process(target=child, args=(str(child_path),))
    proc.start()
    proc.join(120)
    result = {
        "parent": parent,
        "spawn_exit_code": proc.exitcode,
        "child": json.loads(child_path.read_text(encoding="utf-8")) if child_path.is_file() else None,
    }
    (root / "mode_b_source_preserved.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    sys.exit(0 if proc.exitcode == 0 else 3)
PY

ASCEND_RT_VISIBLE_DEVICES=4 PYTHONNOUSERSITE=1 \
  PYTHONPATH="${CANN_GENERATED_PYTHONPATH}" \
  VLLM_PLUGINS="${OFFICIAL_ASCEND_PLUGINS}" \
  "${PYTHON_BIN}" "${ACL_DIR}/acl_spawn_probe.py" "${ACL_DIR}" \
  > "${ACL_DIR}/mode_b_source_preserved.log" 2>&1
MODE_B_EXIT=$?
printf '%s\n' "${MODE_B_EXIT}" > "${ACL_DIR}/mode_b_source_preserved.exit_code.txt"
```

Mode B 必须满足 parent 和 spawn child：

- `acl` origin realpath 位于 `/usr/local/Ascend/...`。
- `acl.rt.memcpy`、`vllm_ascend.device_allocator.camem`、`vllm_ascend.worker.worker` 均可导入。
- `vllm_root == /data/node0_disk1/vllm-0.22.1/vllm`。
- `vllm_ascend_root` 仍位于指定 0.22.1rc1 conda 环境。
- parent/child 的路径组件完全一致，且没有项目、overlay、`sitecustomize` 或用户目录。

### Mode C：source 后再次清空，精确复现上轮顺序

```bash
env -u PYTHONPATH ASCEND_RT_VISIBLE_DEVICES=4 PYTHONNOUSERSITE=1 \
  VLLM_PLUGINS="${OFFICIAL_ASCEND_PLUGINS}" \
  "${PYTHON_BIN}" -c 'import acl; from acl.rt import memcpy; import vllm_ascend.device_allocator.camem' \
  > "${ACL_DIR}/mode_c_post_source_unset.log" 2>&1
MODE_C_EXIT=$?
printf '%s\n' "${MODE_C_EXIT}" > "${ACL_DIR}/mode_c_post_source_unset.exit_code.txt"
```

最后生成 `acl_path_summary.json`，至少逐项记录：

```text
mode_a_clean_no_source_fails_acl
mode_b_parent_acl_origin_is_CANN
mode_b_child_acl_origin_is_CANN
mode_b_parent_acl_rt_camem_worker_imports
mode_b_child_acl_rt_camem_worker_imports
mode_b_vllm_import_roots_unchanged
mode_b_spawn_inherits_exact_path_components
mode_b_has_no_project_sitecustomize_or_user_overlay
mode_c_post_source_unset_reproduces_missing_acl
hypothesis_supported
```

只有 9 项 checks 和总门全部为 true，才写 `diagnostic_green_acl_path_gate` 并进入四卡。Mode B 也失败时，写 `blocked_environment_acl_binding`，只读记录两个 `set_env.sh` 是否存在、source 前/后路径组件、`find_spec("acl")` 结果；可以只读查找 `/usr/local/Ascend/**/python/site-packages/acl*`，但禁止安装、复制、软链、硬编码路径或继续模型。

## 5. 条件式 NPU 4-7 base_no_mtp

仅在 ACL path gate 通过且 NPU 4-7 仍健康空闲时执行。环境顺序固定：

```bash
unset PYTHONPATH
set +u
source /usr/local/Ascend/ascend-toolkit/set_env.sh
source /usr/local/Ascend/nnal/atb/set_env.sh
set -u

export PATH="${ENV_DIR}/bin:${PATH}"
export PYTHONNOUSERSITE=1
export VLLM_PLUGINS="${OFFICIAL_ASCEND_PLUGINS}"
export VLLM_USE_V1=1
export VLLM_WORKER_MULTIPROC_METHOD=spawn
export OMP_PROC_BIND=false
export OMP_NUM_THREADS=8
export PYTORCH_NPU_ALLOC_CONF=expandable_segments:True
export LD_PRELOAD="/usr/lib/aarch64-linux-gnu/libjemalloc.so.2${LD_PRELOAD:+:${LD_PRELOAD}}"
export HCCL_BUFFSIZE=1024
export TASK_QUEUE_ENABLE=1
export HCCL_OP_EXPANSION_MODE=AIV
export ASCEND_RT_VISIBLE_DEVICES=4,5,6,7
```

此后绝对不得再 unset `PYTHONPATH`。先确认当前值与 `acl_path_probe/cann_generated_pythonpath.txt` 逐字相同，然后使用原命令：

```bash
HOST=127.0.0.1
PORT=7000
SERVED_MODEL_NAME=dsv4-official-fp8-four-card
PROFILE_DIR="${ARTIFACT_DIR}/base_no_mtp"
mkdir -p "${PROFILE_DIR}"
npu-smi info > "${PROFILE_DIR}/npu_smi_before.txt" 2>&1 || true

CMD=(
  "${VLLM_BIN}" serve "${MODEL_PATH}"
  --safetensors-load-strategy prefetch
  --max-model-len 8192
  --max-num-batched-tokens 4096
  --served-model-name "${SERVED_MODEL_NAME}"
  --gpu-memory-utilization 0.92
  --max-num-seqs 1
  --data-parallel-size 1
  --tensor-parallel-size 4
  --enable-expert-parallel
  --host "${HOST}" --port "${PORT}"
  --block-size 128
  --tokenizer-mode deepseek_v4
  --tool-call-parser deepseek_v4
  --enable-auto-tool-choice
  --reasoning-parser deepseek_v4
  --no-enable-prefix-caching
  --enforce-eager
  --additional-config '{"enable_flashcomm1":true,"enable_dsa_cp":true,"enable_cpu_binding":true,"multistream_overlap_shared_expert":false}'
)
```

执行要求：

1. 保存 shell-escaped `server_command.txt`、`vllm_server.log`、PID 与 ready exit code。
2. 启动最长等待 3600 秒；进程死亡记 2，超时记 1，health ready 记 0。
3. 仅 ready 后发送一个固定 `4096 input + 64 output` 的 `/v1/completions` 请求，`min_tokens=max_tokens=64`、`ignore_eos=true`、`temperature=0`。
4. 任一失败立即按首错停止；不运行 MTP 或 fallback。
5. 无论成败都停止本轮进程，确认 NPU 4-7 无残留；禁止 kill NPU 0-3。
6. 输出 `probe_result.json`、`probe_status.txt`、`first_failure_excerpt.txt`、前后 NPU 快照。至少统计 `acl` missing、allocator assert、CUDA attention assert、Ascend/NVIDIA model path 次数。

分级：

- `blocked_preflight` / `blocked_resource`：核心或资源门失败。
- `blocked_acl_origin`：ACL/path 来源不满足官方安装约束。
- `blocked_environment_acl_binding`：正确 source 顺序仍不能导入 ACL。
- `diagnostic_red_acl_path_hypothesis_mismatch`：三模式矩阵不支持假设。
- `diagnostic_yellow_acl_path_fixed`：ACL parent/spawn 门通过，四卡越过该首错后在更后阶段失败。
- `diagnostic_green_base_runtime`：server ready 且一个 `4096+64` 请求成功。

单卡 path gate 通过不能写成 P5 runtime green；四卡成功也不授权 MTP、八卡、128K 或 P6。

## 6. 交付等待门

先在服务器本地生成：

```text
${ARTIFACT_DIR}/result_summary.md
${ARTIFACT_DIR}/delivery_candidates.tsv
```

建议主题：

```text
[P5-FP8-v0221rc1-acl-path] <probe_grade> | <first_failure_or_base_success> | 2026-07-11
```

`result_summary.md` 必须包含 task/Git、三模式 exit、CANN 路径组件的脱敏清单、parent/child ACL origin、9-check gate、vLLM import roots、四卡 ready/request/首错、NPU 4-7 健康和残留。`delivery_candidates.tsv` 必须列出每个候选文件的精确路径、bytes、SHA-256、敏感性、email/upload-api 可行性和推荐方式。

本轮尚未批准新产物传输。生成候选清单后暂停，在当前任务会话询问用户选择 `email` 或 `upload-api`。确认前禁止发送状态邮件、附件、upload-api 预检或上传。raw log、完整 NPU SMI、模型和大 artifact 保持 server-local；不得显示 token、`.env` 值、其他用户 PID/命令或未脱敏内容。

确认后只传已批准的精确范围：

- `email`：`python3 通信模块/send_notify.py --subject "<主题>" --body-file <result_summary.md> --attach <已批准附件> --confirmed-method email`
- `upload-api`：不发邮件；一次执行 `python3 通信模块/upload_file.py --upload <result_summary.md> --upload <已批准附件> --session-name <p5-fp8-v0221rc1-acl-path-YYYYMMDD-run-id> --confirmed-method upload-api`

失败后不得自动重试、改名、扩展范围、补发邮件或切换渠道。
