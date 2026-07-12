# Developer to Server

## 当前唯一任务：恢复主镜像并完成 server-local worktree 初始化

```text
task_id: server_local_git_worktree_policy_recover_2026_0712
execution_codebase: main-readonly
```

本任务不使用 NPU，不运行模型，不修改 vLLM/vLLM-Ascend/conda/CANN。

上轮已在 tracked dirty gate 正确停止。外部开发者已收到完整 patch，并确认唯一 tracked 改动是服务器追加的 P5 no-MTP YELLOW 工作记录；对应结果已在外部 `main` 的第 133 条固化，不需要保留服务器的重复追加。

## 永久边界

- 用户和外部开发者始终只通过主镜像 `AK-Infer-Lab` 中的本文档派发任务。
- 主镜像 tracked 文件全部只读。服务器不得修改受 Git 跟踪的工作记录，也不得向 `工作记录与进度笔记本/` 追加任务结果。
- 服务器过程证据和结果只写入 Git 忽略的 `server_local/<task_id>/`；收到回传后，受跟踪的项目工作记录由外部开发者更新。
- 需要服务器专属代码时，只在 `/data/node0_disk1/liguowei/AK-Infer-Lab-server-local` 修改并本地 commit。
- 禁止对任何 remote 执行 `git push`，包括新分支、tag、force push 或删除 remote ref。

## 1. 精确验证当前唯一 dirty 改动

在主镜像执行：

```bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
LOCAL_WORKTREE=/data/node0_disk1/liguowei/AK-Infer-Lab-server-local
LOCAL_BRANCH=server-local/runtime-adaptations
TASK_ID=server_local_git_worktree_policy_recover_2026_0712
RESULT_DIR="${REPO_ROOT}/server_local/${TASK_ID}"
NOTE_PATH='工作记录与进度笔记本/01_工作记录.md'
EXPECTED_DIRTY_SHA=21afc388efd88374ac3c78d82551b7f9c74498913fd7dbffee73a9f5278f4110

mkdir -p "${RESULT_DIR}"
cd "${REPO_ROOT}"

git status --porcelain --untracked-files=no > "${RESULT_DIR}/mirror_tracked_status_before.txt"
git diff --cached --quiet
test "$(git -c core.quotePath=false diff --name-only | wc -l | tr -d ' ')" = 1
test "$(git -c core.quotePath=false diff --name-only)" = "${NOTE_PATH}"
test "$(git -c core.quotePath=false diff --numstat -- "${NOTE_PATH}" | cut -f1-2)" = $'1\t0'
test "$(sha256sum "${NOTE_PATH}" | awk '{print $1}')" = "${EXPECTED_DIRTY_SHA}"
git diff -- "${NOTE_PATH}" > "${RESULT_DIR}/authorized_note_restore.patch"
```

任何一条校验失败，立即停止：不 restore、不 stash、不 reset、不 pull，只报告实际 tracked 改动。

## 2. 仅恢复已审核的单个笔记文件

上述全部校验通过后，外部开发者明确授权本次精确恢复：

```bash
git restore --worktree -- "${NOTE_PATH}"
git status --porcelain --untracked-files=no > "${RESULT_DIR}/mirror_tracked_status_after_restore.txt"
test ! -s "${RESULT_DIR}/mirror_tracked_status_after_restore.txt"
```

该授权只适用于上述路径、当前 SHA-256 和 `1 insertion / 0 deletion` 的已回传内容，不授权恢复任何其他文件。

## 3. 同步最新外部 `main`

```bash
if [ -x "${REPO_ROOT}/server_local/git_pull_remote_wins.sh" ]; then
  "${REPO_ROOT}/server_local/git_pull_remote_wins.sh"
else
  git fetch origin main
  git merge --ff-only origin/main
fi

git rev-parse HEAD > "${RESULT_DIR}/mirror_head_after_pull.txt"
git rev-parse origin/main > "${RESULT_DIR}/origin_main_after_pull.txt"
git status --porcelain --untracked-files=no > "${RESULT_DIR}/mirror_tracked_status_after_pull.txt"
cmp -s "${RESULT_DIR}/mirror_head_after_pull.txt" "${RESULT_DIR}/origin_main_after_pull.txt"
test ! -s "${RESULT_DIR}/mirror_tracked_status_after_pull.txt"
```

同步后必须重新打开拉取后的 `通信模块/docs/developer-to-server.md`，确认当前任务 ID 仍为 `server_local_git_worktree_policy_recover_2026_0712`，然后才继续。

## 4. 初始化独立 server-local worktree

先静态确认同步脚本不包含 push：

```bash
bash -n "${REPO_ROOT}/通信模块/server_local_git_sync.sh"
if grep -nE '(^|[[:space:]])git[[:space:]]+push([[:space:]]|$)' \
  "${REPO_ROOT}/通信模块/server_local_git_sync.sh"; then
  echo "forbidden git push command found" >&2
  exit 1
fi
```

初始化并保留退出码：

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

- `0`：worktree 已创建或已正确存在，与最新 `origin/main` 无真实冲突。
- `2`：真实冲突；停止，不 merge，不自动选择 ours/theirs。
- `4`：无真实冲突但有 same-path overlap；停止，本轮不合并，只报告等待外部开发者单次授权。
- 其他非零：安装或安全门失败，不手工绕过。

## 5. 验收与结果范围

```bash
git worktree list --porcelain > "${RESULT_DIR}/worktree_list.txt"
git -C "${LOCAL_WORKTREE}" branch --show-current > "${RESULT_DIR}/local_branch.txt"
git -C "${LOCAL_WORKTREE}" rev-parse HEAD > "${RESULT_DIR}/local_head.txt"
git -C "${LOCAL_WORKTREE}" status --porcelain > "${RESULT_DIR}/local_status.txt"
git ls-remote --heads origin 'server-local/*' > "${RESULT_DIR}/remote_server_local_refs.txt"
sed -n 's/^REPORT_DIR=//p' "${RESULT_DIR}/init_stdout.txt" \
  > "${RESULT_DIR}/git_sync_report_dir.txt"
```

验收条件：

```text
main mirror HEAD == origin/main
main mirror tracked status is empty
local_branch == server-local/runtime-adaptations
local_status is empty
remote_server_local_refs is empty
```

从 `git_sync_report_dir.txt` 指向的目录核对：

```text
summary.tsv
server_local_changed_paths.txt
upstream_changed_paths.txt
same_path_overlap.txt
conflict_paths.txt
merge_tree.txt
```

在 `${RESULT_DIR}/result_summary.md` 中记录各阶段验证、restore 的精确路径、pull 前后 HEAD、init 退出码、worktree 状态、same-path overlap、conflict paths，并明确声明本轮未执行任何 `git push`。

候选回传文件限于 `result_summary.md`、上述小型状态文件和同步报告六个文件；原始 full status 中若有敏感或无关服务器路径，只在摘要中报告计数与有界脱敏路径。

本轮是新结果范围，尚未获得 `email`、`upload-api` 或 `server-local` 选择。文件生成后，只在当前任务会话报告每个候选的精确路径、bytes、SHA-256、敏感性、可用方式和一个推荐方式，然后暂停。禁止在未确认前发邮件、上传或执行任何外发预检。
