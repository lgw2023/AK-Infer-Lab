# 邮件与网络配置记录

来源：2026-07-06 09:48 CST 最新服务器邮件，主题为 `[AK服务器] 本机邮件与网络代理配置说明`。

本文件只记录外部开发者可见、可用、可知的非密钥信息。SMTP 授权码、代理账号、代理密码只允许保存在昇腾服务器本地 `.env` 或服务器本机 proxychains 配置中，不写入 Git 仓库。

## 服务器身份

- 主机名：`DevServer-BMS-3d97cc99-0`
- 邮件中报告的主机 IP：`7.150.8.22 / 172.17.0.1`
- 服务器项目根目录：`/data/node0_disk1/liguowei/AK-Infer-Lab`
- 仓库发信脚本：`通信模块/send_notify.py`

## SMTP 发信配置

服务器使用 163 邮箱 SMTP 向外部开发者发送任务状态、日志和附件。

```bash
AK_COMM_SMTP_HOST=smtp.163.com
AK_COMM_SMTP_PORT=465
AK_COMM_SMTP_USER=17621223203@163.com
AK_COMM_SMTP_PASSWORD=<163 SMTP 授权码，仅服务器本地 .env 保存>
AK_COMM_MAIL_FROM=17621223203@163.com
AK_COMM_MAIL_TO=gwlee1995@gmail.com,yilili1023@gmail.com
```

- `AK_COMM_SMTP_PORT=465` 时使用 `SMTP_SSL`。
- 其他端口使用 `STARTTLS`。
- `AK_COMM_MAIL_TO` 支持逗号分隔多个收件人；当前默认同时发给两个邮箱。
- `.env` 位于项目根目录，`send_notify.py` 启动时自动加载，且不会覆盖已经存在的 shell 环境变量。

## 昇腾服务器代理边界

代理只是在昇腾服务器受限网络里需要。普通外部开发机网络通常不需要设置 proxychains 或 HTTP 代理。

服务器邮件确认了两套出站入口：

- SMTP 发信：`proxychains4` 包裹 `python3 通信模块/send_notify.py ...`，内层直连 `smtp.163.com:465`。
- shell 出站：`AK_HTTP_PROXY`、`AK_HTTPS_PROXY`、`AK_FTP_PROXY` 供 `curl`、`wget`、`apt`、`git` 等命令使用。

## proxychains4 配置

昇腾服务器上 `proxychains4` 路径为：

```bash
/usr/bin/proxychains4
```

关键配置事实：

```text
strict_chain
proxy_dns
remote_dns_subnet 224
tcp_read_time_out 15000
tcp_connect_time_out 8000

[ProxyList]
http 172.18.94.109 8080 <proxy_user> <proxy_password>
```

仓库脚本支持用 `AK_COMM_PROXYCHAINS_CONFIG` 指定配置文件：

```bash
AK_COMM_USE_PROXYCHAINS=1
AK_COMM_PROXYCHAINS_BIN=proxychains4
AK_COMM_PROXYCHAINS_CONFIG=/etc/proxychains4.conf
AK_COMM_PAYLOAD_DIR=/tmp
```

普通外部开发机若网络可直连 SMTP，可设置 `AK_COMM_USE_PROXYCHAINS=0` 或运行时加 `--no-proxy`。

## Shell HTTP 代理

昇腾服务器本地 `.env` 可保存 shell 层代理入口。以下值只展示格式，不包含真实账号密码：

```bash
AK_HTTP_PROXY=http://<proxy_user>:<proxy_password>@proxysg.huawei.com:8080/
AK_HTTPS_PROXY=http://<proxy_user>:<proxy_password>@proxysg.huawei.com:8080/
AK_FTP_PROXY=http://<proxy_user>:<proxy_password>@proxysg.huawei.com:8080/
AK_NO_PROXY=localhost,127.0.0.1,::1,*.huawei.com,*.huaweicloud.com
```

这些变量不会自动替代 `http_proxy`、`https_proxy`、`ftp_proxy`。需要给 shell 工具使用时，由服务器操作员在 shell 中显式 export。

## 常用检查命令

脱敏查看当前通信配置，不发送邮件：

```bash
python3 通信模块/send_notify.py --show-config
```

发送测试邮件：

```bash
python3 通信模块/send_notify.py --test
```

绕过 proxychains 直连 SMTP 测试：

```bash
python3 通信模块/send_notify.py --test --no-proxy
```

## 安全规则

- 不提交 `.env`。
- 不把 SMTP 授权码、代理账号、代理密码写入 README、任务交接文档、邮件模板、测试数据或工作笔记。
- 如授权码或代理密码轮换，同步更新昇腾服务器本地 `.env` 与 `/etc/proxychains4.conf`，再通过脱敏邮件说明“已轮换”，不要邮件发送明文密钥。
