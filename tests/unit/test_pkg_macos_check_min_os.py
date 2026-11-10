"""packaging/macos/check_min_os.py senza Mac: output di otool registrati.

Gli output qui sotto riproducono il formato di `otool -arch all -l` di
Xcode 15-16 (llvm-otool: "platform 1", "tool 3") e del vecchio otool di
cctools ("platform MACOS"). otool si inietta, quindi il parsing e la
scansione del bundle girano anche su Windows; che otool vero stampi
proprio così lo conferma solo la CI sul Mac (§9.6).
"""

from __future__ import annotations

import importlib.util
import struct
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "packaging" / "macos" / "check_min_os.py"
_spec = importlib.util.spec_from_file_location("check_min_os", SCRIPT)
check = importlib.util.module_from_spec(_spec)
sys.modules["check_min_os"] = check
_spec.loader.exec_module(check)

X86_64 = 0x01000007
ARM64 = 0x0100000C

THIN_OLD_STYLE = """\
/app/Contents/Frameworks/libsndfile.dylib:
Load command 0
      cmd LC_SEGMENT_64
  cmdsize 552
  segname __TEXT
Load command 1
      cmd LC_ID_DYLIB
  cmdsize 56
     name @rpath/libsndfile.dylib (offset 24)
current version 1.0.37
compatibility version 2.0.0
Load command 8
      cmd LC_VERSION_MIN_MACOSX
  cmdsize 16
  version 10.9
      sdk 10.14
Load command 9
      cmd LC_SOURCE_VERSION
  cmdsize 16
  version 99.0
"""

FAT_UNIVERSAL2 = """\
/app/Contents/Frameworks/QtCore (architecture x86_64):
Load command 0
      cmd LC_SEGMENT_64
  cmdsize 72
Load command 10
      cmd LC_BUILD_VERSION
  cmdsize 32
 platform 1
    minos 10.14
      sdk 12.0
   ntools 1
     tool 3
  version 711.0
/app/Contents/Frameworks/QtCore (architecture arm64):
Load command 0
      cmd LC_SEGMENT_64
  cmdsize 72
Load command 10
      cmd LC_BUILD_VERSION
  cmdsize 32
 platform 1
    minos 11.0
      sdk 12.0
   ntools 1
     tool 3
  version 711.0
"""

THIN_CCTOOLS_TOO_NEW = """\
/app/Contents/Frameworks/torch/lib/libtorch_cpu.dylib:
Load command 12
      cmd LC_BUILD_VERSION
  cmdsize 32
 platform MACOS
    minos 10.15.4
      sdk 13.3
   ntools 1
     tool LD
  version 820.1
"""

ZIPPERED = """\
/app/Contents/Frameworks/libzippered.dylib:
Load command 7
      cmd LC_BUILD_VERSION
  cmdsize 32
 platform maccatalyst
    minos 14.0
      sdk 14.0
   ntools 0
Load command 8
      cmd LC_BUILD_VERSION
  cmdsize 32
 platform macos
    minos 10.15
      sdk 14.0
   ntools 0
"""

NO_VERSION = """\
/app/Contents/Frameworks/libmystery.dylib:
Load command 0
      cmd LC_SEGMENT_64
  cmdsize 72
"""


def thin(cputype: int) -> bytes:
    return b"\xcf\xfa\xed\xfe" + struct.pack("<I", cputype) + bytes(56)


def fat(slices: int = 2) -> bytes:
    return b"\xca\xfe\xba\xbe" + struct.pack(">I", slices) + bytes(56)


def make_bundle(tmp_path: Path, files: dict[str, bytes]) -> Path:
    app = tmp_path / "StemForge.app"
    for relative, content in files.items():
        target = app / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return app


def fake_otool(outputs: dict[str, str], calls: list[str] | None = None):
    def run(path: Path) -> str:
        if calls is not None:
            calls.append(path.name)
        result = outputs[path.name]
        if isinstance(result, Exception):
            raise result
        return result
    return run


# ------------------------------------------------------------------ parsing

def test_versions_ignore_trailing_zeros():
    assert check.parse_version("10.15.0") == check.parse_version("10.15")
    assert check.parse_version("11.0") == (11,)
    assert check.parse_version("10.15.4") > check.parse_version("10.15")
    assert check.pretty((11,)) == "11.0" and check.pretty((10, 15, 4)) == "10.15.4"


def test_thin_binary_uses_version_min_and_ignores_other_versions():
    # "version" compare anche in LC_SOURCE_VERSION e nei tool: non è il minimo
    assert check.parse_otool(THIN_OLD_STYLE, "x86_64") == {"x86_64": (10, 9)}


def test_fat_binary_has_one_minimum_per_slice():
    assert check.parse_otool(FAT_UNIVERSAL2) == {"x86_64": (10, 14), "arm64": (11,)}


def test_cctools_platform_name_and_patch_level():
    assert check.parse_otool(THIN_CCTOOLS_TOO_NEW, "x86_64") == {"x86_64": (10, 15, 4)}


def test_mac_catalyst_build_version_is_not_the_macos_minimum():
    assert check.parse_otool(ZIPPERED, "x86_64") == {"x86_64": (10, 15)}


def test_binary_without_minimum_gives_nothing():
    assert check.parse_otool(NO_VERSION, "x86_64") == {}


def test_macho_header_detection():
    assert check.macho_arch(thin(X86_64)) == "x86_64"
    assert check.macho_arch(thin(ARM64)) == "arm64"
    assert check.macho_arch(fat()) == "fat"
    # CAFEBABE è anche una classe Java: al posto delle fette c'è la versione 52
    assert check.macho_arch(b"\xca\xfe\xba\xbe" + struct.pack(">I", 52)) is None
    assert check.macho_arch(b"#!/bin/sh\n") is None
    assert check.macho_arch(b"") is None


# ------------------------------------------------------------ bundle intero

def test_bundle_within_promise_passes(tmp_path):
    app = make_bundle(tmp_path, {
        "Contents/Frameworks/libsndfile.dylib": thin(X86_64),
        "Contents/Frameworks/QtCore": fat(),
        "Contents/Resources/base_library.zip": b"PK\x03\x04",
        "Contents/Info.plist": b"<?xml version='1.0'?>",
    })
    calls: list[str] = []
    otool = fake_otool({"libsndfile.dylib": THIN_OLD_STYLE, "QtCore": FAT_UNIVERSAL2}, calls)
    checked, problems = check.check_bundle(app, (10, 15), "x86_64", otool)
    assert (checked, problems) == (2, [])
    assert sorted(calls) == ["QtCore", "libsndfile.dylib"]  # i non Mach-O non vanno a otool


def test_minimum_above_promise_is_reported_with_file_and_version(tmp_path):
    app = make_bundle(tmp_path, {"Contents/Frameworks/torch/lib/libtorch_cpu.dylib": thin(X86_64)})
    otool = fake_otool({"libtorch_cpu.dylib": THIN_CCTOOLS_TOO_NEW})
    checked, problems = check.check_bundle(app, (10, 15), "x86_64", otool)
    assert checked == 1
    assert problems == ["Contents/Frameworks/torch/lib/libtorch_cpu.dylib [x86_64] richiede macOS 10.15.4"]


def test_arm64_slice_of_universal2_counts_only_without_arch_filter(tmp_path):
    app = make_bundle(tmp_path, {"Contents/Frameworks/QtCore": fat()})
    otool = fake_otool({"QtCore": FAT_UNIVERSAL2})
    assert check.check_bundle(app, (10, 15), "x86_64", otool)[1] == []
    _, problems = check.check_bundle(app, (10, 15), None, otool)
    assert problems == ["Contents/Frameworks/QtCore [arm64] richiede macOS 11.0"]
    assert check.check_bundle(app, (11,), "arm64", otool)[1] == []


def test_thin_binary_of_the_wrong_architecture_is_reported(tmp_path):
    arm_output = THIN_CCTOOLS_TOO_NEW.replace("10.15.4", "11.0")
    app = make_bundle(tmp_path, {"Contents/MacOS/ffmpeg/ffmpeg": thin(ARM64)})
    _, problems = check.check_bundle(app, (10, 15), "x86_64", fake_otool({"ffmpeg": arm_output}))
    assert problems == ["Contents/MacOS/ffmpeg/ffmpeg non contiene la fetta x86_64: su quel Mac non si carica"]


def test_unmeasurable_binaries_are_errors_not_passes(tmp_path):
    app = make_bundle(tmp_path, {
        "Contents/Frameworks/libmystery.dylib": thin(X86_64),
        "Contents/Frameworks/libbroken.dylib": thin(X86_64),
    })
    otool = fake_otool({"libmystery.dylib": NO_VERSION,
                        "libbroken.dylib": check.OtoolError("truncated or malformed object")})
    _, problems = check.check_bundle(app, (10, 15), "x86_64", otool)
    assert problems == [
        "Contents/Frameworks/libbroken.dylib: otool non riesce a leggerlo (truncated or malformed object)",
        "Contents/Frameworks/libmystery.dylib non dichiara il macOS minimo",
    ]


def test_symlinked_duplicates_are_checked_once(tmp_path):
    app = make_bundle(tmp_path, {"Contents/Frameworks/libsndfile.dylib": thin(X86_64)})
    link = app / "Contents" / "Resources" / "libsndfile.dylib"
    link.parent.mkdir(parents=True)
    try:
        link.symlink_to(app / "Contents" / "Frameworks" / "libsndfile.dylib")
    except OSError:
        pytest.skip("questo Windows non permette link simbolici senza privilegi")
    checked, _ = check.check_bundle(app, (10, 15), "x86_64", fake_otool({"libsndfile.dylib": THIN_OLD_STYLE}))
    assert checked == 1


# --------------------------------------------------------------------- main

def test_main_exit_codes(tmp_path, capsys):
    app = make_bundle(tmp_path, {"Contents/Frameworks/torch/lib/libtorch_cpu.dylib": thin(X86_64)})
    otool = fake_otool({"libtorch_cpu.dylib": THIN_CCTOOLS_TOO_NEW})
    assert check.main([str(app), "10.15", "--arch", "x86_64"], otool) == 1
    assert "richiede macOS 10.15.4" in capsys.readouterr().err
    assert check.main([str(app), "11.0", "--arch", "x86_64"], otool) == 0
    assert "ok: 1 binari Mach-O, fetta x86_64" in capsys.readouterr().out


def test_main_refuses_empty_or_missing_bundle(tmp_path, capsys):
    empty = make_bundle(tmp_path, {"Contents/Info.plist": b"<plist/>"})
    assert check.main([str(empty), "10.15"], fake_otool({})) == 1
    assert "nessun binario Mach-O" in capsys.readouterr().err
    assert check.main([str(tmp_path / "manca.app"), "10.15"], fake_otool({})) == 2


def test_main_without_otool_explains_what_to_install(tmp_path, capsys):
    app = make_bundle(tmp_path, {"Contents/MacOS/StemForge": thin(X86_64)})

    def missing(path: Path) -> str:
        raise FileNotFoundError("otool")

    assert check.main([str(app), "10.15"], missing) == 2
    assert "xcode-select --install" in capsys.readouterr().err
