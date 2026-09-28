# -*- coding: utf-8 -*-
"""
달력 메모 (Calendar Notes)

날짜를 누르고 그날 있는 일을 직접 적어두는 간단한 달력 창.

  메모 저장 : %APPDATA%\\CalendarNotes\\notes.json   (입력 후 0.6초 뒤 자동 저장)
  로그 파일 : %APPDATA%\\CalendarNotes\\logs\\calendar.log
  필요 패키지: pip install PySide6

단축키
  Alt+←  / Alt+→   이전 달 / 다음 달   (마우스 휠도 가능)
  Ctrl+T           오늘로 이동
  Ctrl+S           즉시 저장
  더블클릭          해당 날짜 선택 후 바로 입력
  우클릭            설정 메뉴 (메모 칸 자동 숨기기 / 배경 흐림)

창에 마우스가 없고 다른 창을 쓰는 중이면 버튼·메모 칸이 숨고 달력만 보인다.
디버그 로그를 보려면 환경변수 CALENDAR_DEBUG=1 로 실행.
"""
from __future__ import annotations

import calendar
import ctypes
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

__version__ = "1.0.1"  # build.py 가 exe 버전 정보로 사용, 릴리스 태그(v1.0.1)와 일치해야 함

APP_NAME = "CalendarNotes"
DATA_DIR = Path(os.environ.get("APPDATA") or (Path.home() / ".local" / "share")) / APP_NAME
NOTES_FILE = DATA_DIR / "notes.json"
LOG_DIR = DATA_DIR / "logs"
LOG_FILE = LOG_DIR / "calendar.log"
# PyInstaller 빌드면 압축이 풀린 임시 폴더, 아니면 이 파일 옆
RES_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
ICON_FILE = RES_DIR / "app.ico"


# ─────────────────────────────── 로깅 ───────────────────────────────
def setup_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if os.environ.get("CALENDAR_DEBUG") == "1" else logging.INFO
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s.%(funcName)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(level)
    fh = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)
    if sys.stderr is not None:  # pythonw(.pyw) 실행 시 stderr 없음
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(fmt)
        root.addHandler(sh)
    return logging.getLogger(APP_NAME)


log = setup_logging()


def _excepthook(exc_type, exc, tb):
    log.critical("처리되지 않은 예외", exc_info=(exc_type, exc, tb))
    if sys.stderr is not None:
        sys.__excepthook__(exc_type, exc, tb)


sys.excepthook = _excepthook

try:
    from PySide6.QtCore import (QEvent, QRectF, QSettings, Qt, QtMsgType, QTimer, Signal,
                                qInstallMessageHandler)
    from PySide6.QtGui import (QColor, QCursor, QFont, QIcon, QKeySequence, QLinearGradient,
                               QPainter, QPainterPath, QPen, QShortcut, QTextCursor)
    from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QMainWindow, QMenu,
                                   QMessageBox, QPlainTextEdit, QPushButton, QSizePolicy,
                                   QSplitter, QVBoxLayout, QWidget)
except ImportError:
    log.critical("PySide6 import 실패 — 'pip install PySide6' 필요", exc_info=True)
    raise SystemExit(1)

_QT_LEVELS = {
    QtMsgType.QtDebugMsg: logging.DEBUG,
    QtMsgType.QtInfoMsg: logging.INFO,
    QtMsgType.QtWarningMsg: logging.WARNING,
    QtMsgType.QtCriticalMsg: logging.ERROR,
    QtMsgType.QtFatalMsg: logging.CRITICAL,
}


def _qt_message_handler(mode, context, message):
    logging.getLogger("Qt").log(_QT_LEVELS.get(mode, logging.WARNING), message)


# ─────────────────────────────── 색/문구 ───────────────────────────────
# 무녀복 빨강 + 흰색 + 반투명 유리
INK = QColor("#2B1D21")                  # 본문 글자
MUTED = QColor("#8C7479")                # 보조 글자
LINE = QColor(200, 16, 46, 26)           # 격자선 (옅은 붉은 선)
FRAME = QColor(200, 16, 46, 60)          # 달력 외곽선
PAPER = QColor(255, 255, 255, 232)       # 이번 달 칸 (젖빛 유리)
PAPER_OUT = QColor(255, 244, 246, 150)   # 다른 달 칸
HOVER = QColor(255, 233, 237, 240)
ACCENT = QColor("#C8102E")               # 무녀복 빨강
SEL_FILL = QColor(200, 16, 46, 16)
SUN = QColor("#D0243A")
SAT = QColor("#4868A8")
NOTE_INK = QColor("#4A363C")

WEEKDAY_SHORT = ["일", "월", "화", "수", "목", "금", "토"]            # 일요일 시작
WEEKDAY_FULL = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]  # date.weekday() 순서

STYLE = """
QLabel#monthTitle { font-size: 30px; font-weight: 700; color: #B3122C; }
QLabel#yearTitle  { font-size: 15px; color: #8C7479; padding-top: 10px; }
QPushButton {
    background: rgba(255,255,255,170); border: 1px solid rgba(200,16,46,55); border-radius: 8px;
    padding: 5px 14px; color: #9E1027; font-size: 13px;
}
QPushButton:hover   { background: rgba(255,233,237,235); border-color: rgba(200,16,46,120); }
QPushButton:pressed { background: rgba(248,208,216,245); }
QPushButton#navBtn  { padding: 3px 0; min-width: 34px; font-size: 18px; }
QPushButton#winBtn, QPushButton#closeBtn {
    background: transparent; border: none; border-radius: 6px;
    padding: 2px 0; min-width: 32px; font-size: 16px; color: #8C7479;
}
QPushButton#winBtn:hover   { background: rgba(200,16,46,22); color: #9E1027; }
QPushButton#closeBtn:hover { background: #C8102E; color: #FFFFFF; }
QWidget#editorPanel {
    background: rgba(255,255,255,205); border: 1px solid rgba(255,255,255,240);
    border-top: 3px solid #C8102E; border-radius: 12px;
}
QLabel#dateTitle { font-size: 22px; font-weight: 700; color: #B3122C; }
QLabel#dateSub   { font-size: 13px; color: #8C7479; }
QLabel#status    { font-size: 11px; color: #A8959A; }
QPlainTextEdit {
    border: none; border-top: 1px solid rgba(200,16,46,30); background: transparent;
    font-size: 14px; color: #2B1D21; padding-top: 8px;
    selection-background-color: #F6C9D1; selection-color: #2B1D21;
}
QSplitter::handle { background: transparent; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 0; }
QScrollBar::handle:vertical { background: rgba(200,16,46,60); border-radius: 4px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
QMenu { background: #FFFFFF; border: 1px solid rgba(200,16,46,70); padding: 4px; }
QMenu::item { padding: 6px 22px 6px 26px; color: #2B1D21; border-radius: 4px; }
QMenu::item:selected { background: #FBE3E7; color: #9E1027; }
QMenu::indicator { left: 6px; width: 14px; height: 14px; }
QToolTip { background: #FFFFFF; color: #2B1D21; border: 1px solid rgba(200,16,46,90); }
"""


# ─────────────────────────────── Windows 창 효과 ───────────────────────────────
def set_app_user_model_id() -> None:
    """pythonw 로 실행해도 작업표시줄에 파이썬 아이콘 대신 앱 아이콘이 뜨게."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"YGH.{APP_NAME}")
    except (AttributeError, OSError):
        log.warning("AppUserModelID 설정 실패", exc_info=True)


class _AccentPolicy(ctypes.Structure):
    _fields_ = [("AccentState", ctypes.c_int), ("AccentFlags", ctypes.c_int),
                ("GradientColor", ctypes.c_uint), ("AnimationId", ctypes.c_int)]


class _WinCompAttrData(ctypes.Structure):
    _fields_ = [("Attribute", ctypes.c_int), ("Data", ctypes.POINTER(_AccentPolicy)),
                ("SizeOfData", ctypes.c_size_t)]


def apply_window_effects(hwnd: int, blur: bool) -> bool:
    """Win11 둥근 모서리·붉은 테두리 + (선택) 창 뒤 흐림. 흐림이 켜졌으면 True.

    둥근 모서리/테두리색은 Win10 에선 지원되지 않아 조용히 무시된다.
    """
    if sys.platform != "win32":
        return False
    try:
        user32, dwm = ctypes.windll.user32, ctypes.windll.dwmapi
        h = ctypes.c_void_p(hwnd)
        for attr, value in ((33, 2),             # DWMWA_WINDOW_CORNER_PREFERENCE = ROUND
                            (34, 0x00A0A8E8)):   # DWMWA_BORDER_COLOR (0x00BBGGRR) 옅은 빨강
            v = ctypes.c_uint(value)
            dwm.DwmSetWindowAttribute(h, attr, ctypes.byref(v), ctypes.sizeof(v))
        # 테두리 없는 창도 작업표시줄 클릭으로 최소화되도록
        GWL_STYLE, WS_MINIMIZEBOX = -16, 0x00020000
        user32.SetWindowLongW(h, GWL_STYLE, user32.GetWindowLongW(h, GWL_STYLE) | WS_MINIMIZEBOX)
        # 창 뒤 흐림 (4 = ACCENT_ENABLE_ACRYLICBLURBEHIND, 0 = 끄기)
        accent = _AccentPolicy(4 if blur else 0, 0, 0x01FFFFFF, 0)
        data = _WinCompAttrData(19, ctypes.pointer(accent), ctypes.sizeof(accent))  # WCA_ACCENT_POLICY
        ok = bool(user32.SetWindowCompositionAttribute(h, ctypes.byref(data)))
        if blur and not ok:
            log.warning("창 뒤 흐림 적용 실패 — 흐림 없이 표시")
        return blur and ok
    except (AttributeError, OSError):
        log.warning("창 효과 적용 실패", exc_info=True)
        return False


# ─────────────────────────────── 저장소 ───────────────────────────────
class NoteStore:
    """날짜(YYYY-MM-DD) → 메모 텍스트. JSON 파일에 원자적으로 저장."""

    def __init__(self, path: Path):
        self.path = path
        self.notes: dict[str, str] = {}
        self.dirty = False
        self.readonly = False            # 읽기 실패 시 기존 파일을 덮어쓰지 않도록 저장 차단
        self.problem: str | None = None  # 시작 시 사용자에게 보여줄 문제

    def load(self) -> None:
        if not self.path.exists():
            log.info("메모 파일 없음 — 새로 시작: %s", self.path)
            return
        try:
            raw = self.path.read_text(encoding="utf-8")
        except OSError as e:
            self.readonly = True
            self.problem = f"메모 파일을 읽지 못했습니다. 저장을 막아두었습니다.\n{self.path}\n{e}"
            log.exception("메모 파일 읽기 실패: %s", self.path)
            return
        try:
            data = json.loads(raw)
            notes = data.get("notes") if isinstance(data, dict) else None
            if not isinstance(notes, dict):
                raise ValueError("'notes' 항목이 없거나 dict가 아님")
            cleaned: dict[str, str] = {}
            for k, v in notes.items():
                date.fromisoformat(k)  # 키 형식 검증 (잘못되면 ValueError/TypeError)
                if not isinstance(v, str):
                    raise ValueError(f"{k}: 값이 문자열이 아님 ({type(v).__name__})")
                cleaned[k] = v
            self.notes = cleaned
            log.info("메모 %d개 로드: %s", len(cleaned), self.path)
        except (ValueError, TypeError) as e:  # JSONDecodeError 포함
            log.exception("메모 파일 형식 오류: %s", self.path)
            backup = self.path.with_name(f"{self.path.stem}.corrupt-{datetime.now():%Y%m%d-%H%M%S}.json")
            try:
                self.path.replace(backup)
                self.problem = f"메모 파일이 손상되어 따로 보관하고 새로 시작합니다.\n보관 위치: {backup}\n원인: {e}"
                log.warning("손상된 파일 보관: %s", backup)
            except OSError:
                self.readonly = True
                self.problem = f"메모 파일이 손상됐고 보관에도 실패해 저장을 막아두었습니다.\n{self.path}\n원인: {e}"
                log.exception("손상 파일 보관 실패")

    def get(self, d: date) -> str:
        return self.notes.get(d.isoformat(), "")

    def set(self, d: date, text: str) -> None:
        key = d.isoformat()
        if text.strip():
            if self.notes.get(key) != text:
                self.notes[key] = text
                self.dirty = True
        elif key in self.notes:
            del self.notes[key]
            self.dirty = True

    def save(self) -> bool:
        if self.readonly:
            log.error("저장 차단 상태(로드 실패)라 저장하지 않음: %s", self.path)
            return False
        tmp = self.path.with_name(self.path.name + ".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tmp.open("w", encoding="utf-8") as f:
                json.dump({"version": 1, "notes": dict(sorted(self.notes.items()))},
                          f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
            self.dirty = False
            log.debug("저장 완료: %d개", len(self.notes))
            return True
        except OSError:
            log.exception("저장 실패: %s", self.path)
            return False


# ─────────────────────────────── 달력 그리드 ───────────────────────────────
class MonthView(QWidget):
    dateClicked = Signal(object)        # datetime.date
    dateDoubleClicked = Signal(object)
    monthChanged = Signal(int, int)

    HEADER_H = 34
    RADIUS = 10

    def __init__(self, store: NoteStore, parent=None):
        super().__init__(parent)
        self.store = store
        self._cal = calendar.Calendar(firstweekday=calendar.SUNDAY)
        today = date.today()
        self.year, self.month = today.year, today.month
        self.selected = today
        self._hover = -1
        self._wheel_acc = 0
        self._days: list[date] = []
        self._rebuild()
        self.setMouseTracking(True)
        self.setMinimumSize(520, 420)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    # ── 상태 ──
    def _rebuild(self) -> None:
        first = next(iter(self._cal.itermonthdates(self.year, self.month)))
        self._days = [first + timedelta(days=i) for i in range(42)]  # 항상 6주

    def set_month(self, year: int, month: int) -> None:
        if (year, month) == (self.year, self.month):
            return
        self.year, self.month = year, month
        self._rebuild()
        self._hover = -1
        self.update()
        self.monthChanged.emit(year, month)

    def shift_month(self, delta: int) -> None:
        m = self.month - 1 + delta
        self.set_month(self.year + m // 12, m % 12 + 1)

    def set_selected(self, d: date) -> None:
        self.selected = d
        self.set_month(d.year, d.month)
        self.update()

    # ── 좌표 ──
    def _grid_rect(self) -> QRectF:
        return QRectF(0.5, self.HEADER_H + 0.5, self.width() - 1.0, self.height() - self.HEADER_H - 1.0)

    def _cell_rect(self, i: int) -> QRectF:
        g = self._grid_rect()
        cw, ch = g.width() / 7, g.height() / 6
        r, c = divmod(i, 7)
        return QRectF(g.left() + c * cw, g.top() + r * ch, cw, ch)

    def _index_at(self, pos) -> int:
        g = self._grid_rect()
        if not g.contains(pos):
            return -1
        c = min(int((pos.x() - g.left()) / (g.width() / 7)), 6)
        r = min(int((pos.y() - g.top()) / (g.height() / 6)), 5)
        return r * 7 + c

    # ── 그리기 ──
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        today = date.today()
        base = self.font()

        head_font = QFont(base)
        head_font.setBold(True)
        num_font = QFont(base)
        num_font.setBold(True)
        num_font.setPointSizeF(base.pointSizeF() * 1.05)
        note_font = QFont(base)
        note_font.setPointSizeF(base.pointSizeF() * 0.92)

        # 요일 헤더
        p.setFont(head_font)
        g = self._grid_rect()
        cw = g.width() / 7
        for c, name in enumerate(WEEKDAY_SHORT):
            p.setPen(SUN if c == 0 else SAT if c == 6 else MUTED)
            p.drawText(QRectF(g.left() + c * cw + 12, 0, cw, self.HEADER_H),
                       int(Qt.AlignLeft | Qt.AlignVCenter), name)

        # 바탕 (둥근 외곽 안쪽으로 클리핑)
        outer = QPainterPath()
        outer.addRoundedRect(g, self.RADIUS, self.RADIUS)
        p.save()
        p.setClipPath(outer)
        for i, d in enumerate(self._days):
            r = self._cell_rect(i)
            bg = PAPER if d.month == self.month else PAPER_OUT
            if i == self._hover:
                bg = HOVER
            p.fillRect(r, bg)

        # 격자선
        p.setPen(QPen(LINE, 1))
        ch = g.height() / 6
        for c in range(1, 7):
            x = g.left() + c * cw
            p.drawLine(x, g.top(), x, g.bottom())
        for r in range(1, 6):
            y = g.top() + r * ch
            p.drawLine(g.left(), y, g.right(), y)
        p.restore()
        p.setPen(QPen(FRAME, 1))
        p.drawPath(outer)

        # 칸 내용
        for i, d in enumerate(self._days):
            r = self._cell_rect(i)
            in_month = d.month == self.month
            wd = d.weekday()  # 월0 … 일6

            if d == self.selected:
                sel = QPainterPath()
                sel.addRoundedRect(r.adjusted(2, 2, -2, -2), 6, 6)
                p.setPen(QPen(ACCENT, 2))
                p.setBrush(SEL_FILL)
                p.drawPath(sel)
                p.setBrush(Qt.NoBrush)

            nr = QRectF(r.left() + 7, r.top() + 6, 28, 28)
            p.setFont(num_font)
            if d == today:
                p.setPen(Qt.NoPen)
                p.setBrush(ACCENT)
                p.drawEllipse(nr)
                p.setBrush(Qt.NoBrush)
                p.setPen(QColor("#FFFFFF"))
            else:
                col = QColor(SUN if wd == 6 else SAT if wd == 5 else INK)
                if not in_month:
                    col.setAlpha(80)
                p.setPen(col)
            p.drawText(nr, int(Qt.AlignCenter), str(d.day))

            text = self.store.get(d).strip()
            if text:
                tr = r.adjusted(10, 38, -8, -6)
                if tr.height() > 4:
                    col = QColor(NOTE_INK)
                    if not in_month:
                        col.setAlpha(110)
                    p.save()
                    p.setClipRect(tr)
                    p.setFont(note_font)
                    p.setPen(col)
                    p.drawText(tr, int(Qt.AlignLeft | Qt.AlignTop) | int(Qt.TextWordWrap), text)
                    p.restore()
                # 칸이 작아서 글이 안 보일 때를 위한 표시점
                p.setPen(Qt.NoPen)
                p.setBrush(ACCENT if in_month else QColor(ACCENT.red(), ACCENT.green(), ACCENT.blue(), 90))
                p.drawEllipse(QRectF(r.right() - 14, r.top() + 16, 6, 6))
                p.setBrush(Qt.NoBrush)
        p.end()

    # ── 입력 ──
    def mouseMoveEvent(self, e) -> None:
        i = self._index_at(e.position())
        if i != self._hover:
            self._hover = i
            self.update()

    def leaveEvent(self, e) -> None:
        self._hover = -1
        self.update()

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            i = self._index_at(e.position())
            if i >= 0:
                self.dateClicked.emit(self._days[i])

    def mouseDoubleClickEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            i = self._index_at(e.position())
            if i >= 0:
                self.dateDoubleClicked.emit(self._days[i])

    def wheelEvent(self, e) -> None:
        self._wheel_acc += e.angleDelta().y()
        while abs(self._wheel_acc) >= 120:  # 터치패드의 잘게 쪼개진 휠도 한 칸 단위로
            step = -1 if self._wheel_acc > 0 else 1
            self._wheel_acc += 120 * step
            self.shift_month(step)


# ─────────────────────────────── 창 틀 ───────────────────────────────
class GlassRoot(QWidget):
    """창 전체 바탕(유리판)을 그리고, 가장자리를 끌면 창 크기를 바꾼다."""

    EDGE = 7          # 크기 조절을 잡는 가장자리 두께(px)
    RADIUS = 8        # Win11 둥근 모서리와 맞춤

    def __init__(self, parent=None):
        super().__init__(parent)
        self.blurred = False  # 창 뒤 흐림이 켜졌으면 바탕을 더 투명하게
        self.setMouseTracking(True)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = 0 if self.window().isMaximized() else self.RADIUS
        a = 190 if self.blurred else 240
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0.0, QColor(252, 220, 227, a))
        g.setColorAt(0.4, QColor(255, 250, 251, a))
        g.setColorAt(1.0, QColor(250, 226, 232, a))
        path = QPainterPath()
        path.addRoundedRect(r, radius, radius)
        p.fillPath(path, g)
        # 위쪽 가장자리의 빨간 띠 (무녀복 리본 느낌)
        p.save()
        p.setClipPath(path)
        band = QLinearGradient(r.topLeft(), r.topRight())
        band.setColorAt(0.0, QColor(200, 16, 46, 230))
        band.setColorAt(1.0, QColor(226, 70, 95, 200))
        p.fillRect(QRectF(r.left(), r.top(), r.width(), 3), band)
        p.restore()
        p.setPen(QPen(QColor(255, 255, 255, 200), 1))  # 유리 가장자리 반사광
        p.drawPath(path)
        p.end()

    def _edges_at(self, pos) -> Qt.Edge:
        edges = Qt.Edge(0)
        if self.window().isMaximized():
            return edges
        m = self.EDGE
        if pos.x() < m:
            edges |= Qt.LeftEdge
        elif pos.x() >= self.width() - m:
            edges |= Qt.RightEdge
        if pos.y() < m:
            edges |= Qt.TopEdge
        elif pos.y() >= self.height() - m:
            edges |= Qt.BottomEdge
        return edges

    def mouseMoveEvent(self, e) -> None:
        edges = self._edges_at(e.position())
        horiz = edges & (Qt.LeftEdge | Qt.RightEdge)
        vert = edges & (Qt.TopEdge | Qt.BottomEdge)
        if horiz and vert:
            diag = edges in (Qt.LeftEdge | Qt.TopEdge, Qt.RightEdge | Qt.BottomEdge)
            self.setCursor(Qt.SizeFDiagCursor if diag else Qt.SizeBDiagCursor)
        elif horiz:
            self.setCursor(Qt.SizeHorCursor)
        elif vert:
            self.setCursor(Qt.SizeVerCursor)
        else:
            self.unsetCursor()

    def mousePressEvent(self, e) -> None:
        edges = self._edges_at(e.position())
        if e.button() == Qt.LeftButton and edges:
            self.window().windowHandle().startSystemResize(edges)
        else:
            super().mousePressEvent(e)


class TitleBar(QWidget):
    """상단 바. 빈 곳을 끌면 창 이동, 더블클릭하면 최대화/복원."""

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self.window().windowHandle().startSystemMove()
        else:
            super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            w = self.window()
            w.showNormal() if w.isMaximized() else w.showMaximized()


# ─────────────────────────────── 메인 창 ───────────────────────────────
class MainWindow(QMainWindow):
    SHOW_DELAY = 90     # 마우스를 올리고 버튼/메모 칸이 나타나기까지(ms) — 스쳐 지나갈 때 깜빡임 방지
    HIDE_DELAY = 700    # 마우스가 나가고 달력만 남기까지(ms)

    def __init__(self, store: NoteStore):
        super().__init__()
        self.store = store
        self.current = date.today()
        self._last_today = date.today()
        self.settings = QSettings(APP_NAME, APP_NAME)
        self.auto_hide = self.settings.value("autoHide", True, type=bool)
        self.blur = self.settings.value("blur", True, type=bool)
        self._compact = False
        self._split_state = None  # 메모 칸을 숨기기 직전의 분할 비율
        self.setWindowTitle("달력 메모")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        if ICON_FILE.exists():
            self.setWindowIcon(QIcon(str(ICON_FILE)))

        self.root = GlassRoot()
        self.setCentralWidget(self.root)
        outer = QVBoxLayout(self.root)
        outer.setContentsMargins(22, 12, 22, 20)
        outer.setSpacing(8)

        # 상단 바
        title_bar = TitleBar()
        title_bar.setFixedHeight(46)
        top = QHBoxLayout(title_bar)
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(6)
        self.month_label = QLabel(objectName="monthTitle")
        self.year_label = QLabel(objectName="yearTitle")
        self.today_btn = QPushButton("오늘")
        self.prev_btn = QPushButton("‹", objectName="navBtn")
        self.next_btn = QPushButton("›", objectName="navBtn")
        self.min_btn = QPushButton("–", objectName="winBtn")
        self.close_btn = QPushButton("×", objectName="closeBtn")
        self.prev_btn.setToolTip("이전 달 (Alt+←)")
        self.next_btn.setToolTip("다음 달 (Alt+→)")
        self.today_btn.setToolTip("오늘로 이동 (Ctrl+T)")
        self.min_btn.setToolTip("최소화")
        self.close_btn.setToolTip("닫기")
        for b in (self.today_btn, self.prev_btn, self.next_btn, self.min_btn, self.close_btn):
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)
        top.addWidget(self.month_label)
        top.addSpacing(6)
        top.addWidget(self.year_label)
        top.addStretch(1)
        top.addWidget(self.today_btn)
        top.addSpacing(6)
        top.addWidget(self.prev_btn)
        top.addWidget(self.next_btn)
        top.addSpacing(14)
        top.addWidget(self.min_btn)
        top.addWidget(self.close_btn)
        outer.addWidget(title_bar)
        # 대기 상태에서 숨길 것들
        self._chrome = [self.today_btn, self.prev_btn, self.next_btn, self.min_btn, self.close_btn]

        # 달력 + 메모 패널
        self.view = MonthView(store)
        self.panel = panel = QWidget(objectName="editorPanel")
        panel.setAttribute(Qt.WA_StyledBackground, True)
        panel.setMinimumWidth(260)
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(20, 18, 16, 12)
        pl.setSpacing(2)
        self.date_title = QLabel(objectName="dateTitle")
        self.date_sub = QLabel(objectName="dateSub")
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("이 날 있는 일을 적어두세요")
        self.status = QLabel(objectName="status")
        pl.addWidget(self.date_title)
        pl.addWidget(self.date_sub)
        pl.addSpacing(12)
        pl.addWidget(self.editor, 1)
        pl.addWidget(self.status)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(14)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self.view)
        self.splitter.addWidget(panel)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 1)
        outer.addWidget(self.splitter, 1)

        # 자동 저장 타이머
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(600)
        self.save_timer.timeout.connect(self._save_now)

        # 자정이 지나면 '오늘' 표시 갱신
        self.day_timer = QTimer(self)
        self.day_timer.setInterval(60_000)
        self.day_timer.timeout.connect(self._check_day_change)
        self.day_timer.start()

        # 대기(달력만) ↔ 사용 중 전환
        self.mode_timer = QTimer(self)
        self.mode_timer.setSingleShot(True)
        self.mode_timer.timeout.connect(self._apply_mode)

        # 연결
        self.editor.textChanged.connect(self._on_text_changed)
        self.view.dateClicked.connect(self.select_date)
        self.view.dateDoubleClicked.connect(self._on_double_click)
        self.view.monthChanged.connect(self._update_month_label)
        self.prev_btn.clicked.connect(lambda: self.view.shift_month(-1))
        self.next_btn.clicked.connect(lambda: self.view.shift_month(1))
        self.today_btn.clicked.connect(lambda: self.select_date(date.today()))
        self.min_btn.clicked.connect(self.showMinimized)
        self.close_btn.clicked.connect(self.close)
        QShortcut(QKeySequence("Alt+Left"), self, activated=lambda: self.view.shift_month(-1))
        QShortcut(QKeySequence("Alt+Right"), self, activated=lambda: self.view.shift_month(1))
        QShortcut(QKeySequence("Ctrl+T"), self, activated=lambda: self.select_date(date.today()))
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self._save_now)

        self._restore_layout()
        self.select_date(self.current)
        if store.readonly:
            self._set_status(f"저장이 막혀 있습니다. 로그 확인: {LOG_FILE}", error=True)

    # ── 레이아웃 기억 ──
    def _restore_layout(self) -> None:
        geo = self.settings.value("geometry")
        if geo is None or not self.restoreGeometry(geo):
            if geo is not None:
                log.warning("창 위치 복원 실패 — 기본 크기 사용")
            self.resize(1180, 760)
        split = self.settings.value("splitter")
        if split is None or not self.splitter.restoreState(split):
            if split is not None:
                log.warning("분할 비율 복원 실패 — 기본값 사용")
            self.splitter.setSizes([850, 320])

    # ── 창 효과 / 대기 모드 ──
    def showEvent(self, e) -> None:
        super().showEvent(e)
        self.root.blurred = apply_window_effects(int(self.winId()), self.blur)
        self.root.update()

    def _want_compact(self) -> bool:
        if not self.auto_hide or self.isMinimized():
            return False
        if self.isActiveWindow() or QApplication.activePopupWidget() is not None:
            return False
        return not self.frameGeometry().contains(QCursor.pos())

    def _schedule_mode(self) -> None:
        self.mode_timer.start(self.HIDE_DELAY if self._want_compact() else self.SHOW_DELAY)

    def _apply_mode(self) -> None:
        compact = self._want_compact()
        if compact == self._compact:
            return
        self._compact = compact
        log.debug("대기 모드 %s", "켜짐" if compact else "꺼짐")
        if compact:
            self._split_state = self.splitter.saveState()
        self.setUpdatesEnabled(False)  # 한 번에 바뀌어 보이게
        for w in self._chrome:
            w.setVisible(not compact)
        self.panel.setVisible(not compact)
        if not compact and self._split_state is not None:
            self.splitter.restoreState(self._split_state)
        self.setUpdatesEnabled(True)

    def enterEvent(self, e) -> None:
        super().enterEvent(e)
        self._schedule_mode()

    def leaveEvent(self, e) -> None:
        super().leaveEvent(e)
        self._schedule_mode()

    def changeEvent(self, e) -> None:
        super().changeEvent(e)
        if e.type() == QEvent.ActivationChange:
            self._schedule_mode()
        elif e.type() == QEvent.WindowStateChange:
            self.root.update()  # 최대화 시 모서리 둥글기 변경

    def contextMenuEvent(self, e) -> None:
        menu = QMenu(self)
        a_hide = menu.addAction("평소엔 달력만 보이기 (메모 칸·버튼 자동 숨김)")
        a_hide.setCheckable(True)
        a_hide.setChecked(self.auto_hide)
        a_blur = menu.addAction("창 뒤 흐림 효과")
        a_blur.setCheckable(True)
        a_blur.setChecked(self.blur)
        menu.addSeparator()
        a_quit = menu.addAction("닫기")
        chosen = menu.exec(e.globalPos())
        if chosen is a_hide:
            self.auto_hide = a_hide.isChecked()
            self.settings.setValue("autoHide", self.auto_hide)
            self._schedule_mode()
        elif chosen is a_blur:
            self.blur = a_blur.isChecked()
            self.settings.setValue("blur", self.blur)
            self.root.blurred = apply_window_effects(int(self.winId()), self.blur)
            self.root.update()
        elif chosen is a_quit:
            self.close()

    # ── 동작 ──
    def select_date(self, d: date) -> None:
        if self.save_timer.isActive():
            self._save_now()
        self.current = d
        self.view.set_selected(d)
        self.editor.blockSignals(True)
        self.editor.setPlainText(self.store.get(d))
        self.editor.blockSignals(False)
        self.editor.moveCursor(QTextCursor.End)
        self.date_title.setText(f"{d.month}월 {d.day}일")
        sub = f"{d.year}년 {WEEKDAY_FULL[d.weekday()]}"
        if d == date.today():
            sub += ", 오늘"
        self.date_sub.setText(sub)
        self._update_month_label()

    def _on_double_click(self, d: date) -> None:
        self.select_date(d)
        self.editor.setFocus()

    def _update_month_label(self, *_):
        self.month_label.setText(f"{self.view.month}월")
        self.year_label.setText(f"{self.view.year}년")

    def _on_text_changed(self) -> None:
        self.store.set(self.current, self.editor.toPlainText())
        self.view.update()
        self._set_status("입력 중")
        self.save_timer.start()

    def _save_now(self) -> None:
        self.save_timer.stop()
        if self.store.save():
            self._set_status(f"저장됨 {datetime.now():%H:%M:%S}")
        else:
            self._set_status(f"저장 실패. 로그 확인: {LOG_FILE}", error=True)

    def _set_status(self, text: str, error: bool = False) -> None:
        self.status.setText(text)
        self.status.setStyleSheet("color: #C0392B;" if error else "")

    def _check_day_change(self) -> None:
        now = date.today()
        if now != self._last_today:
            log.info("날짜 변경: %s → %s", self._last_today, now)
            self._last_today = now
            self.view.update()
            self.select_date(self.current)  # '오늘' 표기 갱신

    def closeEvent(self, e) -> None:
        self.save_timer.stop()
        if self.store.dirty and not self.store.save():
            r = QMessageBox.question(
                self, "저장 실패",
                f"메모를 저장하지 못했습니다.\n로그: {LOG_FILE}\n\n저장하지 않고 닫을까요?")
            if r != QMessageBox.Yes:
                e.ignore()
                return
        self.settings.setValue("geometry", self.saveGeometry())
        split = self._split_state if self._compact else self.splitter.saveState()
        if split is not None:
            self.settings.setValue("splitter", split)
        log.info("창 닫힘")
        e.accept()


def main() -> int:
    qInstallMessageHandler(_qt_message_handler)
    set_app_user_model_id()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    if ICON_FILE.exists():
        app.setWindowIcon(QIcon(str(ICON_FILE)))
    else:
        log.warning("아이콘 파일 없음: %s", ICON_FILE)
    app.setStyle("Fusion")
    app.setFont(QFont("Malgun Gothic", 10))
    app.setStyleSheet(STYLE)
    log.info("시작 — 데이터 파일: %s", NOTES_FILE)

    store = NoteStore(NOTES_FILE)
    store.load()
    win = MainWindow(store)
    win.show()
    if store.problem:
        QTimer.singleShot(0, lambda: QMessageBox.warning(win, "메모 파일 문제", store.problem))
    rc = app.exec()
    log.info("종료 코드 %d", rc)
    return rc


if __name__ == "__main__":
    sys.exit(main())
