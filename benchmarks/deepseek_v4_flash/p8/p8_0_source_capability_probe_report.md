# P8.0 Target-tag Source Capability Probe Report

- Probe: `p8_target_tag_source_capability_probe_2026_0710`
- Probe date: `2026-07-10`
- Claim ceiling: `instrumented`
- Selected workload validated: `false`
- Selected-workload gate: `waiting_selected_workload_runtime_gate`
- Real VllmAscendAdapter gate: `waiting_selected_workload_runtime_gate`

## Pinned targets

| Target | Tag | Expected commit | Observed commit | Verified |
| --- | --- | --- | --- | --- |
| vllm | `v0.20.2` | `bc150f50299199599673614f80d12a196f377655` | `bc150f50299199599673614f80d12a196f377655` | `true` |
| vllm_ascend | `v0.20.2rc1` | `367b8e62da799870a7476ce34f5f7658589a8aad` | `367b8e62da799870a7476ce34f5f7658589a8aad` | `true` |

## Capability matrix

| Capability | Runtime scope | Source status | Runtime gate |
| --- | --- | --- | --- |
| deepseek_v4_model_registration | vllm, vllm_ascend | `available_uninstrumented` | `waiting_selected_workload_runtime_gate` |
| deepseek_v4_mtp | vllm, vllm_ascend | `available_uninstrumented` | `waiting_selected_workload_runtime_gate` |
| deepseek_v4_tool_reasoning_parser | vllm | `available_uninstrumented` | `waiting_selected_workload_runtime_gate` |
| dsa_context_parallel | vllm_ascend | `available_uninstrumented` | `waiting_selected_workload_runtime_gate` |
| flashcomm1_config_path | vllm_ascend | `available_uninstrumented` | `waiting_selected_workload_runtime_gate` |
| prefix_cache | vllm | `instrumented` | `waiting_selected_workload_runtime_gate` |
| kv_cache_events | vllm | `instrumented` | `waiting_selected_workload_runtime_gate` |
| kv_cache_cpu_offload | vllm, vllm_ascend | `instrumented` | `waiting_selected_workload_runtime_gate` |
| ucm_store_connector | vllm_ascend | `available_uninstrumented` | `waiting_selected_workload_runtime_gate` |
| kv_cache_pool | vllm_ascend | `instrumented` | `waiting_selected_workload_runtime_gate` |
| eplb_recording_static_map | vllm_ascend | `instrumented` | `waiting_selected_workload_runtime_gate` |
| expert_hotness_metrics | vllm, vllm_ascend | `instrumented` | `waiting_selected_workload_runtime_gate` |
| weight_prefetch | vllm_ascend | `available_uninstrumented` | `waiting_selected_workload_runtime_gate` |

## Evidence details

### `deepseek_v4_model_registration`

- `source` `vllm_deepseek_v4_registry` at `vllm:vllm/model_executor/models/registry.py`; blob `01f357a4993a6d451ddae109cddda03bc58672a6`; lines `99`; result `matched`; contains `"DeepseekV4ForCausalLM": ("deepseek_v4", "DeepseekV4ForCausalLM")`.
- `source` `ascend_deepseek_v4_registry` at `vllm_ascend:vllm_ascend/models/__init__.py`; blob `f6bc5e70796ff099e02a5b06331dbe7bf80db5b2`; lines `5`; result `matched`; contains `ModelRegistry.register_model("DeepseekV4ForCausalLM"`.
- `documentation` `vllm_deepseek_v4_supported_model_doc` at `vllm:docs/models/supported_models.md`; blob `7c87359afb27b0d787b832e8a85e9702345c967a`; lines `387`; result `matched`; contains `DeepseekV4ForCausalLM`.

### `deepseek_v4_mtp`

- `source` `vllm_deepseek_v4_mtp_config` at `vllm:vllm/config/speculative.py`; blob `612cc3a1f281af8fc864d2884830a48e87fdaebd`; lines `305`; result `matched`; contains `"architectures": ["DeepSeekV4MTPModel"]`.
- `source` `ascend_deepseek_v4_mtp_registry` at `vllm_ascend:vllm_ascend/models/__init__.py`; blob `f6bc5e70796ff099e02a5b06331dbe7bf80db5b2`; lines `7`; result `matched`; contains `ModelRegistry.register_model("DeepSeekV4MTPModel"`.
- `source` `ascend_deepseek_v4_mtp_model` at `vllm_ascend:vllm_ascend/models/deepseek_v4_mtp.py`; blob `4cb37826cf27569a9dea941f3034e287640eb068`; lines `196`; result `matched`; contains `class DeepSeekV4MTP(`.

### `deepseek_v4_tool_reasoning_parser`

- `source` `vllm_deepseek_v4_tool_parser` at `vllm:vllm/tool_parsers/deepseekv4_tool_parser.py`; blob `45a9c13025788b1b373a1ea4e8a8e1e8186e7039`; lines `7`; result `matched`; contains `class DeepSeekV4ToolParser(`.
- `source` `vllm_deepseek_v4_reasoning_alias` at `vllm:vllm/reasoning/__init__.py`; blob `755fa56d294c6b580943adcff3177c090eb6bcfb`; lines `31`; result `matched`; contains `"deepseek_v4": (`.

### `dsa_context_parallel`

- `source` `ascend_dsa_cp_config_reader` at `vllm_ascend:vllm_ascend/utils.py`; blob `f4b97ab64bb784dfd21a4edf74667d9e25b26507`; lines `1389`; result `matched`; contains `def enable_dsa_cp() -> bool:`.
- `source` `ascend_dsa_cp_metadata_builder` at `vllm_ascend:vllm_ascend/attention/context_parallel/dsa_cp.py`; blob `93917a2f4d1013a8cc7fe262060e97c7a8645d08`; lines `145`; result `matched`; contains `class AscendDSACPMetadataBuilder(`.
- `source` `ascend_deepseek_v4_dsa_cp_use` at `vllm_ascend:vllm_ascend/models/deepseek_v4.py`; blob `ba341b4c058b5f3dc7c327144b74e150b93a16bf`; lines `611`; result `matched`; contains `self.enable_dsa_cp = enable_dsa_cp()`.
- `documentation` `ascend_dsa_cp_config_doc` at `vllm_ascend:docs/source/user_guide/configuration/additional_config.md`; blob `9d57cf9c3336666c56f34f572a52fea875ada799`; lines `101`; result `matched`; contains `'enable_dsa_cp'`.

### `flashcomm1_config_path`

- `source` `ascend_flashcomm1_additional_config` at `vllm_ascend:vllm_ascend/ascend_config.py`; blob `330520c58e40c7f024f91a0b5213d449f031d14c`; lines `83`; result `matched`; contains `self.enable_flashcomm1 = self._get_config_value(`.
- `source` `ascend_flashcomm1_runtime_gate` at `vllm_ascend:vllm_ascend/utils.py`; blob `f4b97ab64bb784dfd21a4edf74667d9e25b26507`; lines `1254`; result `matched`; contains `if not ascend_config.enable_flashcomm1:`.
- `documentation` `ascend_flashcomm1_config_doc` at `vllm_ascend:docs/source/user_guide/configuration/additional_config.md`; blob `9d57cf9c3336666c56f34f572a52fea875ada799`; lines `20,92`; result `matched`; contains `'enable_flashcomm1'`.

### `prefix_cache`

- `source` `vllm_prefix_cache_block_pool` at `vllm:vllm/v1/core/block_pool.py`; blob `9097079ef33a88f9fccb89651fa45bb30c9c0fd8`; lines `159`; result `matched`; contains `self.enable_caching = enable_caching`.
- `source` `vllm_prefix_cache_store_event` at `vllm:vllm/v1/core/block_pool.py`; blob `9097079ef33a88f9fccb89651fa45bb30c9c0fd8`; lines `305`; result `matched`; contains `BlockStored(`.
- `instrumentation` `vllm_prefix_cache_event_queue` at `vllm:vllm/v1/core/block_pool.py`; blob `9097079ef33a88f9fccb89651fa45bb30c9c0fd8`; lines `304,382,474`; result `matched`; contains `self.kv_event_queue.append(`.
- `instrumentation` `vllm_prefix_cache_event_publish` at `vllm:vllm/v1/core/sched/scheduler.py`; blob `395fa80bfe537821d961724ca0f1b8d791fa3c75`; lines `1529`; result `matched`; contains `self.kv_event_publisher.publish(batch)`.

### `kv_cache_events`

- `source` `vllm_kv_events_config` at `vllm:vllm/config/kv_events.py`; blob `d618bc9a73f3ba8b8d0c952a00f0766d2a3f2f4f`; lines `11`; result `matched`; contains `class KVEventsConfig:`.
- `source` `vllm_kv_event_batch` at `vllm:vllm/distributed/kv_events.py`; blob `d3e304f8b6036f9993bfb35b589c72133c0926ec`; lines `106`; result `matched`; contains `class KVEventBatch(`.
- `instrumentation` `vllm_kv_event_batch_build` at `vllm:vllm/v1/core/sched/scheduler.py`; blob `395fa80bfe537821d961724ca0f1b8d791fa3c75`; lines `1528`; result `matched`; contains `batch = KVEventBatch(`.
- `instrumentation` `vllm_kv_event_publisher` at `vllm:vllm/v1/core/sched/scheduler.py`; blob `395fa80bfe537821d961724ca0f1b8d791fa3c75`; lines `1529`; result `matched`; contains `self.kv_event_publisher.publish(batch)`.

### `kv_cache_cpu_offload`

- `source` `vllm_offloading_connector` at `vllm:vllm/distributed/kv_transfer/kv_connector/v1/offloading_connector.py`; blob `f11281dcf14e52b5038656b3b396037e8a2320ea`; lines `44`; result `matched`; contains `class OffloadingConnector(`.
- `source` `ascend_npu_offloading_spec` at `vllm_ascend:vllm_ascend/kv_offload/npu.py`; blob `90816ce3abbc4143e8eb2ab1a081cab8d07c0b86`; lines `16`; result `matched`; contains `class NPUOffloadingSpec(`.
- `instrumentation` `vllm_offload_byte_metric` at `vllm:vllm/distributed/kv_transfer/kv_connector/v1/offloading/metrics.py`; blob `0839b2727ccc01b4b3cea9e1b69e08093fca81d2`; lines `106`; result `matched`; contains `name="vllm:kv_offload_total_bytes"`.
- `instrumentation` `vllm_offload_event_export` at `vllm:vllm/distributed/kv_transfer/kv_connector/v1/offloading_connector.py`; blob `f11281dcf14e52b5038656b3b396037e8a2320ea`; lines `148`; result `matched`; contains `def take_events(self) -> Iterable[KVCacheEvent]:`.
- `documentation` `ascend_cpu_offload_doc` at `vllm_ascend:docs/source/user_guide/feature_guide/kv_cache_cpu_offload.md`; blob `974897e6f3e1ad57bd88a211993e5f859caa2d4a`; lines `7,29,58,70`; result `matched`; contains `NPUOffloadingSpec`.

### `ucm_store_connector`

- `source` `ascend_ucm_connector` at `vllm_ascend:vllm_ascend/distributed/kv_transfer/kv_pool/ucm_connector.py`; blob `de25ae934e89613994033c3ee495af3bd9828b60`; lines `37`; result `matched`; contains `class UCMConnectorV1(`.
- `source` `ascend_ucm_connector_registration` at `vllm_ascend:vllm_ascend/distributed/kv_transfer/__init__.py`; blob `befd8c402c87744de6409fb034c26cf708f35acf`; lines `58`; result `matched`; contains `"UCMConnector", "vllm_ascend.distributed.kv_transfer.kv_pool.ucm_connector"`.
- `documentation` `ascend_ucm_deployment_doc` at `vllm_ascend:docs/source/user_guide/feature_guide/ucm_deployment.md`; blob `fb91b28f6dcbaa329b58ac935c5e3f2e4d3eb6a6`; lines `1`; result `matched`; contains `# UCM Store Deployment Guide`.

### `kv_cache_pool`

- `source` `ascend_store_connector` at `vllm_ascend:vllm_ascend/distributed/kv_transfer/kv_pool/ascend_store/ascend_store_connector.py`; blob `74181914ef1140bcb8ecffe810b4fdfb81010318`; lines `71`; result `matched`; contains `class AscendStoreConnector(`.
- `source` `ascend_store_mooncake_backend` at `vllm_ascend:vllm_ascend/distributed/kv_transfer/kv_pool/ascend_store/backend/mooncake_backend.py`; blob `4476b32ecc44ac2153aca868f8925d09da35818e`; lines `25`; result `matched`; contains `class MooncakeBackend(`.
- `instrumentation` `ascend_store_kv_events` at `vllm_ascend:vllm_ascend/distributed/kv_transfer/kv_pool/ascend_store/ascend_store_connector.py`; blob `74181914ef1140bcb8ecffe810b4fdfb81010318`; lines `37`; result `matched`; contains `class AscendStoreKVEvents(`.
- `instrumentation` `ascend_store_take_events` at `vllm_ascend:vllm_ascend/distributed/kv_transfer/kv_pool/ascend_store/ascend_store_connector.py`; blob `74181914ef1140bcb8ecffe810b4fdfb81010318`; lines `168`; result `matched`; contains `def take_events(self) -> Iterable["KVCacheEvent"]:`.
- `documentation` `ascend_kv_pool_doc` at `vllm_ascend:docs/source/user_guide/feature_guide/kv_pool.md`; blob `41127c452a13c997fafb03898cdad7b08ba91895`; lines `140,208,276,288,292,371,458,541,629,813,815,831`; result `matched`; contains `AscendStoreConnector`.

### `eplb_recording_static_map`

- `source` `ascend_eplb_static_map_load` at `vllm_ascend:vllm_ascend/eplb/core/eplb_utils.py`; blob `226a02d9a8abd35e36de798e7c07fa0ffdfa04dc`; lines `33`; result `matched`; contains `def expert_file_to_tensor(`.
- `source` `ascend_eplb_map_update` at `vllm_ascend:vllm_ascend/eplb/adaptor/vllm_adaptor.py`; blob `e625302f3c5b4e77d1ed18acb297e309853ca0b8`; lines `148`; result `matched`; contains `def do_update_expert_map(`.
- `instrumentation` `ascend_eplb_map_export` at `vllm_ascend:vllm_ascend/eplb/adaptor/vllm_adaptor.py`; blob `e625302f3c5b4e77d1ed18acb297e309853ca0b8`; lines `124`; result `matched`; contains `def _export_tensor_to_file(`.
- `instrumentation` `ascend_eplb_record_path` at `vllm_ascend:vllm_ascend/eplb/eplb_updator.py`; blob `146d6ea25c8e9388530d251de0c731028809f1fc`; lines `54`; result `matched`; contains `self.expert_map_record_path = self.eplb_config.expert_map_record_path`.
- `documentation` `ascend_eplb_static_map_doc` at `vllm_ascend:docs/source/user_guide/feature_guide/eplb_swift_balancer.md`; blob `04878d5e4ad23a6d750e5d2e36b1a9ebdd2b9fc9`; lines `72`; result `matched`; contains `"expert_map_path"`.

### `expert_hotness_metrics`

- `source` `vllm_expert_load_window` at `vllm:vllm/distributed/eplb/eplb_state.py`; blob `1da39caccd806d48c381f614ebb38460908a7015`; lines `67,157,223,228,230,420,421,423,461,562,563,568,569,570,617,626,691,693,696,697,700,701,703,709,711,714,715,717,750,751,756,794,797`; result `matched`; contains `expert_load_window`.
- `source` `ascend_expert_heat_interval` at `vllm_ascend:vllm_ascend/eplb/eplb_updator.py`; blob `146d6ea25c8e9388530d251de0c731028809f1fc`; lines `52,58,61,78,87,90,94`; result `matched`; contains `self.expert_heat_collection_interval`.
- `instrumentation` `vllm_expert_load_record` at `vllm:vllm/model_executor/layers/fused_moe/layer.py`; blob `7174cdd88f258a6418e20653341736bad1a6811f`; lines `1526`; result `matched`; contains `record the load metrics in 'expert_load_view'`.
- `instrumentation` `vllm_expert_load_window_copy` at `vllm:vllm/distributed/eplb/eplb_state.py`; blob `1da39caccd806d48c381f614ebb38460908a7015`; lines `564`; result `matched`; contains `].copy_(eplb_model_state.expert_load_pass)`.
- `documentation` `ascend_expert_load_metric_doc` at `vllm_ascend:docs/source/user_guide/feature_guide/eplb_swift_balancer.md`; blob `04878d5e4ad23a6d750e5d2e36b1a9ebdd2b9fc9`; lines `92`; result `matched`; contains `expert_load_balance_ratio`.

### `weight_prefetch`

- `source` `ascend_weight_prefetch_config` at `vllm_ascend:vllm_ascend/ascend_config.py`; blob `330520c58e40c7f024f91a0b5213d449f031d14c`; lines `573`; result `matched`; contains `class WeightPrefetchConfig:`.
- `source` `ascend_weight_prefetch_method` at `vllm_ascend:vllm_ascend/ops/weight_prefetch.py`; blob `09a052cdc81e68a8d403164f9fe23b33be4b9f5a`; lines `37`; result `matched`; contains `class WeightPrefetchMethod:`.
- `source` `ascend_weight_prefetch_op` at `vllm_ascend:vllm_ascend/ops/weight_prefetch.py`; blob `09a052cdc81e68a8d403164f9fe23b33be4b9f5a`; lines `80,101,150,160,203`; result `matched`; contains `torch.ops.vllm.prefetch_preprocess(`.
- `documentation` `ascend_weight_prefetch_doc` at `vllm_ascend:docs/source/user_guide/feature_guide/weight_prefetch.md`; blob `4a20476ea259f6b506962051d73a5b354e427cc1`; lines `1`; result `matched`; contains `# Weight Prefetch`.

## Boundary

This report proves only that exact source/config/instrumentation symbols exist at the pinned Git objects. It does not import or run either runtime, does not validate the selected workload, and does not authorize a real VllmAscendAdapter.
