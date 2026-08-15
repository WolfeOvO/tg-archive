# TG Archive

**Telegram 频道内容自动归档到云盘**

自动监控 Telegram 频道，将媒体文件（视频、图片、文档）下载并上传到云存储，支持多种云盘后端。

![License](https://img.shields.io/badge/license-MIT-blue)
![Python](https://img.shields.io/badge/python-3.10+-green)
![React](https://img.shields.io/badge/react-18-blue)

## ✨ 特性

- 📡 **自动监控** — 实时监听 Telegram 频道新消息
- 🔔 **多渠道通知** — 归档状态可发送到 Telegram Bot、Discord、QQ Bot（OneBot v11）和通用 Webhook
- ☁️ **OpenList 多挂载** — 实时加载 OpenList 全部驱动，每个挂载点独立配置并可作为任务目标
- 🖥️ **Web 管理界面** — 配置任务、查看状态、浏览日志
- 📊 **实时状态面板** — 传输进度、速度、历史统计
- 🔄 **断点续传** — 自动重试失败任务，支持分片上传
- 📁 **智能整理** — 按频道/日期自动创建目录结构
- 🔐 **安全认证** — WebUI 登录保护
- 🐳 **Docker 部署** — 一键启动

### 消息通知

在 WebUI 的“设置 → 消息通知”中可同时绑定多个渠道：

- **Telegram Bot**：填写 Bot Token 与 Chat ID，可发送到私聊、群组或频道
- **Discord**：填写频道 Incoming Webhook URL
- **QQ Bot**：兼容 NapCat、Lagrange 等提供的 OneBot v11 HTTP 接口，支持群聊和私聊
- **通用 Webhook**：发送结构化 JSON；配置密钥后附带 `X-TG-Archive-Signature` HMAC-SHA256 签名

通知事件可独立选择：单文件成功、单文件失败、扫描摘要和重试摘要。各渠道并发发送且相互隔离，通知失败不会阻塞归档。后台绑定信息保存到 `data/notifications.json`（权限 `0600`），也可通过 `.env` 中的 `NOTIFICATION_*` 变量提供首次启动默认值。

## 📸 截图

| 管理面板 | 任务状态 |
|---------|---------|
| Dashboard | Task Monitor |

## 🚀 快速开始

### Docker 部署（推荐）

```bash
git clone https://github.com/WolfeOvO/tg-archive.git
cd tg-archive

# 编辑配置
cp .env.example .env
vim .env

# 启动
docker compose up -d
```

访问 `http://localhost:8000` 打开管理界面。

### 手动安装

```bash
# 后端
cd backend
pip install -r requirements.txt
cp ../.env.example ../.env
# 编辑 .env 配置
uvicorn main:app --host 0.0.0.0 --port 8000

# 前端
cd frontend
npm install
npm run dev
```

## ⚙️ 配置

复制 `.env.example` 为 `.env` 并填写：

```env
# Telegram API（从 https://my.telegram.org 获取）
TG_API_ID=12345678
TG_API_HASH=abcdef1234567890abcdef1234567890
TG_SESSION_STRING=your_session_string

# 目标频道（用户名或 ID）
TG_CHANNEL=@your_channel

# OpenList 管理连接（挂载点在 WebUI 中创建，初始为空）
OPENLIST_URL=http://openlist:5244
OPENLIST_USERNAME=admin
OPENLIST_PASSWORD=your_openlist_admin_password
OPENLIST_DEFAULT_MOUNT_ID=

# WebUI 管理密码
ADMIN_PASSWORD=your_secure_password
```

### 获取 Telegram Session String

```bash
cd backend
python -c "
from telethon import TelegramClient
import asyncio

async def main():
    client = TelegramClient('session', API_ID, API_HASH)
    await client.start()
    string = client.session.save()
    print(f'Session string: {string}')

asyncio.run(main())
"
```

## 📖 API 文档

启动后端后访问 `http://localhost:8000/docs` 查看 Swagger API 文档。

### 主要接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/login` | 登录获取 token |
| GET | `/api/status` | 系统状态概览 |
| GET | `/api/tasks` | 任务列表 |
| GET | `/api/tasks/{id}` | 任务详情 |
| POST | `/api/tasks/rescan` | 重新扫描频道 |
| GET | `/api/storage/drivers` | OpenList 实时驱动目录 |
| GET | `/api/storage/mounts` | 存储挂载点列表 |
| POST | `/api/storage/mounts` | 创建存储挂载点 |
| GET | `/api/config` | 获取配置 |
| PUT | `/api/config` | 更新配置 |
| GET | `/api/logs` | 操作日志 |
| GET | `/api/stats` | 统计数据 |

## 🏗️ 架构

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Telegram   │────▶│   Archiver   │────▶│ Cloud Storage│
│   Channel    │     │   (Core)     │     │  (123pan/…)  │
└─────────────┘     └──────┬───────┘     └─────────────┘
                           │
                    ┌──────┴───────┐
                    │   SQLite DB   │
                    └──────┬───────┘
                           │
                    ┌──────┴───────┐
                    │  FastAPI +    │
                    │  React WebUI  │
                    └──────────────┘
```

### 核心模块

- **TelegramClient** — 连接 Telegram，监听频道消息
- **Archiver** — 协调下载 → 上传 → 记录的完整流程
- **CloudStorage** — 可插拔的云存储后端接口
- **Scheduler** — 定时任务调度（扫描、重试）
- **WebUI** — React 管理界面 + FastAPI REST API

## 🗂️ 目录结构

```
tg-archive/
├── backend/              # Python 后端
│   ├── main.py           # FastAPI 入口
│   ├── config.py         # 配置管理
│   ├── database.py       # 数据库连接
│   ├── models.py         # SQLAlchemy 模型
│   ├── api/              # REST API 路由
│   ├── core/             # 核心业务逻辑
│   └── storage/          # 云存储后端
├── frontend/             # React 前端
│   └── src/
│       ├── pages/        # 页面组件
│       └── components/   # 通用组件
├── docker-compose.yml
└── .env.example
```

## 🔌 扩展云存储后端

继承 `storage/base.py` 的 `CloudStorageBase` 即可添加新后端：

```python
from storage.base import CloudStorageBase

class MyCloudStorage(CloudStorageBase):
    async def upload_file(self, local_path, remote_path):
        ...
    async def file_exists(self, remote_path):
        ...
    async def get_storage_info(self):
        ...
```

然后在 `config.py` 中注册即可。

## 📄 License

MIT License - 自由使用、修改和分发。

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建功能分支 (`git checkout -b feature/amazing`)
3. 提交更改 (`git commit -m 'Add amazing feature'`)
4. 推送分支 (`git push origin feature/amazing`)
5. 创建 Pull Request
