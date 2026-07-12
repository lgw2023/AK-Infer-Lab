# Developer to Server

## 当前唯一任务：建立服务器本地代码 worktree 与冲突报告机制

任务 ID：

```text
server_local_git_worktree_policy_setup_2026_0712
```

本任务不使用 NPU，不运行模型，不修改 vLLM/vLLM-Ascend/conda/CANN。

目标是建立两个永久隔离的 Git 真值面：

```text
/data/node0_disk1/liguowei/AK-Infer-Lab
  -> 外部开发者的 origin/main 主镜像，只拉取

/data/node0_disk1/liguowei/AK-Infer-Lab-server-local
  -> 服务器本地代码版本，本地分支 server-local/runtime-adaptations
```

## 绝对禁止

- 禁止对任何 remote 执行 `git push`，包括新分支、tag、force push 或删除 remote ref。
- 禁止在主镜像 `main` 中编写或保留服务器项目代码。
- 禁止把 server-local 分支 merge/cherry-pick/rebase 到主镜像 `main`。
- 禁止在发现冲突时自动选择 ours/theirs，禁止为规避冲突而删除或 reset 外部开发者代码。
- 禁止修改 Git remote URL、push URL 或全局/系统 Git 配置。
- 禁止执行任何含有 push 的测试、脚本或演练。

## 1. 保护现有服务器改动

先进入主镜像，只检查 tracked 改动：

```bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
LOCAL_WORKTREE=/data/node0_disk1/liguowei/AK-Infer-Lab-server-local
LOCAL_BRANCH=server-local/runtime-adaptations
TASK_ID=server_local_git_worktree_policy_setup_2026_0712
RESULT_DIR="${REPO_ROOT}/server_local/${TASK_ID}"

mkdir -p "${RESULT_DIR}"
cd "${REPO_ROOT}"

git status --porcelain --untracked-files=no > "${RESULT_DIR}/mirror_tracked_status_before.txt"
git status --porcelain --ignored > "${RESULT_DIR}/mirror_full_status_before.txt"
git rev-parse HEAD > "${RESULT_DIR}/mirror_head_before.txt"
git rev-parse origin/main > "${RESULT_DIR}/origin_main_before.txt"
```

判定：

- `mirror_tracked_status_before.txt` 非空：立即停止。不执行 `git pull-remote`、reset、stash、commit 或迁移；只报告变更路径，等待外部开发者决定如何保留。
- 只有 ignored/untracked server-local 产物而 tracked 状态为空：允许继续。

## 2. 完整同步外部 `main`

仅当上一节 tracked 状态为空时：

```bash
if [ -x "${REPO_ROOT}/server_local/git_pull_remote_wins.sh" ]; then
  "${REPO_ROOT}/server_local/git_pull_remote_wins.sh"
else
  git fetch origin main
  git merge --ff-only origin/main
fi
```

同步后必须重新打开拉取后的本文档，确认任务 ID 仍为：

```text
server_local_git_worktree_policy_setup_2026_0712
```

然后记录：

```bash
git rev-parse HEAD > "${RESULT_DIR}/mirror_head_after_pull.txt"
git rev-parse origin/main > "${RESULT_DIR}/origin_main_after_pull.txt"
git status --porcelain --untracked-files=no > "${RESULT_DIR}/mirror_tracked_status_after_pull.txt"
```

`mirror_head_after_pull.txt` 必须与 `origin_main_after_pull.txt` 一致，tracked status 必须为空。

## 3. 校验并初始化独立 server-local worktree

先做静态安全检查，不运行仓库中任何含 push 的测试：

```bash
bash -n "${REPO_ROOT}/通信模块/server_local_git_sync.sh"

if grep -nE '(^|[[:space:]])git[[:space:]]+push([[:space:]]|$)' \
  "${REPO_ROOT}/通信模块/server_local_git_sync.sh"; then
  echo "forbidden git push command found" >&2
  exit 1
fi
```

初始化：

```bash
set +e
AK_SERVER_MIRROR_ROOT="${REPO_ROOT}" \
AK_SERVER_LOCAL_WORKTREE="${LOCAL_WORKTREE}" \
AK_SERVER_LOCAL_BRANCH="${LOCAL_BRANCH}" \
bash "${REPO_ROOT}/通信模块/server_local_git_sync.sh" init \
  > "${RESULT_DIR}/init_stdout.txt" \
  2> "${RESULT_DIR}/init_stderr.txt"
INIT_EXIT_CODE=$?
set -e
printf '%s\n' "${INIT_EXIT_CODE}" > "${RESULT_DIR}/init_exit_code.txt"
```

- `0`：worktree 已创建或已正确存在，当前与 `origin/main` 无真实冲突。
- `2`：本地分支已存在且与最新 `origin/main` 有真实冲突；脚本已停止，不得合并。
- `4`：没有真实 merge conflict，但双方修改了同一路径；必须先报告外部开发者，本轮不得合并。
- 其他非零：安装或安全门失败，不得手工绕过。

## 4. 只读核验

不创建任何测试提交，不做冲突演练：

```bash
git worktree list --porcelain > "${RESULT_DIR}/worktree_list.txt"
git -C "${LOCAL_WORKTREE}" branch --show-current > "${RESULT_DIR}/local_branch.txt"
git -C "${LOCAL_WORKTREE}" rev-parse HEAD > "${RESULT_DIR}/local_head.txt"
git -C "${LOCAL_WORKTREE}" status --porcelain > "${RESULT_DIR}/local_status.txt"
git ls-remote --heads origin 'server-local/*' > "${RESULT_DIR}/remote_server_local_refs.txt"
```

验收条件：

```text
local_branch == server-local/runtime-adaptations
local_status is empty
remote_server_local_refs is empty
main mirror HEAD == origin/main
```

从 `init_stdout.txt` 中取得 `REPORT_DIR=...`，将该目录路径写入：

```bash
sed -n 's/^REPORT_DIR=//p' "${RESULT_DIR}/init_stdout.txt" \
  > "${RESULT_DIR}/git_sync_report_dir.txt"
```

检查该 report 中的：

```text
summary.tsv
server_local_changed_paths.txt
upstream_changed_paths.txt
same_path_overlap.txt
conflict_paths.txt
merge_tree.txt
```

## 5. 后续永久操作规则

1. 外部开发任务仍从主镜像拉取。
2. 需要服务器本地代码时，只在 `AK-Infer-Lab-server-local` 中修改并本地 commit。
3. 每次合入新 `origin/main` 前先运行 `server_local_git_sync.sh check`。
4. same-path overlap 非空时，即使 `merge-tree` clean，也先向外部开发者报告 YELLOW 风险。
5. 真实冲突时禁止运行 `sync`，禁止自行解决；报告后等待外部决策。
6. 只有 no-conflict 且外部开发者审核了 same-path overlap 后，才可在后续任务的单次命令中显式设置 `AK_SERVER_ALLOW_SAME_PATH_OVERLAP=1` 并执行 `server_local_git_sync.sh sync`；不允许把该变量写入持久环境。
7. 任何时候都不 push。

## 6. 结果摘要与候选文件

在 `${RESULT_DIR}/result_summary.md` 中记录：

- 任务 ID、时间和执行主机；
- 主镜像 pull 前后 HEAD 和 `origin/main`；
- tracked dirty gate 是否通过；
- init exit code；
- server-local worktree、branch、HEAD 和 clean 状态；
- merge base、same-path overlap 列表、conflict path 列表和 `merge-tree` 退出码；
- remote `server-local/*` refs 是否为空；
- 明确声明“本轮未执行任何 git push”；
- 若失败，记录首个失败阶段，不绕过。

候选文件限于：

```text
result_summary.md
init_exit_code.txt
init_stdout.txt
init_stderr.txt
worktree_list.txt
local_branch.txt
local_head.txt
local_status.txt
remote_server_local_refs.txt
git_sync_report_dir.txt
<git_sync_report_dir>/summary.tsv
<git_sync_report_dir>/server_local_changed_paths.txt
<git_sync_report_dir>/upstream_changed_paths.txt
<git_sync_report_dir>/same_path_overlap.txt
<git_sync_report_dir>/conflict_paths.txt
<git_sync_report_dir>/merge_tree.txt
```

原始 full status 中如果包含不宜外传的服务器路径，只在摘要中报告计数和有界脱敏路径。

本轮是新结果范围，尚未获得 `email`、`upload-api` 或 `server-local` 选择。文件生成后，只在当前任务会话报告每个候选的精确路径、bytes、SHA-256、敏感性、可用方式和一个推荐方式，然后暂停。禁止在未确认前发邮件、上传或执行任何外发预检。
