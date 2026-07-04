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
start_time: '2026-07-04T18:26:06.979035+00:00'
end_time: '2026-07-04T18:26:07.157956+00:00'
runtime_ms: 178.936
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
