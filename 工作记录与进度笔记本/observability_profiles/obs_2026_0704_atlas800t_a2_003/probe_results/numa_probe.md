# numa_probe

```yaml
tool: numa_probe
available: false
permission_status: blocked
command:
- numactl
- --hardware
exit_code: 127
start_time: '2026-07-04T17:37:17.070110+00:00'
end_time: '2026-07-04T17:37:17.071313+00:00'
runtime_ms: 1.205
run_as_user: root
inside_container: false
container_privileged: null
effective_user_is_root: true
output_excerpt: '[Errno 2] No such file or directory: ''numactl'''
artifact_path: probe_results/numa_probe.md
maps_to_fields:
- server_observability_profile.numa_available
blocked_reason:
  category: tool_missing
  detail: '[Errno 2] No such file or directory: ''numactl'''
```
