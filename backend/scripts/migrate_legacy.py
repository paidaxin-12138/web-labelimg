"""Legacy data migration script (Web LabelImg 1.x -> 2.0)."""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from pathlib import Path

import httpx


async def migrate(args: argparse.Namespace) -> None:
    headers = {"Authorization": f"Bearer {args.token}"}
    img_dir = Path(args.legacy_img)
    label_dir = Path(args.legacy_label)

    async with httpx.AsyncClient(base_url=args.api, headers=headers, timeout=60.0) as client:
        for image_path in sorted(img_dir.iterdir()):
            if not image_path.is_file():
                continue
            with open(image_path, "rb") as f:
                files = {"files": (image_path.name, f, "image/jpeg")}
                resp = await client.post(f"/api/v1/projects/{args.project_id}/images/upload", files=files)
                resp.raise_for_status()
                uploaded = resp.json()[0]
                image_id = uploaded["id"]

            json_path = label_dir / f"{image_path.stem}.json"
            if json_path.exists():
                data = json.loads(json_path.read_text(encoding="utf-8"))
                anns = []
                for ann in data.get("annotations", []):
                    label = ann.get("label", {})
                    anns.append({
                        "id": str(uuid.uuid4()),
                        "type": "bbox",
                        "label_id": label.get("id"),
                        "geometry": {
                            "x": ann.get("x", 0),
                            "y": ann.get("y", 0),
                            "width": ann.get("width", 0),
                            "height": ann.get("height", 0),
                        },
                    })
                payload = {
                    "base_version": 0,
                    "data": {
                        "schema_version": 2,
                        "image_id": image_id,
                        "image_width": uploaded["width"],
                        "image_height": uploaded["height"],
                        "annotations": anns,
                    },
                }
                await client.put(f"/api/v1/images/{image_id}/annotations", json=payload)
            print(f"Migrated {image_path.name}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--legacy-img", required=True)
    parser.add_argument("--legacy-label", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--api", default="http://localhost:8000")
    args = parser.parse_args()
    asyncio.run(migrate(args))


if __name__ == "__main__":
    main()
