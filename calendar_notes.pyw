# -*- coding: utf-8 -*-
"""
달력 메모 (Calendar Notes)

날짜를 누르고 그날 있는 일을 직접 적어두는 간단한 달력 창.

  메모 저장 : %APPDATA%\\CalendarNotes\\notes.json   (입력 후 0.6초 뒤 자동 저장)
  로그 파일 : %APPDATA%\\CalendarNotes\\logs\\calendar.log
  필요 패키지: pip install -r requirements.txt   (PySide6, holidays)

단축키
  Alt+←  / Alt+→   이전 달 / 다음 달   (마우스 휠도 가능)
  Ctrl+T           오늘로 이동
  Ctrl+S           즉시 저장
  더블클릭          해당 날짜 선택 후 바로 입력
  Ctrl+Alt+Space   (어디서든) 오늘 메모 바로 쓰기 — Esc 로 하던 창으로 복귀
                   다른 프로그램이 쓰는 중이면 다른 후보로 자동 대체, 우클릭 메뉴에서 변경
  F1               사용법 안내
  우클릭            설정 메뉴 (자동 숨김 / 흐림 / 창 위치 / 자동 실행 / 종료)

창에 마우스가 없고 다른 창을 쓰는 중이면 버튼·메모 칸이 숨고 달력만 보인다.
닫기(×)는 트레이로 숨기기이고, 완전히 끄려면 트레이나 우클릭 메뉴의 '종료'.
--autostart 로 실행하면(Windows 시작 시 자동 실행) 포커스를 뺏지 않고 달력만 띄운다.
디버그 로그를 보려면 환경변수 CALENDAR_DEBUG=1 로 실행.
"""
from __future__ import annotations

import calendar
import ctypes
import getpass
import json
import logging
import os
import sys
from ctypes import wintypes
from datetime import date, datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

__version__ = "1.1.0"  # build.py 가 exe 버전 정보로 사용, 릴리스 태그(v1.1.0)와 일치해야 함

APP_NAME = "CalendarNotes"
DATA_DIR = Path(os.environ.get("APPDATA") or (Path.home() / ".local" / "share")) / APP_NAME
NOTES_FILE = DATA_DIR / "notes.json"
LOG_DIR = DATA_DIR / "logs"
LOG_FILE = LOG_DIR / "calendar.log"
# PyInstaller 빌드면 압축이 풀린 임시 폴더, 아니면 이 파일 옆
RES_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
ICON_FILE = RES_DIR / "app.ico"
INSTANCE_SERVER = f"{APP_NAME}-{getpass.getuser()}"  # 중복 실행 방지용 (사용자별)


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
    from PySide6.QtGui import (QActionGroup, QColor, QCursor, QFont, QFontMetricsF, QIcon,
                               QKeySequence, QLinearGradient, QPainter, QPainterPath, QPen,
                               QShortcut, QTextCursor)
    from PySide6.QtNetwork import QLocalServer, QLocalSocket
    from PySide6.QtWidgets import (QApplication, QDialog, QGridLayout, QHBoxLayout, QLabel,
                                   QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QPushButton,
                                   QSizePolicy, QSplitter, QSystemTrayIcon, QVBoxLayout, QWidget)
except ImportError:
    log.critical("PySide6 import 실패 — 'pip install PySide6' 필요", exc_info=True)
    raise SystemExit(1)

try:
    import holidays
except ImportError:  # 공휴일 표시만 빠지고 나머지는 동작
    holidays = None
    log.warning("holidays 패키지 없음 — 공휴일 표시 안 함 ('pip install holidays')")

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
QLabel#guideTitle { font-size: 24px; font-weight: 700; color: #B3122C; }
QLabel#guideSub   { font-size: 13px; color: #8C7479; }
QLabel#section    { font-size: 16px; font-weight: 700; color: #2B1D21; padding-top: 4px; }
QWidget#card {
    background: rgba(255,255,255,215); border: 1px solid rgba(200,16,46,40);
    border-left: 4px solid #C8102E; border-radius: 10px;
}
QLabel#cardTitle { font-size: 15px; font-weight: 700; color: #B3122C; }
QLabel#cardText  { font-size: 13px; color: #4A363C; }
QLabel#key {
    background: #FFFFFF; border: 1px solid rgba(200,16,46,80); border-bottom: 3px solid rgba(200,16,46,80);
    border-radius: 6px; padding: 2px 8px; color: #9E1027; font-size: 12px; font-weight: 700;
}
QLabel#keyDesc { font-size: 13px; color: #2B1D21; }
QLabel#keyWarn { font-size: 12px; color: #C0392B; }
QWidget#recBox { background: rgba(200,16,46,18); border: 1px dashed rgba(200,16,46,110); border-radius: 10px; }
QLabel#recText { font-size: 13px; color: #2B1D21; }
QPushButton#primary {
    background: #C8102E; color: #FFFFFF; border: none; border-radius: 8px;
    padding: 7px 18px; font-size: 13px; font-weight: 700;
}
QPushButton#primary:hover    { background: #A90D26; }
QPushButton#primary:disabled { background: rgba(200,16,46,110); color: #FFFFFF; }
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


# 창 위치(다른 창과의 앞뒤 관계)
LAYER_NORMAL, LAYER_TOP, LAYER_BOTTOM = "normal", "top", "bottom"
_HWND_TOPMOST, _HWND_NOTOPMOST, _HWND_BOTTOM = -1, -2, 1
_SWP_NOSIZE, _SWP_NOMOVE, _SWP_NOZORDER, _SWP_NOACTIVATE = 0x1, 0x2, 0x4, 0x10
_WM_WINDOWPOSCHANGING = 0x0046


class _WindowPos(ctypes.Structure):
    _fields_ = [("hwnd", ctypes.c_void_p), ("hwndInsertAfter", ctypes.c_void_p),
                ("x", ctypes.c_int), ("y", ctypes.c_int), ("cx", ctypes.c_int), ("cy", ctypes.c_int),
                ("flags", ctypes.c_uint)]


def set_window_layer(hwnd: int, layer: str) -> None:
    """항상 위 / 보통 / 맨 뒤로. '바탕화면 고정'은 이후 WM_WINDOWPOSCHANGING 에서 계속 맨 뒤로 붙잡는다."""
    if sys.platform != "win32":
        return
    after = {LAYER_TOP: _HWND_TOPMOST, LAYER_BOTTOM: _HWND_BOTTOM}.get(layer, _HWND_NOTOPMOST)
    try:
        user32 = ctypes.windll.user32
        if layer == LAYER_BOTTOM:  # 항상 위였다면 먼저 풀어야 맨 뒤로 갈 수 있음
            user32.SetWindowPos(ctypes.c_void_p(hwnd), ctypes.c_void_p(_HWND_NOTOPMOST), 0, 0, 0, 0,
                                _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOACTIVATE)
        user32.SetWindowPos(ctypes.c_void_p(hwnd), ctypes.c_void_p(after), 0, 0, 0, 0,
                            _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOACTIVATE)
    except (AttributeError, OSError):
        log.warning("창 위치 설정 실패: %s", layer, exc_info=True)


# 빠른 메모 전역 단축키. 다른 프로그램이 이미 쓰는 키는 등록이 안 되므로 후보 중에서 고른다.
# (개발 도구와 겹치는 Ctrl+Alt+M/N, Ctrl+Shift+Space, 입력 언어 전환인 Alt+Shift 조합은 뺌)
_MOD_ALT, _MOD_CONTROL, _MOD_WIN, _MOD_NOREPEAT = 0x1, 0x2, 0x8, 0x4000
HOTKEYS = {  # 설정 값 → (표시, 수정키, 가상 키 코드)
    "ctrl+alt+space": ("Ctrl + Alt + Space", _MOD_CONTROL | _MOD_ALT, 0x20),
    "ctrl+alt+enter": ("Ctrl + Alt + Enter", _MOD_CONTROL | _MOD_ALT, 0x0D),
    "ctrl+alt+`": ("Ctrl + Alt + `", _MOD_CONTROL | _MOD_ALT, 0xC0),
    "win+alt+n": ("Win + Alt + N", _MOD_WIN | _MOD_ALT, ord("N")),
}
DEFAULT_HOTKEY = "ctrl+alt+space"
_HOTKEY_ID, _PROBE_ID = 1, 2
_WM_HOTKEY = 0x0312


def register_hotkey(hwnd: int, key: str) -> bool:
    """hwnd 에 빠른 메모 단축키를 (다시) 등록. 이전 등록은 먼저 푼다."""
    if sys.platform != "win32" or key not in HOTKEYS:
        return False
    _, mods, vk = HOTKEYS[key]
    try:
        user32 = ctypes.windll.user32
        user32.UnregisterHotKey(ctypes.c_void_p(hwnd), _HOTKEY_ID)
        return bool(user32.RegisterHotKey(ctypes.c_void_p(hwnd), _HOTKEY_ID, mods | _MOD_NOREPEAT, vk))
    except (AttributeError, OSError):
        log.warning("단축키 등록 오류: %s", key, exc_info=True)
        return False


def hotkey_available(key: str) -> bool:
    """다른 프로그램이 쓰고 있지 않은지 (잠깐 등록했다가 바로 푼다)."""
    if sys.platform != "win32":
        return False
    _, mods, vk = HOTKEYS[key]
    user32 = ctypes.windll.user32
    if user32.RegisterHotKey(None, _PROBE_ID, mods | _MOD_NOREPEAT, vk):
        user32.UnregisterHotKey(None, _PROBE_ID)
        return True
    return False


def foreground_window() -> int:
    if sys.platform != "win32":
        return 0
    fn = ctypes.windll.user32.GetForegroundWindow
    fn.restype = ctypes.c_void_p  # 64비트 핸들이 int 로 잘리지 않게
    return fn() or 0


def activate_window(hwnd: int) -> None:
    """빠른 메모를 마치고 원래 쓰던 창으로 돌려보낸다."""
    if sys.platform != "win32" or not hwnd:
        return
    user32 = ctypes.windll.user32
    if user32.IsWindow(ctypes.c_void_p(hwnd)):
        user32.SetForegroundWindow(ctypes.c_void_p(hwnd))


# Windows 시작 시 자동 실행 (HKCU Run — 관리자 권한 불필요)
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_VALUE = "ReimuCalendar"
AUTOSTART_ARG = "--autostart"


def autostart_command() -> str:
    if getattr(sys, "frozen", False):  # PyInstaller exe
        return f'"{sys.executable}" {AUTOSTART_ARG}'
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")  # 콘솔 창 없이
    return f'"{pythonw if pythonw.exists() else exe}" "{Path(__file__).resolve()}" {AUTOSTART_ARG}'


def get_autostart() -> str | None:
    """등록된 명령줄, 없으면 None."""
    if sys.platform != "win32":
        return None
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            return winreg.QueryValueEx(k, _RUN_VALUE)[0]
    except FileNotFoundError:
        return None
    except OSError:
        log.warning("자동 실행 설정 읽기 실패", exc_info=True)
        return None


def set_autostart(enabled: bool) -> bool:
    if sys.platform != "win32":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if enabled:
                winreg.SetValueEx(k, _RUN_VALUE, 0, winreg.REG_SZ, autostart_command())
            else:
                try:
                    winreg.DeleteValue(k, _RUN_VALUE)
                except FileNotFoundError:
                    pass
        log.info("자동 실행 %s", "등록" if enabled else "해제")
        return True
    except OSError:
        log.exception("자동 실행 %s 실패", "등록" if enabled else "해제")
        return False


# ─────────────────────────────── 공휴일 ───────────────────────────────
class KoreanHolidays:
    """날짜 → 한국 공휴일 이름 (설·추석 연휴, 대체공휴일, 선거일 포함). 인터넷 없이 계산."""

    def __init__(self):
        self._kr = None
        if holidays is None:
            return
        try:
            self._kr = holidays.country_holidays("KR", language="ko")
        except Exception:  # 번역 파일 누락 등 — 공휴일만 포기
            log.exception("공휴일 데이터 초기화 실패")

    def name(self, d: date) -> str:
        if self._kr is None:
            return ""
        try:
            return (self._kr.get(d) or "").replace("; ", ", ")
        except Exception:
            log.exception("공휴일 조회 실패: %s", d)
            self._kr = None
            return ""


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

    def __init__(self, store: NoteStore, holidays: KoreanHolidays, parent=None):
        super().__init__(parent)
        self.store = store
        self.holidays = holidays
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
        hol_font = QFont(base)
        hol_font.setPointSizeF(base.pointSizeF() * 0.85)
        hol_metrics = QFontMetricsF(hol_font)

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

            holiday = self.holidays.name(d)
            nr = QRectF(r.left() + 7, r.top() + 6, 28, 28)
            p.setFont(num_font)
            if d == today:
                p.setPen(Qt.NoPen)
                p.setBrush(ACCENT)
                p.drawEllipse(nr)
                p.setBrush(Qt.NoBrush)
                p.setPen(QColor("#FFFFFF"))
            else:
                col = QColor(SUN if wd == 6 or holiday else SAT if wd == 5 else INK)
                if not in_month:
                    col.setAlpha(80)
                p.setPen(col)
            p.drawText(nr, int(Qt.AlignCenter), str(d.day))

            # 공휴일 이름 (숫자 옆, 칸이 좁으면 … 으로 줄임)
            if holiday:
                hr = QRectF(nr.right() + 3, nr.top(), r.right() - 20 - (nr.right() + 3), nr.height())
                if hr.width() > 12:
                    col = QColor(SUN)
                    if not in_month:
                        col.setAlpha(90)
                    p.setFont(hol_font)
                    p.setPen(col)
                    p.drawText(hr, int(Qt.AlignLeft | Qt.AlignVCenter),
                               hol_metrics.elidedText(holiday, Qt.ElideRight, hr.width()))

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

    def __init__(self, parent=None, resizable: bool = True):
        super().__init__(parent)
        self.blurred = False  # 창 뒤 흐림이 켜졌으면 바탕을 더 투명하게
        self.resizable = resizable
        self.setMouseTracking(resizable)

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
        if not self.resizable or self.window().isMaximized():
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
    """상단 바. 빈 곳을 끌면 창 이동, (메인 창이면) 더블클릭하면 최대화/복원."""

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self.window().windowHandle().startSystemMove()
        else:
            super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e) -> None:
        w = self.window()
        if e.button() == Qt.LeftButton and isinstance(w, QMainWindow):
            w.showNormal() if w.isMaximized() else w.showMaximized()


# ─────────────────────────────── 사용법 안내 ───────────────────────────────
GUIDE_CARDS = [
    ("적기만 하면 끝",
     "날짜를 누르고 적으세요. 저장 버튼 없이 바로 저장되고, 저장 중에 전원이 꺼져도 메모가 깨지지 않아요."),
    ("어디서든 1초 메모",
     "다른 프로그램을 쓰다가 {hotkey}를 누르면 오늘 메모가 바로 열려요. 다 적고 Esc를 누르면 하던 일로 돌아가요."),
    ("평소엔 달력만",
     "안 쓸 땐 버튼과 메모 칸이 숨어서 바탕화면 달력처럼 깔끔해요. 설날·추석 같은 공휴일도 알아서 표시해요."),
    ("내 PC에만 저장",
     "계정도, 인터넷 연결도 없어요. 메모는 이 PC 안에만 저장되고 어디로도 보내지 않아요."),
]
GUIDE_KEYS = [
    ("날짜 클릭", "그날 메모 보기·쓰기"),
    ("날짜 더블클릭", "바로 입력"),
    ("{hotkey}", "어디서든 오늘 메모 (Esc로 복귀)"),
    ("휠  ·  Alt + ← →", "이전 / 다음 달"),
    ("Ctrl + T", "오늘로 이동"),
    ("우클릭", "설정 (창 위치, 자동 실행 …)"),
    ("×", "트레이로 숨기기 (끄기: 우클릭 → 종료)"),
    ("F1", "이 안내 다시 보기"),
]


class GuideDialog(QDialog):
    """왜 좋은지 + 쓰는 법. 처음 실행 때 한 번 뜨고, F1·우클릭·트레이 메뉴로 다시 열 수 있다.

    바탕화면 고정 중인 메인 창에 묶이면 같이 뒤로 깔리므로 부모 없는 독립 창으로 띄운다.
    """

    def __init__(self, win: "MainWindow"):
        super().__init__(None)
        self.win = win
        self.setWindowTitle("Reimu Calendar 사용법")
        self.setWindowIcon(win.windowIcon())
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.root = GlassRoot(resizable=False)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.root)
        v = QVBoxLayout(self.root)
        v.setContentsMargins(26, 14, 26, 22)
        v.setSpacing(10)

        # 제목 (끌어서 이동)
        bar = TitleBar()
        h = QHBoxLayout(bar)
        h.setContentsMargins(0, 6, 0, 0)
        h.setSpacing(12)
        icon = QLabel()
        icon.setPixmap(win.windowIcon().pixmap(48, 48))
        titles = QVBoxLayout()
        titles.setSpacing(0)
        titles.addWidget(QLabel("Reimu Calendar", objectName="guideTitle"))
        titles.addWidget(QLabel(f"v{__version__}  ·  적기만 하면 되는 바탕화면 달력", objectName="guideSub"))
        close = QPushButton("×", objectName="closeBtn")
        close.setCursor(Qt.PointingHandCursor)
        close.setFocusPolicy(Qt.NoFocus)
        close.clicked.connect(self.close)
        h.addWidget(icon)
        h.addLayout(titles)
        h.addStretch(1)
        h.addWidget(close, 0, Qt.AlignTop)
        v.addWidget(bar)

        # 이래서 편해요
        v.addWidget(QLabel("이래서 편해요", objectName="section"))
        cards = QGridLayout()
        cards.setSpacing(10)
        hotkey = win.hotkey_text
        for i, (title, text) in enumerate(GUIDE_CARDS):
            text = text.format(hotkey=hotkey)
            card = QWidget(objectName="card")
            card.setAttribute(Qt.WA_StyledBackground, True)
            cl = QVBoxLayout(card)
            cl.setContentsMargins(14, 10, 14, 12)
            cl.setSpacing(4)
            body = QLabel(text, objectName="cardText")
            body.setWordWrap(True)
            cl.addWidget(QLabel(title, objectName="cardTitle"))
            cl.addWidget(body, 1)
            cards.addWidget(card, i // 2, i % 2)
        v.addLayout(cards)

        # 쓰는 법
        v.addWidget(QLabel("쓰는 법", objectName="section"))
        keys = QGridLayout()
        keys.setHorizontalSpacing(12)
        keys.setVerticalSpacing(8)
        half = (len(GUIDE_KEYS) + 1) // 2
        for i, (key, desc) in enumerate(GUIDE_KEYS):
            row, col = i % half, (i // half) * 2
            keys.addWidget(QLabel(key.format(hotkey=hotkey), objectName="key"), row, col, Qt.AlignLeft)
            keys.addWidget(QLabel(desc, objectName="keyDesc"), row, col + 1)
        keys.setColumnStretch(1, 1)
        keys.setColumnStretch(3, 1)
        v.addLayout(keys)
        note = None
        if win.hotkey is None:
            note = "※ 빠른 메모 단축키 후보를 모두 다른 프로그램이 쓰고 있어서 지금은 동작하지 않아요."
        elif win.hotkey != win.hotkey_wanted:
            note = (f"※ {HOTKEYS[win.hotkey_wanted][0]}는 다른 프로그램이 쓰고 있어서 {hotkey}로 대신 쓰고 있어요. "
                    "우클릭 → 빠른 메모 단축키에서 바꿀 수 있어요.")
        if note:
            warn = QLabel(note, objectName="keyWarn")
            warn.setWordWrap(True)
            v.addWidget(warn)

        # 추천 설정
        rec = QWidget(objectName="recBox")
        rec.setAttribute(Qt.WA_StyledBackground, True)
        rl = QHBoxLayout(rec)
        rl.setContentsMargins(14, 10, 10, 10)
        rec_text = QLabel("<b>추천 설정</b> — 바탕화면에 고정 + Windows 시작 시 자동 실행<br>"
                          "컴퓨터를 켜면 바탕화면에 달력이 깔려 있어요.", objectName="recText")
        self.rec_btn = QPushButton("추천 설정 켜기", objectName="primary")
        self.rec_btn.setCursor(Qt.PointingHandCursor)
        self.rec_btn.clicked.connect(self._apply_recommended)
        rl.addWidget(rec_text, 1)
        rl.addWidget(self.rec_btn)
        v.addWidget(rec)
        self._refresh_rec()

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        start = QPushButton("시작하기")
        start.setCursor(Qt.PointingHandCursor)
        start.clicked.connect(self.close)
        bottom.addWidget(start)
        v.addLayout(bottom)

        QShortcut(QKeySequence("Esc"), self, activated=self.close)
        self.setFixedWidth(760)
        self.adjustSize()

    def _recommended_on(self) -> bool:
        autostart = sys.platform != "win32" or get_autostart() is not None
        return self.win.layer == LAYER_BOTTOM and autostart

    def _refresh_rec(self) -> None:
        on = self._recommended_on()
        self.rec_btn.setEnabled(not on)
        self.rec_btn.setText("켜져 있어요" if on else "추천 설정 켜기")

    def _apply_recommended(self) -> None:
        self.win.set_layer(LAYER_BOTTOM)
        if sys.platform == "win32" and not set_autostart(True):
            QMessageBox.warning(self, "자동 실행", f"자동 실행 설정을 바꾸지 못했습니다.\n로그: {LOG_FILE}")
        self._refresh_rec()

    def showEvent(self, e) -> None:
        super().showEvent(e)
        self.root.blurred = apply_window_effects(int(self.winId()), self.win.blur)
        self.root.update()
        # 메인 창이 있는 화면 가운데
        screen = (self.win.screen() or QApplication.primaryScreen()).availableGeometry()
        self.move(screen.center() - self.rect().center())


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
        self.layer = self.settings.value("layer", LAYER_NORMAL, type=str)
        if self.layer not in (LAYER_NORMAL, LAYER_TOP, LAYER_BOTTOM):
            self.layer = LAYER_NORMAL
        self._compact = False
        self._split_state = None  # 메모 칸을 숨기기 직전의 분할 비율
        self._pin_suspended = False  # 바탕화면 고정 중 트레이에서 불러와 잠깐 앞에 나온 상태
        self._quitting = False       # True 면 닫기 = 종료, False 면 닫기 = 트레이로 숨기기
        self._quick = False          # 전역 단축키로 불러온 빠른 메모 중
        self._quick_prev = 0         # 빠른 메모 전에 쓰던 창 (Esc 로 돌아갈 곳)
        self._quick_active_seen = False
        self._quick_was_hidden = False
        self.hotkey_wanted = self.settings.value("hotkey", DEFAULT_HOTKEY, type=str)
        if self.hotkey_wanted not in HOTKEYS:
            self.hotkey_wanted = DEFAULT_HOTKEY
        self.hotkey = None  # 실제로 등록된 단축키 (None = 못 씀)
        self._guide = None
        self.holidays = KoreanHolidays()
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
        self.close_btn.setToolTip("트레이로 숨기기 (완전히 끄려면 우클릭 → 종료)")
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
        self.view = MonthView(store, self.holidays)
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
        QShortcut(QKeySequence("Esc"), self, activated=self.leave_quick)
        QShortcut(QKeySequence("F1"), self, activated=self.show_guide)

        # 트레이 아이콘 (없는 환경이면 닫기 = 종료)
        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(self.windowIcon(), self)
            self.tray.setToolTip("Reimu Calendar")
            tray_menu = QMenu(self)
            tray_menu.addAction("달력 열기", self.show_from_tray)
            self._tray_quick = tray_menu.addAction("오늘 메모 쓰기", self.quick_note)
            tray_menu.addAction("사용법  (F1)", self.show_guide)
            tray_menu.addSeparator()
            tray_menu.addAction("종료", self.quit_app)
            self.tray.setContextMenu(tray_menu)
            self.tray.activated.connect(self._on_tray_activated)
            self.tray.show()
        else:
            log.warning("시스템 트레이 없음 — 닫기를 누르면 종료")

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
        if not self._pin_suspended:
            set_window_layer(int(self.winId()), self.layer)

    def set_layer(self, layer: str) -> None:
        self.layer = layer
        self._pin_suspended = False
        self.settings.setValue("layer", layer)
        set_window_layer(int(self.winId()), layer)
        log.info("창 위치: %s", layer)

    def nativeEvent(self, event_type, message):
        if bytes(event_type) == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == _WM_HOTKEY and msg.wParam == _HOTKEY_ID:
                QTimer.singleShot(0, self.quick_note)  # 네이티브 메시지 처리 밖에서 창 전환
                return True, 0
            # 바탕화면 고정: 클릭·활성화 등으로 앞에 나오려 할 때마다 맨 뒤로 되돌린다
            if (msg.message == _WM_WINDOWPOSCHANGING and msg.lParam
                    and self.layer == LAYER_BOTTOM and not self._pin_suspended):
                pos = _WindowPos.from_address(msg.lParam)
                if not pos.flags & _SWP_NOZORDER:
                    pos.hwndInsertAfter = _HWND_BOTTOM
        return super().nativeEvent(event_type, message)

    def _want_compact(self) -> bool:
        if not self.auto_hide or self.isMinimized() or self._quick:
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
            if self._quick and self.isActiveWindow():
                self._quick_active_seen = True
            elif self._quick and self._quick_active_seen:
                self._quick = False  # 다른 창을 눌러 빠져나감 — 창은 그대로 두고 빠른 메모만 끝
                if self.save_timer.isActive():
                    self._save_now()
            if self._pin_suspended and not self.isActiveWindow():
                self._pin_suspended = False  # 다 쓰고 다른 창으로 가면 다시 바탕화면으로
                set_window_layer(int(self.winId()), self.layer)
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

        layer_menu = menu.addMenu("창 위치")
        group = QActionGroup(layer_menu)
        layer_actions = {}
        for layer, label in ((LAYER_NORMAL, "보통"),
                             (LAYER_TOP, "항상 위"),
                             (LAYER_BOTTOM, "바탕화면에 고정 (다른 창 뒤)")):
            a = layer_menu.addAction(label)
            a.setCheckable(True)
            a.setChecked(self.layer == layer)
            group.addAction(a)
            layer_actions[a] = layer

        hotkey_actions = {}
        if sys.platform == "win32":
            hk_menu = menu.addMenu("빠른 메모 단축키")
            hk_group = QActionGroup(hk_menu)
            for key, (label, _, _) in HOTKEYS.items():
                usable = key == self.hotkey or hotkey_available(key)
                a = hk_menu.addAction(label if usable else f"{label}  (다른 프로그램이 사용 중)")
                a.setCheckable(True)
                a.setChecked(key == self.hotkey)
                a.setEnabled(usable)
                hk_group.addAction(a)
                hotkey_actions[a] = key

        a_auto = None
        if sys.platform == "win32":
            a_auto = menu.addAction("Windows 시작 시 자동 실행")
            a_auto.setCheckable(True)
            a_auto.setChecked(get_autostart() is not None)
        menu.addSeparator()
        a_guide = menu.addAction("사용법  (F1)")
        a_quit = menu.addAction("종료")

        chosen = menu.exec(e.globalPos())
        if chosen is None:
            return
        if chosen is a_hide:
            self.auto_hide = a_hide.isChecked()
            self.settings.setValue("autoHide", self.auto_hide)
            self._schedule_mode()
        elif chosen is a_blur:
            self.blur = a_blur.isChecked()
            self.settings.setValue("blur", self.blur)
            self.root.blurred = apply_window_effects(int(self.winId()), self.blur)
            self.root.update()
        elif chosen in layer_actions:
            self.set_layer(layer_actions[chosen])
        elif chosen in hotkey_actions:
            self.change_hotkey(hotkey_actions[chosen])
        elif chosen is a_auto:
            if not set_autostart(a_auto.isChecked()):
                QMessageBox.warning(self, "자동 실행", f"자동 실행 설정을 바꾸지 못했습니다.\n로그: {LOG_FILE}")
        elif chosen is a_guide:
            self.show_guide()
        elif chosen is a_quit:
            self.quit_app()

    # ── 빠른 메모 / 사용법 ──
    @property
    def hotkey_text(self) -> str:
        return HOTKEYS[self.hotkey][0] if self.hotkey else "(단축키 없음)"

    def register_global_hotkey(self) -> None:
        """원하는 키부터 시도하고, 다른 프로그램이 쓰고 있으면 나머지 후보 중 빈 키로."""
        hwnd = int(self.winId())
        order = [self.hotkey_wanted] + [k for k in HOTKEYS if k != self.hotkey_wanted]
        self.hotkey = next((k for k in order if register_hotkey(hwnd, k)), None)
        if self.hotkey is None:
            log.warning("빠른 메모 단축키 후보를 모두 다른 프로그램이 사용 중 — 단축키 없음")
        elif self.hotkey != self.hotkey_wanted:
            log.warning("%s 는 다른 프로그램이 사용 중 → %s 로 대체",
                        HOTKEYS[self.hotkey_wanted][0], self.hotkey_text)
        else:
            log.info("빠른 메모 단축키: %s", self.hotkey_text)
        self._update_hotkey_labels()

    def change_hotkey(self, key: str) -> None:
        if register_hotkey(int(self.winId()), key):
            self.hotkey = self.hotkey_wanted = key
            self.settings.setValue("hotkey", key)
            log.info("빠른 메모 단축키 변경: %s", self.hotkey_text)
        else:
            QMessageBox.warning(self, "빠른 메모 단축키",
                                f"{HOTKEYS[key][0]}는 다른 프로그램이 쓰고 있어서 쓸 수 없습니다.")
            if self.hotkey:
                register_hotkey(int(self.winId()), self.hotkey)  # 원래 키 복구
        self._update_hotkey_labels()

    def _update_hotkey_labels(self) -> None:
        if self.tray is not None:
            self._tray_quick.setText(f"오늘 메모 쓰기  ({self.hotkey_text})" if self.hotkey else "오늘 메모 쓰기")

    def quick_note(self) -> None:
        """어디서든 단축키 → 오늘 메모에 바로 커서. 한 번 더 누르면 원래 창으로."""
        if self._quick and self.isActiveWindow():
            self.leave_quick()
            return
        prev = foreground_window()
        self._quick_prev = prev if prev != int(self.winId()) else 0
        self._quick_was_hidden = not self.isVisible() or self.isMinimized()
        self._quick = True
        self._quick_active_seen = False  # 실제로 활성화되기 전의 비활성 이벤트로 끝나지 않게
        self.show_from_tray()
        self._apply_mode()  # 달력만 보이던 상태였어도 메모 칸을 바로 펼침
        self.select_date(date.today())
        self.editor.setFocus()
        self.editor.moveCursor(QTextCursor.End)
        log.debug("빠른 메모 시작 (이전 창 %s)", self._quick_prev)

    def leave_quick(self) -> None:
        """Esc: 저장하고 빠른 메모 전 상태(쓰던 창, 트레이에 숨어 있었다면 다시 숨김)로."""
        if not self._quick:
            return
        self._quick = False
        if self.save_timer.isActive():
            self._save_now()
        if self._quick_was_hidden:
            self.hide()
        activate_window(self._quick_prev)
        self._schedule_mode()

    def show_guide(self) -> None:
        if self._guide is not None:  # 단축키·설정이 바뀌었을 수 있으니 매번 새로
            self._guide.close()
            self._guide.deleteLater()
        self._guide = GuideDialog(self)
        self._guide.show()
        self._guide.raise_()
        self._guide.activateWindow()
        self.settings.setValue("guideShown", True)

    # ── 트레이 / 종료 ──
    def _on_tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.show_from_tray()

    def show_from_tray(self) -> None:
        """트레이·중복 실행에서 불러올 때. 바탕화면 고정이어도 잠깐 앞으로 꺼내준다."""
        if self.layer == LAYER_BOTTOM:
            self._pin_suspended = True
            set_window_layer(int(self.winId()), LAYER_NORMAL)
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()

    def hide_to_tray(self) -> None:
        if self.save_timer.isActive():
            self._save_now()
        self.hide()
        if self.tray is not None and not self.settings.value("trayHintShown", False, type=bool):
            self.tray.showMessage("Reimu Calendar",
                                  "트레이로 숨겼습니다. 완전히 끄려면 이 아이콘을 우클릭 → 종료를 누르세요.",
                                  self.windowIcon(), 5000)
            self.settings.setValue("trayHintShown", True)

    def quit_app(self) -> None:
        self._quitting = True
        if self.close():
            QApplication.quit()
        else:
            self._quitting = False  # 저장 실패로 사용자가 종료를 취소함

    def prepare_session_end(self) -> None:
        """Windows 종료·로그오프 직전. 닫기를 트레이로 돌리면 종료를 막게 되므로 '진짜 종료'로 바꾼다."""
        log.info("Windows 종료/로그오프 — 저장하고 종료 준비")
        self._quitting = True
        self.persist()

    def persist(self) -> None:
        """메모·창 위치·분할 비율 저장 (종료 직전 / Windows 로그오프 시)."""
        self.save_timer.stop()
        if self.store.dirty:
            self.store.save()
        self.settings.setValue("geometry", self.saveGeometry())
        split = self._split_state if self._compact else self.splitter.saveState()
        if split is not None:
            self.settings.setValue("splitter", split)
        self.settings.sync()

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
        holiday = self.holidays.name(d)
        if holiday:
            sub += f" · {holiday}"
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
        if not self._quitting and self.tray is not None:  # ×, Alt+F4 → 트레이로
            e.ignore()
            self.hide_to_tray()
            return
        self.save_timer.stop()
        if self.store.dirty and not self.store.save():
            r = QMessageBox.question(
                self, "저장 실패",
                f"메모를 저장하지 못했습니다.\n로그: {LOG_FILE}\n\n저장하지 않고 닫을까요?")
            if r != QMessageBox.Yes:
                e.ignore()
                return
        self.persist()
        if self.tray is not None:
            self.tray.hide()
        log.info("창 닫힘")
        e.accept()


def notify_running_instance() -> bool:
    """이미 실행 중인 창이 있으면 그 창을 불러오라고 알리고 True."""
    sock = QLocalSocket()
    sock.connectToServer(INSTANCE_SERVER)
    if not sock.waitForConnected(500):
        return False
    sock.write(b"show\n")
    sock.waitForBytesWritten(500)
    sock.disconnectFromServer()
    return True


def start_instance_server(win: MainWindow) -> QLocalServer:
    server = QLocalServer(win)
    QLocalServer.removeServer(INSTANCE_SERVER)  # 비정상 종료로 남은 이름 정리 (Windows 에선 영향 없음)
    if not server.listen(INSTANCE_SERVER):
        log.warning("중복 실행 감지 서버 시작 실패: %s", server.errorString())

    def on_connection():
        conn = server.nextPendingConnection()
        if conn is not None:
            conn.disconnected.connect(conn.deleteLater)
            log.info("다른 실행 요청 → 기존 창 표시")
            win.show_from_tray()

    server.newConnection.connect(on_connection)
    return server


def main() -> int:
    qInstallMessageHandler(_qt_message_handler)
    set_app_user_model_id()
    autostarted = AUTOSTART_ARG in sys.argv
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    if notify_running_instance():
        log.info("이미 실행 중 — 기존 창을 불러오고 종료")
        return 0
    app.setQuitOnLastWindowClosed(False)  # 창을 트레이로 숨겨도 계속 실행
    if ICON_FILE.exists():
        app.setWindowIcon(QIcon(str(ICON_FILE)))
    else:
        log.warning("아이콘 파일 없음: %s", ICON_FILE)
    app.setStyle("Fusion")
    app.setFont(QFont("Malgun Gothic", 10))
    app.setStyleSheet(STYLE)
    log.info("시작 v%s%s — 데이터 파일: %s", __version__, " (자동 실행)" if autostarted else "", NOTES_FILE)

    # exe 를 옮겼으면 자동 실행에 등록된 경로도 지금 위치로 갱신
    registered = get_autostart()
    if registered is not None and registered != autostart_command():
        log.info("자동 실행 경로 갱신: %s → %s", registered, autostart_command())
        set_autostart(True)

    store = NoteStore(NOTES_FILE)
    store.load()
    win = MainWindow(store)
    start_instance_server(win)  # 창이 부모라 창과 같이 유지됨
    app.aboutToQuit.connect(win.persist)
    app.commitDataRequest.connect(lambda _m: win.prepare_session_end())  # Windows 로그오프/종료
    if autostarted:  # 부팅 직후엔 포커스를 뺏지 않고 달력만
        win.setAttribute(Qt.WA_ShowWithoutActivating, True)
    win.show()
    win.register_global_hotkey()
    if autostarted:
        win._apply_mode()
    elif not win.settings.value("guideShown", False, type=bool):
        QTimer.singleShot(500, win.show_guide)  # 처음 실행이면 사용법 안내
    if store.problem:
        QTimer.singleShot(0, lambda: QMessageBox.warning(win, "메모 파일 문제", store.problem))
    rc = app.exec()
    log.info("종료 코드 %d", rc)
    return rc


if __name__ == "__main__":
    sys.exit(main())
