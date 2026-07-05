# ebpf_probe

```yaml
tool: ebpf_probe
available: false
permission_status: blocked
command:
- bash
- -lc
- command -v bpftrace >/dev/null 2>&1 || exit 127; bpftrace --version
exit_code: 127
start_time: '2026-07-04T19:17:51.808907+00:00'
end_time: '2026-07-04T19:17:51.989078+00:00'
runtime_ms: 180.176
run_as_user: root
inside_container: false
container_privileged: null
effective_user_is_root: true
output_excerpt: ''
artifact_path: probe_results/ebpf_probe.md
maps_to_fields:
- server_observability_profile.ebpf_available
blocked_reason:
  category: tool_missing
  detail: probe command is not available
```
