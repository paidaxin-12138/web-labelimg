import os
import json
import threading
import time
from datetime import datetime
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from pathlib import Path

app = FastAPI(title="Web LabelImg - 河流出口检测标注工具", description="用于标注河流出口检测数据集的网页工具")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
STATIC_DIR = os.path.join(PROJECT_ROOT, "static")

IMAGE_FOLDER = os.environ.get(
    "IMAGE_FOLDER",
    os.path.join(PROJECT_ROOT, "Self-study", "xz_data", "xz_img"),
)
ANNOTATION_FOLDER = os.environ.get(
    "ANNOTATION_FOLDER",
    os.path.join(PROJECT_ROOT, "Self-study", "xz_data", "xz_label"),
)
LOCK_TIMEOUT = int(os.environ.get("LOCK_TIMEOUT", "120"))

_image_locks = {}
_locks_mutex = threading.Lock()
LOCKS_FILE = None

print("=" * 50)
print("路径信息:")
print(f"项目根目录: {PROJECT_ROOT}")
print(f"静态文件: {STATIC_DIR}")
print(f"图像文件夹: {IMAGE_FOLDER}")
print(f"标注文件夹: {ANNOTATION_FOLDER}")
print(f"锁定超时: {LOCK_TIMEOUT}s")
print("=" * 50)

os.makedirs(IMAGE_FOLDER, exist_ok=True)
os.makedirs(ANNOTATION_FOLDER, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)
LOCKS_FILE = os.path.join(ANNOTATION_FOLDER, ".locks.json")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

VALID_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp'}


class Label(BaseModel):
    id: int
    name: str
    color: str


class Annotation(BaseModel):
    id: int
    x: float
    y: float
    width: float
    height: float
    label: Label


class AnnotationData(BaseModel):
    image: str
    annotations: List[Annotation]
    session_id: str
    username: str
    version: Optional[str] = None
    force: bool = False


class LockRequest(BaseModel):
    filename: str
    session_id: str
    username: str


class HeartbeatRequest(BaseModel):
    filename: str
    session_id: str


class LabelsUpdate(BaseModel):
    labels: List[Label]
    version: Optional[str] = None
    force: bool = False


class ProjectInfo(BaseModel):
    name: str
    image_folder: str
    total_images: int
    annotated_images: int
    total_annotations: int
    active_users: int
    locked_images: int


DEFAULT_LABELS = [
    {"id": 0, "name": "river_outlet", "color": "#e74c3c"},
    {"id": 1, "name": "person", "color": "#3498db"},
    {"id": 2, "name": "vehicle", "color": "#2ecc71"},
    {"id": 3, "name": "building", "color": "#f39c12"},
]


def validate_filename(filename: str) -> str:
    """校验文件名，防止路径遍历。"""
    if not filename or not filename.strip():
        raise HTTPException(status_code=400, detail="无效的文件名")

    raw = filename.strip()
    if ".." in raw or "/" in raw or "\\" in raw:
        raise HTTPException(status_code=400, detail="无效的文件名")

    name = os.path.basename(raw)
    if not name or name in {".", ".."}:
        raise HTTPException(status_code=400, detail="无效的文件名")

    return name


def safe_path(base_dir: str, filename: str) -> str:
    """确保拼接后的路径仍在 base_dir 内。"""
    name = validate_filename(filename)
    base = os.path.abspath(base_dir)
    full_path = os.path.abspath(os.path.join(base, name))
    if not full_path.startswith(base + os.sep) and full_path != base:
        raise HTTPException(status_code=400, detail="无效的文件路径")
    return full_path


def _persist_locks():
    if LOCKS_FILE is None:
        return
    with _locks_mutex:
        payload = {
            "updated_at": datetime.now().isoformat(),
            "locks": _image_locks,
        }
    try:
        with open(LOCKS_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except OSError as exc:
        print(f"警告: 无法持久化锁文件: {exc}")


def _load_locks_from_disk():
    global _image_locks
    if not LOCKS_FILE or not os.path.exists(LOCKS_FILE):
        return
    try:
        with open(LOCKS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        _image_locks = data.get("locks", {})
    except (OSError, json.JSONDecodeError) as exc:
        print(f"警告: 无法加载锁文件: {exc}")
        _image_locks = {}


_load_locks_from_disk()


def cleanup_expired_locks():
    now = time.time()
    changed = False
    with _locks_mutex:
        expired = [name for name, lock in _image_locks.items() if lock.get("expires_at", 0) < now]
        for name in expired:
            del _image_locks[name]
            changed = True
    if changed:
        _persist_locks()


def get_lock(filename: str):
    cleanup_expired_locks()
    name = validate_filename(filename)
    with _locks_mutex:
        lock = _image_locks.get(name)
        return dict(lock) if lock else None


def get_all_locks():
    cleanup_expired_locks()
    with _locks_mutex:
        return {name: dict(lock) for name, lock in _image_locks.items()}


def acquire_lock(filename: str, session_id: str, username: str):
    cleanup_expired_locks()
    name = validate_filename(filename)
    with _locks_mutex:
        existing = _image_locks.get(name)
        now = time.time()
        if existing and existing["session_id"] != session_id and existing.get("expires_at", 0) > now:
            return False, dict(existing)
        _image_locks[name] = {
            "session_id": session_id,
            "username": username,
            "expires_at": now + LOCK_TIMEOUT,
            "locked_at": datetime.now().isoformat(),
        }
        result = True, dict(_image_locks[name])
    _persist_locks()
    return result


def renew_lock(filename: str, session_id: str):
    cleanup_expired_locks()
    name = validate_filename(filename)
    with _locks_mutex:
        lock = _image_locks.get(name)
        if lock and lock["session_id"] == session_id:
            lock["expires_at"] = time.time() + LOCK_TIMEOUT
            ok = True
        else:
            ok = False
    if ok:
        _persist_locks()
    return ok


def release_lock(filename: str, session_id: str):
    name = validate_filename(filename)
    with _locks_mutex:
        lock = _image_locks.get(name)
        if lock and lock["session_id"] == session_id:
            del _image_locks[name]
            released = True
        else:
            released = False
    if released:
        _persist_locks()
    return released


def release_all_locks_for_session(session_id: str):
    with _locks_mutex:
        to_remove = [name for name, lock in _image_locks.items() if lock["session_id"] == session_id]
        for name in to_remove:
            del _image_locks[name]
    if to_remove:
        _persist_locks()
    return len(to_remove)


def is_locked_by_other(filename: str, session_id: str):
    lock = get_lock(filename)
    return lock is not None and lock["session_id"] != session_id


def load_labels_config():
    labels_file = os.path.join(ANNOTATION_FOLDER, "labels.json")
    if os.path.exists(labels_file):
        with open(labels_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "labels" in data:
            return data
        if isinstance(data, list):
            return {"labels": data, "version": datetime.now().isoformat()}
    return {"labels": DEFAULT_LABELS, "version": None}


def save_labels_config(labels: list, version: Optional[str] = None):
    labels_file = os.path.join(ANNOTATION_FOLDER, "labels.json")
    new_version = datetime.now().isoformat()
    payload = {"labels": labels, "version": new_version, "updated_at": new_version}
    with open(labels_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return new_version


def get_labels_version():
    return load_labels_config().get("version")


def get_annotation_paths(image_filename: str):
    name = validate_filename(image_filename)
    base = os.path.splitext(name)[0]
    json_path = safe_path(ANNOTATION_FOLDER, f"{base}.json")
    yolo_path = safe_path(ANNOTATION_FOLDER, f"{base}.txt")
    return name, json_path, yolo_path


def get_annotation_version(image_filename: str):
    _, json_path, yolo_path = get_annotation_paths(image_filename)
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("saved_at"):
                return data["saved_at"]
        except Exception:
            pass
        return str(os.path.getmtime(json_path))
    if os.path.exists(yolo_path):
        return str(os.path.getmtime(yolo_path))
    return None


def count_yolo_annotations(yolo_path: str) -> int:
    if not os.path.exists(yolo_path):
        return 0
    with open(yolo_path, "r", encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def has_annotations(image_filename: str):
    _, json_path, yolo_path = get_annotation_paths(image_filename)
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return len(data.get("annotations", [])) > 0
        except Exception:
            return True
    if os.path.exists(yolo_path):
        return count_yolo_annotations(yolo_path) > 0
    return False


def get_annotation_count(image_filename: str):
    _, json_path, yolo_path = get_annotation_paths(image_filename)
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return len(data.get("annotations", []))
        except Exception:
            return 0
    if os.path.exists(yolo_path):
        return count_yolo_annotations(yolo_path)
    return 0


def find_image_for_base(base_name: str):
    if ".." in base_name or "/" in base_name or "\\" in base_name:
        return None, None
    for ext in [".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp", ".gif"]:
        image_filename = f"{base_name}{ext}"
        image_path = safe_path(IMAGE_FOLDER, image_filename)
        if os.path.exists(image_path):
            return image_filename, image_path
    return None, None


def parse_yolo_annotation(txt_path, image_width, image_height):
    annotations = []

    if not os.path.exists(txt_path):
        return annotations

    try:
        with open(txt_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        labels = load_labels_config()["labels"]

        for line_num, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue

            parts = line.split()
            if len(parts) != 5:
                print(f"警告: 第{line_num + 1}行格式错误: {line}")
                continue

            try:
                class_id = int(parts[0])
                x_center = float(parts[1])
                y_center = float(parts[2])
                width = float(parts[3])
                height = float(parts[4])

                x = (x_center - width / 2) * image_width
                y = (y_center - height / 2) * image_height
                w = width * image_width
                h = height * image_height

                label = next((item for item in labels if item["id"] == class_id), None)
                if not label:
                    print(f"警告: 未找到类别ID {class_id} 对应的标签")
                    label = {"id": class_id, "name": f"class_{class_id}", "color": "#666666"}

                annotations.append({
                    "id": line_num,
                    "x": x,
                    "y": y,
                    "width": w,
                    "height": h,
                    "label": label,
                })

            except (ValueError, IndexError) as exc:
                print(f"解析第{line_num + 1}行时出错: {exc}")
                continue

    except Exception as exc:
        print(f"读取YOLO标注文件时出错 {txt_path}: {exc}")

    return annotations


def convert_json_to_yolo(json_path, image_width, image_height):
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        annotations = data.get("annotations", [])
        yolo_lines = []

        for ann in annotations:
            x_center = (ann["x"] + ann["width"] / 2) / image_width
            y_center = (ann["y"] + ann["height"] / 2) / image_height
            width_norm = ann["width"] / image_width
            height_norm = ann["height"] / image_height

            x_center = max(0, min(1, x_center))
            y_center = max(0, min(1, y_center))
            width_norm = max(0, min(1, width_norm))
            height_norm = max(0, min(1, height_norm))

            class_id = ann["label"]["id"]
            yolo_line = f"{class_id} {x_center:.6f} {y_center:.6f} {width_norm:.6f} {height_norm:.6f}"
            yolo_lines.append(yolo_line)

        return yolo_lines

    except Exception as exc:
        print(f"转换JSON到YOLO格式时出错 {json_path}: {exc}")
        return []


def delete_annotation_files(filename: str):
    _, json_path, yolo_path = get_annotation_paths(filename)
    removed = []
    for path in (json_path, yolo_path):
        if os.path.exists(path):
            os.remove(path)
            removed.append(os.path.basename(path))
    return removed


def save_annotation_files(filename: str, annotation_data: AnnotationData):
    name = validate_filename(filename)
    _, json_path, yolo_path = get_annotation_paths(name)

    if not annotation_data.annotations:
        removed = delete_annotation_files(name)
        if removed:
            return {
                "message": "已清除标注（无边界框）",
                "removed_files": removed,
                "version": None,
            }
        return {"message": "无标注需要保存", "version": None}

    annotation_filename = os.path.basename(json_path)
    data_to_save = annotation_data.model_dump(exclude={"session_id", "username", "version", "force"})
    data_to_save["saved_at"] = datetime.now().isoformat()
    data_to_save["image_filename"] = name
    data_to_save["saved_by"] = annotation_data.username

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data_to_save, f, ensure_ascii=False, indent=2)

    yolo_filename = os.path.basename(yolo_path)
    image_path = safe_path(IMAGE_FOLDER, name)
    if os.path.exists(image_path):
        from PIL import Image
        with Image.open(image_path) as img:
            width, height = img.size

        yolo_lines = convert_json_to_yolo(json_path, width, height)
        with open(yolo_path, "w", encoding="utf-8") as f:
            f.write("\n".join(yolo_lines))

        return {
            "message": "标注保存成功，已同时生成 JSON 和 YOLO 格式",
            "json_filename": annotation_filename,
            "yolo_filename": yolo_filename,
            "version": data_to_save["saved_at"],
        }

    return {
        "message": "标注保存成功(仅 JSON 格式)，无法生成 YOLO 格式(图像不存在)",
        "json_filename": annotation_filename,
        "version": data_to_save["saved_at"],
    }


@app.get("/")
async def read_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/api/images")
async def get_images(session_id: Optional[str] = Query(default=None)):
    images = []

    if not os.path.exists(IMAGE_FOLDER):
        error_msg = f"图像文件夹不存在: {IMAGE_FOLDER}"
        print(error_msg)
        return {"images": [], "error": error_msg}

    try:
        for filename in os.listdir(IMAGE_FOLDER):
            file_path = os.path.join(IMAGE_FOLDER, filename)
            if not os.path.isfile(file_path):
                continue
            if Path(filename).suffix.lower() not in VALID_EXTENSIONS:
                continue
            try:
                validate_filename(filename)
            except HTTPException:
                continue

            lock = get_lock(filename)
            annotated = has_annotations(filename)
            count = get_annotation_count(filename) if annotated else 0
            locked_by_other = lock is not None and (session_id is None or lock["session_id"] != session_id)

            images.append({
                "filename": filename,
                "url": f"/api/image/{filename}",
                "file_size": os.path.getsize(file_path),
                "modified_time": datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat(),
                "annotated": annotated,
                "annotation_count": count,
                "locked": locked_by_other,
                "locked_by": lock["username"] if locked_by_other else None,
            })

        images.sort(key=lambda item: item["filename"])
        print(f"找到 {len(images)} 张图像")
        return {"images": images}

    except Exception as exc:
        error_msg = f"读取图像文件夹时出错: {str(exc)}"
        print(error_msg)
        return {"images": [], "error": error_msg}


@app.get("/api/image/{filename}")
async def get_image(filename: str):
    name = validate_filename(filename)
    file_path = safe_path(IMAGE_FOLDER, name)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="图像不存在")

    if Path(name).suffix.lower() not in VALID_EXTENSIONS:
        raise HTTPException(status_code=400, detail="文件不是图像格式")

    return FileResponse(file_path)


@app.post("/api/lock-image")
async def lock_image(request: LockRequest):
    name = validate_filename(request.filename)
    image_path = safe_path(IMAGE_FOLDER, name)
    if not os.path.exists(image_path):
        raise HTTPException(status_code=404, detail="图像不存在")

    success, lock = acquire_lock(name, request.session_id, request.username)
    if not success:
        raise HTTPException(
            status_code=409,
            detail={
                "message": f"该图像正在被 {lock['username']} 标注",
                "locked_by": lock["username"],
                "locked_at": lock.get("locked_at"),
            },
        )

    return {"message": "锁定成功", "lock": lock}


@app.post("/api/unlock-image")
async def unlock_image(request: LockRequest):
    name = validate_filename(request.filename)
    released = release_lock(name, request.session_id)
    return {"message": "已释放锁定" if released else "无需释放", "released": released}


@app.post("/api/heartbeat")
async def heartbeat(request: HeartbeatRequest):
    name = validate_filename(request.filename)
    renewed = renew_lock(name, request.session_id)
    if not renewed:
        raise HTTPException(status_code=409, detail="锁定已失效，请重新打开图像")
    return {"message": "心跳成功", "expires_in": LOCK_TIMEOUT}


@app.get("/api/locks")
async def list_locks():
    locks = get_all_locks()
    active_users = {lock["username"] for lock in locks.values()}
    return {
        "locks": locks,
        "active_users": sorted(active_users),
        "locked_count": len(locks),
    }


@app.get("/api/load-annotations")
async def load_annotations(image_filename: str, session_id: Optional[str] = Query(default=None)):
    try:
        name = validate_filename(image_filename)
        lock = get_lock(name)
        read_only = lock is not None and (session_id is None or lock["session_id"] != session_id)
        _, json_path, yolo_path = get_annotation_paths(name)
        version = get_annotation_version(name)

        if os.path.exists(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["version"] = version
            data["read_only"] = read_only
            if read_only and lock:
                data["locked_by"] = lock["username"]
            return data

        if os.path.exists(yolo_path):
            image_path = safe_path(IMAGE_FOLDER, name)
            if os.path.exists(image_path):
                from PIL import Image
                with Image.open(image_path) as img:
                    width, height = img.size

                annotations = parse_yolo_annotation(yolo_path, width, height)
                result = {
                    "image": f"/api/image/{name}",
                    "annotations": annotations,
                    "source_format": "yolo",
                    "version": version,
                    "read_only": read_only,
                }
                if read_only and lock:
                    result["locked_by"] = lock["username"]
                return result

        result = {
            "message": "未找到标注数据",
            "annotations": [],
            "version": version,
            "read_only": read_only,
        }
        if read_only and lock:
            result["locked_by"] = lock["username"]
        return result

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"加载标注失败: {str(exc)}")


@app.post("/api/save-annotations")
async def save_annotations(annotation_data: AnnotationData):
    try:
        filename = validate_filename(annotation_data.image.split("/")[-1])

        if is_locked_by_other(filename, annotation_data.session_id):
            lock = get_lock(filename)
            raise HTTPException(
                status_code=409,
                detail=f"该图像正在被 {lock['username']} 标注，无法保存",
            )

        current_version = get_annotation_version(filename)
        if (
            annotation_data.version is not None
            and current_version is not None
            and annotation_data.version != current_version
            and not annotation_data.force
        ):
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "标注已被其他用户修改，请刷新后重试",
                    "current_version": current_version,
                    "conflict": True,
                },
            )

        return save_annotation_files(filename, annotation_data)

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"保存标注失败: {str(exc)}")


@app.get("/api/next-unannotated")
async def get_next_unannotated(
    session_id: str = Query(...),
    username: str = Query(...),
    current: Optional[str] = Query(default=None),
):
    if current:
        current = validate_filename(current)

    images_info = await get_images(session_id=session_id)
    images = images_info.get("images", [])

    if not images:
        return {"message": "没有可用图像", "filename": None}

    unannotated = [img for img in images if not img.get("annotated") and not img.get("locked")]

    if not unannotated:
        return {"message": "所有图像都已标注或正在被其他用户标注", "filename": None}

    if current and len(unannotated) == 1 and unannotated[0]["filename"] == current:
        return {"message": "当前已是唯一未标注图像", "filename": None, "same_image": True}

    start_index = 0
    if current:
        for index, image in enumerate(unannotated):
            if image["filename"] == current:
                start_index = index + 1
                break

    ordered = unannotated[start_index:] + unannotated[:start_index]

    for image in ordered:
        success, _lock = acquire_lock(image["filename"], session_id, username)
        if success:
            return {
                "filename": image["filename"],
                "url": image["url"],
                "message": "已切换到下一个未标注图像",
            }

    return {"message": "所有图像都已标注或正在被其他用户标注", "filename": None}


@app.get("/api/export-all")
async def export_all():
    try:
        converted_count = 0
        skipped_count = 0

        if not os.path.exists(ANNOTATION_FOLDER):
            return {"message": "标注文件夹不存在", "converted_count": 0}

        for filename in os.listdir(ANNOTATION_FOLDER):
            if not filename.endswith(".json") or filename in {"labels.json"}:
                continue
            if filename.startswith("."):
                continue

            json_path = os.path.join(ANNOTATION_FOLDER, filename)
            base_name = filename[:-5]
            image_filename, image_path = find_image_for_base(base_name)

            if not image_path:
                skipped_count += 1
                continue

            from PIL import Image
            with Image.open(image_path) as img:
                width, height = img.size

            yolo_lines = convert_json_to_yolo(json_path, width, height)
            yolo_path = safe_path(ANNOTATION_FOLDER, f"{base_name}.txt")
            with open(yolo_path, "w", encoding="utf-8") as f:
                f.write("\n".join(yolo_lines))

            converted_count += 1

        return {
            "message": f"导出完成：已生成/更新 {converted_count} 个 YOLO 文件，跳过 {skipped_count} 个",
            "converted_count": converted_count,
            "skipped_count": skipped_count,
        }

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"导出失败: {str(exc)}")


@app.get("/api/labels")
async def get_labels():
    config = load_labels_config()
    return {"labels": config["labels"], "version": config.get("version")}


@app.post("/api/labels")
async def update_labels(payload: LabelsUpdate):
    try:
        current_version = get_labels_version()
        if (
            payload.version is not None
            and current_version is not None
            and payload.version != current_version
            and not payload.force
        ):
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "标签已被其他用户修改，请刷新后重试",
                    "current_version": current_version,
                    "conflict": True,
                },
            )

        labels = [label.model_dump() for label in payload.labels]
        new_version = save_labels_config(labels)
        return {"message": "标签配置更新成功", "version": new_version}

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"更新标签配置失败: {str(exc)}")


@app.get("/api/convert-yolo-to-json")
async def convert_yolo_to_json():
    try:
        converted_count = 0

        if not os.path.exists(ANNOTATION_FOLDER):
            return {"message": "标注文件夹不存在", "converted_count": 0}

        for filename in os.listdir(ANNOTATION_FOLDER):
            if not filename.endswith(".txt") or filename.startswith("."):
                continue

            base_name = filename[:-4]
            image_filename, image_path = find_image_for_base(base_name)

            if not image_path:
                continue

            from PIL import Image
            with Image.open(image_path) as img:
                width, height = img.size

            yolo_path = os.path.join(ANNOTATION_FOLDER, filename)
            annotations = parse_yolo_annotation(yolo_path, width, height)
            json_path = safe_path(ANNOTATION_FOLDER, f"{base_name}.json")

            data_to_save = {
                "image": f"/api/image/{image_filename}",
                "annotations": annotations,
                "image_filename": image_filename,
                "saved_at": datetime.now().isoformat(),
                "converted_from": "yolo",
            }

            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=2)

            converted_count += 1

        return {"message": f"成功转换 {converted_count} 个 YOLO 标注文件", "converted_count": converted_count}

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"转换失败: {str(exc)}")


@app.get("/api/convert-json-to-yolo")
async def convert_json_to_yolo_batch():
    return await export_all()


@app.get("/api/project-info")
async def get_project_info():
    images_info = await get_images()
    total_images = len(images_info["images"])

    total_annotations = 0
    annotated_files = set()

    if os.path.exists(ANNOTATION_FOLDER):
        for filename in os.listdir(ANNOTATION_FOLDER):
            if filename.endswith(".json") and filename not in {"labels.json"} and not filename.startswith("."):
                base_name = filename[:-5]
                file_path = os.path.join(ANNOTATION_FOLDER, filename)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    count = len(data.get("annotations", []))
                    if count > 0:
                        annotated_files.add(base_name)
                        total_annotations += count
                except Exception:
                    pass
            elif filename.endswith(".txt") and not filename.startswith("."):
                base_name = filename[:-4]
                if base_name not in annotated_files:
                    if count_yolo_annotations(os.path.join(ANNOTATION_FOLDER, filename)) > 0:
                        annotated_files.add(base_name)

    locks = get_all_locks()
    active_users = {lock["username"] for lock in locks.values()}

    return ProjectInfo(
        name="河流出口检测标注工具",
        image_folder=IMAGE_FOLDER,
        total_images=total_images,
        annotated_images=len(annotated_files),
        total_annotations=total_annotations,
        active_users=len(active_users),
        locked_images=len(locks),
    )


if __name__ == "__main__":
    import uvicorn

    print(f"提示: 可通过环境变量 IMAGE_FOLDER / ANNOTATION_FOLDER / LOCK_TIMEOUT 配置")
    uvicorn.run(app, host="0.0.0.0", port=8000)
