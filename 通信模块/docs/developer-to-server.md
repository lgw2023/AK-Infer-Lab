# 开发机 -> 服务器消息

> 本文件每次只保留当前待执行任务；旧历史信息已清空。

## 当前任务：AK-Infer-Lab 可观测体检第三次运行

- 任务时间：2026-07-04
- Run ID：`obs_2026_0704_atlas800t_a2_003`
- 目标服务器标识：`atlas800t-a2-node-001`
- 任务目的：
  - 复核第二次运行中 `torch-npu import timed out after 5 seconds` 的原因。
  - 明确这次采集是否真的运行在项目 conda 环境：
    `/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab`
  - 重新生成一次带 microbench 的 observability profile，用于判断后续硬件/底层链路测试是否可以进入 P3。

## 背景判断

第二次运行 `obs_2026_0703_atlas800t_a2_002` 的邮件里，manifest 显示 `torch_npu_version: 2.6.0`，但服务器环境初始化邮件里项目 conda 环境显示 `torch_npu 2.9.0.post2`。这说明上次很可能没有在预期 conda 环境下运行，或者脚本中的子进程使用了错误的 Python。

本次代码已经修正为：`torch-npu` 预检使用当前运行 CLI 的 `sys.executable`，不再使用裸 `python`；manifest 会记录 `python_executable`、`python_version`、`conda_prefix`、`conda_default_env`。

## 执行前约束

- 服务器只通过 `git pull` 获取代码和任务文档。
- 不要在服务器上修改、提交或 push 项目代码。
- 不要提交或邮件发送 `.env`、SMTP 授权码、服务器账号、私钥、Cookie 或任何敏感信息。
- 如果当前所有 NPU 都被重要任务占用，请先执行环境预检和只读 inventory，并在邮件中说明；不要抢占正在运行的重要任务。
- 如果命令失败，请回传失败阶段、命令、错误摘要和日志路径，不要在服务器上直接改代码绕过。

## 服务器需要执行的步骤

### 1. 同步仓库并激活项目环境

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab
git pull --ff-only

source /data/miniconda3/etc/profile.d/conda.sh
conda activate /data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab

which python
python -V
python -m tools.observability_profile.cli collect --help
```

### 2. 记录环境预检和 NPU 当前状态

```bash
RUN_ID=obs_2026_0704_atlas800t_a2_003
PRECHECK_DIR=/tmp/ak_observability_${RUN_ID}
mkdir -p "${PRECHECK_DIR}"

{
  date
  hostname
  pwd
  git rev-parse --short HEAD
  which python
  python -V
  timeout 60s python - <<'PY'
import importlib.metadata as metadata
import os
import sys
import time

print("sys.executable:", sys.executable)
print("sys.prefix:", sys.prefix)
print("CONDA_PREFIX:", os.environ.get("CONDA_PREFIX", ""))
print("CONDA_DEFAULT_ENV:", os.environ.get("CONDA_DEFAULT_ENV", ""))

for name in ["torch", "torch-npu", "torch_npu", "vllm", "vllm-ascend", "vllm_ascend"]:
    try:
        print(f"{name}:", metadata.version(name))
    except metadata.PackageNotFoundError:
        print(f"{name}: not installed")

import torch
import torch_npu

print("torch.__version__:", torch.__version__)
print("torch_npu_import_ok: true")
print("torch.npu.is_available:", torch.npu.is_available())
print("torch.npu.device_count:", torch.npu.device_count())

if torch.npu.is_available() and torch.npu.device_count() > 0:
    started = time.perf_counter()
    x = torch.ones((256, 256), device="npu:0")
    y = x @ x
    torch.npu.synchronize()
    elapsed_ms = (time.perf_counter() - started) * 1000
    print("tiny_npu_matmul_ms:", round(elapsed_ms, 3))
    print("tiny_npu_matmul_value:", float(y[0, 0].cpu()))
PY
} 2>&1 | tee "${PRECHECK_DIR}/env_precheck.log"
ENV_PRECHECK_EXIT=${PIPESTATUS[0]}
echo "env_precheck_exit_code=${ENV_PRECHECK_EXIT}" | tee -a "${PRECHECK_DIR}/env_precheck.log"

npu-smi info > "${PRECHECK_DIR}/npu_smi_info.txt" 2>&1 || true
npu-smi info -t board > "${PRECHECK_DIR}/npu_smi_board.txt" 2>&1 || true
```

如果 `env_precheck_exit_code=124`，表示 60 秒超时；请在邮件中标记为 `torch-npu precheck timeout`，并继续执行第 3 步，让正式采集脚本记录 blocked reason。

### 3. 准备 scratch 目录

```bash
SCRATCH_DIR=/data/ak-trace/observability_scratch
mkdir -p "${SCRATCH_DIR}"
df -h "${SCRATCH_DIR}"
```

如果该目录不可写或空间不足，请换成服务器上可写、空间充足、允许临时 I/O 的 scratch 路径，并在邮件正文里写明实际路径。不要把 SSD 写入类 microbench 偷偷写到系统盘。

### 4. 执行正式体检

```bash
RUN_ID=obs_2026_0704_atlas800t_a2_003
SCRATCH_DIR=/data/ak-trace/observability_scratch
PRECHECK_DIR=/tmp/ak_observability_${RUN_ID}

set -o pipefail
python -m tools.observability_profile.cli collect \
  --server-id atlas800t-a2-node-001 \
  --operator ascend-server \
  --run-id "${RUN_ID}" \
  --include-microbench \
  --scratch-dir "${SCRATCH_DIR}" \
  --copy-sizes 4K,16K,64K,1M,16M,256M,1G \
  --fio-qdepth 1,4,16,32 \
  --microbench-duration 10 2>&1 | tee "${PRECHECK_DIR}/collect.log"
COLLECT_EXIT=${PIPESTATUS[0]}
echo "collect_exit_code=${COLLECT_EXIT}" | tee -a "${PRECHECK_DIR}/collect.log"
```

### 5. 检查输出并打包

```bash
RUN_ID=obs_2026_0704_atlas800t_a2_003
RUN_DIR=/data/node0_disk1/liguowei/AK-Infer-Lab/工作记录与进度笔记本/observability_profiles/${RUN_ID}
PRECHECK_DIR=/tmp/ak_observability_${RUN_ID}

find "${RUN_DIR}" -maxdepth 3 -type f | sort | tee "${PRECHECK_DIR}/artifact_list.txt"
python - <<'PY'
import csv
from pathlib import Path
import yaml

run_id = "obs_2026_0704_atlas800t_a2_003"
run_dir = Path("/data/node0_disk1/liguowei/AK-Infer-Lab/工作记录与进度笔记本/observability_profiles") / run_id

manifest = yaml.safe_load((run_dir / "manifest.yaml").read_text())
print("manifest_summary:")
for key in [
    "git_commit",
    "python_executable",
    "python_version",
    "conda_prefix",
    "conda_default_env",
    "cann_version",
    "driver_version",
    "firmware_version",
    "npu_count",
    "hbm_per_npu_gb",
    "torch_npu_version",
    "vllm_ascend_version",
]:
    print(f"  {key}: {manifest.get(key)}")

fields = yaml.safe_load((run_dir / "field_availability.yaml").read_text())["fields"]
counts = {}
for field in fields:
    status = field["availability"]["status"]
    counts[status] = counts.get(status, 0) + 1
print("field_status_counts:", counts)

print("microbench_summary:")
for path in sorted((run_dir / "microbench").glob("*.csv")):
    rows = list(csv.DictReader(path.open()))
    if not rows:
        print(f"  {path.name}: empty")
        continue
    row = rows[0]
    print(
        f"  {row.get('bench_name')}: status={row.get('status')} "
        f"blocked_category={row.get('blocked_category')} "
        f"blocked_detail={row.get('blocked_detail')}"
    )
PY

cd /data/node0_disk1/liguowei/AK-Infer-Lab/工作记录与进度笔记本/observability_profiles
zip -r "${PRECHECK_DIR}/${RUN_ID}.zip" "${RUN_ID}"
```

## 邮件回传要求

- 邮件主题：
  - 成功：`[AK服务器] 任务完成：observability profile obs_2026_0704_atlas800t_a2_003`
  - 失败：`[AK服务器] 运行失败：observability profile obs_2026_0704_atlas800t_a2_003`
- 邮件收件人至少包含：`yilili1023@gmail.com`
- 邮件正文请包含：
  - 主机名、执行时间、`git rev-parse --short HEAD`。
  - 实际 `which python`、`python -V`、`sys.executable`、`CONDA_PREFIX`。
  - `torch`、`torch-npu`、`vllm`、`vllm-ascend` 版本。
  - `torch_npu_import_ok` 是否出现，tiny NPU matmul 是否完成。
  - `npu-smi info` 摘要：卡数、HBM、当前占用进程。
  - 正式 collect 的完整命令、退出码、输出目录绝对路径。
  - `manifest.yaml` 中 listed summary 的全部字段。
  - `field_availability.yaml` 的 measurable / partial / blocked / unknown / not_applicable 数量。
  - `microbench/*.csv` 每项的 `bench_name`、`status`、`blocked_category`、`blocked_detail`。
  - 如果 `torch_npu_version` 仍不是 `2.9.0.post2`，请明确标记为环境不匹配，不要解释为硬件问题。
  - 如果 `npu_count` 或 `hbm_per_npu_gb` 仍是 `unknown`，请附上原始 `npu-smi info`，不要只给摘要。
- 邮件附件请包含：
  - `/tmp/ak_observability_obs_2026_0704_atlas800t_a2_003/env_precheck.log`
  - `/tmp/ak_observability_obs_2026_0704_atlas800t_a2_003/npu_smi_info.txt`
  - `/tmp/ak_observability_obs_2026_0704_atlas800t_a2_003/npu_smi_board.txt`
  - `/tmp/ak_observability_obs_2026_0704_atlas800t_a2_003/collect.log`
  - `/tmp/ak_observability_obs_2026_0704_atlas800t_a2_003/artifact_list.txt`
  - `/tmp/ak_observability_obs_2026_0704_atlas800t_a2_003/obs_2026_0704_atlas800t_a2_003.zip`

## 判读口径

- 如果本次 manifest 显示 `python_executable` 不在项目 conda 环境下，则本次仍只用于环境诊断，不进入硬件性能分析。
- 如果 `torch-npu` 在项目 conda 环境下可以导入并完成 tiny matmul，第二次运行中的 timeout 就应归因于执行环境/子进程解释器问题，不应归因于 NPU 硬件堵塞。
- 如果 `torch-npu` 在项目 conda 环境下仍超时或失败，需要结合 `npu-smi info` 当前占用、CANN 环境变量、driver/firmware 版本继续定位。
- `perf`、`fio`、`numactl` 缺失属于服务器工具安装/权限问题；请记录 blocked reason，但不要把它们混同为 NPU 不可用。
