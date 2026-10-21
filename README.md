# 工学云管理平台

基于原项目 [27xk/gongxueyun](https://github.com/27xk/gongxueyun) 修改，感谢原作者和贡献者。

## 主要功能

- 自动上下班打卡、手动补卡。
- 日报、周报、月报管理。
- 支付宝授权二维码和链接。
- 邮箱授权提醒及异常恢复通知。
- PushPlus 微信通知：可设 ClawBot → 微信公众号 → 邮箱保底，未确认投递也会降级，可能重复提醒。在「系统设置 → 微信 PushPlus」配置，凭据加密保存。授权二维码上传需官方图片服务权限，失败时仍发送授权链接。

## 启动（Windows / Linux / macOS）

准备 Python 3.11+（CI / Docker 使用 3.12）、满足前端依赖要求的 Node.js 和 MySQL 8。在**项目根目录**创建虚拟环境：

```sh
python -m venv .venv
```

激活环境：Windows PowerShell 执行 `.\.venv\Scripts\Activate.ps1`；Linux / macOS 执行 `source .venv/bin/activate`。

首次部署将 `.env.example` 复制为 `.env`，已有配置不要覆盖。填写自己的 `DATABASE_URL`、`APP_SECRET`、`USER_PASSWORD_KEY`、`ADMIN_USERNAME` 和 `ADMIN_PASSWORD`，确保 MySQL 可连接。

仅本地 HTTP 开发时设置 `APP_ENV=development`、`AUTH_COOKIE_SECURE=false`、`ENABLE_HSTS=false`；线上部署使用 HTTPS 并配置可信域名，详见后端说明。

激活环境后，在项目根目录执行：

```sh
python -m pip install -r server/requirements.txt
npm --prefix web ci
npm --prefix web run build
python -m alembic upgrade head
python -m uvicorn server.main:app --host 127.0.0.1 --port 8147
```

打开 [管理端](http://localhost:8147/login) 或 [用户端](http://localhost:8147/u/login)。远程部署的域名、HTTPS 和进程管理参见后端说明。

停止：在运行终端按 **Ctrl+C**；重启时重新执行最后一条命令。以上方式不设置开机启动，也不会停止独立运行的 MySQL。

### 前端开发

上面的 `npm --prefix web run build` 会生成前端页面，由后端在 **8147** 端口提供，无需另外启动前端。

需要修改页面时，保持后端运行，另开终端在项目根目录执行：

```sh
npm --prefix web ci
npm --prefix web run dev
```

打开 [开发管理端](http://localhost:5173/login) 或 [开发用户端](http://localhost:5173/u/login)。开发服务默认将 `/api` 代理到 `http://127.0.0.1:8147`；它不能替代后端。停止同样按 **Ctrl+C**。

## 使用说明

1. 配置工学云账号、实际地址和上下班时间，启用自动打卡。
2. 如需邮件提醒，在系统设置及账号通知中启用并配置邮箱。
3. 遇到验证时本人扫码完成，再点击“我已完成授权，仅检查记录”。

验证后仅回查，不会重复提交签到。是否成功以服务端考勤记录为准，授权完成不等于签到成功。

## 相关文档
- [前端开发说明](./web/README.md)
- [后端部署说明](./server/README.md)

非官方项目，不保证免验证或每次打卡成功。保留原项目 [GPL v3 许可证](./LICENSE)。
