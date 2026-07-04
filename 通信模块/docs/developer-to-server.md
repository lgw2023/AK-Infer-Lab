# 开发机 -> 服务器消息

> 本文件每次只保留当前待执行任务；旧历史信息已清空。

## 当前任务：工具安装后第五次可观测体检复测

- 任务时间：2026-07-05
- 目标服务器标识：`atlas800t-a2-node-001`
- Run ID：`obs_2026_0705_atlas800t_a2_005`
- 任务目的：
  - 基于最新邮件确认的状态，重新采集安装后的 `fio`、`numactl`、`perf` 证据。
  - 覆盖 `obs_2026_0705_atlas800t_a2_004` 中已经过期的 `fio/numactl/perf tool_missing` 结论。
  - 保留第四次 run 已验证的 NPU copy、D2H/H2D、overlap、matmul microbench 采集路径。

## 背景

- 最新双收件人补发邮件：`[AK服务器] 补发：fio/numactl/perf 安装成功`。
- 邮件时间：2026-07-05 03:06 CST。
- 邮件结论：
  - `fio` 已安装并可用。
  - `numactl` 已安装并可用。
  - `perf` 已安装并可用。
  - `obs_2026_0705_atlas800t_a2_004` 附件里的 `fio/numactl/perf tool_missing` 是安装前状态，已经过期。
- 遗留问题：
  - `apt-get install` 曾因系统原有半配置包 `ascend910b-driver` 的 post-install 脚本失败而最终退出码为 `100`。
  - 该问题不影响 `fio`、`numactl`、`perf` 实际可用性。
  - 本轮不要自动修复、重装或重新配置 `ascend910b-driver`。

## 执行约束

- 服务器只通过 `git pull` 获取本文件。
- 不要在服务器上修改、提交或 push 项目代码。
- 不要执行新的 apt 安装、dpkg 修复、driver 重装或 `ascend910b-driver` 维护动作。
- 不要提交或邮件发送 `.env`、SMTP 授权码、代理凭据、服务器账号、私钥、Cookie 或任何敏感信息。
- 本轮只做工具安装后的观测复测；如工具状态又变为不可用，只记录事实并回传，不要现场修系统包。

## 服务器需要执行的步骤

### 1. 同步仓库

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab
git pull --ff-only
git rev-parse --short HEAD
```

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
RUN_ID=obs_2026_0705_atlas800t_a2_005
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
  numactl --hardware | head -40 || true
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

### 4. 执行第五次 collect

优先使用 NPU 6；如果执行前看到 NPU 6 已被占用，而 NPU 7 空闲，可把 `AK_OBS_NPU_DEVICE` 改成 `npu:7`，并在邮件正文说明。

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab
RUN_ID=obs_2026_0705_atlas800t_a2_005
SCRATCH_DIR=/data/ak-trace/observability_scratch
COLLECT_LOG=/tmp/${RUN_ID}_collect.log

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

### 5. 打包并回传结果

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab
RUN_ID=obs_2026_0705_atlas800t_a2_005
RUN_DIR="工作记录与进度笔记本/observability_profiles/${RUN_ID}"
PRECHECK_LOG=/tmp/${RUN_ID}_precheck.log
COLLECT_LOG=/tmp/${RUN_ID}_collect.log
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
  echo "AK-Infer-Lab 可观测体检第五次复测 -- 工具安装后回传"
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
  echo "- 请重点确认 perf_probe、fio_probe、numa_probe 是否从 tool_missing 变成 available。"
  echo "- 请重点确认 microbench/cpu_perf.csv、microbench/ssd_fio.csv、microbench/numa_topology.csv 的 status。"
  echo "- 本轮不处理 ascend910b-driver 半配置问题。"
  echo
  echo "## 关键摘要"
  if [ -f "${RUN_DIR}/server_observability_profile.md" ]; then
    grep -E 'perf_probe|fio_probe|numa_probe|cpu_perf|ssd_fio|numa_topology|tool_missing|blocked|measurable' "${RUN_DIR}/server_observability_profile.md" || true
  fi
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
  --attach "${PRECHECK_LOG}"
```

## 回传要求

邮件正文至少说明：

- 实际使用的 `AK_OBS_NPU_DEVICE`。
- `collect_exit_code`。
- `perf_probe`、`fio_probe`、`numa_probe` 的 available/permission/exit_code。
- `cpu_perf`、`ssd_fio`、`numa_topology` 三个 microbench 的 status。
- 如果任何一项仍为 blocked，给出原始 blocked reason，不要现场修复系统包。

附件至少包含：

- `obs_2026_0705_atlas800t_a2_005.zip`
- `obs_2026_0705_atlas800t_a2_005_artifact_list.txt`
- `obs_2026_0705_atlas800t_a2_005_collect.log`
- `obs_2026_0705_atlas800t_a2_005_precheck.log`

## 开发机判读口径

- 如果 `perf/fio/numactl` 相关字段本轮变为 measurable，开发机将把 P0.5 的系统工具缺口从“缺安装”改为“已具备基础工具，继续进入 P1 统一事件模型和 workload manifest”。
- 如果仍为 blocked，开发机只根据本轮原始日志定位是权限、PATH、内核 perf 包还是脚本解析问题。
- `bpftrace/eBPF` 不在本轮修复目标内，可以继续保持 blocked。
