# P0/P3 Hardware Ceiling Sweep Handoff

任务 ID：`hardware_ceiling_sweep_2026_0708_p0_007`

上一轮依据：`runtime_vllm_api_msprof_larger_controlled_replay_2026_0708_p1_028`

目标：P1.28 已证明小 prompt 推理链路观测闭环强成功，但 P0-P4 阶段仍不能完整收尾，因为 P0/P3 的硬件天花板基线尚停留在轻量可观测体检和 microbench 可测状态。本轮只做独立于模型推理场景的 hardware ceiling sweep，补齐 H2D/D2H、copy sync/async、pinned 尝试、AI Core matmul、CPU/DRAM、SSD fio 多 block/qdepth 的上限型证据。

本轮不是模型推理任务，不加载模型，不启动 vLLM，不采集 msprof，不做生产 benchmark，不做瓶颈归因。

## 必须回答

1. `git pull --ff-only` 后的 commit 是什么？
2. `tests/observability_profile/test_hardware_ceiling.py` 和相关 microbench 测试是否通过？
3. NPU copy sweep 是否覆盖 H2D/D2H、多个 size、sync/async、pinned 尝试？
4. NPU matmul sweep 是否覆盖至少 `1024/2048/4096` shape 的 `float16`，`8192` 若失败是否有明确 blocked reason？
5. CPU/DRAM sweep 是否产生 NumPy 大块 read/copy 带宽？
6. SSD fio sweep 是否覆盖多 block size、queue depth 和 read/write/randread/randwrite？
7. 是否生成 `hardware_ceiling_result.json`、`summary.txt`、四类 CSV 和 `mail_attachment_candidates.tsv`？
8. 是否遵守 70KB 邮件正文和附件上限？

## 执行边界

允许：

- `git pull --ff-only`。
- 使用当前 conda 环境运行本地 Python 脚本和指定 pytest。
- source `/usr/local/Ascend/cann-9.0.0/set_env.sh`。
- 使用当前已有 `torch` / `torch_npu`、`numpy`、`fio`、`perf`、`numactl`。
- 使用一个可见 NPU 做 copy/matmul microbench，默认 `ASCEND_RT_VISIBLE_DEVICES=6`、`--npu-device npu:0`。
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

## 建议执行命令

在服务器上执行：

```bash
set -u

cd /data/node0_disk1/liguowei/AK-Infer-Lab

RUN_ID=hardware_ceiling_sweep_2026_0708_p0_007
ARTIFACT_BASE="工作记录与进度笔记本/hardware_ceiling_runs"
ARTIFACT_DIR="${ARTIFACT_BASE}/${RUN_ID}"
PYTHON_BIN="${PYTHON_BIN:-/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab/bin/python}"
SCRATCH_DIR="${SCRATCH_DIR:-/data/ak-trace/hardware_ceiling_scratch}"
NPU_DEVICE="${AK_CEILING_NPU_DEVICE:-npu:0}"

mkdir -p "${ARTIFACT_DIR}" "${SCRATCH_DIR}"

git pull --ff-only > "${ARTIFACT_DIR}/git_pull.log" 2>&1
git_pull_exit_code=$?
echo "${git_pull_exit_code}" > "${ARTIFACT_DIR}/git_pull_exit_code.txt"

{
  echo "run_id=${RUN_ID}"
  echo "commit=$(git rev-parse HEAD)"
  echo "timestamp=$(date -Is)"
  echo "PYTHON_BIN=${PYTHON_BIN}"
  echo "SCRATCH_DIR=${SCRATCH_DIR}"
  echo "ARTIFACT_DIR=${ARTIFACT_DIR}"
  echo "ASCEND_RT_VISIBLE_DEVICES=${ASCEND_RT_VISIBLE_DEVICES:-6}"
  echo "NPU_DEVICE=${NPU_DEVICE}"
  echo "git_pull_exit_code=${git_pull_exit_code}"
} > "${ARTIFACT_DIR}/server_run_context.txt"

if [ -f /usr/local/Ascend/cann-9.0.0/set_env.sh ]; then
  # shellcheck disable=SC1091
  source /usr/local/Ascend/cann-9.0.0/set_env.sh
fi

export ASCEND_RT_VISIBLE_DEVICES="${ASCEND_RT_VISIBLE_DEVICES:-6}"

"${PYTHON_BIN}" -m pytest \
  tests/observability_profile/test_hardware_ceiling.py \
  tests/observability_profile/test_microbench.py \
  -q > "${ARTIFACT_DIR}/pytest_hardware_ceiling.log" 2>&1
pytest_exit_code=$?
echo "${pytest_exit_code}" > "${ARTIFACT_DIR}/pytest_exit_code.txt"

"${PYTHON_BIN}" -m tools.observability_profile.hardware_ceiling collect \
  --run-id "${RUN_ID}" \
  --output-base "${ARTIFACT_BASE}" \
  --scratch-dir "${SCRATCH_DIR}" \
  --python-bin "${PYTHON_BIN}" \
  --npu-device "${NPU_DEVICE}" \
  --copy-sizes "4K,16K,64K,1M,16M,64M,256M,1G" \
  --copy-repeats 5 \
  --matmul-dims "512,1024,2048,4096,8192" \
  --matmul-dtypes "float16" \
  --matmul-repeats 5 \
  --dram-sizes "256M,1G,4G" \
  --dram-repeats 3 \
  --fio-block-sizes "4k,128k,1m" \
  --fio-queue-depths "1,4,16,32" \
  --fio-rw-modes "read,write,randread,randwrite" \
  --fio-runtime-s 5 \
  --fio-size "1G" \
  --npu-timeout-s 1800 \
  --overwrite \
  > "${ARTIFACT_DIR}/hardware_ceiling_collect.log" 2>&1
hardware_ceiling_exit_code=$?
echo "${hardware_ceiling_exit_code}" > "${ARTIFACT_DIR}/hardware_ceiling_exit_code.txt"

if [ ! -f "${ARTIFACT_DIR}/mail_summary.txt" ]; then
  {
    echo "# Hardware Ceiling Sweep Summary"
    echo ""
    echo "run_id=${RUN_ID}"
    echo "overall_status=missing_mail_summary"
    echo "git_pull_exit_code=${git_pull_exit_code}"
    echo "pytest_exit_code=${pytest_exit_code}"
    echo "hardware_ceiling_exit_code=${hardware_ceiling_exit_code}"
    echo ""
    echo "hardware_ceiling_collect.log tail:"
    tail -80 "${ARTIFACT_DIR}/hardware_ceiling_collect.log" 2>/dev/null || true
  } > "${ARTIFACT_DIR}/mail_summary.txt"
fi

{
  echo ""
  echo "## execution_status"
  echo "git_pull_exit_code=${git_pull_exit_code}"
  echo "pytest_exit_code=${pytest_exit_code}"
  echo "hardware_ceiling_exit_code=${hardware_ceiling_exit_code}"
} >> "${ARTIFACT_DIR}/mail_summary.txt"

if [ ! -f "${ARTIFACT_DIR}/mail_attachment_candidates.tsv" ]; then
  "${PYTHON_BIN}" - <<'PY' "${ARTIFACT_DIR}"
import sys
from pathlib import Path
artifact_dir = Path(sys.argv[1])
paths = [
    artifact_dir / "mail_summary.txt",
    artifact_dir / "summary.txt",
    artifact_dir / "run_context.json",
    artifact_dir / "server_run_context.txt",
    artifact_dir / "hardware_ceiling_result.json",
    artifact_dir / "npu_copy_sweep.csv",
    artifact_dir / "npu_matmul_sweep.csv",
    artifact_dir / "cpu_dram_sweep.csv",
    artifact_dir / "ssd_fio_sweep.csv",
]
lines = ["path\tsize_bytes\tmail_ok"]
for path in paths:
    if not path.exists():
        continue
    size = path.stat().st_size
    lines.append(f"{path}\t{size}\t{str(size <= 70 * 1024).lower()}")
(artifact_dir / "mail_attachment_candidates.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
fi

echo "DONE"
echo "artifact_dir=${ARTIFACT_DIR}"
cat "${ARTIFACT_DIR}/mail_summary.txt"
```

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
- 生成 `mail_attachment_candidates.tsv`，候选附件均不超过 70KB 或明确标记 `mail_ok=false`

最低完成：

- 即使任何一类 sweep 失败，也必须回传 `server_run_context.txt`、`mail_summary.txt`、`hardware_ceiling_result.json`（如已生成）、`mail_attachment_candidates.tsv`、失败日志尾部和服务器侧路径。
- 不允许把失败项静默删除；必须在对应 CSV 中写 blocked/error，或在正文列出缺失文件与失败原因。

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
