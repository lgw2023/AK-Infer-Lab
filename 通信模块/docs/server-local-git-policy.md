# 服务器本地代码版本与外部 `main` 同步策略

本策略适用于 Ascend 服务器需要保留只在真实服务器环境中有意义的代码、补丁或运维辅助时。

## 所有权与边界

- 远程 `origin/main` 只由外部开发者维护。
- 服务器只允许 fetch/pull，任何分支都禁止从服务器 push。
- 主镜像工作区 `/data/node0_disk1/liguowei/AK-Infer-Lab` 只跟踪 `origin/main`，不承载服务器代码开发。
- 服务器代码固定放在独立 worktree `/data/node0_disk1/liguowei/AK-Infer-Lab-server-local`，分支固定为 `server-local/runtime-adaptations`。
- 服务器本地分支可以 commit，但不得合并回主镜像 `main`，不得创建任何远程 `server-local/*` ref。
- 服务器主镜像的 tracked 文件全部只读；这包括 `工作记录与进度笔记本/`、`通信模块/docs/`、源码、测试和契约。服务器不得向这些文件追加执行记录。
- 服务器任务的过程证据和结果只写入主镜像中 Git 忽略的 `server_local/<task_id>/`；外部开发机在收到结果后负责更新受跟踪的项目工作记录。

## 工作区模型

```text
origin/main
    |
    v
AK-Infer-Lab                    clean mirror, external main
    |
    | fetch + conflict precheck + local-only merge
    v
AK-Infer-Lab-server-local       server-local/runtime-adaptations
```

主镜像中原有的 `server_local/`、`.conda/` 和实验产物仍是 Git 忽略的服务器资产；它们不是“服务器代码版本”。需要持续维护的项目代码必须在 server-local worktree 中形成本地 commit，不能长期留在 dirty working tree。

对用户和外部开发者而言，任务派发入口始终只有主镜像中的 `通信模块/docs/developer-to-server.md`。服务器同步并重新打开该文档后，再根据文档的 `execution_codebase` 执行：

- `main-readonly`：从主镜像读取代码和任务，不改写任何 tracked 文件；结果写入 `server_local/<task_id>/`。
- `server-local`：任务明确需要服务器专属代码改动时，才进入 `AK-Infer-Lab-server-local` 修改并本地 commit；任务仍从主镜像交接文档派发。

如果交接文档没有显式声明 `execution_codebase`，按 `main-readonly` 处理。

## 可执行入口

从主镜像运行：

```bash
bash 通信模块/server_local_git_sync.sh init
bash 通信模块/server_local_git_sync.sh check
bash 通信模块/server_local_git_sync.sh sync
```

- `init`：只在主镜像无 tracked 修改时创建本地分支与独立 worktree，然后执行首次冲突检查。
- `check`：fetch 最新 `origin/main`，但不改写任何 worktree；使用服务器 Git 2.54 的 `merge-tree --write-tree` 接口，生成双方变更路径、同路径重叠与真实冲突报告。
- `sync`：只在 `check` 为 clean 时把 `origin/main` merge 到 server-local 分支；不向反方合并，不 push。同路径重叠时默认返回 `4` 并停止；只有外部开发者审核后，才能在当次命令显式设置 `AK_SERVER_ALLOW_SAME_PATH_OVERLAP=1`。

脚本拒绝把 `main`/`master` 当作本地分支，拒绝主镜像和 server-local worktree 共用同一路径，并在 server-local worktree 存在未提交改动时停止同步。

## 冲突与重叠处理

每次检查都在主镜像的忽略目录下生成：

```text
server_local/git_sync_reports/<timestamp>_<pid>/
  summary.tsv
  server_local_changed_paths.txt
  upstream_changed_paths.txt
  same_path_overlap.txt
  conflict_paths.txt
  merge_tree.txt
```

处理规则：

1. `same_path_overlap.txt` 非空代表双方修改了同一路径，检查状态为 `overlap_review_required`，必须作为 YELLOW 风险告知外部开发者，即使 Git 可自动合并。未获得外部开发者当次授权时，`sync` 必须返回 `4` 且不 merge。
2. `merge_tree_exit_code=1` 且 `conflict_paths.txt` 非空代表真实冲突，返回 `2`；脚本必须停止，不得执行 merge，不得自动选择 ours/theirs。
3. `merge_tree_exit_code` 为 `1` 以外的非零值代表预检工具本身失败，不得误报为代码冲突；状态为 `check_error`、返回 `5` 并停止。若预检通过但实际 merge 意外失败，脚本必须 abort 并返回 `3`。
4. 服务器应向外部开发者报告 `server_local_head`、`upstream_head`、`merge_base`、`merge_tree_mode`、双方 changed paths、same-path overlap、conflict paths 和 `merge_tree.txt` 的有界摘录，等待决策。
5. 不允许服务器 AI 自行解决冲突，也不允许为规避冲突而改写、删除或 reset 外部开发者的提交。

## 服务器本地提交记录

每个 server-local commit 的说明至少包含：

```text
upstream_base=<origin/main commit>
purpose=<why this only exists on the server>
scope=<changed paths>
verification=<tests or runtime check>
server_only_reason=<environment/runtime dependency>
```

外部开发者默认不获取这些代码。如果后续判定某个本地实现应吸收回远程项目，服务器只先报告变更范围和冲突状态；是否取回 patch 或由外部重新实现，由外部开发者决定。
