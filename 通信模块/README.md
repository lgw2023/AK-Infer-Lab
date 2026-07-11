# 通信模块：开发机与服务器消息传递

本目录是项目内的“开发机 ↔ 服务器”通讯子项目，用于在服务器外联受限时维持最小可用协作链路，并在用户明确选择后回传必要文件。

## 通信约束与方向

- **服务器 → 开发人员状态消息**：使用 `send_notify.py` 发送状态、精简日志和告警；正文不超过 70KB。
- **服务器 → 开发人员文件**：完成交付使用 `email + 小附件` 或 `upload-api + 文本总结/文件`；`server-local` 只是大文件或敏感原始数据的留存状态，不等于附件已交付。任何附件或 API 上传前必须由用户针对具体文件明确选择。
- **开发机 → 服务器**：开发人员直接在本目录写 Markdown/文本文档并提交，服务器通过服务器本地 `git pull-remote` 获取这些文档信息。
- **通信容量上限**：昇腾服务器每次邮件正文和每个附件都按不超过 70KB 处理；不要通过邮件回传 raw profiler、长日志、模型输出、实验目录或其他大文件。
- **大数据留在服务器**：实验产生的大规模数据只能留在昇腾服务器上；如需分析大数据，由外部开发者（本机）在 `docs/developer-to-server.md` 下达服务器本地分析任务，服务器只邮件回传精简摘要、小清单、少量样例和服务器路径。
- **用户确认门**：传输前报告路径、大小、敏感性、候选方式和建议理由；没有明确选择就不传，失败后也不得自动切换方式。
- **不在仓库保存密钥**：SMTP 账号和授权码通过环境变量注入；默认收件人可通过环境变量覆盖。
- **代理只属于昇腾服务器受限网络**：普通外部开发机网络通常不需要 proxychains 或 HTTP 代理。

## 文件说明

- `send_notify.py`：服务器侧发信脚本，默认使用 `smtp.163.com:465`，并在昇腾服务器上通过 `proxychains4` 发信。
- `upload_file.py`：用户选择 `upload-api` 后使用的单文件检查/上传工具；支持脱敏配置、100MB 默认保护、HTTP 201 与 SHA-256 双校验；2026-07-10 已在真实昇腾服务器通过 proxychains4 完成预检和首个汇总文件回传。
- `docs/developer-to-server.md`：开发机写给服务器读取的消息模板。
- `docs/server-to-developer.md`：服务器邮件通知的主题和正文模板。
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

发送连通性测试邮件：

```bash
python3 通信模块/send_notify.py --test
```

发送一条任务完成通知：

```bash
python3 通信模块/send_notify.py -s "任务完成" -b "训练已结束，loss=0.12"
```

只读检查待传文件，不访问网络：

```bash
python3 通信模块/upload_file.py --inspect /path/to/result.zip
```

脱敏查看上传配置，不访问网络：

```bash
python3 通信模块/upload_file.py --show-config
```

用户已经针对该任务选择 `upload-api` 后，在昇腾服务器先做小文件预检：

```bash
python3 通信模块/upload_file.py --preflight --confirmed-method upload-api
```

预检通过后上传用户确认的唯一文件：

```bash
python3 通信模块/upload_file.py \
  --upload /path/to/result.zip \
  --confirmed-method upload-api
```

普通公网机器确认可直连时可加 `--no-proxy`。超过 100MB 默认拒绝；只有用户明确接受可能的 `413` 风险后才可加 `--allow-over-100mb`，该参数不保证服务端接受。

从文件读取正文并附加小日志（正文和附件均需不超过 70KB）：

```bash
python3 通信模块/send_notify.py -s "运行日志" --body-file /tmp/run.log --attach /tmp/run.log
```

在确认服务器可直连 SMTP 时绕过代理：

```bash
python3 通信模块/send_notify.py --test --no-proxy
```

## 开发机到服务器的文档流

1. 开发人员在 `docs/developer-to-server.md` 追加或更新指令、问题、实验计划。
2. 开发人员提交并推送仓库。
3. 服务器执行本地 alias `git pull-remote` 后读取本目录文档；该 alias 指向服务器本地 `server_local/git_pull_remote_wins.sh`，执行 `fetch + reset --hard origin/main`，让已跟踪文件以远端为准，同时保留未跟踪实验产物、conda 环境和服务器本地脚本。
4. 服务器如需反馈，可直接发送 70KB 内的状态正文；若涉及文件，先回报文件清单、大小、敏感性与建议的外部交付方式（`email` 或 `upload-api`），等待用户选择。已选定范围不得被“仅发正文”默默取代。
5. 用户选择后，开发机在当前任务交接中记录选定方式和文件范围；服务器只执行该方式，不自动扩展范围或切换通道。

## 双向协作约束

- 昇腾服务器只从远端同步，不从服务器 push；日常同步使用服务器本地 `git pull-remote`。
- 昇腾服务器不直接修改仓库内项目代码；如需改代码，用 `send_notify.py` 发邮件说明需求、复现方式和期望行为。
- 外部开发机完成代码或文档改动后提交并 push，服务器再 pull 同步。
- `server_local/`、`.conda/` 和实验产物只属于服务器本地，不提交到仓库。
- 服务器本地独立脚本 `/data/node0_disk1/Public/send_notify.py` 不属于本仓库；仓库内统一使用 `通信模块/send_notify.py`。
- 服务器邮件只适合回传 70KB 以内的小摘要、小清单、少量样例和路径；大规模实验数据、原始 profiler、完整日志和大 zip 都保留在服务器本地。
- 外部开发机需要基于大数据继续判断时，应把分析步骤写成新的服务器任务，让服务器就地处理后再返回小结果。
- 对外文件回传方式必须是用户针对当前文件明确选择的 `email` 或 `upload-api`；`server-local` 可作为留存/就地分析结果，但不能声称文件已回传。一次确认不能复用于后续文件。
- API 上传失败时只报告错误与候选方式；不得自动改名重传、改发邮件或改走其他通道。

## 安全注意事项

- 不要把邮箱授权码、密码、Cookie、私钥写入本目录或任何提交文件。
- `.env` 必须保持在 Git 忽略范围内；仓库只提交 `.env.example` 与脱敏说明。
- 代理账号密码与 SMTP 授权码都属于密钥，不写入 README、任务交接文档、邮件模板或测试数据。
- 上传 token 同样只保存在服务器本地 `.env`；工具只显示 `token_set`，并通过权限为 `0600` 的临时 header 文件交给 curl，结束后删除。
- 邮件附件只放 70KB 以内的必要日志，发送前先脱敏路径、账号、机器标识等敏感信息。
- `--send-mail-internal` 是脚本内部配合 `proxychains4` 使用的参数，不应手动调用。
