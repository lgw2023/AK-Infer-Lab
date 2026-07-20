# Developer to Server

## 当前唯一服务器动作：P8.2-K1A-R3-R2-R1 installed-source gate repair + same lifecycle

~~~text
task_id: p8_2_k1a_r3_r2_r1_deepseek_v4_flash_simple_cpu_offload_store_restore_2026_0720
execution_mode: authorized_installed_source_gate_repair_same_accepted_capacity_single_lifecycle_six_request_mechanism
server_sync_review_authorized: true
parent_r3_r2_evidence_review_authorized: true
installed_source_and_import_probe_authorized: true
accepted_r2_provenance_review_authorized: true
npu_execution_authorized: true
keep_alive_stop_and_restore_authorized: true
vllm_server_start_authorized: true
model_requests_authorized: true
formal_model_lifecycle_count_exact: 1
model_request_count_exact: 6
request_retry_count_exact: 0
result_directory_creation_authorized: true
runtime_overlay_authorized: true
observer_authorized: true
observer_mode: observe_only_no_decision_or_copy_mutation
capacity_search_authorized: false
second_capacity_point_authorized: false
second_lifecycle_authorized: false
profiler_authorized: false
hbm_sampler_authorized: false
runtime_or_dependency_upgrade_authorized: false
runtime_or_dependency_mutation_authorized: false
result_transfer_authorized: true
transfer_method_selected: false
next_task_authorized: false
no_k2_k3_k4_p8_3_i1_p8_4_p8_5_or_p9: true
standing_npu_and_vllm_consumption_authorization: true
~~~

## 0. 背景、首错和不可变实验边界

R3-R2 已把 R3-R1 的跨 Bash `%q` 命令身份缺陷修复为 exact argv canonical JSON：服务器
Section 1 的 17-file repo gate、33 tests、portable argv contract 与
`server_command_sha256=8301f4c4c4f203e42f7954e4e4c9b961b55725b132dcbd6fb4b8625bc271bde6`
全部通过；R2 accepted-capacity provenance 也通过。R3-R2 的第一失败发生在零 NPU source gate：handoff
额外假设了一个服务器上不存在的 vLLM-Ascend checkout 路径。keep-alive 未停、vLLM 未启动、请求
`0/6`，因此 parent 正式保留：

~~~text
parent_task_id=p8_2_k1a_r3_r2_deepseek_v4_flash_simple_cpu_offload_store_restore_2026_0719
parent_grade=blocked_p8_2_k1a_r3_r2_source_or_resource_gate
parent_failure_class=unverified_vllm_ascend_checkout_path_contract
parent_vllm_started=false
parent_npu_started=false
parent_model_request_count=0
parent_keep_alive_disrupted=false
~~~

这不是 capacity/runtime/store/restore red，不撤销
`ready_p8_2_k1a_r2_allocator_capacity`；R3 保留
`blocked_p8_2_k1a_r3_source_or_provenance_gate`。R3-R1 已在同一服务器用
`${RUNTIME_PREFIX}/lib/python3.11/site-packages` 的 frozen installed-content hashes 和 runtime
import/registration 关闭过安装态 source gate。本轮只恢复该已验证方式；服务器上其他
vLLM-Ascend checkout 的 HEAD 不参与正式身份，不得把它改写为冻结版本，也不得 checkout、patch、复制或
修改 site-packages。

已关闭 lineage 全部保留：P6.3B-R4-R1=`green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab`，
P8.1-R1=`green_p8_1_r1_official_mtp_observe_only_matrix`，P8.2-K0=
`green_p8_2_k0_order_balanced_prefix_cache_baseline`；legacy K1 继续为
`blocked_p8_2_k1_frozen_stack_import_incompatible`，P6.3C 继续为
`blocked_p6_3c_not_strict_single_variable`。P8.3-I0-R1 保留
`green_p8_3_i0_r1_unclassified_taxonomy` 与 budget incomplete，
本任务不重跑上述任务，也不授权 expert track。

以下实验值逐项不变：vLLM `0.22.1+empty@0decac0d...`、vLLM-Ascend
`0.22.1rc1@5f6faa0c...` 的安装内容、W8A8、TP8+EP、MTP speculative token=`1`、
`FULL_DECODE_ONLY`、Prefix Cache、Chunked Prefill、R2 hybrid-KV repair、observer、
`max_model_len=135168`、`max_num_batched_tokens=4096`、`max_num_seqs=1`、block size=`128`、
六个 frozen request body 和唯一 accepted capacity：

~~~text
server_command_identity_schema=ak_infer_lab_server_argv_v1
server_command_sha256=8301f4c4c4f203e42f7954e4e4c9b961b55725b132dcbd6fb4b8625bc271bde6
P8_2_K1A_EXPECTED_COMMAND_SHA256=8301f4c4c4f203e42f7954e4e4c9b961b55725b132dcbd6fb4b8625bc271bde6
required_restore_tokens=16384
required_cpu_blocks=128
bytes_per_block=3364096
cpu_bytes_to_use_per_rank=430604288
cpu_bytes_to_use=3444834304
request_order=warmup,prime,pressure,restore_follower,repeat_follower,isolated_control
~~~

只允许一个 lifecycle、六请求、零 retry。不得 capacity search、second capacity point、second lifecycle、
第七请求、compatibility patch、profiler、HBM sampler、依赖升级、checkpoint/source/site-packages 修改。
不得进入 K2、P8.3-I1、P8.4、P8.5 或 P9。任一首错保留后立即停止后续执行，只做清理、分级与有界报告。

## 1. 同步、冻结仓库、portable argv 与 parent evidence gate（零 NPU）

从干净 `main` 执行。不得 reset、stash、server commit、push 或运行 server-local Git sync；本节结束前
不得创建正式 `RESULT_DIR`、不得停 keep-alive。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
TASK_ID=p8_2_k1a_r3_r2_r1_deepseek_v4_flash_simple_cpu_offload_store_restore_2026_0720
RESULT_DIR=${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p8_2_k1a_r3_r2_r1_deepseek_v4_flash_simple_cpu_offload_store_restore_2026_0720_run01
RUNNER=${REPO_ROOT}/tools/inference_contracts/run_deepseek_p8_2_k1a_r3_r2_r1_simple_cpu_offload.sh
MODE_RUNNER=${REPO_ROOT}/tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh
ARGV_IDENTITY=${REPO_ROOT}/tools/inference_contracts/canonicalize_server_argv.py
PARENT_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r3_r2_deepseek_v4_flash_simple_cpu_offload_store_restore_2026_0719
cd "${REPO_ROOT}"

git status --short --branch --untracked-files=no
test -z "$(git status --porcelain --untracked-files=no)"
git fetch origin main
git merge --ff-only origin/main
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
test -z "$(git status --porcelain --untracked-files=no)"
test ! -e "${RESULT_DIR}"

python3 - <<'PY'
from pathlib import Path
import hashlib

expected = {
    "benchmarks/deepseek_v4_flash/p8_2_k1a_simple_cpu_offload_feasibility_audit.yaml": "51fe967ff093678fdf7f4f208b09288c4ea020062b954d04c32a5925dfa7ba16",
    "benchmarks/deepseek_v4_flash/p8_2_k1a_r2_geometry_rendezvous_audit.yaml": "7553ec2ee67422eacad6f6e4ca1f37da55b46a71706f74db07bc73dba5db9e82",
    "benchmarks/deepseek_v4_flash/p8_2_k1a_r3_formal_lifecycle_audit.yaml": "dc9588d8d71c2742e5831bf6facdd82348b5e6d3ab4f5dd466c1d771d7ffe9dc",
    "benchmarks/deepseek_v4_flash/p8_2_k1a_r3_r1_provenance_gate_audit.yaml": "99f44bbcd95bff9bc65d044ddc82d5c70aea357e0694df38b3373778253908eb",
    "benchmarks/deepseek_v4_flash/p8_2_k1a_r3_r2_portable_argv_audit.yaml": "b74c46278de38c10db21a8dd817da632c15e9c26ecc9b391b0489b65f3a4d178",
    "benchmarks/deepseek_v4_flash/p8_2_k1a_r3_r2_r1_installed_source_gate_audit.yaml": "7b56dd48465d1ff73e0afccc44689182963077a703b64524474670ebfb37b9b2",
    "benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r3_simple_cpu_offload_store_restore.yaml": "91c697b63824bd279be3fd8676e058bf66b968608d8292ce133f5fc2da617702",
    "tools/inference_contracts/audit_deepseek_p8_2_k1a_simple_cpu_offload.py": "d1af39ef7622bee62b6b10f774ef012f306d0bc5b0318666bc6d41df786836e3",
    "tools/inference_contracts/canonicalize_server_argv.py": "c1bfd1cc7df7b18a5b8abfb5b50e827a2c245d716ab4100f48d831a8fa5eea0d",
    "tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py": "b31d212378c8aaed87c872c67a29b8d2ea039fbd7e97e5f7e6c54b29ef99a680",
    "tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py": "ecdcda7aa7e1420a9b118fb3a1dfcb326717e13dfbb71c976289f314817618c0",
    "tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh": "06e7c6ba2976418797a92110c406e79b938e2314394d39e6ca82519ef8261462",
    "tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.sh": "0ebafa2381fb8398e9823f1ca99d87b207bf9de8c3414c09e7f1614b173fea56",
    "tools/inference_contracts/run_deepseek_p8_2_k1a_r3_simple_cpu_offload.sh": "28065c30588413e839cd0195709b645e416b06aa91db361808b6ac72aff6edf4",
    "tools/inference_contracts/run_deepseek_p8_2_k1a_r3_r2_simple_cpu_offload.sh": "bcf8e22535f0fa075d91b3b2ebcc6a5ca1a1478e3eaf5705813fc20c00a9ff0d",
    "tools/inference_contracts/run_deepseek_p8_2_k1a_r3_r2_r1_simple_cpu_offload.sh": "d4fc964b9cca828689688a32ef538fbd709cfce5c05ff2d607ed24e8978ac887",
    "benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_simple_cpu_offload_observer_overlay.patch": "5db6a0c78d36eb9821474cfef21245b45bd858d07361b7f9afd36ef49e76c2b6",
    "tests/inference_contracts/test_deepseek_p8_2_k1a_r3_formal_lifecycle.py": "20a38a3157b526d7046b793f7fdd61540ca2619d810b95c212f41089cef2efa8",
    "tests/inference_contracts/test_deepseek_p8_2_k1a_r3_r2_portable_argv.py": "19c44fc247266e61c32b1abe90de9fe880ccc3c9a892c1b1ff112ffbe854b14e",
    "tests/inference_contracts/test_deepseek_p8_2_k1a_r3_r2_r1_installed_source_gate.py": "abd90691eb7cb877b258e3ab0eaf85139e08e0746c0946ea262d49428e9e5326",
}
for relative, wanted in expected.items():
    got = hashlib.sha256(Path(relative).read_bytes()).hexdigest()
    assert got == wanted, (relative, got, wanted)
print(f"frozen_repo_hash_gate=pass files={len(expected)}")
PY

python3 -m pytest \
  tests/inference_contracts/test_deepseek_p8_2_k1a_simple_cpu_offload_feasibility.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r2_geometry_rendezvous.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r3_formal_lifecycle.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r3_r1_provenance_gate.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r3_r2_portable_argv.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r3_r2_r1_installed_source_gate.py -q
python3 -m py_compile "${ARGV_IDENTITY}" \
  tools/inference_contracts/audit_deepseek_p8_2_k1a_simple_cpu_offload.py \
  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py
bash -n "${MODE_RUNNER}" "${RUNNER}"

P8_2_K1A_AUDIT_ONLY=1 bash "${RUNNER}" /tmp/p8_2_k1a_r3_r2_r1_audit_only \
  > /tmp/p8_2_k1a_r3_r2_r1_top_audit.txt
grep -Fx "task_id=${TASK_ID}" /tmp/p8_2_k1a_r3_r2_r1_top_audit.txt
grep -Fx 'cpu_bytes_to_use=3444834304' /tmp/p8_2_k1a_r3_r2_r1_top_audit.txt
grep -Fx 'cpu_bytes_to_use_per_rank=430604288' /tmp/p8_2_k1a_r3_r2_r1_top_audit.txt
grep -Fx 'server_command_sha256=8301f4c4c4f203e42f7954e4e4c9b961b55725b132dcbd6fb4b8625bc271bde6' \
  /tmp/p8_2_k1a_r3_r2_r1_top_audit.txt

P8_2_K1A_MODE_AUDIT_ONLY=1 bash "${RUNNER}" /tmp/p8_2_k1a_r3_r2_r1_mode_audit \
  > /tmp/p8_2_k1a_r3_r2_r1_mode_audit.txt
grep -Fx 'server_command_identity_schema=ak_infer_lab_server_argv_v1' \
  /tmp/p8_2_k1a_r3_r2_r1_mode_audit.txt
grep -Fx 'server_command_sha256=8301f4c4c4f203e42f7954e4e4c9b961b55725b132dcbd6fb4b8625bc271bde6' \
  /tmp/p8_2_k1a_r3_r2_r1_mode_audit.txt
test ! -e /tmp/p8_2_k1a_r3_r2_r1_audit_only
test ! -e /tmp/p8_2_k1a_r3_r2_r1_mode_audit

test -d "${PARENT_ROOT}"
python3 - "${PARENT_ROOT}" <<'PY'
from pathlib import Path
import hashlib
import json
import sys

root = Path(sys.argv[1])
expected = {
    "result_summary.md": (7444, "74439fceb5c502dfbe84ec72e30b28cbefec2512fd0421acf16404116604b6de"),
    "first_failure_excerpt.txt": (1241, "301cb52d2c6b439e71f43f50314e5cec4aee5d950a2f6446b170c5f9100139b7"),
    "accepted_r2_capacity_provenance.json": (533, "bf2a5282910d267247c9345cb11a8a152e1c256450bad1515a38f03ced8983a2"),
    "section1_top_audit.txt": (514, "bdc8a073f6557104779d6925ee7ecff7ca0630a96b6437fa032b958a6b8c3e56"),
    "section1_mode_audit.txt": (1810, "70e8ae52b0d9559bbef913b5759288367e292a2da866db1e6d23cd111089b098"),
}
for name, (size, wanted) in expected.items():
    path = root / name
    assert path.is_file(), path
    assert path.stat().st_size == size, (path, path.stat().st_size, size)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == wanted, path

summary = (root / "result_summary.md").read_text()
failure = (root / "first_failure_excerpt.txt").read_text()
provenance = json.loads((root / "accepted_r2_capacity_provenance.json").read_text())
assert "blocked_p8_2_k1a_r3_r2_source_or_resource_gate" in summary
assert "portable_argv_contract_gate=pass" in summary
assert "declared vllm-ascend repo path does not exist" in failure
assert provenance["accepted_r2_capacity_provenance_gate"] == "pass"
assert provenance["accepted_capacity_bytes_per_rank"] == 430604288
assert provenance["accepted_capacity_bytes_total"] == 3444834304
print("parent_r3_r2_evidence_gate=pass")
PY

test ! -e "${RESULT_DIR}"
test -z "$(git status --porcelain --untracked-files=no)"
~~~

本节任一失败给 `blocked_p8_2_k1a_r3_r2_r1_repository_or_parent_gate` 并停止。不得停 keep-alive、
不得创建正式结果目录、不得启动 vLLM/NPU。

## 2. R2 provenance、冻结安装态 source/import 与资源门（零 NPU）

只读复核既有 R2 evidence、安装态 frozen content、runtime import/registration、模型、host memory、
端口和 keep-alive。其他 vLLM-Ascend checkout 不参与本任务，既不读取其 HEAD 作为身份，也不修改它。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
RESULT_DIR=${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p8_2_k1a_r3_r2_r1_deepseek_v4_flash_simple_cpu_offload_store_restore_2026_0720_run01
AUDITOR=${REPO_ROOT}/tools/inference_contracts/audit_deepseek_p8_2_k1a_simple_cpu_offload.py
R2_ROOT=${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p8_dual_track_k1a_r2_rendezvous_and_p8_3_i0_r1_taxonomy_2026_0717_run01
K1A_R2=${R2_ROOT}/p8_2_k1a_r2_geometry_and_allocator
RENDEZVOUS=${K1A_R2}/geometry_probe/runtime/geometry/geometry.rendezvous.complete.json
VLLM_ROOT=/data/node0_disk1/vllm-0.22.1
RUNTIME_PREFIX=${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1
RUNTIME_PYTHON=${RUNTIME_PREFIX}/bin/python
VLLM_ASCEND_ROOT=${RUNTIME_PREFIX}/lib/python3.11/site-packages
MODEL_PATH=/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
TMP_AUDIT=$(mktemp -d /tmp/opencode/p8_2_k1a_r3_r2_r1_preflight_2026_0720_XXXXXX)
TMP_AUDIT_POINTER=/tmp/opencode/p8_2_k1a_r3_r2_r1_preflight_current_2026_0720.path
test ! -e "${TMP_AUDIT_POINTER}"
printf '%s\n' "${TMP_AUDIT}" > "${TMP_AUDIT_POINTER}"
cd "${REPO_ROOT}"

test ! -e "${RESULT_DIR}"
test -d "${R2_ROOT}"
test "$(sha256sum "${K1A_R2}/k1a_r2_geometry_summary.json" | awk '{print $1}')" = 8430730a583371ebdcc1cb35ff80903376a007cb3f2645ce6a55114bdb9ea6d1
test "$(sha256sum "${RENDEZVOUS}" | awk '{print $1}')" = fa258790475303b88a41d4e3f2db684a41a79026b22d434ba9827f0275280796
test "$(sha256sum "${K1A_R2}/pinned_allocator_envelope_summary.json" | awk '{print $1}')" = 99f997a66cb14aeaf1941d34c525729c70dcda0569d45c465a0f1c7f55dfc6b2
test "$(sha256sum "${R2_ROOT}/candidate_manifest.server_local.json" | awk '{print $1}')" = 5a65d66911ac8f073c1dd939b06d78de2a6f51dd2d5ecd66f60f5ee212cc01e9

python3 "${AUDITOR}" accepted-capacity-provenance \
  --geometry-summary "${K1A_R2}/k1a_r2_geometry_summary.json" \
  --rendezvous-marker "${RENDEZVOUS}" \
  --allocator-summary "${K1A_R2}/pinned_allocator_envelope_summary.json" \
  --output "${TMP_AUDIT}/accepted_r2_capacity_provenance.json"

test -x "${RUNTIME_PYTHON}"
test "$(git -C "${VLLM_ROOT}" rev-parse HEAD)" = 0decac0d96c42b49572498019f0a0e3600f50398
test -z "$(git -C "${VLLM_ROOT}" status --porcelain --untracked-files=no)"
python3 "${AUDITOR}" installed-source-audit \
  --vllm-root "${VLLM_ROOT}" \
  --vllm-ascend-root "${VLLM_ASCEND_ROOT}" \
  --output "${TMP_AUDIT}/installed_source_audit.json"
python3 "${AUDITOR}" runtime-import-probe \
  --runtime-python "${RUNTIME_PYTHON}" \
  --output "${TMP_AUDIT}/runtime_import_probe.json"

"${RUNTIME_PYTHON}" - "${VLLM_ASCEND_ROOT}" "${TMP_AUDIT}/runtime_package_resolution.json" <<'PY'
from pathlib import Path
import importlib.metadata
import importlib.util
import json
import sys

root = Path(sys.argv[1]).resolve()
output = Path(sys.argv[2])
spec = importlib.util.find_spec("vllm_ascend")
assert spec is not None and spec.origin is not None
origin = Path(spec.origin).resolve()
assert origin.is_relative_to(root), (origin, root)
value = {
    "vllm_version": importlib.metadata.version("vllm"),
    "vllm_ascend_version": importlib.metadata.version("vllm-ascend"),
    "vllm_ascend_import_origin": str(origin),
    "vllm_ascend_root": str(root),
}
assert value["vllm_version"] == "0.22.1+empty"
assert value["vllm_ascend_version"] == "0.22.1rc1"
output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
PY

python3 - "${TMP_AUDIT}" <<'PY'
from pathlib import Path
import json
import sys

root = Path(sys.argv[1])
provenance = json.loads((root / "accepted_r2_capacity_provenance.json").read_text())
source = json.loads((root / "installed_source_audit.json").read_text())
runtime = json.loads((root / "runtime_import_probe.json").read_text())
assert provenance["accepted_r2_capacity_provenance_gate"] == "pass"
assert provenance["world_size"] == 8
assert provenance["rank_coverage"] == list(range(8))
assert provenance["required_cpu_blocks"] == 128
assert provenance["required_restore_tokens"] == 16384
assert provenance["accepted_capacity_bytes_per_rank"] == 430604288
assert provenance["accepted_capacity_bytes_total"] == 3444834304
assert source["audit_grade"] == "conditional_p8_2_k1a_simple_cpu_offload_source_candidate"
assert source["source_hash_gate"] is True
assert len(source["source_inventory"]) == 9
assert all(row["matched"] is True for row in source["source_inventory"])
assert source["vllm_commit"] == "0decac0d96c42b49572498019f0a0e3600f50398"
assert source["vllm_ascend_commit"] == "5f6faa0cb8830f667266f3b8121cd1383606f2a1"
assert source["ascend_connector_override_present"] is True
assert source["supports_hma_present"] is True
assert source["hybrid_multi_group_source_support_present"] is True
assert source["npu_d2h_h2d_backend_present"] is True
assert runtime["subprocess_exit"] == 0
probe = runtime["probe"]
assert probe is not None and "probe_error" not in probe
assert probe["registry_class"] == "AscendSimpleCPUOffloadConnector"
assert probe["connector_import"] == "success"
assert probe["worker_import"] == "success"
assert probe["copy_backend_import"] == "success"
assert probe["ascend_connector_inherits_upstream"] is True
assert probe["npu_started"] is False
assert probe["vllm_server_started"] is False
assert probe["model_request_sent"] is False
print("installed_source_import_registration_gate=pass")
PY

test -x "${RUNTIME_PREFIX}/bin/vllm"
test -r "${MODEL_PATH}"
test -f "${MODEL_PATH}/quant_model_weights.safetensors.index.json"
test -z "$(ss -ltnp | grep ':7000' || true)"
test -z "$(pgrep -af '[v]llm.*serve' || true)"
python3 - <<'PY'
from pathlib import Path
values = {}
for line in Path('/proc/meminfo').read_text().splitlines():
    key, raw = line.split(':', 1)
    values[key] = int(raw.strip().split()[0]) * 1024
assert values['MemAvailable'] >= 412316860416
assert values['SwapTotal'] == values['SwapFree']
PY

ps -eo pid=,ppid=,pgid=,stat=,args= | awk '$0 ~ /#[0-7]#/' > "${TMP_AUDIT}/keep_alive_markers_before.txt"
test "$(wc -l < "${TMP_AUDIT}/keep_alive_markers_before.txt" | tr -d ' ')" = 16
for card in 0 1 2 3 4 5 6 7; do
  grep -F "#${card}#" "${TMP_AUDIT}/keep_alive_markers_before.txt" >/dev/null
done
npu-smi info > "${TMP_AUDIT}/npu_before.txt"
test -z "$(git status --porcelain --untracked-files=no)"
printf '%s\n' resource_gate=pass
~~~

本节任一失败给 `blocked_p8_2_k1a_r3_r2_r1_source_or_resource_gate` 并停止。不得改用其他 checkout、
不得创建新 checkout、不得改 expected commit、不得 patch/安装/升级，也不得停 keep-alive 或启动 vLLM/NPU。

## 3. 唯一 NPU lifecycle：同一 accepted capacity、六请求、零 retry

只有第 1–2 节全部通过才执行。只从真实 `#[0-7]#` marker 提取 PGID；不得碰其他进程组。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
RESULT_DIR=${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p8_2_k1a_r3_r2_r1_deepseek_v4_flash_simple_cpu_offload_store_restore_2026_0720_run01
RUNNER=${REPO_ROOT}/tools/inference_contracts/run_deepseek_p8_2_k1a_r3_r2_r1_simple_cpu_offload.sh
KEEP_ALIVE_SCRIPT=/data/node0_disk1/Public/npu_keep_alive.sh
TMP_AUDIT_POINTER=/tmp/opencode/p8_2_k1a_r3_r2_r1_preflight_current_2026_0720.path
test -f "${TMP_AUDIT_POINTER}"
TMP_AUDIT=$(cat "${TMP_AUDIT_POINTER}")
cd "${REPO_ROOT}"
KEEP_ALIVE_STOPPED=0

cleanup() {
  set +e
  if test "${KEEP_ALIVE_STOPPED}" -eq 1; then
    bash "${KEEP_ALIVE_SCRIPT}" 0 1 2 3 4 5 6 7 \
      > "${TMP_AUDIT}/keep_alive_restore_stdout.txt" \
      2> "${TMP_AUDIT}/keep_alive_restore_stderr.txt"
    restore_exit=$?
    printf '%s\n' "${restore_exit}" > "${TMP_AUDIT}/keep_alive_restore_exit_code.txt"
    sleep 10
    ps -eo pid=,ppid=,pgid=,stat=,args= | awk '$0 ~ /#[0-7]#/' > "${TMP_AUDIT}/keep_alive_markers_after.txt"
    npu-smi info > "${TMP_AUDIT}/npu_after.txt" 2>&1
    test "${restore_exit}" -eq 0
    test "$(wc -l < "${TMP_AUDIT}/keep_alive_markers_after.txt" | tr -d ' ')" = 16
    for card in 0 1 2 3 4 5 6 7; do
      grep -F "#${card}#" "${TMP_AUDIT}/keep_alive_markers_after.txt" >/dev/null
    done
    printf '%s\n' true > "${TMP_AUDIT}/keep_alive_restored_exact.txt"
  fi
  test -z "$(ss -ltnp | grep ':7000' || true)"
  test -z "$(pgrep -af '[v]llm.*serve' || true)"
}
trap cleanup EXIT

test ! -e "${RESULT_DIR}"
test -f "${RUNNER}"
test -f "${KEEP_ALIVE_SCRIPT}"
ps -eo pid=,ppid=,pgid=,stat=,args= | awk '$0 ~ /#[0-7]#/' > "${TMP_AUDIT}/keep_alive_markers_pre_stop.txt"
CURRENT_PGID=$(ps -o pgid= -p $$ | tr -d ' ')
mapfile -t KEEP_ALIVE_PGIDS < <(awk '{print $3}' "${TMP_AUDIT}/keep_alive_markers_pre_stop.txt" | sort -u)
test "${#KEEP_ALIVE_PGIDS[@]}" -ge 1
KEEP_ALIVE_STOPPED=1
for pgid in "${KEEP_ALIVE_PGIDS[@]}"; do
  test -n "${pgid}"
  test "${pgid}" != "${CURRENT_PGID}"
  kill -TERM -- "-${pgid}"
done
for _ in $(seq 1 60); do
  if ! ps -eo args= | grep -E '#[0-7]#' | grep -v grep >/dev/null; then
    break
  fi
  sleep 1
done
test -z "$(ps -eo args= | grep -E '#[0-7]#' | grep -v grep || true)"
npu-smi info > "${TMP_AUDIT}/npu_after_keep_alive_stop.txt"
grep -F 'No running processes found' "${TMP_AUDIT}/npu_after_keep_alive_stop.txt" >/dev/null
test -z "$(ss -ltnp | grep ':7000' || true)"

set +e
bash "${RUNNER}" "${RESULT_DIR}" \
  > "${TMP_AUDIT}/runner_stdout.txt" \
  2> "${TMP_AUDIT}/runner_stderr.txt"
RUNNER_EXIT=$?
set -e
printf '%s\n' "${RUNNER_EXIT}" > "${TMP_AUDIT}/runner_exit_code.txt"

test -d "${RESULT_DIR}"
test -f "${RESULT_DIR}/grading_inputs.json"
test -f "${RESULT_DIR}/candidate_manifest.server_local.json"
test -f "${RESULT_DIR}/cleanup_status.txt"
test "$(cat "${RESULT_DIR}/cleanup_status.txt")" = clean
test -z "$(ss -ltnp | grep ':7000' || true)"
test -z "$(pgrep -af '[v]llm.*serve' || true)"
~~~

请求顺序必须严格为：

~~~text
4K warmup -> 32K prime -> 131K pressure -> 32K restore_follower -> 32K repeat_follower -> 32K isolated_control
~~~

不得 retry。任何失败都保留首错并进入第 4 节离线分级，不得重跑、调容量、启动 second lifecycle 或补第七请求。

## 4. 独立分级、failure-safe manifest 与恢复复核

runner 结束后只读解析，不重跑。finalizer 必须保留已有 `first_failure_excerpt.txt`，并生成含
`missing_candidate_files` 的 `candidate_manifest.server_local.json`。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
RESULT_DIR=${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p8_2_k1a_r3_r2_r1_deepseek_v4_flash_simple_cpu_offload_store_restore_2026_0720_run01
TMP_AUDIT=$(cat /tmp/opencode/p8_2_k1a_r3_r2_r1_preflight_current_2026_0720.path)
cd "${REPO_ROOT}"

python3 - "${RESULT_DIR}" "${TMP_AUDIT}" <<'PY'
from pathlib import Path
import csv
import hashlib
import json
import sys

root, audit = map(Path, sys.argv[1:])
grading = json.loads((root / "grading_inputs.json").read_text())
manifest = json.loads((root / "candidate_manifest.server_local.json").read_text())
trace = json.loads((root / "transfer_trace_summary.json").read_text())
rows = list(csv.DictReader((root / "request_summary.tsv").open(), delimiter="\t"))
runner_exit = int((audit / "runner_exit_code.txt").read_text())

assert grading["task_id"] == "p8_2_k1a_r3_r2_r1_deepseek_v4_flash_simple_cpu_offload_store_restore_2026_0720"
assert grading["cpu_bytes_to_use"] == 3444834304
assert grading["cpu_bytes_to_use_per_rank"] == 430604288
assert grading["cleanup"] == "clean"
assert manifest["schema_version"] == "p8_2_k1a_candidate_manifest_v1"
assert manifest["result_transfer_authorized"] is True
assert manifest["candidate_total_bytes"] <= 71680
assert isinstance(manifest["missing_candidate_files"], list)
assert (audit / "keep_alive_restored_exact.txt").read_text().strip() == "true"

for name, record in manifest["files"].items():
    path = root / name
    assert path.is_file()
    assert path.stat().st_size == record["bytes"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]
    assert record["sensitivity"] == "bounded_operational_metadata_no_content_or_token_ids"

if runner_exit == 0:
    assert grading["server_grade"] == "candidate_green_p8_2_k1a_r3_r2_r1_simple_cpu_offload_store_restore"
    assert grading["successful_request_count"] == 6
    assert len(rows) == 6
    assert [row["k1a_role"] for row in rows] == [
        "warmup", "prime", "pressure", "restore_follower", "repeat_follower", "isolated_control"
    ]
    assert grading["accepted_capacity_exact"] is True
    assert grading["request_evidence_exact"] is True
    assert grading["connector_resolution_ok"] is True
    assert grading["repair_diagnostic_ok"] is True
    assert trace["d2h_worker_count"] == 8
    assert trace["h2d_worker_count"] == 8
    assert trace["d2h_store_complete"] is True
    assert trace["h2d_restore_complete"] is True
    assert manifest["missing_candidate_files"] == []
else:
    assert grading["server_grade"] != "candidate_green_p8_2_k1a_r3_r2_r1_simple_cpu_offload_store_restore"
    assert (root / "first_failure_excerpt.txt").read_text().strip()

print(json.dumps({
    "runner_exit": runner_exit,
    "server_grade": grading["server_grade"],
    "successful_request_count": grading["successful_request_count"],
    "d2h_worker_count": trace["d2h_worker_count"],
    "h2d_worker_count": trace["h2d_worker_count"],
    "candidate_file_count": manifest["candidate_file_count"],
    "candidate_total_bytes": manifest["candidate_total_bytes"],
    "missing_candidate_files": manifest["missing_candidate_files"],
}, sort_keys=True))
PY

test -z "$(git status --porcelain --untracked-files=no)"
test -z "$(ss -ltnp | grep ':7000' || true)"
test -z "$(pgrep -af '[v]llm.*serve' || true)"
~~~

分级严格为：

- repository/parent evidence 门失败：`blocked_p8_2_k1a_r3_r2_r1_repository_or_parent_gate`；
- R2 provenance、installed source/import 或 resource 门失败：
  `blocked_p8_2_k1a_r3_r2_r1_source_or_resource_gate`；
- server 启动后 0/6 成功：`red_p8_2_k1a_r3_r2_r1_no_success`；
- 请求结构不完整或部分成功：`yellow_p8_2_k1a_r3_r2_r1_partial`；
- 6/6 成功且 8/8 D2H store 完整，但没有 8/8 H2D restore：
  `yellow_p8_2_k1a_r3_r2_r1_store_only_no_restore`；
- request/connector/capacity/R2 repair/MTP/health/queue/cleanup 任一证据不完整：
  `red_p8_2_k1a_r3_r2_r1_evidence_incomplete`；
- 只有 6/6 首次成功、accepted capacity exact、8/8 worker D2H submit+complete、8/8 worker H2D
  submit+complete、restore scheduler CPU hit/load schedule/load complete、R2/MTP/queue/health/cleanup/
  keep-alive 全过，才给 `candidate_green_p8_2_k1a_r3_r2_r1_simple_cpu_offload_store_restore`。

candidate green 也只证明该冻结 lifecycle 的双向机制，不是 performance reference、加速收益、通用支持、
K2 解锁或硬件瓶颈归因。服务器只能给 candidate，仍需开发机独立复核结果包。

## 5. 最终报告与传输边界

最终报告必须包含：同步前后 HEAD/origin/ahead-behind/tracked；parent R3-R2 五文件 replay；canonical
argv schema/hash；R2 accepted provenance；installed source inventory/import origin/runtime registration；资源门；
keep-alive stop/restore；runner/mode/finalize exit；六个 slot 的 HTTP/token/SSE/MTP/prefix 摘要；resolved
connector/capacity；D2H/H2D worker/bytes/completion；repair/health/queue；cleanup；最终 grade 和 claim boundary。

同时报告 `RESULT_DIR` 和 `candidate_manifest.server_local.json` 的完整文件清单、
`missing_candidate_files`、逐文件 bytes/SHA-256/sensitivity、总量，以及可用
`email / upload-api / server-local` 和一个推荐理由。当前 `result_transfer_authorized:true`，不得再用该字段
阻断有界结果包；但它不代表已经选定渠道。必须等待用户针对完整清单明确选择一个渠道，之后只传批准
范围；失败不重试、不自动换渠道。raw logs、metrics、trace、request bodies、generated content/token IDs
全部留服务器。

完成后停止等待：`next_task_authorized:false`。不得自动重跑或改变容量；不得进入 K2；不得进入 P8.3-I1、P8.4、P8.5 或 P9。
