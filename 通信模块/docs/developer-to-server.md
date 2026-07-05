# 开发机 -> 服务器消息

> 本文件每次只保留当前待执行任务；旧历史信息已清空。

## 当前任务：第六次可观测体检复测，验证系统 microbench 解析修复

- 任务时间：2026-07-05
- 目标服务器标识：`atlas800t-a2-node-001`
- Run ID：`obs_2026_0705_atlas800t_a2_006`
- 任务目的：
  - 拉取开发机已提交的 microbench 解析修复。
  - 重新采集 `fio`、`perf stat`、`numactl --hardware` 结果。
  - 验证 `microbench/ssd_fio.csv`、`microbench/cpu_perf.csv`、`microbench/numa_topology.csv` 不再只记录工具可用性，而是包含结构化指标。

## 背景

- 第五次 run `obs_2026_0705_atlas800t_a2_005` 已确认：
  - `fio`、`perf`、`numactl` 都已安装并可用。
  - `collect_exit_code=0`。
  - `ssd_fio.csv` 只有 `fio_completed=1`，缺 IOPS、bandwidth、latency。
  - `cpu_perf.csv` 只有 `tool_available=1`，缺 perf counter。
  - `numa_topology.csv` 只有 `tool_available=1`，缺 NUMA node、CPU、内存和距离矩阵指标。
- 本次 006 的目标不是安装工具，而是验证开发机修复后的解析结果。
- `bpftrace/eBPF` 缺失仍不在本轮修复范围。
- `ascend910b-driver` 半配置问题仍需单独维护窗口处理，本轮不要自动修复或重装 driver。

## 执行约束

- 服务器只通过 `git pull` 获取代码和本文件。
- 不要在服务器上修改、提交或 push 项目代码。
- 不要执行新的 apt 安装、dpkg 修复、driver 重装或 `ascend910b-driver` 维护动作。
- 不要提交或邮件发送 `.env`、SMTP 授权码、代理凭据、服务器账号、私钥、Cookie 或任何敏感信息。
- fio 只能写入指定 `SCRATCH_DIR`，不要写系统盘或仓库目录。
- 如果 `perf` 的 cycles/instructions 权限不足，按代码降级结果回传；不要现场改内核权限。

## 服务器需要执行的步骤

### 1. 同步仓库

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab
git pull --ff-only
git rev-parse --short HEAD
```

请在邮件正文中写明实际 commit short hash。

### 2. 激活项目环境

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab
source /data/miniconda3/etc/profile.d/conda.sh
conda activate /data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab
which python
python -V
```

### 3. 记录工具与环境预检

```bash
RUN_ID=obs_2026_0705_atlas800t_a2_006
PRECHECK_LOG=/tmp/${RUN_ID}_precheck.log

{
  echo "===== time ====="
  date '+%Y-%m-%d %H:%M:%S %Z'
  echo
  echo "===== hostname ====="
  hostname
  echo
  echo "===== git ====="
  git rev-parse --short HEAD
  echo
  echo "===== python ====="
  which python
  python -V
  python - <<'PY'
import sys
print("sys.executable:", sys.executable)
try:
    import torch
    print("torch:", torch.__version__)
except Exception as exc:
    print("torch import failed:", repr(exc))
try:
    import torch_npu
    print("torch_npu:", getattr(torch_npu, "__version__", "unknown"))
    import torch
    print("torch.npu.is_available:", torch.npu.is_available())
    print("torch.npu.device_count:", torch.npu.device_count())
except Exception as exc:
    print("torch_npu precheck failed:", repr(exc))
PY
  echo
  echo "===== fio ====="
  which fio || true
  fio --version || true
  echo
  echo "===== numactl ====="
  which numactl || true
  numactl --hardware | head -80 || true
  echo
  echo "===== perf ====="
  which perf || true
  perf --version || true
  perf stat -e task-clock -- sleep 0.1 || true
  echo
  echo "===== npu-smi summary ====="
  npu-smi info || true
} > "${PRECHECK_LOG}" 2>&1

cat "${PRECHECK_LOG}"
```

### 4. 执行第六次 collect

优先使用 NPU 6；如果执行前看到 NPU 6 已被占用，而 NPU 7 空闲，可把 `AK_OBS_NPU_DEVICE` 改成 `npu:7`，并在邮件正文说明。

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab
RUN_ID=obs_2026_0705_atlas800t_a2_006
SCRATCH_DIR=/data/ak-trace/observability_scratch
COLLECT_LOG=/tmp/${RUN_ID}_collect.log
SUMMARY_LOG=/tmp/${RUN_ID}_microbench_summary.txt

mkdir -p "${SCRATCH_DIR}"
export AK_OBS_NPU_DEVICE=npu:6

python -m tools.observability_profile.cli collect \
  --server-id atlas800t-a2-node-001 \
  --operator ascend-server \
  --run-id "${RUN_ID}" \
  --include-microbench \
  --scratch-dir "${SCRATCH_DIR}" \
  --copy-sizes 4K,16K,64K,1M,16M,256M \
  --fio-qdepth 1,4,16 \
  --microbench-duration 3 > "${COLLECT_LOG}" 2>&1

COLLECT_EXIT_CODE=$?
cat "${COLLECT_LOG}"
echo "collect_exit_code=${COLLECT_EXIT_CODE}" | tee -a "${COLLECT_LOG}"
```

### 5. 摘要检查三个修复目标

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab
RUN_ID=obs_2026_0705_atlas800t_a2_006
RUN_DIR="工作记录与进度笔记本/observability_profiles/${RUN_ID}"
SUMMARY_LOG=/tmp/${RUN_ID}_microbench_summary.txt

python - <<'PY' > "${SUMMARY_LOG}" 2>&1
import csv
from pathlib import Path

run_id = "obs_2026_0705_atlas800t_a2_006"
run_dir = Path("工作记录与进度笔记本/observability_profiles") / run_id
for name in ["ssd_fio", "cpu_perf", "numa_topology"]:
    path = run_dir / "microbench" / f"{name}.csv"
    print(f"===== {name} =====")
    print(f"path={path}")
    if not path.exists():
        print("missing=true")
        continue
    rows = list(csv.DictReader(path.open(encoding="utf-8", newline="")))
    print(f"rows={len(rows)}")
    if rows:
        print(f"status={rows[0].get('status')}")
        print(f"blocked_category={rows[0].get('blocked_category')}")
        print(f"blocked_detail={rows[0].get('blocked_detail')}")
    metric_names = [row.get("metric_name") for row in rows if row.get("metric_name")]
    print("metric_names=" + ",".join(metric_names))
    for row in rows[:12]:
        print(f"{row.get('metric_name')}={row.get('metric_value')} {row.get('unit')}")
    print()
PY

cat "${SUMMARY_LOG}"
cat "${SUMMARY_LOG}" >> "/tmp/${RUN_ID}_collect.log"
```

预期摘要：

- `ssd_fio` 至少应出现 `fio_read_iops`、`fio_write_iops`、`fio_total_iops`、bandwidth 或 latency 指标。
- `cpu_perf` 至少应出现 `perf_task_clock_ms`；如果权限允许，还应出现 `perf_cycles`、`perf_instructions`、`perf_ipc`。
- `numa_topology` 至少应出现 `numa_node_count`、每节点 CPU/内存指标和 `numa_distance_*` 指标。

### 6. 打包并回传结果

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab
RUN_ID=obs_2026_0705_atlas800t_a2_006
RUN_DIR="工作记录与进度笔记本/observability_profiles/${RUN_ID}"
PRECHECK_LOG=/tmp/${RUN_ID}_precheck.log
COLLECT_LOG=/tmp/${RUN_ID}_collect.log
SUMMARY_LOG=/tmp/${RUN_ID}_microbench_summary.txt
ARTIFACT_LIST=/tmp/${RUN_ID}_artifact_list.txt
ZIP_PATH=/tmp/${RUN_ID}.zip
BODY_PATH=/tmp/${RUN_ID}_mail_body.txt

rm -f "${ZIP_PATH}"
if [ -d "${RUN_DIR}" ]; then
  find "${RUN_DIR}" -maxdepth 3 -type f | sort > "${ARTIFACT_LIST}"
  zip -r "${ZIP_PATH}" "${RUN_DIR}"
else
  echo "RUN_DIR missing: ${RUN_DIR}" > "${ARTIFACT_LIST}"
  echo "RUN_DIR missing: ${RUN_DIR}" > /tmp/${RUN_ID}_run_dir_missing.txt
  zip -j "${ZIP_PATH}" /tmp/${RUN_ID}_run_dir_missing.txt
fi

{
  echo "AK-Infer-Lab 可观测体检第六次复测 -- microbench 解析修复验证"
  echo
  echo "## 基本信息"
  echo "- 主机名：$(hostname)"
  echo "- 执行时间：$(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "- git commit：$(git rev-parse --short HEAD)"
  echo "- Run ID：${RUN_ID}"
  echo "- AK_OBS_NPU_DEVICE：${AK_OBS_NPU_DEVICE:-未设置}"
  echo "- collect_exit_code：$(grep -o 'collect_exit_code=.*' "${COLLECT_LOG}" 2>/dev/null | tail -1 || true)"
  echo
  echo "## 本轮重点"
  echo "- 验证 ssd_fio/cpu_perf/numa_topology 是否输出结构化指标。"
  echo "- 如果 cpu_perf 因 cycles/instructions 权限降级，请保留 partial 和原始原因。"
  echo "- 本轮不处理 ascend910b-driver 半配置问题，也不处理 bpftrace/eBPF。"
  echo
  echo "## 关键摘要"
  if [ -f "${RUN_DIR}/server_observability_profile.md" ]; then
    grep -E 'perf_probe|fio_probe|numa_probe|cpu_perf|ssd_fio|numa_topology|tool_missing|blocked|partial|measurable' "${RUN_DIR}/server_observability_profile.md" || true
  fi
  echo
  echo "## microbench metric 摘要"
  cat "${SUMMARY_LOG}" 2>/dev/null || true
  echo
  echo "## 双收件人确认"
  echo "dual recipient mail verified: gwlee1995@gmail.com,yilili1023@gmail.com"
} > "${BODY_PATH}"

python3 通信模块/send_notify.py \
  -t gwlee1995@gmail.com,yilili1023@gmail.com \
  -s "[AK服务器] 任务完成：observability profile ${RUN_ID}" \
  --body-file "${BODY_PATH}" \
  --attach "${ZIP_PATH}" \
  --attach "${ARTIFACT_LIST}" \
  --attach "${COLLECT_LOG}" \
  --attach "${PRECHECK_LOG}" \
  --attach "${SUMMARY_LOG}"
```

## 回传要求

邮件正文至少说明：

- 实际使用的 `AK_OBS_NPU_DEVICE`。
- `git commit` short hash。
- `collect_exit_code`。
- `perf_probe`、`fio_probe`、`numa_probe` 的 available/permission/exit_code。
- `ssd_fio`、`cpu_perf`、`numa_topology` 的 status 和 metric_names。
- 如果 `cpu_perf` 为 partial，说明是否是 cycles/instructions 权限导致，并保留原始 blocked_detail。
- 如果任何一项 blocked，给出原始 blocked reason，不要现场修复系统包。

附件至少包含：

- `obs_2026_0705_atlas800t_a2_006.zip`
- `obs_2026_0705_atlas800t_a2_006_artifact_list.txt`
- `obs_2026_0705_atlas800t_a2_006_collect.log`
- `obs_2026_0705_atlas800t_a2_006_precheck.log`
- `obs_2026_0705_atlas800t_a2_006_microbench_summary.txt`

## 开发机判读口径

- 如果 `ssd_fio.csv` 出现 IOPS、bandwidth、latency 指标，则 SSD fio 采集进入可用基线状态。
- 如果 `cpu_perf.csv` 至少出现 `perf_task_clock_ms`，则 CPU perf 已不再是“仅工具可用”；若 cycles/instructions 权限受限，记录为 partial caveat。
- 如果 `numa_topology.csv` 出现 node count、per-node CPU/内存和 distance matrix，则 NUMA topology 采集进入可用状态。
- 本轮结果只用于修正系统 microbench 可测性，不直接推出 KV restore、expert load、SSD restore 或 H2D/D2H copy 的瓶颈结论。
