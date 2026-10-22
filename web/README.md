# 工学云管理平台前端

基于 [27xk/gongxueyun](https://github.com/27xk/gongxueyun) 修改。使用 Vue 3、Vite、Pinia、Vue Router 和 Element Plus，包含管理端与用户端。

## 开发启动

需要 Node.js 和 npm；当前锁定的 Vite 要求 Node.js `^20.19.0 || >=22.12.0`。下面命令均从**项目根目录**执行。

先按 [项目说明](../README.md) 配置并启动后端，然后另开终端：

```sh
npm --prefix web ci
npm --prefix web run dev
```

- 管理端：[localhost:5173/login](http://localhost:5173/login)。
- 用户端：[localhost:5173/u/login](http://localhost:5173/u/login)。
- 保存前端源码后 Vite 会更新页面；停止开发服务按 **Ctrl+C**。
- 前端开发服务默认监听 `0.0.0.0:5173`，端口占用时会报错，不会自动换端口。不要将开发服务器直接作为公网生产服务。

## 后端连接

前端请求统一使用 `/api`，开发时由 Vite 代理到 `http://127.0.0.1:8147`。只有页面能打开不代表后端已经运行；账号登录、任务和数据库均依赖后端。

后端地址不同时，可在 `web/.env.local` 写入：

```dotenv
VITE_API_PROXY_TARGET=http://127.0.0.1:8147
```

将示例地址改为实际后端地址后，重启前端开发服务。该配置仅控制 Vite 开发 / 预览代理，不会替生产服务器配置反向代理。不要把密码或 token 放进 `VITE_*` 变量。

本地开发保持浏览器地址中的 `localhost` 或 `127.0.0.1` 一致，避免 Cookie 混用；后端本地 HTTP 配置见根 README。远程前后端分离时，还需正确配置后端的可信域名、Origin、HTTPS 和 Cookie。

## 构建与部署

```sh
npm --prefix web ci
npm --prefix web run build
```

产物位于 `web/dist`。本项目后端会提供这个目录，启动后端后通过 **8147** 端口访问完整应用，不必同时运行 Vite。

如果用 Nginx 等单独提供前端静态文件，需要将 `/api` 反向代理到后端，并为 Vue Router 配置页面回退到 `index.html`。正式环境使用 HTTPS；不要把 `npm run preview` 当作生产部署方案。

## 页面与关键功能

| 入口 | 说明 |
| --- | --- |
| `/login` | 管理端登录 |
| `/` | 会话分流及管理端用户列表 |
| `/settings` | 系统设置、SMTP 和 AI 配置 |
| `/u/login`、`/u/register` | 用户登录 / 注册，注册受后端开关控制 |
| `/u`、`/u/settings` | 用户工作台与个人配置 |

任务状态面板显示下次执行、最近结果、验证事务和回查状态。需要支付宝验证时可查看二维码、复制链接，后台每 3 秒检测授权状态，官方确认后自动用已保存的原请求续提一次，无需点击续提。超时或结果不确定不重复发送，成功以服务端记录为准；旧事务缺少上下文时仅回查。

旧预授权页面属于兼容入口，本地“已授权”不代表未来每次考勤已获得官方授权。SMTP 设置仅显示是否已配置授权码，输入留空保留服务端原值。

## 检查命令

```sh
npm --prefix web run lint
npm --prefix web test
npm --prefix web run build
```

`lint` / `test` 当前运行项目的静态质量检查，不是浏览器端到端测试。开发代理、实际账号和官方验证仍需要分别验证。

## 目录

- `src/views/`：管理端与用户端页面。
- `src/components/`：共享组件及 `TaskStatusPanel.vue`。
- `src/api/`：两端请求实例、Cookie / CSRF 处理。
- `src/router/`、`src/stores/`：路由和独立登录态。
- `src/styles/`：样式；`vite.config.js`：构建与代理配置。

返回 [项目 README](../README.md)。许可证沿用原项目 [GPL v3](../LICENSE)。
