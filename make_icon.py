# -*- coding: utf-8 -*-
"""
icon.png(2048×2048, 크림색 바탕 위 달력 카드 그림) → 앱 아이콘(app.ico) 생성.

  python make_icon.py

카드 바깥(크림색 바탕)은 둥근 모서리를 따라 투명하게 잘라낸다.
크기별 미리보기: icon_options/preview.png
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPainterPath

HERE = Path(__file__).resolve().parent
SRC = HERE / "icon.png"
OUT_ICO = HERE / "app.ico"
OPT_DIR = HERE / "icon_options"
ICO_SIZES = [256, 128, 64, 48, 40, 32, 24, 20, 16]

# icon.png 안의 카드 위치 (2048 기준, 빨간 외곽선 바깥쪽 끝에서 잰 값)
CARD_X, CARD_Y, CARD_SIZE, CARD_RADIUS = 236, 236, 1576, 270


def cut_card(src: QImage) -> QImage:
    k = src.width() / 2048  # 다른 해상도로 다시 뽑은 그림도 같은 구도면 동작하게
    x, y, size, radius = (round(v * k) for v in (CARD_X, CARD_Y, CARD_SIZE, CARD_RADIUS))
    out = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    clip = QPainterPath()
    clip.addRoundedRect(QRectF(0, 0, size, size), radius, radius)
    p.setClipPath(clip)
    p.drawImage(0, 0, src, x, y, size, size)
    p.end()
    return out


def write_ico(img: QImage, path: Path) -> None:
    """PNG 압축 항목으로 된 다중 크기 .ico (Vista 이후 Windows/PyInstaller 모두 지원)."""
    blobs = []
    for s in ICO_SIZES:
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        img.scaled(s, s, Qt.KeepAspectRatio, Qt.SmoothTransformation).save(buf, "PNG")
        blobs.append(bytes(buf.data()))
    offset = 6 + 16 * len(ICO_SIZES)
    head = struct.pack("<HHH", 0, 1, len(ICO_SIZES))
    for s, b in zip(ICO_SIZES, blobs):
        head += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(b), offset)
        offset += len(b)
    path.write_bytes(head + b"".join(blobs))


def preview(img: QImage, path: Path) -> None:
    sizes = [256, 64, 48, 32, 24, 16]
    width = 40 + sum(s + 24 for s in sizes)
    row = 256 + 44
    sheet = QImage(width, row * 2, QImage.Format_ARGB32)
    p = QPainter(sheet)
    p.setFont(QFont("Malgun Gothic", 13))
    for i, (name, bg, fg) in enumerate((("밝은 배경", "#F3F3F3", "#222222"),
                                        ("어두운 작업표시줄", "#1F1F1F", "#EEEEEE"))):
        y = i * row
        p.fillRect(0, y, width, row, QColor(bg))
        p.setPen(QColor(fg))
        p.drawText(14, y + 28, f"{name}   (256 / 64 / 48 / 32 / 24 / 16)")
        x = 20
        for s in sizes:
            p.drawImage(x, y + 40 + (256 - s) // 2,
                        img.scaled(s, s, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            x += s + 24
    p.end()
    sheet.save(str(path))


def main() -> int:
    app = QGuiApplication(sys.argv)  # noqa: F841  (QFont/QPainter 텍스트에 필요)
    src = QImage(str(SRC))
    if src.isNull():
        print(f"이미지를 읽지 못했습니다: {SRC}")
        return 1
    card = cut_card(src)
    OPT_DIR.mkdir(exist_ok=True)
    preview(card, OPT_DIR / "preview.png")
    write_ico(card, OUT_ICO)
    print(f"아이콘: {OUT_ICO}\n미리보기: {OPT_DIR / 'preview.png'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
