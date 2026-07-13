from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "docs" / "ui-reference" / "pink-diary"
OUT = ROOT / "static" / "assets" / "reference"


def soften_light_background(asset: Image.Image) -> Image.Image:
    pixels = []
    for r, g, b, a in asset.getdata():
        spread = max(r, g, b) - min(r, g, b)
        if r > 240 and g > 228 and b > 228 and spread < 38:
            pixels.append((r, g, b, 0))
        elif r > 232 and g > 216 and b > 220 and spread < 46:
            pixels.append((r, g, b, min(a, 46)))
        else:
            pixels.append((r, g, b, a))
    asset.putdata(pixels)
    return asset


def crop(source: str, name: str, box: tuple[int, int, int, int], transparent_light: bool = False) -> None:
    image = Image.open(REF / source).convert("RGBA")
    asset = image.crop(box)
    if transparent_light:
        asset = soften_light_background(asset)
    asset.save(OUT / name)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    # Reference 01: write diary page.
    crop("pink-diary-reference-01.png", "brand-book-ref.png", (36, 58, 268, 168))
    crop("pink-diary-reference-01.png", "sidebar-girl-card-ref.png", (22, 615, 266, 812))
    crop("pink-diary-reference-01.png", "write-upload-coffee-ref.png", (498, 655, 623, 767))
    crop("pink-diary-reference-01.png", "write-upload-cake-ref.png", (636, 655, 761, 767))
    crop("pink-diary-reference-01.png", "write-upload-flower-ref.png", (778, 655, 904, 767))
    crop("pink-diary-reference-01.png", "write-upload-book-ref.png", (919, 655, 1045, 767))
    crop("pink-diary-reference-01.png", "write-upload-sky-ref.png", (1059, 655, 1186, 767))
    crop("pink-diary-reference-01.png", "analysis-flower-ref.png", (1528, 152, 1632, 214))

    # Reference 02: her diary letter decoration.
    crop("pink-diary-reference-02.png", "her-letter-flower-ref.png", (1496, 474, 1605, 710))

    # Reference 07: dashboard card doodles.
    crop("pink-diary-reference-07.png", "dashboard-calendar-ref.png", (515, 174, 622, 262), transparent_light=True)
    crop("pink-diary-reference-07.png", "dashboard-book-ref.png", (844, 174, 944, 265), transparent_light=True)
    crop("pink-diary-reference-07.png", "dashboard-pen-ref.png", (1158, 158, 1270, 278), transparent_light=True)
    crop("pink-diary-reference-07.png", "dashboard-heart-ref.png", (1492, 166, 1607, 276), transparent_light=True)


if __name__ == "__main__":
    main()
