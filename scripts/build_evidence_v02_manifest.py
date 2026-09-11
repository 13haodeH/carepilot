"""Freeze the user-provided visual evaluation set without exposing image bytes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
IMAGE_ROOT = ROOT / "evals" / "fixtures" / "evidence-images-v0.2"
OUTPUT = ROOT / "evals" / "fixtures" / "real-vision-eval-v0.2.json"

FOLDER_SPEC = {
    "明显破损": ("DAMAGE", "VISIBLE_DAMAGE", False),
    "明显缺件": ("MISSING", "VISIBLE_MISSING_PART", False),
    "包装破损状态不确定": ("PACKAGING_UNCERTAIN", "PACKAGING_UNCERTAIN", True),
    "模糊遮挡证据不足": ("INSUFFICIENT", "INSUFFICIENT_EVIDENCE", True),
    "与投诉内容不一致": ("MISMATCH", "COMPLAINT_MISMATCH", True),
}


def main() -> None:
    files = []
    for folder, (prefix, expected_signal, expected_review) in FOLDER_SPEC.items():
        for index, path in enumerate(sorted((IMAGE_ROOT / folder).glob("*.jpg")), start=1):
            with Image.open(path) as image:
                files.append({
                    "id": f"VE2-{prefix}-{index:02d}",
                    "relative_path": str(path.relative_to(IMAGE_ROOT)),
                    "content_type": "image/jpeg",
                    "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "input_byte_size": path.stat().st_size,
                    "width": image.width,
                    "height": image.height,
                    "expected_signal": expected_signal,
                    "expected_needs_human_review": expected_review,
                })
    manifest = {
        "fixture_set": "real-vision-eval-v0.2",
        "source_note": "项目负责人确认的 20 张无个人信息图片；技术检查未发现 EXIF。目录标签仅作为冻结评测期望，不会提供给真实 Agent。",
        "folder_counts": {folder: len(list((IMAGE_ROOT / folder).glob("*.jpg"))) for folder in FOLDER_SPEC},
        "files": files,
    }
    OUTPUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
