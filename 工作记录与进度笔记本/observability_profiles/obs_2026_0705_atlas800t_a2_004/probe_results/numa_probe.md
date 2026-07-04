# numa_probe

```yaml
tool: numa_probe
available: false
permission_status: blocked
command:
- numactl
- --hardware
exit_code: 127
start_time: '2026-07-04T18:26:07.159588+00:00'
end_time: '2026-07-04T18:26:07.160690+00:00'
runtime_ms: 1.103
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
