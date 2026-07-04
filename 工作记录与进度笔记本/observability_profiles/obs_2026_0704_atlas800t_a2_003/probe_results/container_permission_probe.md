# container_permission_probe

```yaml
tool: container_permission_probe
available: true
permission_status: ok
command:
- bash
- -lc
- id && test -r /proc/1/cgroup && head -5 /proc/1/cgroup
exit_code: 0
start_time: '2026-07-04T17:37:17.071476+00:00'
end_time: '2026-07-04T17:37:17.253056+00:00'
runtime_ms: 181.598
run_as_user: root
inside_container: false
container_privileged: null
effective_user_is_root: true
output_excerpt: 'uid=0(root) gid=0(root) groups=0(root),3000(shareddata)

  0::/init.scope'
artifact_path: probe_results/container_permission_probe.md
maps_to_fields:
- server_observability_profile.container_cgroup_readable
blocked_reason:
  category: null
  detail: null
```
