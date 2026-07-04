# perf_probe

```yaml
tool: perf_probe
available: false
permission_status: blocked
command:
- perf
- --version
exit_code: 127
start_time: '2026-07-04T17:37:16.889307+00:00'
end_time: '2026-07-04T17:37:16.890738+00:00'
runtime_ms: 1.434
run_as_user: root
inside_container: false
container_privileged: null
effective_user_is_root: true
output_excerpt: '[Errno 2] No such file or directory: ''perf'''
artifact_path: probe_results/perf_probe.md
maps_to_fields:
- server_observability_profile.perf_available
blocked_reason:
  category: tool_missing
  detail: '[Errno 2] No such file or directory: ''perf'''
```
