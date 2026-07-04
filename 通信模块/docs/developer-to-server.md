# 开发机 -> 服务器消息

> 本文件每次只保留当前待执行任务；旧历史信息已清空。

## 当前任务：AK-Infer-Lab 可观测体检第四次复测

- 任务时间：2026-07-05
- Run ID：`obs_2026_0705_atlas800t_a2_004`
- 目标服务器标识：`atlas800t-a2-node-001`
- 任务目的：
  - 验证开发机针对第三次反馈做的修复：NPU copy/matmul microbench 不再只写 `torch_npu_initialization=ok` 的 partial，而是在 `torch-npu` 可用时实际产出短测指标。
  - 验证 manifest 是否能从服务器表格型 `npu-smi info` 中解析出 `npu_count`、`hbm_per_npu_gb` 和 `driver_version`。
  - 使用用户已空出的 NPU 6/7 进行复测，其中 NPU 6 为主测卡，NPU 7 为备用卡。
  - 本次只解决体检脚本测试问题，不推进模型推理实验计划，不抢占线上重要任务。

## 背景判断

最新邮件 `obs_2026_0704_atlas800t_a2_003` 显示：

- collect CLI 已成功退出，项目 conda 环境正确。
- `torch_npu 2.9.0.post2` 可导入，tiny NPU matmul 已完成。
- 用户确认 `torch 2.9.0+cpu` + `torch_npu 2.9.0.post2` 是这台 Ascend 服务器的标准组合；只要 `torch.npu.is_available=True`，不要因 `torch.__version__` 带 `+cpu` 后缀而判为异常。
- 第二次 run 的 `torch-npu import timed out after 5 seconds` 已归因于执行环境/子进程解释器问题，不是 NPU 硬件不可用。
- 遗留问题是 NPU microbench 仍为 partial，manifest 仍未解析出 `npu_count` 和 HBM。

开发机本次修复内容：

- NPU microbench 在 `torch-npu` 预检通过后，会通过当前 Python 子进程实际运行 H2D、D2H、copy overlap 和 matmul shape 短测，并写入 CSV 指标。
- 如果 NPU 不可用、超时、被占用导致 runtime error，会写 structured blocked reason，不会让 collect 异常中断。
- manifest 增加表格型 `npu-smi info` fallback 解析，用于读取 `npu-smi 26.0.rc1`、NPU 行和 `Memory-Usage(MB)` 的 HBM 总量。

## 执行前约束

- 服务器只通过 `git pull` 获取代码和任务文档。
- 不要在服务器上修改、提交或 push 项目代码。
- 不要提交或邮件发送 `.env`、SMTP 授权码、服务器账号、私钥、Cookie 或任何敏感信息。
- 用户已确认服务器允许为本项目安装工具和执行必要测试。
- 用户已空出 NPU 6/7；本次默认使用 NPU 6，若 NPU 6 预检异常则改用 NPU 7，并在邮件正文说明。
- 本次不是性能基线采集，只验证脚本能产出指标；选择较小 copy size，避免对正在运行的任务造成明显干扰。

## 服务器需要执行的步骤

### 1. 同步仓库并激活项目环境

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab
git pull --ff-only

source /data/miniconda3/etc/profile.d/conda.sh
conda activate /data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab

which python
python -V
git rev-parse --short HEAD
python -m tools.observability_profile.cli collect --help
```

### 2. 安装/确认基础工具

如果有 root 或免密 sudo 权限，先补齐本轮已知缺失工具：

```bash
APT_PREFIX=
APT_INSTALL_NEEDS_HUMAN=0
if [ "$(id -u)" -ne 0 ]; then
  if command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
    APT_PREFIX=sudo
  else
    APT_INSTALL_NEEDS_HUMAN=1
    echo "apt install paused: current user is not root and passwordless sudo is unavailable"
    echo "manual action required: ask the server operator to run the apt-get install commands interactively"
  fi
fi

if [ "$(id -u)" -eq 0 ] || [ -n "${APT_PREFIX}" ]; then
  ${APT_PREFIX} apt-get update
  ${APT_PREFIX} apt-get install -y fio numactl linux-tools-common linux-tools-generic "linux-tools-$(uname -r)" || true
fi

which fio || true
which numactl || true
which perf || true
fio --version || true
numactl --version || true
perf --version || true
```

如果需要交互式 sudo 或人工授权，不要停在密码提示里，也不要在邮件里发送密码；请把 `manual action required` 写入邮件正文，让人工登录服务器执行安装。工具安装失败不阻塞本次 NPU 复测。

如果 `linux-tools-$(uname -r)` 不存在，不要中断本次 NPU 复测；在邮件里说明 `perf` 仍缺失即可。`fio` 和 `numactl` 能装上时，SSD/NUMA blocked 应同步解除。

### 3. 记录环境和 NPU 占用

```bash
RUN_ID=obs_2026_0705_atlas800t_a2_004
PRECHECK_DIR=/tmp/ak_observability_${RUN_ID}
mkdir -p "${PRECHECK_DIR}"

{
  date
  hostname
  pwd
  git rev-parse --short HEAD
  which python
  python -V
  python - <<'PY'
import importlib.metadata as metadata
import os
import sys

print("sys.executable:", sys.executable)
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
PY
} > "${PRECHECK_DIR}/env_precheck.log" 2>&1
ENV_PRECHECK_EXIT=$?
cat "${PRECHECK_DIR}/env_precheck.log"
echo "env_precheck_exit_code=${ENV_PRECHECK_EXIT}" | tee -a "${PRECHECK_DIR}/env_precheck.log"

npu-smi info > "${PRECHECK_DIR}/npu_smi_info.txt" 2>&1 || true
{
  for NPU_ID in 0 1 2 3 4 5 6 7; do
    echo "===== npu-smi info -t board -i ${NPU_ID} ====="
    npu-smi info -t board -i "${NPU_ID}" || true
  done
} > "${PRECHECK_DIR}/npu_smi_board.txt" 2>&1
```

本次默认使用用户已空出的 NPU 6：

```bash
export AK_OBS_NPU_DEVICE=npu:6
```

如果 `npu_smi_info.txt` 显示 NPU 6 仍有异常占用或健康状态异常，请改用 NPU 7：

```bash
export AK_OBS_NPU_DEVICE=npu:7
```

不要设置 `ASCEND_RT_VISIBLE_DEVICES`，避免设备编号被重映射；本项目 microbench 会直接使用 `AK_OBS_NPU_DEVICE` 指定的全局 NPU 编号。

### 4. 准备 scratch 目录

```bash
SCRATCH_DIR=/data/ak-trace/observability_scratch
mkdir -p "${SCRATCH_DIR}"
df -h "${SCRATCH_DIR}"
```

### 5. 执行正式复测

```bash
RUN_ID=obs_2026_0705_atlas800t_a2_004
SCRATCH_DIR=/data/ak-trace/observability_scratch
PRECHECK_DIR=/tmp/ak_observability_${RUN_ID}

python -m tools.observability_profile.cli collect \
  --server-id atlas800t-a2-node-001 \
  --operator ascend-server \
  --run-id "${RUN_ID}" \
  --include-microbench \
  --scratch-dir "${SCRATCH_DIR}" \
  --copy-sizes 4K,16K,64K,1M,16M,256M \
  --fio-qdepth 1,4,16 \
  --microbench-duration 3 > "${PRECHECK_DIR}/collect.log" 2>&1
COLLECT_EXIT=$?
cat "${PRECHECK_DIR}/collect.log"
echo "collect_exit_code=${COLLECT_EXIT}" | tee -a "${PRECHECK_DIR}/collect.log"
```

### 6. 检查输出并打包

```bash
RUN_ID=obs_2026_0705_atlas800t_a2_004
RUN_DIR=/data/node0_disk1/liguowei/AK-Infer-Lab/工作记录与进度笔记本/observability_profiles/${RUN_ID}
PRECHECK_DIR=/tmp/ak_observability_${RUN_ID}

find "${RUN_DIR}" -maxdepth 3 -type f | sort | tee "${PRECHECK_DIR}/artifact_list.txt"
python - <<'PY'
import csv
from pathlib import Path
import yaml

run_id = "obs_2026_0705_atlas800t_a2_004"
run_dir = Path("/data/node0_disk1/liguowei/AK-Infer-Lab/工作记录与进度笔记本/observability_profiles") / run_id

manifest = yaml.safe_load((run_dir / "manifest.yaml").read_text())
print("manifest_summary:")
for key in [
    "git_commit",
    "python_executable",
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
    first = rows[0]
    metric_names = [row.get("metric_name") for row in rows if row.get("metric_name")]
    print(
        f"  {first.get('bench_name')}: status={first.get('status')} "
        f"blocked_category={first.get('blocked_category')} "
        f"blocked_detail={first.get('blocked_detail')} "
        f"metrics={metric_names[:6]}"
    )
PY

cd /data/node0_disk1/liguowei/AK-Infer-Lab/工作记录与进度笔记本/observability_profiles
zip -r "${PRECHECK_DIR}/${RUN_ID}.zip" "${RUN_ID}"
```

## 邮件回传要求

- 邮件主题：
  - 成功：`[AK服务器] 任务完成：observability profile obs_2026_0705_atlas800t_a2_004`
  - 如果未跑正式 microbench：`[AK服务器] 暂缓：observability profile obs_2026_0705_atlas800t_a2_004`
  - 失败：`[AK服务器] 运行失败：observability profile obs_2026_0705_atlas800t_a2_004`
- 邮件收件人至少包含：`yilili1023@gmail.com`
- 邮件正文请包含：
  - 主机名、执行时间、`git rev-parse --short HEAD`。
  - 实际 `which python`、`python -V`、`sys.executable`、`CONDA_PREFIX`。
  - `torch`、`torch-npu`、`vllm`、`vllm-ascend` 版本。
  - `AK_OBS_NPU_DEVICE` 的实际取值；默认应为 `npu:6`，如果改用 `npu:7` 请说明原因。
  - `npu-smi info` 摘要：卡数、HBM、当前占用进程。
  - `fio`、`numactl`、`perf` 是否安装成功；如果需要交互式 sudo，请明确写 `manual action required` 和需要人工执行的命令。
  - 正式 collect 的完整命令、退出码、输出目录绝对路径。
  - `manifest.yaml` 中 listed summary 的全部字段。
  - `field_availability.yaml` 的 measurable / partial / blocked / unknown / not_applicable 数量。
  - `microbench/*.csv` 每项的 `bench_name`、`status`、`blocked_category`、`blocked_detail`、前几个 `metric_name`。
  - 如果 NPU 项仍 blocked/partial，请贴出对应 CSV 的 `blocked_detail`。
  - 如果 `npu_count` 或 `hbm_per_npu_gb` 仍是 `unknown`，请附上原始 `npu_smi_info.txt`，不要只给摘要。
- 邮件附件请包含：
  - `/tmp/ak_observability_obs_2026_0705_atlas800t_a2_004/env_precheck.log`
  - `/tmp/ak_observability_obs_2026_0705_atlas800t_a2_004/npu_smi_info.txt`
  - `/tmp/ak_observability_obs_2026_0705_atlas800t_a2_004/npu_smi_board.txt`
  - `/tmp/ak_observability_obs_2026_0705_atlas800t_a2_004/collect.log`
  - `/tmp/ak_observability_obs_2026_0705_atlas800t_a2_004/artifact_list.txt`
  - `/tmp/ak_observability_obs_2026_0705_atlas800t_a2_004/obs_2026_0705_atlas800t_a2_004.zip`

## 判读口径

- `torch-npu` 可导入但 NPU CSV 仍没有指标，优先看对应 `blocked_detail`，不要再按第三次邮件的“脚本只做初始化检查”解释。
- `torch.__version__` 显示 `2.9.0+cpu` 是本服务器标准组合的一部分；只要 `torch_npu` 和 `torch.npu` 可用，不作为异常。
- `npu-smi info -t board -i <id>` 作为固定附件采集，便于后续补 board/firmware 细节。
- `perf`、`fio`、`numactl` 已允许安装；如果仍缺失，按实际安装错误记录，不要阻塞 NPU microbench 复测。
- 本次结果只用于验证体检脚本修复，不作为最终硬件性能基线。
