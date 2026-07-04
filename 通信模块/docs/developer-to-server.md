# 开发机 -> 服务器消息

> 本文件每次只保留当前待执行任务；旧历史信息已清空。

## 当前任务：邮件链路补救与双收件人验证

- 任务时间：2026-07-05
- 目标服务器标识：`atlas800t-a2-node-001`
- 任务目的：
  - 修复服务器反馈邮件只进入单一邮箱导致开发机漏看最新邮件的问题。
  - 后续所有 AK-Infer-Lab 服务器反馈邮件同时发送到两个收件人：
    - `gwlee1995@gmail.com`
    - `yilili1023@gmail.com`
  - 补发一次 `fio/numactl/perf` 安装成功摘要到两个邮箱，避免开发机侧只看到安装前的 `tool_missing` 旧状态。

## 背景

- 当前 Codex Gmail 工具连接的是 `yilili1023@gmail.com`。
- 用户实际看到的 `2026-07-05 02:43 CST` 邮件：
  `[AK服务器] 任务完成：fio/numactl/perf 安装成功`
  没有出现在该 Gmail 连接账号里，推断该邮件只发到了 `gwlee1995@gmail.com`。
- 这导致开发机一度只根据 `obs_2026_0705_atlas800t_a2_004` 附件判断 `fio/numactl/perf` 仍是 `tool_missing`。
- 正确时间线：
  - `obs_2026_0705_atlas800t_a2_004` 是工具安装前的 run，附件里 `fio/numactl/perf` 为 `tool_missing`。
  - `2026-07-05 02:43 CST` 后，服务器已验证 `fio`、`numactl`、`perf` 可用。

## 执行约束

- 服务器只通过 `git pull` 获取本文件。
- 不要在服务器上修改、提交或 push 项目代码。
- 不要提交或邮件发送 `.env`、SMTP 授权码、代理凭据、服务器账号、私钥、Cookie 或任何敏感信息。
- 本任务只补救通信链路，不自动修复或重装 `ascend910b-driver`。

## 服务器需要执行的步骤

### 1. 同步仓库

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab
git pull --ff-only
git rev-parse --short HEAD
```

### 2. 更新服务器本地 `.env` 收件人

请只改服务器本地 `/data/node0_disk1/liguowei/AK-Infer-Lab/.env`，不要提交 `.env`。

将默认收件人设置为逗号分隔的双收件人：

```bash
AK_COMM_MAIL_TO=gwlee1995@gmail.com,yilili1023@gmail.com
```

如果 `.env` 中已有 `AK_COMM_MAIL_TO`，请替换为上面这一行；不要在邮件中回显 `.env` 全文。

### 3. 发送双收件人连通性测试

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab
python3 通信模块/send_notify.py \
  --test \
  -t gwlee1995@gmail.com,yilili1023@gmail.com
```

预期：两个邮箱都收到测试邮件。测试邮件不得包含任何密钥或代理凭据。

### 4. 补发工具安装成功摘要

请把 `fio/numactl/perf` 安装成功摘要补发给两个邮箱，主题使用：

```text
[AK服务器] 补发：fio/numactl/perf 安装成功
```

正文至少包含：

- 主机名：`DevServer-BMS-3d97cc99-0`
- 目标服务器：`atlas800t-a2-node-001`
- 说明：这是双收件人补发，用于修复此前单一邮箱漏看问题。
- 当前工具验证：
  - `which fio && fio --version`
  - `which numactl && numactl --hardware | head -20`
  - `which perf && perf --version`
  - `perf stat -e task-clock -- sleep 0.1`
- 遗留问题：
  - `apt-get install` 曾因系统原有半配置包 `ascend910b-driver` 的 post-install 脚本失败而最终退出码为 `100`。
  - 该问题不影响 `fio`、`numactl`、`perf` 实际可用性。
  - 不要在本轮自动修复或重装 `ascend910b-driver`；如需处理，另开维护窗口。

可以使用以下模板：

```bash
cat > /tmp/ak_tool_install_resend_body.txt <<'EOF'
AK-Infer-Lab 双收件人补发：fio / numactl / perf 安装成功

这是对 2026-07-05 02:43 CST 工具安装成功邮件的补发，用于修复此前邮件只进入单一邮箱导致开发机漏看最新状态的问题。

服务器：DevServer-BMS-3d97cc99-0
目标服务器标识：atlas800t-a2-node-001

当前状态：
- fio 已安装并可用。
- numactl 已安装并可用。
- perf 已安装并可用。

请以本邮件为准：obs_2026_0705_atlas800t_a2_004 附件中的 fio/numactl/perf tool_missing 是工具安装前状态，已经过期。

遗留问题：
- apt-get install 曾因系统原有半配置包 ascend910b-driver 的 post-install 脚本失败而最终退出码为 100。
- 该问题不影响 fio、numactl、perf 实际可用性。
- 本轮不要自动修复或重装 ascend910b-driver；如需处理，应另开维护窗口。
EOF

{
  echo "===== hostname ====="
  hostname
  echo
  echo "===== git ====="
  cd /data/node0_disk1/liguowei/AK-Infer-Lab && git rev-parse --short HEAD
  echo
  echo "===== fio ====="
  which fio || true
  fio --version || true
  echo
  echo "===== numactl ====="
  which numactl || true
  numactl --hardware | head -20 || true
  echo
  echo "===== perf ====="
  which perf || true
  perf --version || true
  perf stat -e task-clock -- sleep 0.1 || true
} > /tmp/ak_tool_install_verify.txt 2>&1

python3 通信模块/send_notify.py \
  -t gwlee1995@gmail.com,yilili1023@gmail.com \
  -s "[AK服务器] 补发：fio/numactl/perf 安装成功" \
  --body-file /tmp/ak_tool_install_resend_body.txt \
  --attach /tmp/ak_tool_install_verify.txt
```

## 回传要求

- 如果双收件人测试成功，请邮件正文明确写：
  `dual recipient mail verified: gwlee1995@gmail.com,yilili1023@gmail.com`
- 如果任一邮箱退信或发送失败，请说明失败邮箱、错误摘要和是否已重试。
- 不需要在本轮重新跑完整 observability collect；除非开发机后续明确要求。

## 后续判读口径

- `obs_2026_0705_atlas800t_a2_004` 是工具安装前的 artifact；其中 `fio/numactl/perf tool_missing` 已不是服务器当前状态。
- 当前服务器侧应视为：
  - NPU microbench 已跑通。
  - `fio`、`numactl`、`perf` 已可用。
  - `ascend910b-driver` 的 dpkg 半配置问题仍需单独维护，不要混入本轮自动脚本处理。
