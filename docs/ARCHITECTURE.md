# Web LabelImg 2.0 架构说明

## 系统架构

```
┌─────────────────────────────────────────────────────────┐
│  Browser (Vue 3 + Pinia + Konva)                        │
│  Login → Projects → Annotate (Canvas + Sidebar)         │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP /api/v1  +  WS /ws/projects/{id}
┌────────────────────────▼────────────────────────────────┐
│  Nginx (可选，生产)                                       │
└────────────────────────┬────────────────────────────────┘
                         │
        ┌────────────────┼────────────────┐
        ▼                ▼                ▼
   FastAPI API       Redis            PostgreSQL
   (REST + WS)    (锁/可选 PubSub)   (元数据/标注历史)
        │
        ▼
   Object Storage (local / MinIO / S3)
   原图 + 缩略图 + 导出 zip
```

## 后端模块

| 目录 | 职责 |
|------|------|
| `app/api/v1/` | REST 路由（auth、projects、images、annotations） |
| `app/ws/` | WebSocket 协作（房间、锁、广播） |
| `app/models/` | SQLAlchemy ORM 表定义 |
| `app/schemas/` | Pydantic 请求/响应模型 |
| `app/services/` | 标注保存、导出、Redis 锁 |
| `app/storage/` | Local / S3 存储抽象 |

## 数据库表

| 表 | 说明 |
|----|------|
| `users` | 用户与全局角色 |
| `projects` | 标注项目 |
| `project_members` | 项目成员与角色 |
| `images` | 图像元数据 + `version` 乐观锁 |
| `labels` | 项目标签（class_id、颜色） |
| `annotation_versions` | 标注历史（JSONB） |
| `reviews` | 审核记录（Phase 3） |
| `export_jobs` | 异步导出任务 |

## 协作流程

1. 用户 WebSocket 连接项目房间（带 JWT）
2. `join_image` → Redis 尝试获取编辑锁（120s TTL）
3. 主编辑者绘制/移动框 → WS 广播 `annotation_*`
4. 协作者只读渲染，可见 `cursor_move`
5. 主编辑者 `PUT /annotations` 持久化（`base_version` 乐观锁）
6. `leave_image` 或断线 → 释放锁

## 前端 Store

| Store | 职责 |
|-------|------|
| `auth` | JWT、当前用户 |
| `project` | 项目列表、图像、标签 |
| `annotation` | 标注数据、undo/redo 栈 |
| `collaboration` | WebSocket、在线用户、光标 |
| `ui` | 主题、快捷键面板 |

## 部署拓扑（Docker Compose）

| 服务 | 端口 | 说明 |
|------|------|------|
| nginx | 80 | 统一入口 |
| api | 8000 | FastAPI |
| frontend | 5173→80 | Vue 静态资源 |
| postgres | 5432 | 生产数据库 |
| redis | 6379 | 分布式锁 |
| minio | 9000/9001 | S3 兼容存储（可选） |
| prometheus | 9090 | 监控（profile） |
| grafana | 3000 | 看板（profile） |

更多细节见 [README.md](../README.md) 与 [API.md](../API.md)。
