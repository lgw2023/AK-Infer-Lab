# P1.31 server feedback archive

Run id: `runtime_vllm_api_prefix_ratio_long_context_matrix_2026_0709_p1_031`

Server artifact root:

```text
/data/node0_disk1/liguowei/AK-Infer-Lab/工作记录与进度笔记本/runtime_trace_smokes/runtime_vllm_api_prefix_ratio_long_context_matrix_2026_0709_p1_031
```

This directory archives the 20 downloaded server email Markdown files and the small attachments from `/Users/liguowei/Downloads/`.

Download note:

- Several on/off attachments used the same local file names, including `request_summary.tsv`, `server_stats_summary.tsv`, `phase_memory_summary.tsv`, and `result.json`.
- The first manual download overwrote some same-name files in `/Users/liguowei/Downloads/`.
- The user then re-downloaded the important attachments with unique names that include the mail title and attachment name.
- Those unique-name attachments are archived under `matrix_summary/`, `prefix_cache_on/`, and `prefix_cache_off/`.
- The `downloaded_singletons/` directory keeps the earlier overwritten-name local copies only as process evidence; prefer the mode-specific files.
- The prefix-cache on `server_stats_summary.tsv` attachment has blank mode/cell label columns, but its stats values are preserved; use `matrix_summary/prefix_ratio_matrix_delta_summary.tsv` for cell-labeled hit-rate and KV-cache proxy facts.
- The complete raw server artifact tree remains on the server at the path above and is indexed by `artifact_index/mail_artifact_index.tsv`.

Acceptance note:

- One measured request in `cap8192_prefix60` generated `1023` of the target `1024` tokens.
- Per user direction and the server acceptance policy, this is treated as a successful sample for matrix statistics.
- This run still does not make compute-bound, memory-bound, HBM bottleneck, scheduler-bound, or prefix-cache benefit attribution claims.
