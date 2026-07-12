# P8.0 Target-tag Source Capability Probe Report

- Probe: `p8_target_tag_source_capability_probe_v0221_2026_0712`
- Probe date: `2026-07-12`
- Claim ceiling: `instrumented`
- Selected workload validated: `false`
- Selected-workload gate: `waiting_selected_workload_runtime_gate`
- Real VllmAscendAdapter gate: `waiting_selected_workload_runtime_gate`

## Pinned targets

| Target | Tag | Expected commit | Observed commit | Verified |
| --- | --- | --- | --- | --- |
| vllm | `v0.22.1` | `0decac0d96c42b49572498019f0a0e3600f50398` | `0decac0d96c42b49572498019f0a0e3600f50398` | `true` |
| vllm_ascend | `v0.22.1rc1` | `5f6faa0cb8830f667266f3b8121cd1383606f2a1` | `5f6faa0cb8830f667266f3b8121cd1383606f2a1` | `true` |

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

- `source` `vllm_deepseek_v4_registry` at `vllm:vllm/model_executor/models/registry.py`; blob `59a26b1e83ea174c95095f01c0fcf77d67e8049c`; lines `101`; result `matched`; contains `"DeepseekV4ForCausalLM": ("vllm.models.deepseek_v4", "DeepseekV4ForCausalLM")`.
- `source` `ascend_deepseek_v4_registry` at `vllm_ascend:vllm_ascend/models/__init__.py`; blob `f6bc5e70796ff099e02a5b06331dbe7bf80db5b2`; lines `5`; result `matched`; contains `ModelRegistry.register_model("DeepseekV4ForCausalLM"`.
- `documentation` `vllm_deepseek_v4_supported_model_doc` at `vllm:docs/models/supported_models.md`; blob `fa852fce7f449643c2781912f9b14dd01fb2c21f`; lines `388`; result `matched`; contains `DeepseekV4ForCausalLM`.

### `deepseek_v4_mtp`

- `source` `vllm_deepseek_v4_mtp_config` at `vllm:vllm/config/speculative.py`; blob `47d35f4ff4b5c2178e1820b3dc45cd6cf27d68c1`; lines `318`; result `matched`; contains `"architectures": ["DeepSeekV4MTPModel"]`.
- `source` `ascend_deepseek_v4_mtp_registry` at `vllm_ascend:vllm_ascend/models/__init__.py`; blob `f6bc5e70796ff099e02a5b06331dbe7bf80db5b2`; lines `7`; result `matched`; contains `ModelRegistry.register_model("DeepSeekV4MTPModel"`.
- `source` `ascend_deepseek_v4_mtp_model` at `vllm_ascend:vllm_ascend/models/deepseek_v4_mtp.py`; blob `30e95b90f44751a8d4f8f1b68123b98214989af9`; lines `201`; result `matched`; contains `class DeepSeekV4MTP(`.

### `deepseek_v4_tool_reasoning_parser`

- `source` `vllm_deepseek_v4_tool_parser` at `vllm:vllm/tool_parsers/deepseekv4_tool_parser.py`; blob `e32451cd8bbd272f30e10f15391a8d9048f640a8`; lines `14`; result `matched`; contains `class DeepSeekV4ToolParser(`.
- `source` `vllm_deepseek_v4_reasoning_alias` at `vllm:vllm/reasoning/__init__.py`; blob `cd51f106503ade38a376eac64cbea97ec6cd1e67`; lines `31`; result `matched`; contains `"deepseek_v4": (`.

### `dsa_context_parallel`

- `source` `ascend_dsa_cp_config_reader` at `vllm_ascend:vllm_ascend/utils.py`; blob `f0ef65006efeb19f1aa5269e41267875e74060fd`; lines `1345`; result `matched`; contains `def enable_dsa_cp() -> bool:`.
- `source` `ascend_dsa_cp_metadata_builder` at `vllm_ascend:vllm_ascend/attention/context_parallel/dsa_cp.py`; blob `2ae175c9f79ed6a7ebce3231a3beb8bedf1561e2`; lines `137`; result `matched`; contains `class AscendDSACPMetadataBuilder(`.
- `source` `ascend_deepseek_v4_dsa_cp_use` at `vllm_ascend:vllm_ascend/models/deepseek_v4.py`; blob `f516c35ee687a1076868083c0485d05c145fcd77`; lines `731`; result `matched`; contains `self.enable_dsa_cp = enable_dsa_cp()`.
- `documentation` `ascend_dsa_cp_config_doc` at `vllm_ascend:docs/source/user_guide/configuration/additional_config.md`; blob `4bee3872601a49b65bb25126201ce8734978767d`; lines `102`; result `matched`; contains `'enable_dsa_cp'`.

### `flashcomm1_config_path`

- `source` `ascend_flashcomm1_additional_config` at `vllm_ascend:vllm_ascend/ascend_config.py`; blob `dfb4054259cd2770abee6d007b96c1cd8cf72c8a`; lines `83`; result `matched`; contains `self.enable_flashcomm1 = self._get_config_value(`.
- `source` `ascend_flashcomm1_runtime_gate` at `vllm_ascend:vllm_ascend/utils.py`; blob `f0ef65006efeb19f1aa5269e41267875e74060fd`; lines `1195`; result `matched`; contains `if not ascend_config.enable_flashcomm1:`.
- `documentation` `ascend_flashcomm1_config_doc` at `vllm_ascend:docs/source/user_guide/configuration/additional_config.md`; blob `4bee3872601a49b65bb25126201ce8734978767d`; lines `20,93`; result `matched`; contains `'enable_flashcomm1'`.

### `prefix_cache`

- `source` `vllm_prefix_cache_block_pool` at `vllm:vllm/v1/core/block_pool.py`; blob `513e4bf380b92e636315dbe3ae3c2666786e9ce2`; lines `159`; result `matched`; contains `self.enable_caching = enable_caching`.
- `source` `vllm_prefix_cache_store_event` at `vllm:vllm/v1/core/block_pool.py`; blob `513e4bf380b92e636315dbe3ae3c2666786e9ce2`; lines `316`; result `matched`; contains `BlockStored(`.
- `instrumentation` `vllm_prefix_cache_event_queue` at `vllm:vllm/v1/core/block_pool.py`; blob `513e4bf380b92e636315dbe3ae3c2666786e9ce2`; lines `315,393,485`; result `matched`; contains `self.kv_event_queue.append(`.
- `instrumentation` `vllm_prefix_cache_event_publish` at `vllm:vllm/v1/core/sched/scheduler.py`; blob `c69c9a8119ab71a06b3e894457706d95b1b261b9`; lines `1568`; result `matched`; contains `self.kv_event_publisher.publish(batch)`.

### `kv_cache_events`

- `source` `vllm_kv_events_config` at `vllm:vllm/config/kv_events.py`; blob `d618bc9a73f3ba8b8d0c952a00f0766d2a3f2f4f`; lines `11`; result `matched`; contains `class KVEventsConfig:`.
- `source` `vllm_kv_event_batch` at `vllm:vllm/distributed/kv_events.py`; blob `ee21185969f316a0b10d0348f8b31cc3dfd608ed`; lines `112`; result `matched`; contains `class KVEventBatch(`.
- `instrumentation` `vllm_kv_event_batch_build` at `vllm:vllm/v1/core/sched/scheduler.py`; blob `c69c9a8119ab71a06b3e894457706d95b1b261b9`; lines `1567`; result `matched`; contains `batch = KVEventBatch(`.
- `instrumentation` `vllm_kv_event_publisher` at `vllm:vllm/v1/core/sched/scheduler.py`; blob `c69c9a8119ab71a06b3e894457706d95b1b261b9`; lines `1568`; result `matched`; contains `self.kv_event_publisher.publish(batch)`.

### `kv_cache_cpu_offload`

- `source` `vllm_offloading_connector` at `vllm:vllm/distributed/kv_transfer/kv_connector/v1/offloading_connector.py`; blob `6c75bda0c4cf5393383919c086eb4c333f0812e8`; lines `46`; result `matched`; contains `class OffloadingConnector(`.
- `source` `ascend_npu_offloading_spec` at `vllm_ascend:vllm_ascend/kv_offload/npu.py`; blob `90816ce3abbc4143e8eb2ab1a081cab8d07c0b86`; lines `16`; result `matched`; contains `class NPUOffloadingSpec(`.
- `instrumentation` `vllm_offload_byte_metric` at `vllm:vllm/distributed/kv_transfer/kv_connector/v1/offloading/metrics.py`; blob `0839b2727ccc01b4b3cea9e1b69e08093fca81d2`; lines `106`; result `matched`; contains `name="vllm:kv_offload_total_bytes"`.
- `instrumentation` `vllm_offload_event_export` at `vllm:vllm/distributed/kv_transfer/kv_connector/v1/offloading_connector.py`; blob `6c75bda0c4cf5393383919c086eb4c333f0812e8`; lines `169`; result `matched`; contains `def take_events(self) -> Iterable[KVCacheEvent]:`.
- `documentation` `ascend_cpu_offload_doc` at `vllm_ascend:docs/source/user_guide/feature_guide/kv_cache_cpu_offload.md`; blob `974897e6f3e1ad57bd88a211993e5f859caa2d4a`; lines `7,29,58,70`; result `matched`; contains `NPUOffloadingSpec`.

### `ucm_store_connector`

- `source` `ascend_ucm_connector` at `vllm_ascend:vllm_ascend/distributed/kv_transfer/kv_pool/ucm_connector.py`; blob `de25ae934e89613994033c3ee495af3bd9828b60`; lines `37`; result `matched`; contains `class UCMConnectorV1(`.
- `source` `ascend_ucm_connector_registration` at `vllm_ascend:vllm_ascend/distributed/kv_transfer/__init__.py`; blob `e0beaadfb3db95335ef6ecbaa9c1ecbb7d156727`; lines `58`; result `matched`; contains `"UCMConnector", "vllm_ascend.distributed.kv_transfer.kv_pool.ucm_connector"`.
- `documentation` `ascend_ucm_deployment_doc` at `vllm_ascend:docs/source/user_guide/feature_guide/ucm_deployment.md`; blob `b244c9ad3c15977e423ed56f5b80befb5cee3087`; lines `1`; result `matched`; contains `# UCM Store Deployment Guide`.

### `kv_cache_pool`

- `source` `ascend_store_connector` at `vllm_ascend:vllm_ascend/distributed/kv_transfer/kv_pool/ascend_store/ascend_store_connector.py`; blob `72a31d8285129c264296095e274f706c3b4e7635`; lines `73`; result `matched`; contains `class AscendStoreConnector(`.
- `source` `ascend_store_mooncake_backend` at `vllm_ascend:vllm_ascend/distributed/kv_transfer/kv_pool/ascend_store/backend/mooncake_backend.py`; blob `4d6d937ea8582edf936f68595fb5216676ea3061`; lines `62`; result `matched`; contains `class MooncakeBackend(`.
- `instrumentation` `ascend_store_kv_events` at `vllm_ascend:vllm_ascend/distributed/kv_transfer/kv_pool/ascend_store/ascend_store_connector.py`; blob `72a31d8285129c264296095e274f706c3b4e7635`; lines `39`; result `matched`; contains `class AscendStoreKVEvents(`.
- `instrumentation` `ascend_store_take_events` at `vllm_ascend:vllm_ascend/distributed/kv_transfer/kv_pool/ascend_store/ascend_store_connector.py`; blob `72a31d8285129c264296095e274f706c3b4e7635`; lines `173`; result `matched`; contains `def take_events(self) -> Iterable["KVCacheEvent"]:`.
- `documentation` `ascend_kv_pool_doc` at `vllm_ascend:docs/source/user_guide/feature_guide/kv_pool.md`; blob `3ae80ff41159e5e89d90794c8823ba30562020dd`; lines `162,231,300,312,316,396,462,538,620,708,892,894,910`; result `matched`; contains `AscendStoreConnector`.

### `eplb_recording_static_map`

- `source` `ascend_eplb_static_map_load` at `vllm_ascend:vllm_ascend/eplb/core/eplb_utils.py`; blob `dc7bd5233893f6c898c515dc4459ac980290af5d`; lines `27`; result `matched`; contains `def expert_file_to_tensor(`.
- `source` `ascend_eplb_map_update` at `vllm_ascend:vllm_ascend/eplb/adaptor/vllm_adaptor.py`; blob `e625302f3c5b4e77d1ed18acb297e309853ca0b8`; lines `148`; result `matched`; contains `def do_update_expert_map(`.
- `instrumentation` `ascend_eplb_map_export` at `vllm_ascend:vllm_ascend/eplb/adaptor/vllm_adaptor.py`; blob `e625302f3c5b4e77d1ed18acb297e309853ca0b8`; lines `124`; result `matched`; contains `def _export_tensor_to_file(`.
- `instrumentation` `ascend_eplb_record_path` at `vllm_ascend:vllm_ascend/eplb/eplb_updator.py`; blob `5e999503002f5ebeef6df6f5c4f629b4fdf21472`; lines `55`; result `matched`; contains `self.expert_map_record_path = self.eplb_config.expert_map_record_path`.
- `documentation` `ascend_eplb_static_map_doc` at `vllm_ascend:docs/source/user_guide/feature_guide/eplb_swift_balancer.md`; blob `5cdc7941a2740a5537974f9741ab2b81672c5ec3`; lines `98`; result `matched`; contains `"expert_map_path"`.

### `expert_hotness_metrics`

- `source` `vllm_expert_load_window` at `vllm:vllm/distributed/eplb/eplb_state.py`; blob `319a5f22c9220b69f60dbf1e7047282dc633eab2`; lines `67,157,223,228,230,420,421,423,461,562,563,568,569,570,617,626,691,693,696,697,700,701,703,709,711,714,715,717,750,751,756,794,797`; result `matched`; contains `expert_load_window`.
- `source` `ascend_expert_heat_interval` at `vllm_ascend:vllm_ascend/eplb/eplb_updator.py`; blob `5e999503002f5ebeef6df6f5c4f629b4fdf21472`; lines `53,59,63,80,90,93,97`; result `matched`; contains `self.expert_heat_collection_interval`.
- `instrumentation` `vllm_expert_load_record` at `vllm:vllm/model_executor/layers/fused_moe/layer.py`; blob `776e86770ef1156ae22c67d7f2ce0f63979e3cfe`; lines `1277`; result `matched`; contains `record the load metrics in 'expert_load_view'`.
- `instrumentation` `vllm_expert_load_window_copy` at `vllm:vllm/distributed/eplb/eplb_state.py`; blob `319a5f22c9220b69f60dbf1e7047282dc633eab2`; lines `564`; result `matched`; contains `].copy_(eplb_model_state.expert_load_pass)`.
- `documentation` `ascend_expert_load_metric_doc` at `vllm_ascend:docs/source/user_guide/feature_guide/eplb_swift_balancer.md`; blob `5cdc7941a2740a5537974f9741ab2b81672c5ec3`; lines `118`; result `matched`; contains `expert_load_balance_ratio`.

### `weight_prefetch`

- `source` `ascend_weight_prefetch_config` at `vllm_ascend:vllm_ascend/ascend_config.py`; blob `dfb4054259cd2770abee6d007b96c1cd8cf72c8a`; lines `589`; result `matched`; contains `class WeightPrefetchConfig:`.
- `source` `ascend_weight_prefetch_method` at `vllm_ascend:vllm_ascend/ops/weight_prefetch.py`; blob `09a052cdc81e68a8d403164f9fe23b33be4b9f5a`; lines `37`; result `matched`; contains `class WeightPrefetchMethod:`.
- `source` `ascend_weight_prefetch_op` at `vllm_ascend:vllm_ascend/ops/weight_prefetch.py`; blob `09a052cdc81e68a8d403164f9fe23b33be4b9f5a`; lines `80,101,150,160,203`; result `matched`; contains `torch.ops.vllm.prefetch_preprocess(`.
- `documentation` `ascend_weight_prefetch_doc` at `vllm_ascend:docs/source/user_guide/feature_guide/weight_prefetch.md`; blob `4610486d4e0f00e3cbc3ea1bdcd9d91ef217db7b`; lines `1`; result `matched`; contains `# Weight Prefetch`.

## Boundary

This report proves only that exact source/config/instrumentation symbols exist at the pinned Git objects. It does not import or run either runtime, does not validate the selected workload, and does not authorize a real VllmAscendAdapter.
