# 通信模块：开发机与服务器消息传递

本目录是项目内的“开发机 ↔ 服务器”通讯子项目，用于在服务器外联受限时维持最小可用协作链路，并在用户明确选择后一次性交付任务正文与必要附件。

## 通信约束与方向

- **任务结束先等待**：服务器先在本地生成 `result_summary.md` 与有界附件清单，在当前任务会话中请求用户选择；确认前不得发送状态邮件正文、附件、upload-api 预检或文件。
- **服务器 → 开发人员结果**：完成交付使用 `email + 正文/小附件` 或 `upload-api + result_summary.md/附件`；正文与附件必须走用户为当前范围选择的同一渠道。`server-local` 只是大文件或敏感原始数据的留存状态，不等于已交付。
- **开发机 → 服务器**：开发人员直接在本目录写 Markdown/文本文档并提交，服务器通过服务器本地 `git pull-remote` 获取这些文档信息。
- **通信容量上限**：昇腾服务器每次邮件正文和每个附件都按不超过 70KB 处理；不要通过邮件回传 raw profiler、长日志、模型输出、实验目录或其他大文件。
- **大数据留在服务器**：实验产生的大规模数据只能留在昇腾服务器上；如需分析大数据，由外部开发者（本机）在 `docs/developer-to-server.md` 下达服务器本地分析任务，服务器只按用户已选渠道回传精简摘要、小清单、少量样例和服务器路径。
- **用户确认门**：在当前任务会话中报告摘要文件与附件的路径、大小、SHA-256、敏感性、候选方式和建议理由；没有明确选择就不传，失败后也不得先发邮件说明或自动切换方式。
- **不在仓库保存密钥**：SMTP 账号和授权码通过环境变量注入；默认收件人可通过环境变量覆盖。
- **代理只属于昇腾服务器受限网络**：普通外部开发机网络通常不需要 proxychains 或 HTTP 代理。

## 文件说明

- `send_notify.py`：用户明确选择 `email` 后使用的服务器侧交付脚本；必须显式传入 `--confirmed-method email`，默认使用 `smtp.163.com:465`，并在昇腾服务器上通过 `proxychains4` 发信。
- `upload_file.py`：用户选择 `upload-api` 后使用的单文件检查/上传工具；支持脱敏配置、100MB 默认保护、HTTP 201 与 SHA-256 双校验；2026-07-10 已在真实昇腾服务器通过 proxychains4 完成预检和首个汇总文件回传。
- `docs/developer-to-server.md`：开发机写给服务器读取的消息模板。
- `docs/server-to-developer.md`：服务器本地结果准备、等待确认及确认后交付的模板。
- `docs/file-transfer-policy.md`：三种文件传输方式、用户确认模板、上传命令和失败边界。
- `docs/mail-network-config.md`：最新服务器邮件确认的邮件与网络配置事实，已脱敏。
- `docs/server-docker-images.md`：服务器侧已加载并冒烟通过的 Docker 镜像登记。

## 服务器侧配置

在昇腾服务器的项目根目录复制模板并填写真实 SMTP 授权码。普通外部开发机一般不需要创建 `.env`，除非要本地复现发信链路：

```bash
cd <项目根目录>
cp .env.example .env
# 编辑 .env，填入真实 163 SMTP 授权码；不要提交 .env
```

`.env` 只保留在服务器本地，不提交到仓库。`send_notify.py` 启动时会自动读取项目根目录 `.env`，且不会覆盖 shell 中已经存在的环境变量。

`.env` 中的必填项：

```bash
AK_COMM_SMTP_HOST=smtp.163.com
AK_COMM_SMTP_PORT=465
AK_COMM_SMTP_USER=17621223203@163.com
AK_COMM_SMTP_PASSWORD=你的 163 SMTP 授权码
AK_COMM_MAIL_FROM=17621223203@163.com
AK_COMM_MAIL_TO=yilili1023@gmail.com
```

`AK_COMM_MAIL_TO` 支持逗号分隔多个收件人。当前项目默认只发送到 `yilili1023@gmail.com`，不再发送到 `gwlee1995@gmail.com`。

只有用户选择 `upload-api` 时才需要在服务器本地 `.env` 配置：

```bash
AK_COMM_UPLOAD_URL=https://upload.ultrahardcore.net/v1/files
AK_COMM_UPLOAD_TOKEN=<上传 token，仅服务器本地保存>
AK_COMM_UPLOAD_USE_PROXYCHAINS=1
AK_COMM_UPLOAD_MAX_TIME=600
AK_COMM_CURL_BIN=curl
```

仓库不提供真实 `AK_COMM_UPLOAD_TOKEN`。未设置 token 时，`--inspect` 和 `--show-config` 仍可用，但预检和上传会拒绝执行。

可选配置：

```bash
AK_COMM_USE_PROXYCHAINS=1      # 昇腾服务器默认 1；普通网络可设为 0/false/no 直连 SMTP
AK_COMM_PROXYCHAINS_BIN=proxychains4
AK_COMM_PROXYCHAINS_CONFIG=/etc/proxychains4.conf
AK_COMM_PAYLOAD_DIR=/tmp
```

服务器 shell 层出站代理只在昇腾服务器受限网络中使用，通常外部开发机不要设置：

```bash
AK_HTTP_PROXY=http://proxy_user:proxy_password@proxysg.huawei.com:8080/
AK_HTTPS_PROXY=http://proxy_user:proxy_password@proxysg.huawei.com:8080/
AK_FTP_PROXY=http://proxy_user:proxy_password@proxysg.huawei.com:8080/
AK_NO_PROXY=localhost,127.0.0.1,::1,*.huawei.com,*.huaweicloud.com
```

SMTP 发信使用 `proxychains4` 时走服务器的 proxychains 配置；shell 代理用于 `curl`、`wget`、`apt`、`git` 等命令。两者不是同一个入口。

## 常用命令

脱敏查看当前配置，不发送邮件：

```bash
python3 通信模块/send_notify.py --show-config
```

用户已明确同意发送测试邮件后，发送连通性测试邮件：

```bash
python3 通信模块/send_notify.py --test --confirmed-method email
```

用户已对当前结果包选择 `email` 后，发送任务正文：

```bash
python3 通信模块/send_notify.py \
  -s "任务完成" \
  -b "训练已结束，loss=0.12" \
  --confirmed-method email
```

只读检查待传文件，不访问网络：

```bash
python3 通信模块/upload_file.py --inspect /path/to/result.zip
```

脱敏查看上传配置，不访问网络：

```bash
python3 通信模块/upload_file.py --show-config
```

`--preflight` 会在接收端创建额外文件，只有用户对当前范围明确包含预检时才执行：

```bash
python3 通信模块/upload_file.py --preflight --confirmed-method upload-api
```

用户选择 `upload-api` 后，把正文文件和已批准附件作为一个具名结果会话、通过一次请求共同上传；不要补发状态邮件。`--session-name` 在接收端当天必须唯一：

```bash
python3 通信模块/upload_file.py \
  --upload /path/to/result_summary.md \
  --upload /path/to/approved_attachment.txt \
  --session-name <task-name-YYYYMMDD-run-id> \
  --confirmed-method upload-api
```

普通公网机器确认可直连时可加 `--no-proxy`。单个文件或结果包总大小超过 100MB 默认拒绝；只有用户明确接受可能的 `413` 风险后才可加 `--allow-over-100mb`，该参数不保证服务端接受。

从文件读取正文并附加已批准的小文件（正文和每个附件均需不超过 70KB）：

```bash
python3 通信模块/send_notify.py \
  -s "任务结果" \
  --body-file /path/to/result_summary.md \
  --attach /path/to/approved_attachment.txt \
  --confirmed-method email
```

在确认服务器可直连 SMTP 时绕过代理：

```bash
python3 通信模块/send_notify.py --test --no-proxy --confirmed-method email
```

## 开发机到服务器的文档流

1. 开发人员在 `docs/developer-to-server.md` 追加或更新指令、问题、实验计划。
2. 开发人员提交并推送仓库。
3. 服务器执行本地 alias `git pull-remote` 后读取本目录文档；该 alias 指向服务器本地 `server_local/git_pull_remote_wins.sh`，执行 `fetch + reset --hard origin/main`，让已跟踪文件以远端为准，同时保留未跟踪实验产物、conda 环境和服务器本地脚本。
4. 服务器完成任务后只在服务器本地生成 `result_summary.md`、候选附件和清单；通过当前任务会话请求用户在 `email` 与 `upload-api` 中选择，不调用任何外发命令。
5. 用户选择后，服务器只按该方式交付已列明的正文与附件：`email` 把摘要作为正文并附上批准文件；`upload-api` 用一个 `session_name` 和一次多文件请求提交摘要与全部批准附件。不得先发状态邮件、扩展范围或切换通道。

## 双向协作约束

- 昇腾服务器只从远端同步，不从服务器 push；日常同步使用服务器本地 `git pull-remote`。
- 昇腾服务器不直接修改仓库内项目代码；如需反馈代码问题，也先在当前任务会话等待用户选择结果交付渠道。
- 外部开发机完成代码或文档改动后提交并 push，服务器再 pull 同步。
- `server_local/`、`.conda/` 和实验产物只属于服务器本地，不提交到仓库。
- 服务器本地独立脚本 `/data/node0_disk1/Public/send_notify.py` 不属于本仓库；仓库内统一使用 `通信模块/send_notify.py`。
- 用户选择邮件后，邮件只适合回传 70KB 以内的正文、小清单、少量样例和路径；大规模实验数据、原始 profiler、完整日志和大 zip 都保留在服务器本地。
- 外部开发机需要基于大数据继续判断时，应把分析步骤写成新的服务器任务，让服务器就地处理后再返回小结果。
- 对外文件回传方式必须是用户针对当前文件明确选择的 `email` 或 `upload-api`；`server-local` 可作为留存/就地分析结果，但不能声称文件已回传。一次确认不能复用于后续文件。
- 邮件或 API 交付失败时只在当前任务会话报告错误与候选方式；不得自动改名重传、补发状态邮件或改走其他通道。

## 安全注意事项

- 不要把邮箱授权码、密码、Cookie、私钥写入本目录或任何提交文件。
- `.env` 必须保持在 Git 忽略范围内；仓库只提交 `.env.example` 与脱敏说明。
- 代理账号密码与 SMTP 授权码都属于密钥，不写入 README、任务交接文档、邮件模板或测试数据。
- 上传 token 同样只保存在服务器本地 `.env`；工具只显示 `token_set`，并通过权限为 `0600` 的临时 header 文件交给 curl，结束后删除。
- 邮件附件只放 70KB 以内的必要日志，发送前先脱敏路径、账号、机器标识等敏感信息。
- `--send-mail-internal` 是脚本内部配合 `proxychains4` 使用的参数，不应手动调用。
