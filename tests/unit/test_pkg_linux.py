"""Packaging Linux (BUILD_SPEC §9.8): cio' che si puo' provare da ogni sistema.

La build vera gira in manylinux_2_28 (CI o rootless_container.py su WSL):
qui si provano le parti che decidono COSA entra nell'AppImage, con output
di readelf/ldd registrati da file reali, e i contratti fra i file di
packaging/linux/ e il resto del repository.
"""

from __future__ import annotations

import configparser
import importlib.util
import io
import re
import subprocess
import sys
import tarfile
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
LINUX = ROOT / "packaging" / "linux"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"pkg_linux_{name}", LINUX / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # le dataclass cercano il loro modulo qui
    spec.loader.exec_module(module)
    return module


bundle_libs = _load("bundle_libs")
rootless = _load("rootless_container")

# `readelf -d -V -W libqxcb.so` di PySide6 6.7.3, accorciato: sezione
# dinamica, versioni definite (d) e chieste (r).
READELF_QXCB = """
Dynamic section at offset 0x1fd40 contains 34 entries:
  Tag        Type                         Name/Value
 0x0000000000000001 (NEEDED)             Shared library: [libQt6XcbQpa.so.6]
 0x0000000000000001 (NEEDED)             Shared library: [libxcb-cursor.so.0]
 0x0000000000000001 (NEEDED)             Shared library: [libstdc++.so.6]
 0x0000000000000001 (NEEDED)             Shared library: [libc.so.6]
 0x000000000000000e (SONAME)             Library soname: [libqxcb.so]

Version definition section '.gnu.version_d' contains 2 entries:
  000000: Rev: 1  Flags: BASE  Index: 1  Cnt: 1  Name: libqxcb.so
  0x001c: Rev: 1  Flags: none  Index: 2  Cnt: 1  Name: GLIBC_2.99

Version needs section '.gnu.version_r' contains 2 entries:
 Addr: 0x0000000000003a48  Offset: 0x003a48  Link: 4 (.dynstr)
  000000: Version: 1  File: libstdc++.so.6  Cnt: 2
  0x0010:   Name: CXXABI_1.3.9  Flags: none  Version: 5
  0x0020:   Name: GLIBCXX_3.4.21  Flags: none  Version: 4
  0x0030: Version: 1  File: libc.so.6  Cnt: 2
  0x0040:   Name: GLIBC_2.14  Flags: none  Version: 3
  0x0050:   Name: GLIBC_2.2.5  Flags: none  Version: 2
"""

LDD_QXCB = """\
\tlinux-vdso.so.1 (0x00007ffd1a5e2000)
\tlibQt6XcbQpa.so.6 => /b/_internal/PySide6/Qt/lib/libQt6XcbQpa.so.6 (0x00007f3c)
\tlibxcb-cursor.so.0 => not found
\tlibstdc++.so.6 => /lib64/libstdc++.so.6 (0x00007f3b)
\tlibc.so.6 => /lib64/libc.so.6 (0x00007f3a)
\t/lib64/ld-linux-x86-64.so.2 (0x00007f3d)
"""


def test_readelf_gives_direct_deps_and_only_required_versions() -> None:
    info = bundle_libs.parse_readelf(READELF_QXCB)
    assert info.needed == ["libQt6XcbQpa.so.6", "libxcb-cursor.so.0", "libstdc++.so.6", "libc.so.6"]
    # GLIBC_2.99 e' DEFINITA dal file (version_d), non chiesta: non conta
    assert info.versions == {"GLIBC": (2, 14), "GLIBCXX": (3, 4, 21), "CXXABI": (1, 3, 9)}
    assert bundle_libs.too_new(info) == []


def test_symbols_newer_than_the_promised_minimum_are_reported() -> None:
    newer = READELF_QXCB.replace("GLIBC_2.14", "GLIBC_2.34").replace("GLIBCXX_3.4.21", "GLIBCXX_3.4.29")
    problems = bundle_libs.too_new(bundle_libs.parse_readelf(newer))
    assert problems == ["GLIBC_2.34 > 2.28", "GLIBCXX_3.4.29 > 3.4.25"]


def test_ldd_resolution_and_missing_libraries() -> None:
    deps = bundle_libs.parse_ldd(LDD_QXCB)
    assert deps["libxcb-cursor.so.0"] is None
    assert deps["libstdc++.so.6"] == "/lib64/libstdc++.so.6"
    assert "linux-vdso.so.1" not in deps  # niente '=>': ne' copiabile ne' mancante


@pytest.fixture(scope="module")
def host_patterns() -> list[re.Pattern[str]]:
    return bundle_libs.load_host_patterns(LINUX / "host_libs.txt")


@pytest.mark.parametrize("soname", [
    "libc.so.6", "libm.so.6", "ld-linux-x86-64.so.2", "libstdc++.so.6", "libgcc_s.so.1",
    "libGL.so.1", "libEGL.so.1", "libX11.so.6", "libxcb.so.1", "libfontconfig.so.1",
    "libwayland-client.so.0", "libdbus-1.so.3", "libglib-2.0.so.0", "libpulse.so.0",
])
def test_libraries_bound_to_the_host_stay_out(host_patterns: list[re.Pattern[str]], soname: str) -> None:
    assert bundle_libs.is_host(soname, host_patterns)


@pytest.mark.parametrize("soname", [
    # senza libxcb-cursor Qt >= 6.5 non apre finestre su X11: va nel pacchetto
    "libxcb-cursor.so.0", "libxcb-icccm.so.4", "libxcb-image.so.0", "libxcb-keysyms.so.1",
    "libxcb-render-util.so.0", "libxkbcommon-x11.so.0", "libxkbcommon.so.0",
    "libsndfile.so.1", "libQt6Core.so.6", "libcrypt.so.2",
])
def test_libraries_not_guaranteed_by_a_desktop_are_bundled(
    host_patterns: list[re.Pattern[str]], soname: str
) -> None:
    assert not bundle_libs.is_host(soname, host_patterns)


def _layer(tmp_path: Path, name: str, files: dict[str, bytes]) -> Path:
    path = tmp_path / name
    with tarfile.open(path, "w") as archive:
        for member, data in files.items():
            info = tarfile.TarInfo(member)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return path


def test_oci_layers_apply_whiteouts(tmp_path: Path) -> None:
    root = tmp_path / "rootfs"
    root.mkdir()
    rootless._extract_layer(_layer(tmp_path, "l1", {"etc/a": b"1", "etc/b": b"2", "opt/x/y": b"3"}), root)
    rootless._extract_layer(_layer(tmp_path, "l2", {"etc/.wh.a": b"", "opt/x/.wh..wh..opq": b"",
                                                    "opt/x/z": b"4"}), root)
    assert not (root / "etc" / "a").exists()
    assert (root / "etc" / "b").read_bytes() == b"2"
    assert sorted(p.name for p in (root / "opt" / "x").iterdir()) == ["z"]


def test_oci_layer_cannot_escape_the_rootfs(tmp_path: Path) -> None:
    root = tmp_path / "rootfs"
    root.mkdir()
    with pytest.raises(SystemExit, match="esce dalla radice"):
        rootless._extract_layer(_layer(tmp_path, "evil", {"../fuori": b"x"}), root)
    assert not (tmp_path / "fuori").exists()


@pytest.mark.parametrize(("image", "expected"), [
    ("ubuntu:20.04", ("docker.io", "library/ubuntu", "20.04")),
    ("quay.io/pypa/manylinux_2_28_x86_64@sha256:ab", ("quay.io", "pypa/manylinux_2_28_x86_64", "sha256:ab")),
    ("quay.io/pypa/manylinux_2_28_x86_64", ("quay.io", "pypa/manylinux_2_28_x86_64", "latest")),
])
def test_image_references(image: str, expected: tuple[str, str, str]) -> None:
    assert rootless._split_image(image) == expected


def _shell_value(script: str, name: str) -> str:
    match = re.search(rf'^{name}="([^"]*)"$', script, re.MULTILINE)
    assert match, f"{name} non trovata"
    return match.group(1)


def test_build_tools_are_pinned_with_sha256() -> None:
    script = (LINUX / "build_appimage.sh").read_text(encoding="utf-8")
    for tool in ("APPIMAGETOOL", "RUNTIME"):
        assert re.fullmatch(r"[0-9a-f]{64}", _shell_value(script, f"{tool}_SHA256"))
        version = _shell_value(script, f"{tool}_VERSION")
        assert version and version != "continuous", "una versione mobile non e' riproducibile"
        assert f"/download/${tool}_VERSION/" in _shell_value(script, f"{tool}_URL")


def test_source_only_packages_match_the_lock_generator() -> None:
    script = (LINUX / "build_appimage.sh").read_text(encoding="utf-8")
    allow = re.search(r"SDIST_ALLOWLIST\s*=\s*(?:frozenset\()?\{([^}]*)\}",
                      (ROOT / "packaging" / "gen_locks.py").read_text(encoding="utf-8"))
    assert allow
    expected = sorted(re.findall(r'"([^"]+)"', allow.group(1)))
    assert sorted(_shell_value(script, "SDIST_ONLY").split(",")) == expected


def test_desktop_entry_is_valid_and_opens_audio() -> None:
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    parser.optionxform = str  # le chiavi .desktop distinguono maiuscole
    parser.read(LINUX / "stemforge.desktop", encoding="utf-8")
    entry = parser["Desktop Entry"]
    assert entry["Type"] == "Application" and entry["Icon"] == "stemforge"
    assert entry["Exec"].split()[-1] == "%F", "deve accettare piu' file da 'Apri con'"
    mime = {m for m in entry["MimeType"].split(";") if m}
    assert {"audio/wav", "audio/flac", "audio/mpeg", "audio/ogg", "audio/mp4", "audio/aiff"} <= mime
    assert all(m.startswith("audio/") for m in mime)


def _git_index() -> dict[str, tuple[str, str]]:
    proc = subprocess.run(["git", "ls-files", "-s", "--eol", "packaging/linux"],
                          cwd=ROOT, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        pytest.skip("non e' un checkout git")
    index: dict[str, tuple[str, str]] = {}
    for line in proc.stdout.splitlines():
        # "<mode> <sha> <stage>\t<i/eol> <w/eol> <attr>\t<path>"
        stage_info, eol_info, path = line.split("\t")
        index[Path(path).name] = (stage_info.split()[0], eol_info.split()[0])
    return index


@pytest.mark.parametrize("name", ["build_appimage.sh", "test_appimage.sh", "AppRun"])
def test_scripts_run_on_linux_as_committed(name: str) -> None:
    mode, eol = _git_index()[name]
    assert mode == "100755", f"{name} senza bit di esecuzione nel repository"
    assert eol == "i/lf", f"{name} con CRLF: bash si fermerebbe a 'set -e\\r'"
