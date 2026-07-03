# 开发机 → 服务器消息

服务器通过 `git pull` 获取本文件内容。开发人员可按下面模板追加消息。

## 消息模板

```markdown
### YYYY-MM-DD HH:MM 开发机消息

- 任务/请求：
- 需要服务器执行的命令或检查：
- 输入文件/参数：
- 期望服务器通过邮件返回的信息：
- 优先级：普通/紧急
```

## 当前待处理消息

### 2026-07-03 15:43 开发机消息

- 任务/请求：
  - 请在昇腾服务器上执行一次 AK-Infer-Lab 服务器可观测能力体检，生成正式的 `observability_profiles/<run>/` 结果。
  - 这次 run 的目的不是判断模型性能优劣，而是确认 Atlas/CANN/NPU/CPU/DRAM/SSD/profiler 等字段在真实服务器环境里哪些可采、哪些被权限或工具阻塞。
- 执行前约束：
  - 服务器只执行 `git pull` 获取本任务文档和代码，不从服务器 push。
  - 不修改仓库内项目代码。
  - 不提交 `.env`、SMTP 授权码、服务器账号、私钥、Cookie 或任何敏感信息。
  - 如命令或代码在服务器上失败，请通过邮件回传失败阶段、命令、错误摘要和日志路径，不要直接在服务器上改代码。
- 需要服务器执行的命令或检查：
  1. 同步仓库并进入项目根目录：

     ```bash
     cd <AK-Infer-Lab 项目根目录>
     git pull
     ```

  2. 确认可观测体检 CLI 可用：

     ```bash
     python -m tools.observability_profile.cli collect --help
     ```

  3. 准备 SSD/fio scratch 目录。请使用服务器上可写、空间充足、允许临时 I/O 的路径；如果 `/data/ak-trace/observability_scratch` 不合适，请替换成服务器实际 scratch 路径：

     ```bash
     mkdir -p /data/ak-trace/observability_scratch
     ```

  4. 执行正式体检。若当前服务器不适合跑 microbench，请先去掉 `--include-microbench` 和 `--scratch-dir ...` 跑一版只读体检，并在邮件里说明原因。

     ```bash
     python -m tools.observability_profile.cli collect \
       --server-id atlas800t-a2-node-001 \
       --operator ascend-server \
       --run-id obs_2026_0703_atlas800t_a2_001 \
       --include-microbench \
       --scratch-dir /data/ak-trace/observability_scratch \
       --copy-sizes 4K,16K,64K,1M,16M,256M,1G \
       --fio-qdepth 1,4,16,32 \
       --microbench-duration 10
     ```

  5. 检查输出目录是否存在：

     ```bash
     ls -lah 工作记录与进度笔记本/observability_profiles/obs_2026_0703_atlas800t_a2_001
     ```

- 输入文件/参数：
  - 代码入口：`tools/observability_profile/cli.py`
  - 默认输出目录：`工作记录与进度笔记本/observability_profiles/obs_2026_0703_atlas800t_a2_001/`
  - 建议 scratch 目录：`/data/ak-trace/observability_scratch`
  - 目标服务器标识：`atlas800t-a2-node-001`
- 期望服务器通过邮件返回的信息：
  - 邮件主题建议：`[AK服务器] 任务完成：observability profile obs_2026_0703_atlas800t_a2_001` 或 `[AK服务器] 运行失败：observability profile obs_2026_0703_atlas800t_a2_001`
  - 邮件正文请包含：
    - 执行主机名与时间。
    - 实际执行的完整命令。
    - 是否启用了 `--include-microbench`；如果未启用，请说明原因。
    - 输出目录绝对路径。
    - `manifest.yaml` 中的 `hardware_topology_hash`、`software_stack_hash`、`cann_version`、`npu_count`、`hbm_per_npu_gb`。
    - `field_availability.yaml` 中 measurable / partial / blocked / unknown / not_applicable 的数量汇总。
    - 关键 blocked reason，尤其是 `npu-smi`、`msprof`、`perf`、`fio`、`numactl`、容器权限相关阻塞。
    - `p0_acceptance_fields.yaml` 中可进入 P0 硬验收的字段数量。
    - 如失败，提供失败阶段、错误摘要和日志路径。
  - 邮件附件建议：
    - `server_observability_profile.md`
    - `manifest.yaml`
    - `field_availability.yaml`
    - `join_key_readiness.yaml`
    - `p0_acceptance_fields.yaml`
    - 如文件过大，只附摘要文件，并在正文写明完整输出目录。
- 优先级：普通
