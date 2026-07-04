# cann_profiler_probe

```yaml
tool: cann_profiler_probe
available: true
permission_status: ok
command:
- bash
- -lc
- command -v msprof >/dev/null 2>&1 || exit 127; msprof --help | head -40
exit_code: 0
start_time: '2026-07-04T17:37:16.684612+00:00'
end_time: '2026-07-04T17:37:16.888964+00:00'
runtime_ms: 204.374
run_as_user: root
inside_container: false
container_privileged: null
effective_user_is_root: true
output_excerpt: "Usage:\n      msprof [--options]\n\nThis is subcommand for operator\
  \ optimization situation:\n      op                                Use binary msopprof\
  \ to operator optimization (msprof op ...)\n\nOptions:\n      --output         \
  \                 <Optional> Specify the directory that is used for storing data\
  \ results.\n      --application                     <Optional> Specify application\
  \ path, considering the risk of privilege escalation, please pay attention to\n\t\
  \t\t\t\t\t   the group of the application and confirm whether it is the same as\
  \ the user currently.\n\t\t\t\t\t\t   [Note] This option will be discarded in later\
  \ versions.\n\t\t\t\t\t\t   you can try to use: msprof [msprof arguments] <app>\
  \ [app arguments]\n      --ascendcl                        <Optional> Show acl profiling\
  \ data, the default value is on.\n      --ge-api                          <Optional>\
  \ Specify if report GE event, the default value is off. The possible parameters\
  \ are 'l0', 'l1' or 'off'.\n      --runtime-api                     <Optional> Show\
  \ runtime api profiling data, the default value is off.\n      --task-time     \
  \                  <Optional> Show task profiling data, the default value is on.\
  \ The possible parameters are 'l0', 'l1', 'l2', 'on' or 'off'.\n      --task-memory\
  \                     <Optional> Show the memory usage of the operator, the default\
  \ value is off. The possible parameters are 'on' or 'off'.\n      --ai-core    \
  \                     <Optional> Turn on / off the ai core profiling, the default\
  \ value is on when collecting app Profiling.\n      --aic-mode                 \
  \       <Optional> Set the aic profiling mode to task-based or sample-based.\n\t\
  \t\t\t\t\t   In task-based mode, profiling data will be collected by tasks.\n\t\t\
  \t\t\t\t   In sample-based mode, profiling data will be collected in a specific\
  \ interval.\n\t\t\t\t\t\t   The default value is task-based in AI task mode, sample-based\
  \ in system mode.\n      --aic-freq                        <Optional> The aic sampling\
  \ frequency in hertz, the default value is 100 Hz, the range is 1 to 100 Hz.\n \
  \     --environment                     <Optional> User app custom environment variable\
  \ configuration.\n      --sys-period                      <Optional> Set total sampling\
  \ period of system profiling in seconds.\n      --sys-devices                  \
  \   <Optional> Specify the profiling scope by device ID when collect sys profiling.The\
  \ value is all or ID list (split with ',').\n      --hccl                      \
  \      <Optional> Show hccl profiling data, the default value is off. [Note] This\
  \ option will be discarded in later versions.\n      --msproftx                \
  \        <Optional> Show msproftx and mstx data, the default value is off.\n   \
  \   --mstx-domain-include             <Optional> Choose to only include mstx events\
  \ from a comma separated list of domains;\n\t\t\t\t\t\t   `default` filters the\
  \ mstx default domain;\n\t\t\t\t\t\t   The switch is only applicable when parameter\
  \ msproftx is set to on;\n\t\t\t\t\t\t   The switch cannot be set with mstx-domain-exclude\
  \ at the same time.\n      --mstx-domain-exclude             <Optional> Choose to\
  \ exclude mstx events from a comma separated list of domains;\n\t\t\t\t\t\t   `default`\
  \ excludes the mstx default domain;\n\t\t\t\t\t\t   The switch is only applicable\
  \ when parameter msproftx is set to on;\n\t\t\t\t\t\t   The switch cannot be set\
  \ with mstx-domain-include at the same time.\n      --storage-limit            \
  \       <Optional> Specify the output directory volume. range 200MB ~ 4294967295MB.\n\
  \      --model-execution                 <Optional> Show ge model execution profiling\
  \ data, the default value is off. [Note] This option will be discarded in later\
  \ versions.\n      --aic-metrics                     <Optional> The aic metrics\
  \ groups, include ArithmeticUtilization, PipeUtilization, Memory, MemoryL0, ResourceConflictRatio,\
  \ MemoryUB, L2Cache, MemoryAccess."
artifact_path: probe_results/cann_profiler_probe.md
maps_to_fields:
- server_observability_profile.cann_profiler_available
blocked_reason:
  category: null
  detail: null
```
