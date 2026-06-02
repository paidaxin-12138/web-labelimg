# Web LabelImg 2.0

可部署、可协作、可审核的 Web 图像标注平台，面向目标检测数据集标注。

> 旧版 1.x（单 HTML + 文件存储）仍保留在 `by_self_web/` 与 `static/`，见文末说明。

## 功能概览

| 能力 | 2.0 状态 |
|------|----------|
| JWT 用户认证（admin / reviewer / annotator） | ✅ |
| 项目管理、成员、图像批量上传 | ✅ |
| 矩形标注（Konva 绘制、拖拽、8 点 resize） | ✅ |
| 撤销/重做（50 步）、快捷键 | ✅ |
| 乐观锁 + 标注版本历史 | ✅ |
| WebSocket 实时协作（在线用户、光标、标注广播） | ✅ |
| YOLO 异步导出 | ✅ |
| 暗黑主题 | ✅ |
| Docker Compose 一键部署 | ✅ |
| 多边形 / 点 / 折线 | 🔜 Phase 2 |
| COCO / VOC 导出、版本回滚 UI | 🔜 Phase 2 |
| 审核流程、仪表盘 | 🔜 Phase 3 |

## 快速启动

### 方式一：本地开发（推荐）

```bash
cp .env.example .env          # 可选，首次会自动复制到 backend/.env
./start.sh
```

| 入口 | 地址 |
|------|------|
| 前端 | http://localhost:5173 |
| API 文档 | http://localhost:8000/docs |
| 健康检查 | http://localhost:8000/health |
| 指标 | http://localhost:8000/metrics |

**默认管理员**（首次 `seed` 自动创建）：

- 邮箱：`admin@example.com`
- 密码：`admin123`

### 方式二：Docker Compose

```bash
cp .env.example .env
docker compose up -d --build
```

访问 http://localhost（Nginx 反代前端 + API + WebSocket）

启用监控（可选）：

```bash
docker compose --profile monitoring up -d
# Prometheus: http://localhost:9090
# Grafana:    http://localhost:3000
```

### 方式三：分别启动

```bash
# 后端
cd backend
python3 -m pip install -r requirements.txt
mkdir -p data/storage
PYTHONPATH=. python3 scripts/seed.py
PYTHONPATH=. python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# 前端（新终端）
cd frontend
npm install
npm run dev
```

## 环境要求

| 组件 | 版本 | 说明 |
|------|------|------|
| Python | 3.9+ | 后端 |
| Node.js | 20+ | 前端构建 |
| Redis | 7+ | 生产推荐；本地无 Redis 时自动降级为内存锁 |
| PostgreSQL | 16+ | 生产；开发默认 SQLite |

## 环境变量

完整模板见 [.env.example](.env.example)，复制到 `backend/.env` 或项目根目录 `.env`。

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/labelimg.db` | 数据库连接 |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis |
| `JWT_SECRET` | — | **生产必须修改** |
| `STORAGE_BACKEND` | `local` | `local` 或 `s3` |
| `LOCAL_STORAGE_PATH` | `./data/storage` | 本地对象存储根目录 |
| `S3_ENDPOINT` / `S3_BUCKET` 等 | — | MinIO / OSS 配置 |
| `LOCK_TTL_SECONDS` | `120` | 图像编辑锁超时（秒） |
| `CORS_ORIGINS` | `http://localhost:5173,...` | 允许的前端来源 |

## 项目结构

```
web-labelimg-main/
├── backend/                 # FastAPI 2.0 后端
│   ├── app/
│   │   ├── api/v1/          # REST 路由
│   │   ├── ws/              # WebSocket 协作
│   │   ├── models/          # SQLAlchemy ORM
│   │   ├── services/        # 业务逻辑
│   │   └── storage/         # 本地 / S3 存储抽象
│   ├── scripts/
│   │   ├── seed.py          # 初始化管理员
│   │   └── migrate_legacy.py
│   └── tests/
├── frontend/                # Vue 3 + TypeScript + Konva
│   └── src/
│       ├── views/           # 登录、项目、标注页
│       ├── stores/          # Pinia（auth / annotation / collaboration）
│       └── components/canvas/
├── by_self_web/             # 【旧版 1.x】FastAPI 单体
├── static/                  # 【旧版 1.x】单页 HTML 前端
├── nginx/                   # 反向代理配置
├── docker-compose.yml
├── start.sh                 # 本地一键启动
├── API.md                   # API 与 WebSocket 说明
└── MIGRATION.md             # 1.x → 2.0 迁移指南
```

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3、TypeScript、Vite、Pinia、Vue Router、Konva |
| 后端 | FastAPI、SQLAlchemy 2（async）、Pydantic v2、JWT |
| 数据库 | SQLite（开发）/ PostgreSQL（生产） |
| 缓存/锁 | Redis（可选，无则内存降级） |
| 对象存储 | 本地目录 / S3 兼容（MinIO） |
| 部署 | Docker Compose、Nginx、Prometheus（可选） |

## 使用流程

1. 登录 → 创建项目
2. 进入项目 → **上传** 图像（支持多选）
3. 选择图像 → 用 **矩形** 工具绘制边界框
4. 拖拽移动框、拖动 8 个控制点调整大小
5. **Ctrl+S** 保存，**Ctrl+Z / Ctrl+Y** 撤销重做
6. 多人协作：打开两个浏览器窗口，可看到彼此光标与标注实时变化
7. **导出 YOLO** → 后台生成 zip（`labels/*.txt` + `classes.txt`）

## 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Ctrl+Z` | 撤销 |
| `Ctrl+Y` / `Ctrl+Shift+Z` | 重做 |
| `Ctrl+S` | 保存标注 |
| `?` | 显示/隐藏快捷键面板 |

## 测试

```bash
# 后端
cd backend
PYTHONPATH=. python3 -m pytest tests/ -v

# 前端
cd frontend
npm test
npm run build
```

CI 配置见 [.github/workflows/ci.yml](.github/workflows/ci.yml)。

## 从 1.x 迁移

旧版数据在 `Self-study/xz_data/`，详见 [MIGRATION.md](MIGRATION.md)。

## 旧版 Web LabelImg 1.x

仍可直接运行，适合轻量内网标注：

```bash
cd by_self_web
python3 -m pip install -r requirements.txt
python3 main.py
# 访问 http://localhost:8000
```

特点：单文件 HTML 前端、文件系统存储、Session 锁协作，无需数据库。

## 文档

- [API.md](API.md) — REST 与 WebSocket 协议
- [MIGRATION.md](MIGRATION.md) — 数据迁移
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — 架构说明
- [博客.md](博客.md) — 项目介绍（含 1.x 历史）

## 路线图

- **Phase 1（当前）**：MVP 基础平台 ✅
- **Phase 2**：多形状标注、COCO/VOC、版本回滚 UI、移动端手势
- **Phase 3**：审核流、统计仪表盘、生产级 S3 + 监控

## License

开源项目，使用前请阅读仓库 License 文件（如有）。
