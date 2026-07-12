# Developer to Server

## 当前唯一任务：验证 Git 2.54 现代预检并同步 server-local 分支

```text
task_id: server_local_git_compat_sync_2026_0712
execution_codebase: main-readonly
```

本任务不使用 NPU，不运行模型，不修改 vLLM、vLLM-Ascend、conda 或 CANN。上轮已经完成主镜像恢复和独立 worktree 初始化；不要再次 restore 任何 tracked 文件，也不要重新创建 worktree。

## 已知状态与本轮目的

- 主镜像：`/data/node0_disk1/liguowei/AK-Infer-Lab`
- server-local worktree：`/data/node0_disk1/liguowei/AK-Infer-Lab-server-local`
- server-local 分支：`server-local/runtime-adaptations`
- 上轮两侧 HEAD 均为 `bc4d412c5c572bf3bdf2c5b5665e441baa6b254f`，两侧工作区干净，远端无 `server-local/*` ref。
- 上轮 `init=2` 是假冲突：当时服务器 Git 2.34.1 不支持 `merge-tree --write-tree`，命令返回 129 后被旧脚本误分类。
- 用户现已将服务器 Git 升级为 **2.54.0**。新脚本继续使用现代 `merge-tree --write-tree`，但只把退出码 `1` 认定为真实冲突；其他非零值标记为 `check_error`，same-path overlap 仍单独等待审核。

永久边界不变：主镜像 tracked 文件全部只读；服务器专属代码只能在 server-local worktree 本地 commit；任何 remote、任何分支和 tag 都禁止 `git push`；不得自动选择 ours/theirs。

## 1. 同步前安全门

```bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
LOCAL_WORKTREE=/data/node0_disk1/liguowei/AK-Infer-Lab-server-local
LOCAL_BRANCH=server-local/runtime-adaptations
TASK_ID=server_local_git_compat_sync_2026_0712
RESULT_DIR="${REPO_ROOT}/server_local/${TASK_ID}"

mkdir -p "${RESULT_DIR}"

git -C "${REPO_ROOT}" status --porcelain --untracked-files=no \
  > "${RESULT_DIR}/mirror_status_before.txt"
git -C "${LOCAL_WORKTREE}" status --porcelain \
  > "${RESULT_DIR}/local_status_before.txt"
test ! -s "${RESULT_DIR}/mirror_status_before.txt"
test ! -s "${RESULT_DIR}/local_status_before.txt"
test "$(git -C "${LOCAL_WORKTREE}" branch --show-current)" = "${LOCAL_BRANCH}"
```

任一检查失败立即停止；不得 restore、stash、reset、merge 或 pull，只报告实际路径和状态。

## 2. 快进主镜像并重新读取当前任务

```bash
git -C "${REPO_ROOT}" fetch origin main
git -C "${REPO_ROOT}" merge --ff-only origin/main
git -C "${REPO_ROOT}" rev-parse HEAD \
  > "${RESULT_DIR}/mirror_head_after_pull.txt"
git -C "${REPO_ROOT}" rev-parse origin/main \
  > "${RESULT_DIR}/origin_main_after_pull.txt"
cmp -s "${RESULT_DIR}/mirror_head_after_pull.txt" \
  "${RESULT_DIR}/origin_main_after_pull.txt"
test -z "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=no)"
```

同步后重新打开拉取后的 `通信模块/docs/developer-to-server.md`。只有任务 ID 仍为 `server_local_git_compat_sync_2026_0712` 才继续。

## 3. 静态安全检查

```bash
SCRIPT="${REPO_ROOT}/通信模块/server_local_git_sync.sh"
bash -n "${SCRIPT}"
if grep -nE '(^|[[:space:]])git[[:space:]]+push([[:space:]]|$)' "${SCRIPT}"; then
  echo "forbidden git push command found" >&2
  exit 1
fi
git --version > "${RESULT_DIR}/git_version.txt"
grep -Fx 'git version 2.54.0' "${RESULT_DIR}/git_version.txt"
git merge-tree -h > "${RESULT_DIR}/merge_tree_help.txt" 2>&1 || true
grep -F -- '--write-tree' "${RESULT_DIR}/merge_tree_help.txt"
```

## 4. 先 check，再单向 sync

```bash
set +e
AK_SERVER_MIRROR_ROOT="${REPO_ROOT}" \
AK_SERVER_LOCAL_WORKTREE="${LOCAL_WORKTREE}" \
AK_SERVER_LOCAL_BRANCH="${LOCAL_BRANCH}" \
bash "${SCRIPT}" check \
  > "${RESULT_DIR}/check_before_stdout.txt" \
  2> "${RESULT_DIR}/check_before_stderr.txt"
CHECK_BEFORE_EXIT=$?
set -e
printf '%s\n' "${CHECK_BEFORE_EXIT}" > "${RESULT_DIR}/check_before_exit_code.txt"
test "${CHECK_BEFORE_EXIT}" = 0

CHECK_BEFORE_REPORT=$(sed -n 's/^REPORT_DIR=//p' \
  "${RESULT_DIR}/check_before_stdout.txt")
test -n "${CHECK_BEFORE_REPORT}"
cp "${CHECK_BEFORE_REPORT}/summary.tsv" \
  "${RESULT_DIR}/check_before_summary.tsv"
grep -Fx $'status\tclean' "${RESULT_DIR}/check_before_summary.tsv"
grep -Fx $'merge_tree_mode\twrite-tree' \
  "${RESULT_DIR}/check_before_summary.tsv"
grep -Fx $'merge_tree_exit_code\t0' \
  "${RESULT_DIR}/check_before_summary.tsv"
test ! -s "${CHECK_BEFORE_REPORT}/same_path_overlap.txt"
test ! -s "${CHECK_BEFORE_REPORT}/conflict_paths.txt"

AK_SERVER_MIRROR_ROOT="${REPO_ROOT}" \
AK_SERVER_LOCAL_WORKTREE="${LOCAL_WORKTREE}" \
AK_SERVER_LOCAL_BRANCH="${LOCAL_BRANCH}" \
bash "${SCRIPT}" sync \
  > "${RESULT_DIR}/sync_stdout.txt" \
  2> "${RESULT_DIR}/sync_stderr.txt"
```

本轮没有 server-local 独有提交，预期 `check=0/status=clean`，随后 `sync=0` 并把本地分支快进到最新 `origin/main`。若返回 `2`、`3`、`4`、`5` 或其他非零，立即停止，不得手工 merge 或绕过安全门：

- `2`：真实冲突；
- `3`：预检通过但实际 merge 失败且已 abort；
- `4`：same-path overlap，等待外部开发者单次审核；
- `5`：`check_error`，预检工具失败，不得冒充代码冲突。

## 5. 同步后复核

```bash
AK_SERVER_MIRROR_ROOT="${REPO_ROOT}" \
AK_SERVER_LOCAL_WORKTREE="${LOCAL_WORKTREE}" \
AK_SERVER_LOCAL_BRANCH="${LOCAL_BRANCH}" \
bash "${SCRIPT}" check \
  > "${RESULT_DIR}/check_after_stdout.txt" \
  2> "${RESULT_DIR}/check_after_stderr.txt"

CHECK_AFTER_REPORT=$(sed -n 's/^REPORT_DIR=//p' \
  "${RESULT_DIR}/check_after_stdout.txt")
cp "${CHECK_AFTER_REPORT}/summary.tsv" \
  "${RESULT_DIR}/check_after_summary.tsv"
grep -Fx $'status\tclean' "${RESULT_DIR}/check_after_summary.tsv"
grep -Fx $'merge_tree_mode\twrite-tree' \
  "${RESULT_DIR}/check_after_summary.tsv"
grep -Fx $'merge_tree_exit_code\t0' \
  "${RESULT_DIR}/check_after_summary.tsv"

git -C "${LOCAL_WORKTREE}" rev-parse HEAD \
  > "${RESULT_DIR}/local_head_after_sync.txt"
git -C "${REPO_ROOT}" rev-parse origin/main \
  > "${RESULT_DIR}/origin_main_after_sync.txt"
cmp -s "${RESULT_DIR}/local_head_after_sync.txt" \
  "${RESULT_DIR}/origin_main_after_sync.txt"
git -C "${REPO_ROOT}" status --porcelain --untracked-files=no \
  > "${RESULT_DIR}/mirror_status_after.txt"
git -C "${LOCAL_WORKTREE}" status --porcelain \
  > "${RESULT_DIR}/local_status_after.txt"
test ! -s "${RESULT_DIR}/mirror_status_after.txt"
test ! -s "${RESULT_DIR}/local_status_after.txt"
git -C "${REPO_ROOT}" worktree list --porcelain \
  > "${RESULT_DIR}/worktree_list.txt"
git -C "${REPO_ROOT}" ls-remote --heads origin 'server-local/*' \
  > "${RESULT_DIR}/remote_server_local_refs.txt"
test ! -s "${RESULT_DIR}/remote_server_local_refs.txt"
```

## 6. 结果与暂停点

在 `${RESULT_DIR}/result_summary.md` 中记录：Git 版本、pull 前后 HEAD、check-before/sync/check-after 退出码和状态、`merge_tree_mode`、双方 changed paths、same-path overlap、conflict paths、两侧最终 HEAD/branch/status、远端 `server-local/*` ref，并明确声明未执行任何 `git push`、未修改任何 tracked 文件、未使用 NPU。

候选回传文件只包含 `result_summary.md`、两份 `summary.tsv`、退出码、最终 HEAD/status/worktree/ref 和必要的有界 stderr；每个文件必须小于 70KB。结果生成后先在当前任务会话报告精确路径、bytes、SHA-256、敏感性、可用方式与推荐方式，然后暂停。本轮尚未获得 `email`、`upload-api` 或 `server-local` 的传输选择，禁止先发邮件、上传或自动切换方式。
