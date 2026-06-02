# Web LabelImg 2.0 API 文档

在线交互文档：启动服务后访问 **http://localhost:8000/docs**

- Base URL：`/api/v1`
- 认证头：`Authorization: Bearer <access_token>`

---

## 通用约定

### 分页

列表接口支持：

```
GET /projects/{id}/images?page=1&page_size=20
```

响应：

```json
{
  "total": 100,
  "page": 1,
  "page_size": 20,
  "items": [ ... ]
}
```

### 错误

| 状态码 | 含义 |
|--------|------|
| 400 | 参数无效 |
| 401 | 未登录 / Token 无效 |
| 403 | 无项目权限 |
| 404 | 资源不存在 |
| 409 | 乐观锁冲突 / 编辑锁冲突 |

409 冲突示例（标注保存）：

```json
{
  "detail": {
    "message": "Version conflict",
    "current_version": 3,
    "server_data": { ... }
  }
}
```

---

## 认证 `/auth`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/auth/register` | 注册（首个用户自动为 admin） |
| POST | `/auth/login` | 登录，返回 access + refresh token |
| GET | `/auth/me` | 当前用户信息 |

### 注册

```http
POST /api/v1/auth/register
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "secret12",
  "display_name": "Alice"
}
```

### 登录

```http
POST /api/v1/auth/login

{
  "email": "admin@example.com",
  "password": "admin123"
}
```

响应：

```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer"
}
```

---

## 项目 `/projects`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/projects` | 当前用户参与的项目列表 |
| POST | `/projects` | 创建项目（创建者自动为 admin 成员） |
| POST | `/projects/{id}/members` | 邀请成员 |
| GET | `/projects/{id}/labels` | 获取标签 |
| PUT | `/projects/{id}/labels` | 批量更新标签 |
| GET | `/projects/{id}/images` | 图像分页列表 |
| POST | `/projects/{id}/images/upload` | 批量上传（multipart） |
| POST | `/projects/{id}/exports` | 创建 YOLO 导出任务 |

### 创建项目

```json
{ "name": "河流出口检测", "description": "2026 Q2 数据集" }
```

### 邀请成员

```json
{ "email": "annotator@example.com", "role": "annotator" }
```

角色：`admin` | `reviewer` | `annotator`

### 上传图像

```http
POST /api/v1/projects/{project_id}/images/upload
Content-Type: multipart/form-data

files: (binary) × N
```

上传后自动生成缩略图（最大边 512px）。

### 标签结构

```json
{
  "labels": [
    { "class_id": 0, "name": "river_outlet", "color": "#e74c3c", "sort_order": 0 }
  ]
}
```

---

## 标注 `/images`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/images/{id}` | 图像元数据 + URL |
| GET | `/images/{id}/annotations` | 最新标注 + version |
| PUT | `/images/{id}/annotations` | 保存（乐观锁） |
| GET | `/images/{id}/annotations/history` | 版本历史列表 |
| GET | `/exports/{job_id}` | 查询导出任务 |

### 标注 JSON Schema（schema_version=2）

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
      "label_id": "label-uuid",
      "geometry": {
        "x": 100,
        "y": 200,
        "width": 150,
        "height": 80
      }
    }
  ]
}
```

### 保存标注

```http
PUT /api/v1/images/{image_id}/annotations

{
  "base_version": 2,
  "data": { ... AnnotationDocument ... },
  "comment": "修正框位置",
  "force": false
}
```

成功响应：

```json
{
  "version": 3,
  "saved_at": "2026-06-02T10:00:00Z",
  "saved_by": "user-uuid"
}
```

### YOLO 导出

```http
POST /api/v1/projects/{project_id}/exports
{ "format": "yolo" }
```

返回 `export_jobs` 记录；完成后 `result_url` 指向 zip 下载地址。

zip 内容：

```
classes.txt
labels/image001.txt
labels/image002.txt
```

每行格式（归一化坐标）：

```
class_id x_center y_center width height
```

---

## 系统

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/metrics` | Prometheus 指标 |

---

## WebSocket 实时协作

### 连接

```
ws://localhost:8000/ws/projects/{project_id}?token=<JWT>
```

生产环境通过 Nginx 反代时使用 `wss://`。

### 协作模型

- 每张图像同一时刻只有 **一个主编辑者**（Redis 锁，默认 120s）
- 主编辑者操作实时广播给其他协作者（只读 + 光标）
- 持久化仍通过 REST `PUT /annotations` 完成

### 消息 Envelope

所有消息统一格式：

```json
{
  "type": "annotation_add",
  "payload": { },
  "sender": {
    "user_id": "uuid",
    "display_name": "Alice"
  },
  "timestamp": "2026-06-02T10:00:00Z",
  "message_id": "uuid"
}
```

### 客户端 → 服务端

| type | payload | 说明 |
|------|---------|------|
| `ping` | `{}` | 心跳 |
| `join_image` | `{ "image_id": "uuid" }` | 进入图像房间，尝试获取编辑锁 |
| `leave_image` | `{ "image_id": "uuid" }` | 离开并释放锁 |
| `cursor_move` | `{ "x": 100, "y": 200 }` | 光标位置 |
| `annotation_add` | `{ "image_id", "annotation" }` | 新增框（主编辑者） |
| `annotation_update` | `{ "image_id", "annotation_id", "geometry" }` | 修改框 |
| `annotation_delete` | `{ "image_id", "annotation_id" }` | 删除框 |
| `annotation_move` | `{ "image_id", "annotation_id", "geometry" }` | 移动框 |

### 服务端 → 客户端

| type | 说明 |
|------|------|
| `pong` | 心跳响应 |
| `presence` | 在线用户列表 |
| `lock_status` | `{ "is_editor": true/false, "lock": {...} }` |
| `cursor_move` | 协作者光标 |
| `annotation_*` | 标注变更广播 |
| `conflict` | 非编辑者尝试操作时 |

### 示例：加入图像

客户端发送：

```json
{ "type": "join_image", "payload": { "image_id": "550e8400-e29b-41d4-a716-446655440000" } }
```

服务端响应：

```json
{
  "type": "lock_status",
  "payload": {
    "image_id": "550e8400-e29b-41d4-a716-446655440000",
    "is_editor": true,
    "lock": { "user_id": "...", "display_name": "Alice" }
  },
  "sender": { ... },
  "timestamp": "...",
  "message_id": "..."
}
```

---

## 旧版 1.x API（兼容参考）

旧版无 `/api/v1` 前缀，无 JWT，详见 `by_self_web/main.py`：

| 路径 | 说明 |
|------|------|
| `GET /api/images` | 图像列表 |
| `POST /api/save-annotations` | 保存 JSON + YOLO |
| `POST /api/lock-image` | Session 锁 |
| `GET /api/next-unannotated` | 下一个未标注 |
