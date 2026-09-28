# -*- coding: utf-8 -*-
"""
exe 빌드: dist\\reimu-calendar.exe

  python build.py

calendar_notes.pyw 의 __version__ 을 읽어 exe 파일 속성(제품 이름·버전)에 넣는다.
로컬 빌드와 GitHub Actions 빌드가 같은 스크립트를 쓴다.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "calendar_notes.pyw"
ICON = HERE / "app.ico"
BUILD_DIR = HERE / "build"
EXE_NAME = "reimu-calendar"
PRODUCT = "Reimu Calendar"
COPYRIGHT = "Copyright (c) 2026 YGH. MIT License."

VERSION_TEMPLATE = """\
VSVersionInfo(
  ffi=FixedFileInfo(filevers={vt}, prodvers={vt}, mask=0x3f, flags=0x0,
                    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'YGH'),
      StringStruct('FileDescription', {product!r}),
      StringStruct('FileVersion', {version!r}),
      StringStruct('InternalName', {exe!r}),
      StringStruct('LegalCopyright', {copyright!r}),
      StringStruct('OriginalFilename', {exe_file!r}),
      StringStruct('ProductName', {product!r}),
      StringStruct('ProductVersion', {version!r})])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def read_version() -> str:
    m = re.search(r'^__version__\s*=\s*"(\d+\.\d+\.\d+)"', SOURCE.read_text(encoding="utf-8"), re.M)
    if not m:
        raise SystemExit(f"{SOURCE.name} 에서 __version__ = \"x.y.z\" 를 찾지 못했습니다.")
    return m.group(1)


def main() -> int:
    version = read_version()
    if len(sys.argv) > 1 and sys.argv[1] == "--print-version":
        print(version)
        return 0
    BUILD_DIR.mkdir(exist_ok=True)
    version_file = BUILD_DIR / "version_info.txt"
    version_file.write_text(VERSION_TEMPLATE.format(
        vt=tuple(int(x) for x in version.split(".")) + (0,), version=version, product=PRODUCT,
        exe=EXE_NAME, exe_file=f"{EXE_NAME}.exe", copyright=COPYRIGHT), encoding="utf-8")
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--noconsole",
           "--name", EXE_NAME,
           "--icon", str(ICON),
           "--add-data", f"{ICON}{';' if sys.platform == 'win32' else ':'}.",
           "--version-file", str(version_file),
           "--specpath", str(BUILD_DIR),
           str(SOURCE)]
    print(f"{PRODUCT} {version} 빌드 중…", flush=True)
    rc = subprocess.call(cmd, cwd=HERE)
    if rc == 0:
        print(f"완료: {HERE / 'dist' / (EXE_NAME + '.exe')}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
