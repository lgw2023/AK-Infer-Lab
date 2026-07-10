# 用户确认式服务器文件传输实施计划

日期：2026-07-10

依据：`docs/superpowers/specs/2026-07-10-user-confirmed-server-file-transfer-design.md`

状态：已完成开发机侧实现与验证；真实昇腾服务器通路待用户针对具体文件授权后预检。

## 目标

在不改变现有邮件脚本和当前服务器交接任务的前提下，新增一个受用户确认门保护的上传 API 工具，并把 `email`、`upload-api`、`server-local` 三种回传方式统一写入稳定通信规则。

## 实施步骤

1. 在 `tests/communication/test_upload_file.py` 先定义确认门、脱敏配置、大小边界、代理命令、HTTP/SHA-256 验收及错误处理契约。
2. 新增 `通信模块/upload_file.py`，实现只读检查、脱敏配置、预检和正式上传；上传命令不包含明文 token，且不自动重试或切换通道。
3. 更新 `.env.example`、`通信模块/README.md`，新增 `通信模块/docs/file-transfer-policy.md`，同步 `server-to-developer.md` 与 `AGENTS.md`。
4. 在 `工作记录与进度笔记本/01_工作记录.md` 记录本轮启动、完成、验证结果和真实服务器尚未验证的边界。
5. 运行通信测试、推理契约回归、Python 编译、敏感信息扫描与 `git diff --check`；比较 `通信模块/docs/developer-to-server.md` 的实施前后 SHA-256，确认当前交接内容未被本轮改变。

## 验收命令

```bash
python -m pytest tests/communication -q
python -m pytest tests/inference_contracts -q
python -m py_compile 通信模块/send_notify.py 通信模块/upload_file.py
rg -n 'AK_COMM_UPLOAD_TOKEN=[A-Za-z0-9_-]{20,}' . --glob '!reference_repos/**'
git diff --check
```

真实上传和真实昇腾服务器 proxychains 预检不属于本轮本地实施；后续只有用户针对具体文件明确选择 `upload-api` 后才执行。
