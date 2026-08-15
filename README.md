# TG Archive

**Telegram 频道内容自动归档到云盘**

自动监控 Telegram 频道，将媒体文件（视频、图片、文档）下载并上传到云存储，支持多种云盘后端。

![License](https://img.shields.io/badge/license-MIT-blue)
![Python](https://img.shields.io/badge/python-3.10+-green)
![React](https://img.shields.io/badge/react-18-blue)

## ✨ 特性

- 📡 **自动监控** — 实时监听 Telegram 频道新消息
- ☁️ **多云盘支持** — 123云盘、本地存储，架构可扩展
- 🖥️ **Web 管理界面** — 配置任务、查看状态、浏览日志
- 📊 **实时状态面板** — 传输进度、速度、历史统计
- 🔄 **断点续传** — 自动重试失败任务，支持分片上传
- 📁 **智能整理** — 按频道/日期自动创建目录结构
- 🔐 **安全认证** — WebUI 登录保护
- 🐳 **Docker 部署** — 一键启动

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

访问 `http://localhost:3000` 打开管理界面。

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

# 云盘类型: pan123 | local
CLOUD_TYPE=pan123
PAN123_ACCESS_TOKEN=your_token

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
