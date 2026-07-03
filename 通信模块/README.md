# 通信模块：开发机与服务器消息传递

本目录是项目内的“开发机 ↔ 服务器”通讯子项目，用于在服务器外联受限时维持最小可用协作链路。

## 通信约束与方向

- **服务器 → 开发人员**：服务器只能通过邮件向外发消息，使用 `send_notify.py` 发送状态、日志、告警或附件。
- **开发机 → 服务器**：开发人员直接在本目录写 Markdown/文本文档并提交，服务器通过 `git pull` 获取这些文档信息。
- **不在仓库保存密钥**：SMTP 账号、授权码、默认收件人全部通过环境变量注入。

## 文件说明

- `send_notify.py`：服务器侧发信脚本，默认使用 `smtp.163.com:465`，并通过 `proxychains4` 发信。
- `docs/developer-to-server.md`：开发机写给服务器读取的消息模板。
- `docs/server-to-developer.md`：服务器邮件通知的主题和正文模板。

## 服务器侧配置

在昇腾服务器的项目根目录复制模板并填写真实 SMTP 信息：

```bash
cd <项目根目录>
cp .env.example .env
# 编辑 .env，填入真实 163 邮箱与 SMTP 授权码
```

`.env` 只保留在服务器本地，不提交到仓库。`send_notify.py` 启动时会自动读取项目根目录 `.env`，且不会覆盖 shell 中已经存在的环境变量。

`.env` 中的必填项：

```bash
AK_COMM_SMTP_HOST=smtp.163.com
AK_COMM_SMTP_PORT=465
AK_COMM_SMTP_USER=你的 163 邮箱地址
AK_COMM_SMTP_PASSWORD=你的 163 SMTP 授权码
AK_COMM_MAIL_FROM=通常与 AK_COMM_SMTP_USER 相同
AK_COMM_MAIL_TO=gwlee1995@gmail.com,yilili1023@gmail.com
```

可选配置：

```bash
AK_COMM_USE_PROXYCHAINS=1      # 默认 1；设为 0/false/no 则直连 SMTP
AK_COMM_PROXYCHAINS_BIN=proxychains4
AK_COMM_PAYLOAD_DIR=/tmp
```

## 常用命令

发送连通性测试邮件：

```bash
python3 通信模块/send_notify.py --test
```

发送一条任务完成通知：

```bash
python3 通信模块/send_notify.py -s "任务完成" -b "训练已结束，loss=0.12"
```

从文件读取正文并附加日志：

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
3. 服务器执行 `git pull` 后读取本目录文档。
4. 服务器如需反馈，运行 `send_notify.py` 将结果发到开发人员邮箱。

## 双向协作约束

- 昇腾服务器只执行 `git pull`，不从服务器 push。
- 昇腾服务器不直接修改仓库内项目代码；如需改代码，用 `send_notify.py` 发邮件说明需求、复现方式和期望行为。
- 外部开发机完成代码或文档改动后提交并 push，服务器再 pull 同步。
- 服务器本地独立脚本 `/data/node0_disk1/Public/send_notify.py` 不属于本仓库；仓库内统一使用 `通信模块/send_notify.py`。

## 安全注意事项

- 不要把邮箱授权码、密码、Cookie、私钥写入本目录或任何提交文件。
- 邮件附件只放必要日志，发送前先脱敏路径、账号、机器标识等敏感信息。
- `--send-mail-internal` 是脚本内部配合 `proxychains4` 使用的参数，不应手动调用。
