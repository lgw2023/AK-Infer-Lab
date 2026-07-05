import functools
import importlib
import inspect
import json
import os
import time
from pathlib import Path

artifact_dir = Path(__file__).resolve().parent
inventory_path = artifact_dir / "hook_target_inventory.jsonl"
patchability_path = artifact_dir / "hook_patchability.tsv"
trace_path = artifact_dir / "runtime_hook_proto_trace.jsonl"
device = os.environ.get("AK_OBS_NPU_DEVICE", "npu:6")

target_modules = [
    ("request_runtime", "vllm.v1.engine.core", ["EngineCore"], ["add_request", "step", "run", "run_busy_loop"]),
    ("request_runtime", "vllm.v1.engine.async_llm", ["AsyncLLM"], ["add_request", "generate", "step", "run"]),
    ("request_runtime", "vllm.v1.engine.llm_engine", ["LLMEngine"], ["add_request", "step", "run"]),
    ("scheduler", "vllm.v1.core.sched.scheduler", ["Scheduler"], ["schedule", "update_from_output"]),
    ("model_execute", "vllm.v1.worker.gpu_model_runner", ["GPUModelRunner"], ["execute_model", "synchronize_input_prep", "sample"]),
    ("model_execute", "vllm_ascend.worker.model_runner_v1", ["NPUModelRunner"], ["execute_model", "update_stream", "sample"]),
    ("model_execute", "vllm_ascend.worker.worker", ["*"], ["execute_model"]),
    ("model_execute", "vllm_ascend.worker.v2.model_runner", ["NPUModelRunner"], ["execute_model", "update_stream", "sample"]),
]

def safe_signature(obj):
    try:
        return str(inspect.signature(obj))
    except Exception as exc:
        return f"<signature_error:{type(exc).__name__}:{exc}>"

def source_location(obj):
    try:
        return inspect.getsourcefile(obj), inspect.getsourcelines(obj)[1]
    except Exception as exc:
        return None, f"<source_error:{type(exc).__name__}:{exc}>"

def candidate_classes(module, class_names):
    for name, obj in inspect.getmembers(module, inspect.isclass):
        if "*" in class_names or name in class_names:
            yield name, obj

def candidate_methods(cls, method_names):
    for name, obj in inspect.getmembers(cls, inspect.isfunction):
        if any(token in name for token in method_names):
            yield name, obj

def make_wrapper(original):
    @functools.wraps(original)
    def wrapper(*args, **kwargs):
        return original(*args, **kwargs)
    return wrapper

inventory = []
patch_rows = ["category\tmodule\tclass\tmethod\tpatch_status\trestore_status\tsource_file\tsource_line\tsignature"]

for category, module_name, class_names, method_names in target_modules:
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        inventory.append({
            "category": category,
            "module": module_name,
            "status": "import_error",
            "error": f"{type(exc).__name__}: {exc}",
        })
        continue

    module_file = getattr(module, "__file__", None)
    inventory.append({
        "category": category,
        "module": module_name,
        "status": "import_ok",
        "module_file": module_file,
    })

    for class_name, cls in candidate_classes(module, class_names):
        class_file, class_line = source_location(cls)
        inventory.append({
            "category": category,
            "module": module_name,
            "class": class_name,
            "status": "class_found",
            "source_file": class_file,
            "source_line": class_line,
        })

        for method_name, method in candidate_methods(cls, method_names):
            method_file, method_line = source_location(method)
            signature = safe_signature(method)
            record = {
                "category": category,
                "module": module_name,
                "class": class_name,
                "method": method_name,
                "status": "method_found",
                "source_file": method_file,
                "source_line": method_line,
                "signature": signature,
            }
            inventory.append(record)

            patch_status = "not_attempted"
            restore_status = "not_attempted"
            original = getattr(cls, method_name, None)
            try:
                setattr(cls, method_name, make_wrapper(original))
                patch_status = "patched_in_process"
            except Exception as exc:
                patch_status = f"patch_error:{type(exc).__name__}:{exc}"
            finally:
                try:
                    setattr(cls, method_name, original)
                    restore_status = "restored"
                except Exception as exc:
                    restore_status = f"restore_error:{type(exc).__name__}:{exc}"

            patch_rows.append(
                "\t".join(
                    [
                        category,
                        module_name,
                        class_name,
                        method_name,
                        patch_status,
                        restore_status,
                        str(method_file),
                        str(method_line),
                        signature.replace("\t", " "),
                    ]
                )
            )

with inventory_path.open("w", encoding="utf-8") as handle:
    for record in inventory:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

patchability_path.write_text("\n".join(patch_rows) + "\n", encoding="utf-8")

now = time.monotonic_ns()
base_event = {
    "schema_version": "0.1.0",
    "trace_id": "trace_p1_hook_proto_0001",
    "request_id": "req_hook_proto_0001",
    "session_id": "session_hook_proto",
    "queue_wait_us": 0,
    "overlap_ratio": None,
    "hit_or_miss": "not_applicable",
    "stall_reason": "unknown",
    "artifact_path": "runtime_hook_proto_trace.jsonl",
}

events = [
    {
        **base_event,
        "event_id": "evt_hook_request_enqueue",
        "timestamp_ns": now,
        "time_base": "host_monotonic_ns",
        "phase": "enqueue",
        "event_type": "point",
        "resource_scope": "request_runtime_profile",
        "layer_id": None,
        "op_name": "hook_proto_request",
        "kernel_name": None,
        "stream_id": "host:runtime",
        "device_id": "host:cpu",
        "object_type": None,
        "object_id": None,
        "source_tier": "host_dram",
        "target_tier": "hbm",
        "bytes_read": 0,
        "bytes_write": 0,
        "latency_us": 0,
        "policy_decision": "prototype_hook_emit",
        "evidence_source": "runtime_hook_probe",
    },
    {
        **base_event,
        "event_id": "evt_hook_activation_state",
        "timestamp_ns": now + 1_000,
        "time_base": "host_monotonic_ns",
        "phase": "prefill",
        "event_type": "lifecycle",
        "resource_scope": "state_object_profile",
        "layer_id": 0,
        "op_name": "hook_proto_activation",
        "kernel_name": None,
        "stream_id": f"{device}:copy:proto",
        "device_id": device,
        "object_type": "activation",
        "object_id": "activation:req_hook_proto_0001:L00",
        "source_tier": "host_dram",
        "target_tier": "hbm",
        "bytes_read": 16384,
        "bytes_write": 16384,
        "latency_us": 1,
        "policy_decision": "prototype_state_object",
        "evidence_source": "runtime_hook_probe",
    },
    {
        **base_event,
        "event_id": "evt_hook_h2d_done",
        "timestamp_ns": now + 2_000,
        "time_base": "host_monotonic_ns",
        "phase": "prefill",
        "event_type": "span_end",
        "resource_scope": "transfer_overlap_profile",
        "layer_id": 0,
        "op_name": "hook_proto_h2d",
        "kernel_name": "prototype_copy",
        "stream_id": f"{device}:copy:proto",
        "device_id": device,
        "object_type": "activation",
        "object_id": "activation:req_hook_proto_0001:L00",
        "source_tier": "host_dram",
        "target_tier": "hbm",
        "bytes_read": 16384,
        "bytes_write": 16384,
        "latency_us": 1,
        "policy_decision": "prototype_copy",
        "evidence_source": "runtime_hook_probe",
    },
    {
        **base_event,
        "event_id": "evt_hook_operator",
        "timestamp_ns": now + 3_000,
        "time_base": "host_monotonic_ns",
        "phase": "prefill",
        "event_type": "span_end",
        "resource_scope": "operator_timeline_profile",
        "layer_id": 0,
        "op_name": "hook_proto_execute_model",
        "kernel_name": "prototype_operator",
        "stream_id": f"{device}:compute:proto",
        "device_id": device,
        "object_type": "activation",
        "object_id": "activation:req_hook_proto_0001:L00",
        "source_tier": "hbm",
        "target_tier": "hbm",
        "bytes_read": 32768,
        "bytes_write": 16384,
        "latency_us": 1,
        "policy_decision": "prototype_operator_marker",
        "evidence_source": "runtime_hook_probe",
    },
]

with trace_path.open("w", encoding="utf-8") as handle:
    for event in events:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
