# -*- coding: utf-8 -*-
"""
icon.png(흰 배경 전신 그림) → 앱 아이콘(app.ico) 생성.

  python make_icon.py            후보 비교표만 만들기 (icon_options/preview.png)
  python make_icon.py D          D안으로 app.ico 만들기 (A/B/C/D)

  A 얼굴 클로즈업 · B 상반신 · C 전신 · D 빨간 원형 배지 + 얼굴
"""
from __future__ import annotations

import struct
import sys
from collections import deque
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QGuiApplication, QImage, QLinearGradient, QPainter,
                           QPainterPath)

HERE = Path(__file__).resolve().parent
SRC = HERE / "icon.png"
OUT_ICO = HERE / "app.ico"
OPT_DIR = HERE / "icon_options"
S = 512                                     # 후보 원본 크기
ICO_SIZES = [256, 128, 64, 48, 40, 32, 24, 20, 16]
LABELS = {"A": "얼굴 클로즈업", "B": "상반신", "C": "전신", "D": "빨간 원형 배지 + 얼굴"}


def cut_out(src: QImage) -> QImage:
    """가장자리에서 이어진 흰 배경만 투명하게 (캐릭터 안쪽 흰 부분은 유지)."""
    src = src.convertToFormat(QImage.Format_ARGB32)
    w, h = src.width(), src.height()

    def dist_white(c: int) -> int:
        return 765 - (((c >> 16) & 255) + ((c >> 8) & 255) + (c & 255))

    bg = bytearray(w * h)
    q = deque([(x, y) for x in range(w) for y in (0, h - 1)] +
              [(x, y) for y in range(h) for x in (0, w - 1)])
    while q:
        x, y = q.popleft()
        i = y * w + x
        if bg[i] or dist_white(src.pixel(x, y)) > 60:
            continue
        bg[i] = 1
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < w and 0 <= ny < h and not bg[ny * w + nx]:
                q.append((nx, ny))

    out = QImage(w, h, QImage.Format_ARGB32)
    for y in range(h):
        for x in range(w):
            c = src.pixel(x, y)
            if not bg[y * w + x]:
                out.setPixel(x, y, c | 0xFF000000)
                continue
            edge = any(0 <= x + dx < w and 0 <= y + dy < h and not bg[(y + dy) * w + x + dx]
                       for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
            a = min(255, dist_white(c) * 4) if edge else 0  # 윤곽선 옆은 살짝 남겨 계단 현상 완화
            out.setPixel(x, y, (a << 24) | (c & 0xFFFFFF))
    return out


def crop_square(cut: QImage, x: float, y: float, size: float) -> QImage:
    out = QImage(S, S, QImage.Format_ARGB32_Premultiplied)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.drawImage(QRectF(0, 0, S, S), cut, QRectF(x, y, size, size))
    p.end()
    return out


def badge(inner: QImage) -> QImage:
    out = QImage(S, S, QImage.Format_ARGB32_Premultiplied)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    r = QRectF(8, 8, S - 16, S - 16)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#C8102E"))
    p.drawEllipse(r)
    ir = r.adjusted(28, 28, -28, -28)
    g = QLinearGradient(ir.topLeft(), ir.bottomLeft())
    g.setColorAt(0, QColor("#FFFFFF"))
    g.setColorAt(1, QColor("#FBE9EC"))
    p.setBrush(g)
    p.drawEllipse(ir)
    clip = QPainterPath()
    clip.addEllipse(ir)
    p.setClipPath(clip)
    p.drawImage(ir.adjusted(-10, 6, 10, 26), inner)
    p.end()
    return out


def candidates(cut: QImage) -> dict[str, QImage]:
    return {
        "A": crop_square(cut, 58, 0, 140),
        "B": crop_square(cut, 26, 0, 210),
        "C": crop_square(cut, -102, 5, 432),
        "D": badge(crop_square(cut, 52, 0, 150)),
    }


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


def preview(cands: dict[str, QImage], path: Path) -> None:
    sizes = [256, 64, 48, 32, 24, 16]
    width = 40 + sum(s + 24 for s in sizes)
    row = 256 + 44
    sheet = QImage(width, row * 2 * len(cands), QImage.Format_ARGB32)
    p = QPainter(sheet)
    p.setRenderHint(QPainter.Antialiasing)
    f = QFont("Malgun Gothic", 13)
    f.setBold(True)
    p.setFont(f)
    y = 0
    for key, img in cands.items():
        for bg_name, bg, fg in (("밝은 배경", "#F3F3F3", "#222222"), ("어두운 작업표시줄", "#1F1F1F", "#EEEEEE")):
            p.fillRect(0, y, width, row, QColor(bg))
            p.setPen(QColor(fg))
            p.drawText(14, y + 28, f"{key}. {LABELS[key]} — {bg_name}   (256 / 64 / 48 / 32 / 24 / 16)")
            x = 20
            for s in sizes:
                p.drawImage(x, y + 40 + (256 - s) // 2,
                            img.scaled(s, s, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                x += s + 24
            y += row
    p.end()
    sheet.save(str(path))


def main() -> int:
    app = QGuiApplication(sys.argv)  # noqa: F841  (QFont/QPainter 텍스트에 필요)
    choice = sys.argv[1].upper() if len(sys.argv) > 1 else None
    if choice and choice not in LABELS:
        print(f"알 수 없는 안: {choice} (A/B/C/D 중 선택)")
        return 1
    src = QImage(str(SRC))
    if src.isNull():
        print(f"이미지를 읽지 못했습니다: {SRC}")
        return 1
    cands = candidates(cut_out(src))
    OPT_DIR.mkdir(exist_ok=True)
    for key, img in cands.items():
        img.save(str(OPT_DIR / f"{key}.png"))
    preview(cands, OPT_DIR / "preview.png")
    print(f"비교표: {OPT_DIR / 'preview.png'}")
    if choice:
        write_ico(cands[choice], OUT_ICO)
        print(f"{choice}안({LABELS[choice]}) → {OUT_ICO}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
