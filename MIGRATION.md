# Web LabelImg 1.x → 2.0 迁移指南

本文说明如何从旧版（文件存储 + Session 锁）迁移到 2.0（数据库 + JWT + WebSocket）。

## 版本对比

| 项目 | 1.x | 2.0 |
|------|-----|-----|
| 前端 | `static/index.html` 单文件 | `frontend/` Vue 3 + Konva |
| 后端 | `by_self_web/main.py` | `backend/app/` 分层架构 |
| 存储 | 本地文件夹 JSON/TXT | SQLite/PostgreSQL + 对象存储 |
| 认证 | 浏览器 localStorage 姓名 | JWT（邮箱 + 密码） |
| 协作 | 文件锁 `.locks.json` + 心跳 | Redis 锁 + WebSocket 广播 |
| API 前缀 | `/api/...` | `/api/v1/...` |

## 旧版数据位置

默认路径（可在 `by_self_web/main.py` 中修改）：

```
Self-study/xz_data/
├── xz_img/          # 待标注图像
└── xz_label/        # 标注结果
    ├── *.json       # 前端标注 JSON
    ├── *.txt        # YOLO 格式
    ├── labels.json  # 标签配置
    └── .locks.json  # 协作锁（2.0 不再使用）
```

## 迁移方式

### 方式 A：Web UI 手动导入（小数据量）

1. 启动 2.0：`./start.sh`
2. 登录 `admin@example.com` / `admin123`
3. 创建项目
4. 在标注页点击 **上传**，选择 `xz_img/` 中的图像
5. 在 2.0 中重新标注，或使用方式 B 导入已有标注

### 方式 B：迁移脚本（推荐）

**前置条件：**

1. 2.0 服务已启动
2. 已创建目标项目，记下 `project_id`（UUID）
3. 已登录并获取 JWT Token

**获取 Token：**

```bash
curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com","password":"admin123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])"
```

**运行迁移：**

```bash
cd backend
PYTHONPATH=. python3 scripts/migrate_legacy.py \
  --legacy-img ../Self-study/xz_data/xz_img \
  --legacy-label ../Self-study/xz_data/xz_label \
  --project-id <your-project-uuid> \
  --token <your-jwt-token> \
  --api http://localhost:8000
```

脚本会：

1. 逐张上传图像到指定项目
2. 若存在同名 `.json` 标注，转换为 2.0 schema 并写入数据库

### 方式 C：仅迁移 YOLO TXT

若只有 `.txt` 无 `.json`：

1. 先上传图像
2. 在 2.0 中手动打开每张图确认（或后续 Phase 2 提供 YOLO 批量导入 API）

## 标注格式映射

### 1.x JSON → 2.0

**1.x：**

```json
{
  "image": "/api/image/foo.jpg",
  "annotations": [
    {
      "id": 1,
      "x": 100, "y": 200, "width": 50, "height": 80,
      "label": { "id": 0, "name": "river_outlet", "color": "#e74c3c" }
    }
  ]
}
```

**2.0：**

```json
{
  "schema_version": 2,
  "image_id": "uuid",
  "image_width": 1920,
  "image_height": 1080,
  "annotations": [
    {
      "id": "ann-uuid",
      "type": "bbox",
      "label_id": "label-uuid-from-db",
      "geometry": { "x": 100, "y": 200, "width": 50, "height": 80 }
    }
  ]
}
```

> 注意：`label_id` 在 2.0 中是数据库 UUID，需在项目中先配置好对应 `class_id` 的标签。

### YOLO TXT

格式不变，导出仍为：

```
class_id x_center y_center width height
```

坐标均为相对图像宽高的 **0~1 归一化值**。

### 标签 labels.json → labels 表

| 1.x 字段 | 2.0 字段 |
|----------|----------|
| `id` | `class_id` |
| `name` | `name` |
| `color` | `color` |

在 2.0 项目设置中通过 API `PUT /projects/{id}/labels` 或 UI 标签面板配置。

## 迁移后验证

1. 图像数量与 1.x 一致
2. 随机抽查 5 张图的框位置与类别
3. 导出 YOLO zip，用训练脚本试加载
4. 双人打开同一项目，确认 WebSocket 协作正常

## 并行运行

1.x 与 2.0 可同时存在，端口需注意：

| 版本 | 默认端口 |
|------|----------|
| 1.x | 8000 |
| 2.0 后端 | 8000 |
| 2.0 前端 dev | 5173 |

不要同时占用 8000。可改 1.x 端口或只运行 2.0。

## 常见问题

**Q：迁移后标签 ID 对不上 YOLO class_id？**  
A：在 2.0 项目中按训练时的 `class_id` 顺序重新配置标签，再检查导出 zip 中的 `classes.txt`。

**Q：没有 Redis 能跑 2.0 吗？**  
A：可以。本地开发会自动降级为内存锁；生产环境建议使用 Redis。

**Q：旧版 `.locks.json` 需要迁移吗？**  
A：不需要，2.0 使用 Redis（或内存）管理编辑锁。

**Q：邮箱为什么不能用 `.local` 域名？**  
A：Pydantic EmailStr 校验限制，请使用 `admin@example.com` 等标准格式。
