# 昇腾服务器文件传输选择策略

日期：2026-07-11

状态：开发机侧工具与文档已实现；真实昇腾服务器 upload-api 预检与首个汇总文件回传已通过。

## 1. 核心规则

任务完成后不再默认先发状态邮件。服务器先把正文写入本地 `result_summary.md`，整理有界附件清单，然后只在当前任务会话中请求用户为整个结果包选择 `email` 或 `upload-api`。确认前不得调用 `send_notify.py` 的发送/测试模式，也不得调用 upload-api 预检或上传。

```text
待传正文：<result_summary.md 服务器绝对路径>
待传附件：<服务器绝对路径或有界清单>
文件大小：<正文与附件逐文件 bytes + 人类可读大小>
SHA-256：<正文与附件逐文件 SHA-256>
敏感性：普通 / 可能敏感 / 敏感
候选方式：email / upload-api / server-local
建议方式及理由：<一句话>
需要用户明确选择：<方式>
```

一次确认只覆盖已列出的正文、附件、所选方式和当前任务。没有确认就不传；失败后只在当前任务会话报告错误和候选方式，重新等待用户选择，不自动重试、改名、补发邮件或切换通道。

## 2. 两种对外交付方式与一种服务器留存状态

| 方式 | 适用情况 | 默认边界 |
| --- | --- | --- |
| `email` | 精简正文和小附件 | 用户已选择邮件，正文与每个附件均不超过 70KB；一次邮件共同交付 |
| `upload-api` | 用户希望回传非敏感结果包，且上传服务可用 | `result_summary.md` 与所有批准附件都上传；不超过 50MB 常规，50–100MB 警告，超过 100MB 默认拒绝 |
| `server-local` | 大文件、敏感文件、服务不可用或用户不希望外传 | 文件不离开服务器；这是留存状态，不是已完成的附件交付 |

“敏感”默认建议 `server-local`。如果用户仍要求外传，确认内容必须明确正文、附件范围和风险，不能用一次泛化授权覆盖后续文件。对于已获得 `email` 或 `upload-api` 确认的范围，正文和附件必须走同一已选渠道；不得先用邮件发正文，再单独询问附件渠道。

## 3. 只读检查

先在服务器检查文件，不访问网络：

```bash
python3 通信模块/upload_file.py --inspect /path/to/result.zip
```

输出包含绝对路径、大小、十进制 MB、SHA-256、大小分档和三种候选方式。工具不读取文件内容语义，也不替用户判断敏感性。

## 4. 服务器本地配置

真实 token 只写入昇腾服务器项目根目录的 `.env`：

```bash
AK_COMM_UPLOAD_URL=https://upload.ultrahardcore.net/v1/files
AK_COMM_UPLOAD_TOKEN=<真实 token>
AK_COMM_UPLOAD_USE_PROXYCHAINS=1
AK_COMM_UPLOAD_MAX_TIME=600
AK_COMM_CURL_BIN=curl
AK_COMM_PROXYCHAINS_BIN=proxychains4
AK_COMM_PROXYCHAINS_CONFIG=/etc/proxychains4.conf
AK_COMM_PAYLOAD_DIR=/tmp
```

不要把 `.env`、token、proxychains 配置或代理账号密码写入 Git、邮件或任务文档。脱敏检查配置：

```bash
python3 通信模块/upload_file.py --show-config
```

该命令只显示 `token_set: true/false`，不显示 token。

## 5. 用户选择邮件后的执行顺序

`send_notify.py` 不接受环境变量或历史选择作为授权；每次发送必须显式传入当前命令参数：

```bash
python3 通信模块/send_notify.py \
  --subject "<任务结果主题>" \
  --body-file /path/to/result_summary.md \
  --attach /path/to/approved_attachment_1 \
  --attach /path/to/approved_attachment_2 \
  --confirmed-method email
```

遗漏 `--confirmed-method email` 时，脚本在读取正文和访问 SMTP 前拒绝执行。正文和每个附件都必须小于等于 70KB；本轮未列入确认范围的文件不得附加。

## 6. 用户选择上传 API 后的执行顺序

不得额外发送状态邮件。把 `result_summary.md` 视为结果包中的第一个文件，再逐个上传本轮已批准的附件：

```bash
python3 通信模块/upload_file.py \
  --upload /path/to/result_summary.md \
  --confirmed-method upload-api
python3 通信模块/upload_file.py \
  --upload /path/to/approved_attachment_1 \
  --confirmed-method upload-api
```

`--preflight` 会在接收端留下额外文件，不再例行自动执行；只有用户的当前确认明确包含预检时才可使用。

普通公网机器确认可直连时可以加 `--no-proxy`。命令不会自动重试，不跟随非预期重定向，也不会自动换成邮件。

工具仅在以下条件全部满足时返回成功：

- curl 进程成功退出；
- HTTP 状态为 `201`；
- 响应为 JSON 且包含文件名、保存路径和 `sha256`；
- 远端 `sha256` 与上传前本地 SHA-256 完全一致。

## 7. 文件大小

- `0–50_000_000 bytes`：常规档。
- `50_000_001–100_000_000 bytes`：警告档，默认超时为 600 秒。
- `>100_000_000 bytes`：本地默认拒绝，优先建议 `server-local` 或其他经用户选择的通道。

只有用户明确接受可能的 `413` 风险后，才可使用：

```bash
python3 通信模块/upload_file.py \
  --upload /path/to/result.zip \
  --confirmed-method upload-api \
  --allow-over-100mb
```

`--allow-over-100mb` 只解除本地保护，不保证接收端或 Cloudflare 接受文件。

## 8. 失败处理

| 结果 | 处理 |
| --- | --- |
| 邮件确认参数缺失 | 不读取正文、不访问 SMTP；回到当前任务会话等待选择 |
| `401` | 服务器本地 token 无效或未同步；不显示 token |
| `409` | 当天同名文件已存在；是否改名重传由用户决定 |
| `413` | 服务端或 Cloudflare 大小限制；返回方式选择门 |
| `3xx`、HTML 告警页、非 JSON | 视为代理/网络通路异常，先报告并重新选择 |
| `502/530` | 上传服务或 Tunnel 暂不可用 |
| curl 超时或非零退出 | 不重试，返回脱敏错误摘要 |
| HTTP `201` 但 SHA-256 不一致 | 判定失败，不声称文件可靠到达 |

失败后不自动发送邮件摘要。只在当前任务会话报告脱敏错误，等待用户决定是否对同一范围重新授权。当前接收端删除能力不在本项目契约内，因此不能声称失败文件已从远端删除。

## 9. 当前证据边界

本仓库已通过 mock 测试验证邮件与 upload-api 的显式用户确认门，以及上传命令构造、临时凭据文件清理、大小边界、HTTP 状态和 SHA-256 判定。2026-07-10 服务器在用户已选择 `upload-api` 的具体范围内，使用 `proxychains4 + curl` 完成真实小文件预检：HTTP `201`、远端与本地 SHA-256 一致、exit `0`、耗时 `1.64s`；随后 `server_status_summary_2026_0710.md` 也经同一通道到达开发机。

开发机侧事实源为 `/Volumes/SSD1/Inbox/2026-07-10/server_status_summary_2026_0710.md`，文件大小 `3303 bytes`，SHA-256 为 `725d034490ba3565e8fa70e0ebb9cbafe54f2de75204ab4ec4367846f0135757`。该成功只证明当前配置、代理、上传服务和小文件路径可用，不取消逐文件用户确认门，也不保证后续大文件不会遇到 `409`、`413`、超时或服务异常。
