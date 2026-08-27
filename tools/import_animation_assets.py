from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
TARGET_ROOT = ROOT / "assets" / "animations"

STATE_SOURCES = [
    ("打招呼", "hello", "开机hello"),
    ("工作", "work", "工作"),
    ("吃饭", "eat", "吃饭"),
    ("睡觉", "sleep", "睡觉"),
    ("开心", "happy", "开心"),
    ("难过", "sad", "emo"),
    ("生气", "angry", "生气"),
    ("无聊", "bored", "无聊"),
    ("洗澡", "bath", "洗澡"),
    ("上厕所", "toilet", "拉屎"),
    ("甜蜜", "sweet", "甜蜜"),
]


def inspect_gif(path: Path) -> dict:
    with Image.open(path) as image:
        return {
            "size": list(image.size),
            "frames": int(getattr(image, "n_frames", 1)),
            "duration_ms": int(image.info.get("duration", 40) or 40),
        }


def import_assets(source_root: Path) -> dict:
    if not source_root.is_dir():
        raise FileNotFoundError(f"Animation source folder does not exist: {source_root}")

    TARGET_ROOT.mkdir(parents=True, exist_ok=True)
    states = []
    for status, key, source_folder in STATE_SOURCES:
        source_dir = source_root / source_folder
        source_files = sorted(source_dir.glob("*.gif"), key=lambda path: path.name)
        if not source_files:
            raise FileNotFoundError(f"No GIF files found in: {source_dir}")

        target_dir = TARGET_ROOT / key
        target_dir.mkdir(parents=True, exist_ok=True)
        variants = []
        for index, source in enumerate(source_files, start=1):
            metadata = inspect_gif(source)
            if metadata["size"] != [400, 400]:
                raise ValueError(f"Unexpected GIF size for {source}: {metadata['size']}")
            target_name = f"{key}_{index:02d}.gif"
            target = target_dir / target_name
            shutil.copy2(source, target)
            variants.append(
                {
                    "file": f"{key}/{target_name}",
                    "name": source.stem.strip(),
                    **metadata,
                }
            )
        states.append(
            {
                "status": status,
                "key": key,
                "source_type": source_folder,
                "variants": variants,
            }
        )

    drag_source = source_root / "指针拖动时候.gif"
    if not drag_source.exists():
        raise FileNotFoundError(f"Drag animation does not exist: {drag_source}")
    drag_metadata = inspect_gif(drag_source)
    shutil.copy2(drag_source, TARGET_ROOT / "drag.gif")

    manifest = {
        "version": 1,
        "states": states,
        "drag": {
            "file": "drag.gif",
            "name": "指针拖动",
            **drag_metadata,
        },
    }
    (TARGET_ROOT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Import the supplied desktop pet GIF animation set.")
    parser.add_argument("source", type=Path, help="Folder containing the 11 animation type folders.")
    args = parser.parse_args()
    manifest = import_assets(args.source)
    variant_count = sum(len(state["variants"]) for state in manifest["states"])
    print(f"Imported {len(manifest['states'])} states, {variant_count} variants, and 1 drag animation.")
    print(f"Manifest: {TARGET_ROOT / 'manifest.json'}")


if __name__ == "__main__":
    main()
