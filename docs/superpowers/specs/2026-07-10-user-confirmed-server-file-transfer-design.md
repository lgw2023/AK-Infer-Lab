# 用户确认式服务器文件传输设计

日期：2026-07-10

状态：待用户复核

## 1. 目标

把上传 API 纳入 AK-Infer-Lab 的“昇腾服务器 → 外部开发机”文件回传候选，同时保留既有邮件小附件和服务器本地留存两条路径。任何文件传输前，都必须先向用户报告文件、大小、敏感性与候选方式，由用户明确选择；执行端不得自行决定，也不得在失败后自动切换通道。

本次完整集成包括：

- 新增可执行的上传 API 工具及自动化测试。
- 新增稳定的文件传输策略文档，并同步通信 README、服务器反馈模板和 `AGENTS.md`。
- 在 `.env.example` 登记脱敏配置字段，真实上传密钥只保留在昇腾服务器本地 `.env`。
- 同步 `工作记录与进度笔记本/01_工作记录.md` 的启动、结果、验证和后续使用边界。

## 2. 非目标

- 不替换 `通信模块/send_notify.py`，也不改变开发机通过 Git 向服务器下发任务的方向。
- 不在本轮向上传服务发送真实文件或连通性探针。
- 不把上传 API 设为默认回传方式。
- 不实现分片上传、断点续传、自动重试、后台队列或服务端删除。
- 不复制 `/Volumes/SSD1/upload-api-service/小白版上传策略.md` 中的明文密钥。
- 不修改当前处于“等待运行时升级反馈”状态的 `通信模块/docs/developer-to-server.md`；未来只有在具体任务中得到用户确认后，才在该文件写入本轮传输选择。

## 3. 传输方式与选择门

稳定策略提供三种方式：

| 方式 | 适用范围 | 默认边界 |
| --- | --- | --- |
| `email` | 精简摘要、小清单、少量样例、小附件 | 邮件正文和每个附件均不超过 70KB |
| `upload-api` | 用户希望把非敏感文件传到外部开发机，且上传服务与网络通路可用 | 0–50MB 常规；50–100MB 警告；超过 100MB 默认拒绝 |
| `server-local` | 大文件、敏感文件、服务不可用或用户不希望外传 | 文件保留服务器，只回传路径、大小、摘要或就地分析结果 |

执行前必须给用户提供以下信息：

```text
待传文件：<服务器绝对路径>
文件大小：<bytes + 人类可读大小>
敏感性：普通 / 可能敏感 / 敏感
候选方式：email / upload-api / server-local
建议方式及理由：<一句话>
需要用户明确选择：<方式>
```

没有明确选择时不得执行。用户确认只对指定文件或明确列出的文件集合、指定方式和当前任务有效，不得扩展到后续文件。传输失败后只报告失败原因和仍可选方式，必须再次取得用户选择，不能自动从上传 API 改用邮件，或反向切换。

## 4. 上传工具

新增 `通信模块/upload_file.py`，使用 Python 标准库完成参数、文件检查、哈希和响应解析，使用系统 `curl` 发起 multipart 上传；在昇腾服务器受限网络中默认通过既有 `proxychains4` 配置执行 `curl`。

### 4.1 命令面

工具提供三个互斥入口：

```bash
# 只读检查，不访问网络
python3 通信模块/upload_file.py --inspect /path/to/file

# 用户选择上传 API 后，执行唯一文件上传
python3 通信模块/upload_file.py \
  --upload /path/to/file \
  --confirmed-method upload-api

# 用户选择上传 API 后，生成唯一命名的小文件做网络预检
python3 通信模块/upload_file.py \
  --preflight \
  --confirmed-method upload-api
```

辅助参数：

- `--show-config`：打印脱敏配置，只显示 URL、token 是否已设置、代理开关、可执行文件路径和大小阈值。
- `--no-proxy`：仅在已确认普通公网或直连可用时绕过 proxychains。
- `--allow-over-100mb`：允许突破默认 100MB 本地保护；仍必须同时提供 `--confirmed-method upload-api`，且文档要求用户已经知悉服务可能返回 `413`。该参数不保证服务端接受文件。

`--inspect` 输出文件绝对路径、字节数、十进制 MB、SHA-256、大小分档和三种候选方式，不读取文件内容语义，也不替用户判断敏感性。

### 4.2 显式确认保护

`--upload` 和 `--preflight` 必须带精确值 `--confirmed-method upload-api`，缺少或不匹配时以参数错误退出，不访问网络。该参数是执行层防误触保护；用户确认事实仍必须记录在当前任务对话或未来的 `developer-to-server.md` 中。

工具不会提供“自动推荐后立即上传”或交互式默认选项，避免无人值守服务器任务把建议误当成授权。

### 4.3 配置

`.env.example` 增加：

```bash
AK_COMM_UPLOAD_URL=https://upload.ultrahardcore.net/v1/files
AK_COMM_UPLOAD_TOKEN=
AK_COMM_UPLOAD_USE_PROXYCHAINS=1
AK_COMM_UPLOAD_MAX_TIME=600
```

代理二进制和配置路径复用：

```bash
AK_COMM_PROXYCHAINS_BIN=proxychains4
AK_COMM_PROXYCHAINS_CONFIG=/etc/proxychains4.conf
```

`AK_COMM_UPLOAD_TOKEN` 无仓库默认值；未设置时只允许 `--inspect` 和脱敏 `--show-config`，上传与预检直接失败。真实 token 只能存在服务器本地 `.env` 或当前进程环境中。

### 4.4 凭据与进程安全

工具不得把真实 token 放进日志、JSON 报告、异常文本或测试 fixture；测试只使用明确的假 sentinel，并验证它不会进入命令或输出。为避免 token 直接出现在 `ps` 可见的 curl 参数中，运行前创建权限为 `0600` 的临时 header 文件，curl 使用 `--header @<临时文件>` 读取认证头；无论成功、失败或超时都在 `finally` 中删除该文件。

临时响应文件也使用受限权限并在解析后删除。curl 命令可以包含待传文件路径，但不得包含 token。`--show-config` 只输出 `token_set: true|false`。

## 5. 上传与校验流程

正式上传流程：

1. 验证文件存在、是普通文件且可读，解析为绝对路径。
2. 获取字节数并计算本地 SHA-256。
3. 按十进制阈值分档：不超过 `50_000_000` bytes 为常规，超过 `50_000_000` 且不超过 `100_000_000` bytes 为警告，超过 `100_000_000` bytes 为默认拒绝。
4. 超过 100MB 且没有 `--allow-over-100mb` 时本地拒绝，不访问网络。
5. 校验 URL、token、curl 和所需 proxychains 可用。
6. 构造不含 token 的命令列表；不使用 shell 拼接。
7. 单次执行上传，不自动重试，不自动跟随非预期重定向。
8. 仅当 HTTP 状态为 `201`、响应为 JSON、响应 `sha256` 与本地 SHA-256 一致时判定成功。
9. 输出脱敏结果：原文件名、保存文件名、保存路径、字节数、本地/远端 SHA-256、HTTP 状态和总耗时。

预检流程生成唯一文件名的短文本文件，走同一上传和校验路径，随后删除服务器本地临时文件。预检本身会在接收端留下一个小文件，因此也必须在用户已经选择 `upload-api` 后执行。

## 6. 错误处理

工具按以下方式给出可行动错误，不做通道切换：

| 情况 | 行为 |
| --- | --- |
| `401` | 报告上传凭据无效或未同步，不显示 token |
| `409` | 报告当天同名文件已存在，要求用户决定是否改名后重传 |
| `413` | 报告服务端/Cloudflare 大小限制，返回方式选择门 |
| `3xx`、HTML 告警页或非 JSON | 报告网络/代理通路异常，建议先重新做小文件预检 |
| `502/530` | 报告上传服务或 Tunnel 暂不可用 |
| curl 超时/非零退出 | 返回脱敏 stderr 摘要，不重试 |
| SHA-256 不一致 | 判定上传失败，保留远端返回信息供人工核对 |

错误信息不得声称远端文件已删除，也不得在 `409` 时自动改名，因为接收端当前没有纳入本设计的查询或删除接口。

## 7. 文档落点

- `AGENTS.md`：固化“先报告、用户选择、再执行；失败后重新确认”的行为规则。
- `通信模块/README.md`：把通信方向改为邮件、上传 API、服务器留存三种回传路径，加入命令入口和安全摘要。
- `通信模块/docs/file-transfer-policy.md`：记录完整选择表、用户确认模板、脱敏配置、预检/正式上传命令、大小与错误边界。
- `通信模块/docs/server-to-developer.md`：反馈模板增加文件清单、大小、敏感性、候选方式和“等待用户选择”字段。
- `.env.example`：只增加占位符和非秘密默认项。
- `工作记录与进度笔记本/01_工作记录.md`：记录本轮启动、完成状态、验证结果和“尚未在真实昇腾服务器运行”的证据边界。

当前 `通信模块/docs/developer-to-server.md` 不修改。后续真实任务需要传文件时，必须先由用户选择，再清空并重写该文件，将选择写成明确字段，例如：

```text
transfer_method: upload-api
transfer_scope: /absolute/path/to/file
user_confirmed: true
oversize_risk_accepted: false
```

## 8. 自动化测试

新增 `tests/communication/test_upload_file.py`，不访问真实网络，通过临时文件和 mock subprocess 覆盖：

- `.env` 加载、缺 token 拒绝和 `--show-config` 脱敏。
- `--inspect` 不调用 subprocess，输出大小、SHA-256 和候选方式。
- 缺少/错误 `--confirmed-method` 时不访问网络。
- 代理与直连命令构造正确，proxychains 可选配置路径生效。
- curl 命令及配置报告不含 token，临时 header/响应文件最终被清理。
- 50MB、100MB 分档边界和超过 100MB 默认拒绝。
- `--allow-over-100mb` 只解除本地大小保护，不解除确认要求。
- `201` + 相同 SHA-256 成功；非 JSON、SHA 不匹配、`401/409/413/502/530`、超时和非零退出失败。
- 预检文件名唯一，并复用相同的成功校验。

回归验证：

```bash
python -m pytest tests/communication -q
python -m pytest tests/inference_contracts -q
python -m py_compile 通信模块/send_notify.py 通信模块/upload_file.py
git diff --check
```

不把开发机上的 mock 测试写成真实昇腾服务器网络验证；首次真实使用仍需用户选择方式后，在服务器通过 `proxychains4` 完成预检。

## 9. 验收标准

完成必须同时满足：

1. 仓库不含源策略中的真实上传 token，日志与测试也不泄露 token。
2. 没有显式 `--confirmed-method upload-api` 时，工具不会访问网络。
3. 大于 100MB 的文件默认不会上传；显式风险接受也不被描述为服务端保证。
4. 成功必须同时满足 HTTP `201` 和 SHA-256 一致。
5. 文档在所有稳定入口中一致表达三种方式、70KB 邮件边界、用户确认门和失败后禁止自动切换。
6. 当前等待升级的服务器交接内容保持不变。
7. 自动化测试和静态检查通过；真实服务器能力保持 `not_yet_verified`，直到另一次经用户授权的服务器预检返回证据。
