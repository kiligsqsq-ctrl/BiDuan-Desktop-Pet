from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
BRANDING_DIR = ROOT / "assets" / "branding"
SOURCE = BRANDING_DIR / "biduan_icon_source.png"
ICON_PNG = BRANDING_DIR / "biduan_icon.png"
TRAY_PNG = BRANDING_DIR / "biduan_tray.png"
ICON_ICO = BRANDING_DIR / "biduan.ico"


def rounded_icon(image: Image.Image, size: int) -> Image.Image:
    image = image.convert("RGB")
    side = min(image.size)
    left = (image.width - side) // 2
    top = (image.height - side) // 2
    image = image.crop((left, top, left + side, top + side))
    image = image.resize((size, size), Image.Resampling.LANCZOS)

    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    inset = max(1, size // 128)
    draw.rounded_rectangle(
        (inset, inset, size - inset - 1, size - inset - 1),
        radius=round(size * 0.19),
        fill=255,
    )
    result = image.convert("RGBA")
    result.putalpha(mask)
    return result


def main() -> None:
    if not SOURCE.exists():
        raise FileNotFoundError(f"Missing icon source: {SOURCE}")

    BRANDING_DIR.mkdir(parents=True, exist_ok=True)
    source = Image.open(SOURCE)
    icon = rounded_icon(source, 1024)
    icon.save(ICON_PNG, optimize=True)
    icon.resize((64, 64), Image.Resampling.LANCZOS).save(TRAY_PNG, optimize=True)
    icon.save(
        ICON_ICO,
        format="ICO",
        sizes=[(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"Created {ICON_PNG}")
    print(f"Created {TRAY_PNG}")
    print(f"Created {ICON_ICO}")


if __name__ == "__main__":
    main()
