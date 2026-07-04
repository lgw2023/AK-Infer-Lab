# fio_probe

```yaml
tool: fio_probe
available: false
permission_status: blocked
command:
- fio
- --version
exit_code: 127
start_time: '2026-07-04T18:26:07.158208+00:00'
end_time: '2026-07-04T18:26:07.159434+00:00'
runtime_ms: 1.227
run_as_user: root
inside_container: false
container_privileged: null
effective_user_is_root: true
output_excerpt: '[Errno 2] No such file or directory: ''fio'''
artifact_path: probe_results/fio_probe.md
maps_to_fields:
- server_observability_profile.fio_available
blocked_reason:
  category: tool_missing
  detail: '[Errno 2] No such file or directory: ''fio'''
```
