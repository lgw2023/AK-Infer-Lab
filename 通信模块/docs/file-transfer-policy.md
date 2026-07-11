# 昇腾服务器文件传输选择策略

日期：2026-07-10

状态：开发机侧工具与文档已实现；真实昇腾服务器 upload-api 预检与首个汇总文件回传已通过。

## 1. 核心规则

服务器状态正文仍可通过邮件正常发送。只要涉及文件附件或外部上传，就必须先向用户报告具体文件、大小、敏感性和候选方式，并取得用户针对当前范围的明确选择。

```text
待传文件：<服务器绝对路径或有界清单>
文件大小：<逐文件 bytes + 人类可读大小>
敏感性：普通 / 可能敏感 / 敏感
候选方式：email / upload-api / server-local
建议方式及理由：<一句话>
需要用户明确选择：<方式>
```

一次确认只覆盖已列出的文件、所选方式和当前任务。没有确认就不传；失败后只报告错误和候选方式，重新等待用户选择，不自动重试、改名或切换通道。

## 2. 两种对外交付方式与一种服务器留存状态

| 方式 | 适用情况 | 默认边界 |
| --- | --- | --- |
| `email` | 精简小附件 | 用户已选择邮件，且每个附件不超过 70KB |
| `upload-api` | 用户希望回传非敏感文件，且上传服务可用 | 不超过 50MB 常规；50–100MB 警告；超过 100MB 默认拒绝 |
| `server-local` | 大文件、敏感文件、服务不可用或用户不希望外传 | 文件不离开服务器；这是留存状态，不是已完成的附件交付 |

“敏感”默认建议 `server-local`。如果用户仍要求外传，确认内容必须明确文件范围和风险，不能用一次泛化授权覆盖后续文件。对于已获得 `email` 或 `upload-api` 确认的范围，任务不得再用“默认无附件”或“仅留服务器”替代已选定的交付。

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

## 5. 用户选择上传 API 后的执行顺序

在昇腾服务器受限网络中，先做唯一命名的小文件预检：

```bash
python3 通信模块/upload_file.py \
  --preflight \
  --confirmed-method upload-api
```

预检会在接收端留下一个小文件。只有预检成功后，才上传用户确认的具体文件：

```bash
python3 通信模块/upload_file.py \
  --upload /path/to/result.zip \
  --confirmed-method upload-api
```

普通公网机器确认可直连时可以加 `--no-proxy`。命令不会自动重试，不跟随非预期重定向，也不会自动换成邮件。

工具仅在以下条件全部满足时返回成功：

- curl 进程成功退出；
- HTTP 状态为 `201`；
- 响应为 JSON 且包含文件名、保存路径和 `sha256`；
- 远端 `sha256` 与上传前本地 SHA-256 完全一致。

## 6. 文件大小

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

## 7. 失败处理

| 结果 | 处理 |
| --- | --- |
| `401` | 服务器本地 token 无效或未同步；不显示 token |
| `409` | 当天同名文件已存在；是否改名重传由用户决定 |
| `413` | 服务端或 Cloudflare 大小限制；返回方式选择门 |
| `3xx`、HTML 告警页、非 JSON | 视为代理/网络通路异常，先报告并重新选择 |
| `502/530` | 上传服务或 Tunnel 暂不可用 |
| curl 超时或非零退出 | 不重试，返回脱敏错误摘要 |
| HTTP `201` 但 SHA-256 不一致 | 判定失败，不声称文件可靠到达 |

失败邮件只发送 70KB 内的状态摘要，不附带原文件。当前接收端删除能力不在本项目契约内，因此不能声称失败文件已从远端删除。

## 8. 当前证据边界

本仓库已通过 mock 测试验证命令构造、用户确认门、临时凭据文件清理、大小边界、HTTP 状态和 SHA-256 判定。2026-07-10 服务器在用户已选择 `upload-api` 的具体范围内，使用 `proxychains4 + curl` 完成真实小文件预检：HTTP `201`、远端与本地 SHA-256 一致、exit `0`、耗时 `1.64s`；随后 `server_status_summary_2026_0710.md` 也经同一通道到达开发机。

开发机侧事实源为 `/Volumes/SSD1/Inbox/2026-07-10/server_status_summary_2026_0710.md`，文件大小 `3303 bytes`，SHA-256 为 `725d034490ba3565e8fa70e0ebb9cbafe54f2de75204ab4ec4367846f0135757`。该成功只证明当前配置、代理、上传服务和小文件路径可用，不取消逐文件用户确认门，也不保证后续大文件不会遇到 `409`、`413`、超时或服务异常。
