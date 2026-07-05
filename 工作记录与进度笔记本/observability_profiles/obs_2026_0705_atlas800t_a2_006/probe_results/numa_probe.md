# numa_probe

```yaml
tool: numa_probe
available: true
permission_status: ok
command:
- numactl
- --hardware
exit_code: 0
start_time: '2026-07-05T10:15:21.383762+00:00'
end_time: '2026-07-05T10:15:21.386515+00:00'
runtime_ms: 2.755
run_as_user: root
inside_container: false
container_privileged: null
effective_user_is_root: true
output_excerpt: "available: 8 nodes (0-7)\nnode 0 cpus: 0 1 2 3 4 5 6 7 8 9 10 11\
  \ 12 13 14 15 16 17 18 19 20 21 22 23\nnode 0 size: 193050 MB\nnode 0 free: 38779\
  \ MB\nnode 1 cpus: 24 25 26 27 28 29 30 31 32 33 34 35 36 37 38 39 40 41 42 43 44\
  \ 45 46 47\nnode 1 size: 193533 MB\nnode 1 free: 167153 MB\nnode 2 cpus: 48 49 50\
  \ 51 52 53 54 55 56 57 58 59 60 61 62 63 64 65 66 67 68 69 70 71\nnode 2 size: 193533\
  \ MB\nnode 2 free: 11972 MB\nnode 3 cpus: 72 73 74 75 76 77 78 79 80 81 82 83 84\
  \ 85 86 87 88 89 90 91 92 93 94 95\nnode 3 size: 193533 MB\nnode 3 free: 167984\
  \ MB\nnode 4 cpus: 96 97 98 99 100 101 102 103 104 105 106 107 108 109 110 111 112\
  \ 113 114 115 116 117 118 119\nnode 4 size: 193496 MB\nnode 4 free: 81199 MB\nnode\
  \ 5 cpus: 120 121 122 123 124 125 126 127 128 129 130 131 132 133 134 135 136 137\
  \ 138 139 140 141 142 143\nnode 5 size: 193533 MB\nnode 5 free: 164867 MB\nnode\
  \ 6 cpus: 144 145 146 147 148 149 150 151 152 153 154 155 156 157 158 159 160 161\
  \ 162 163 164 165 166 167\nnode 6 size: 193533 MB\nnode 6 free: 153147 MB\nnode\
  \ 7 cpus: 168 169 170 171 172 173 174 175 176 177 178 179 180 181 182 183 184 185\
  \ 186 187 188 189 190 191\nnode 7 size: 188402 MB\nnode 7 free: 135442 MB\nnode\
  \ distances:\nnode   0   1   2   3   4   5   6   7 \n  0:  10  11  24  25  24  25\
  \  24  25 \n  1:  11  10  25  32  25  32  25  32 \n  2:  24  25  10  11  24  25\
  \  24  25 \n  3:  25  32  11  10  25  32  25  32 \n  4:  24  25  24  25  10  11\
  \  24  25 \n  5:  25  32  25  32  11  10  25  32 \n  6:  24  25  24  25  24  25\
  \  10  11 \n  7:  25  32  25  32  25  32  11  10"
artifact_path: probe_results/numa_probe.md
maps_to_fields:
- server_observability_profile.numa_available
blocked_reason:
  category: null
  detail: null
```
