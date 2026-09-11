"""Generate CarePilot's deterministic, self-authored Evidence fixture images."""

import hashlib
import json
import struct
import zlib
from pathlib import Path


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
IMAGE_DIR = FIXTURE_DIR / "evidence-images-v0.1"
SCENARIOS = {
    "DIGITAL": [
        "MISSING_PART", "DAMAGED_ITEM", "SCREEN_DEFECT", "POWER_FAILURE", "PACKAGING_DAMAGE",
        "WRONG_ITEM", "SEAL_BROKEN", "ACCESSORY_MISMATCH", "LABEL_CHECK", "QUALITY_UNCLEAR",
    ],
    "APPAREL": [
        "SIZE_MISMATCH", "STAIN", "SEAM_DAMAGE", "WRONG_ITEM", "TAG_CHECK",
        "COLOR_MISMATCH", "PACKAGING_DAMAGE", "RETURN_CONDITION", "LABEL_CHECK", "QUALITY_UNCLEAR",
    ],
    "HOME": [
        "MISSING_PART", "DAMAGED_ITEM", "CRACK", "PACKAGING_DAMAGE", "ASSEMBLY_CHECK",
        "WRONG_ITEM", "SURFACE_SCRATCH", "HARDWARE_CHECK", "LABEL_CHECK", "QUALITY_UNCLEAR",
    ],
}


def png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def png_bytes(index: int) -> bytes:
    width, height = 96, 64
    base = ((index * 37) % 160 + 48, (index * 61) % 160 + 48, (index * 83) % 160 + 48)
    accent = tuple(255 - value // 2 for value in base)
    rows = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            in_card = 10 < x < 86 and 8 < y < 56
            marker = abs(x - (20 + (index * 7) % 56)) + abs(y - 32) < 10
            pixel = accent if marker else base if in_card else (246, 248, 250)
            row.extend(pixel)
        rows.append(bytes(row))
    return b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + png_chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + png_chunk(b"IEND", b"")


def expected_analysis(category: str, scenario: str) -> dict[str, object]:
    low_quality = scenario == "QUALITY_UNCLEAR"
    damage = "可见破损" if any(token in scenario for token in ("DAMAGE", "CRACK", "SCRATCH", "STAIN", "DEFECT")) else None
    missing_parts = "模拟缺少部件" if scenario in {"MISSING_PART", "ACCESSORY_MISMATCH", "HARDWARE_CHECK"} else None
    return {
        "evidence_type": "PRODUCT_AND_PACKAGING",
        "damage_type": damage,
        "damage_location": "模拟右侧区域" if damage else None,
        "packaging_status": "模拟包装可见",
        "missing_parts": missing_parts,
        "label_match": "SIMULATED_MATCH",
        "image_quality": "BLURRY" if low_quality else "CLEAR",
        "confidence": 0.55 if low_quality else 0.9,
        "needs_human_review": low_quality,
        "review_reason": "SIMULATED_LOW_QUALITY" if low_quality else None,
    }


def main() -> None:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    files = []
    index = 1
    for category, scenarios in SCENARIOS.items():
        for scenario in scenarios:
            fixture_id = f"EVI-{category[0]}-{index:02d}"
            filename = f"{fixture_id}.png"
            content = png_bytes(index)
            (IMAGE_DIR / filename).write_bytes(content)
            files.append({
                "id": fixture_id,
                "category": category,
                "scenario": scenario,
                "filename": filename,
                "content_type": "image/png",
                "input_sha256": hashlib.sha256(content).hexdigest(),
                "expected_analysis": expected_analysis(category, scenario),
            })
            index += 1
    payload = {
        "fixture_set": "self-authored-evidence-v0.1",
        "source_note": "30 张图片均为本脚本生成的抽象栅格测试图，不含人物、地址、订单、品牌或第三方素材；标注仅用于文件链路测试，不是视觉模型评测或真实 Evidence 结论。",
        "files": files,
    }
    (FIXTURE_DIR / "evidence-v0.1.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Generated {len(files)} self-authored Evidence fixture images.")


if __name__ == "__main__":
    main()
