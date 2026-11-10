"""packaging/stemforge.spec per i quattro profili, senza PyInstaller (§9.1).

Lo spec è codice Python che PyInstaller esegue con Analysis/EXE/COLLECT/
BUNDLE già definiti. Qui li sostituiamo con registratori e simuliamo
sistema e architettura: così da Windows si controlla che cosa lo spec
chiederebbe a PyInstaller su un Mac Intel, un Mac arm64 e Linux. Non
prova che PyInstaller accetti quei parametri (lo prova l'analisi vera)
né che l'app parta (serve il Mac).
"""

from __future__ import annotations

import platform
import shutil
import sys
import types
from pathlib import Path

import pytest

PACKAGING = Path(__file__).resolve().parents[2] / "packaging"
FFMPEG_NAMES = {"win-x64": "ffmpeg.exe"}


class _Recorder:
    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs
        self.binaries = kwargs.get("binaries", [])
        self.datas = kwargs.get("datas", [])
        self.pure = []
        self.scripts = []


def _fake_pyinstaller(monkeypatch: pytest.MonkeyPatch) -> None:
    hooks = types.ModuleType("PyInstaller.utils.hooks")
    hooks.collect_data_files = lambda package: [(f"{package}/remote/files.txt", f"{package}/remote")]
    hooks.collect_submodules = lambda package: [f"{package}.fake"]
    versioninfo = types.ModuleType("PyInstaller.utils.win32.versioninfo")
    for name in ("FixedFileInfo", "StringFileInfo", "StringStruct", "StringTable",
                 "VarFileInfo", "VarStruct", "VSVersionInfo"):
        setattr(versioninfo, name, _Recorder)
    modules = {
        "PyInstaller": types.ModuleType("PyInstaller"),
        "PyInstaller.utils": types.ModuleType("PyInstaller.utils"),
        "PyInstaller.utils.hooks": hooks,
        "PyInstaller.utils.win32": types.ModuleType("PyInstaller.utils.win32"),
        "PyInstaller.utils.win32.versioninfo": versioninfo,
        "PIL": types.ModuleType("PIL"),
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)


def _layout(root: Path, profile: str | None, with_qm: bool) -> Path:
    spec_dir = root / "packaging"
    spec_dir.mkdir(parents=True)
    for name in ("stemforge.spec", "icon.png", "entitlements.plist"):
        shutil.copy2(PACKAGING / name, spec_dir / name)
    (root / "src").mkdir()
    if profile:
        ffmpeg = spec_dir / "ffmpeg" / "out" / profile / FFMPEG_NAMES.get(profile, "ffmpeg")
        ffmpeg.parent.mkdir(parents=True)
        ffmpeg.write_bytes(b"segnaposto")
    if with_qm:
        i18n = root / "resources" / "i18n"
        i18n.mkdir(parents=True)
        (i18n / "stemforge_it.qm").write_bytes(b"qm")
    return spec_dir


def run_spec(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, system: str, machine: str,
             env: dict[str, str] | None = None, ffmpeg_for: str | None = None,
             with_qm: bool = True) -> dict[str, _Recorder]:
    for name in ("STEMFORGE_PROFILE", "STEMFORGE_TARGET_ARCH", "STEMFORGE_MACOS_MIN",
                 "STEMFORGE_CODESIGN_IDENTITY", "STEMFORGE_REQUIRE_FFMPEG"):
        monkeypatch.delenv(name, raising=False)
    for name, value in (env or {}).items():
        monkeypatch.setenv(name, value)
    _fake_pyinstaller(monkeypatch)
    spec_dir = _layout(tmp_path / "repo", ffmpeg_for, with_qm)
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setattr(sys, "platform", system)
    monkeypatch.setattr(platform, "machine", lambda: machine)
    made: dict[str, _Recorder] = {}

    def factory(kind: str):
        def build(*args, **kwargs):
            made[kind] = _Recorder(*args, **kwargs)
            return made[kind]
        return build

    namespace = {"SPECPATH": str(spec_dir), "workpath": str(tmp_path / "build"),
                 **{kind: factory(kind) for kind in ("Analysis", "PYZ", "EXE", "COLLECT", "BUNDLE")}}
    source = (spec_dir / "stemforge.spec").read_text(encoding="utf-8")
    exec(compile(source, str(spec_dir / "stemforge.spec"), "exec"), namespace)
    return made


def _dest(entries: list[tuple[str, str]], folder: str) -> list[str]:
    return [Path(source).name for source, dest in entries if dest == folder]


def test_legacy_intel_is_x86_64_for_catalina(tmp_path, monkeypatch):
    made = run_spec(tmp_path, monkeypatch, "darwin", "x86_64", ffmpeg_for="legacy-intel")
    exe = made["EXE"].kwargs
    assert exe["target_arch"] == "x86_64"
    assert exe["codesign_identity"] == "-"
    assert exe["entitlements_file"].endswith("entitlements.plist")
    assert exe["version"] is None
    assert exe["icon"].endswith("icon.png")
    plist = made["BUNDLE"].kwargs["info_plist"]
    assert plist["LSMinimumSystemVersion"] == "10.15"
    assert {"m4a", "aac"} <= set(plist["CFBundleDocumentTypes"][0]["CFBundleTypeExtensions"])
    analysis = made["Analysis"].kwargs
    assert _dest(analysis["binaries"], "ffmpeg") == ["ffmpeg"]
    assert _dest(analysis["datas"], "i18n") == ["stemforge_it.qm"]
    assert "av" in analysis["excludes"]


def test_mac_arm64_is_arm64_for_big_sur(tmp_path, monkeypatch):
    made = run_spec(tmp_path, monkeypatch, "darwin", "arm64", ffmpeg_for="mac-arm64")
    assert made["EXE"].kwargs["target_arch"] == "arm64"
    assert made["BUNDLE"].kwargs["info_plist"]["LSMinimumSystemVersion"] == "11.0"
    assert _dest(made["Analysis"].kwargs["binaries"], "ffmpeg") == ["ffmpeg"]


def test_windows_gets_exe_version_and_no_mac_options(tmp_path, monkeypatch):
    made = run_spec(tmp_path, monkeypatch, "win32", "AMD64", ffmpeg_for="win-x64")
    exe = made["EXE"].kwargs
    assert exe["target_arch"] is None and exe["codesign_identity"] is None
    assert exe["entitlements_file"] is None
    assert Path(exe["version"]).is_file()
    assert "BUNDLE" not in made
    assert _dest(made["Analysis"].kwargs["binaries"], "ffmpeg") == ["ffmpeg.exe"]


def test_linux_has_no_icon_and_no_bundle(tmp_path, monkeypatch):
    made = run_spec(tmp_path, monkeypatch, "linux", "x86_64", ffmpeg_for="linux-x64")
    exe = made["EXE"].kwargs
    assert exe["icon"] is None and exe["version"] is None and exe["target_arch"] is None
    assert "BUNDLE" not in made
    assert _dest(made["Analysis"].kwargs["binaries"], "ffmpeg") == ["ffmpeg"]
    assert made["COLLECT"].kwargs["name"] == "StemForge"


def test_missing_ffmpeg_warns_and_goes_on(tmp_path, monkeypatch, capsys):
    made = run_spec(tmp_path, monkeypatch, "darwin", "x86_64", with_qm=False)
    assert made["Analysis"].kwargs["binaries"] == []
    assert _dest(made["Analysis"].kwargs["datas"], "i18n") == []
    warnings = capsys.readouterr().err
    assert "m4a" in warnings and "legacy-intel" in warnings
    assert ".qm" in warnings


def test_ffmpeg_of_another_profile_does_not_count(tmp_path, monkeypatch):
    made = run_spec(tmp_path, monkeypatch, "darwin", "x86_64", ffmpeg_for="mac-arm64")
    assert made["Analysis"].kwargs["binaries"] == []


def test_required_ffmpeg_missing_fails_clearly(tmp_path, monkeypatch):
    with pytest.raises(SystemExit) as failure:
        run_spec(tmp_path, monkeypatch, "linux", "x86_64", env={"STEMFORGE_REQUIRE_FFMPEG": "1"})
    message = str(failure.value)
    assert "ffmpeg" in message and "linux-x64" in message
    assert "STEMFORGE_REQUIRE_FFMPEG" in message


def test_required_ffmpeg_present_is_fine(tmp_path, monkeypatch):
    made = run_spec(tmp_path, monkeypatch, "win32", "AMD64", ffmpeg_for="win-x64",
                    env={"STEMFORGE_REQUIRE_FFMPEG": "1"})
    assert _dest(made["Analysis"].kwargs["binaries"], "ffmpeg") == ["ffmpeg.exe"]


@pytest.mark.parametrize(
    ("system", "machine", "env", "expected"),
    [
        ("darwin", "x86_64", {"STEMFORGE_PROFILE": "mac-arm64"}, "arm64"),
        ("win32", "AMD64", {"STEMFORGE_PROFILE": "legacy-intel"}, "darwin"),
        ("darwin", "x86_64", {"STEMFORGE_PROFILE": "legacy-intel", "STEMFORGE_TARGET_ARCH": "arm64"},
         "contraddice"),
        ("linux", "x86_64", {"STEMFORGE_PROFILE": "linux-arm64"}, "non valido"),
        ("linux", "aarch64", {}, "x64"),
    ],
)
def test_impossible_profiles_are_refused(tmp_path, monkeypatch, system, machine, env, expected):
    with pytest.raises(SystemExit) as failure:
        run_spec(tmp_path, monkeypatch, system, machine, env=env)
    assert expected in str(failure.value)


def test_default_profile_follows_the_mac(tmp_path, monkeypatch, capsys):
    run_spec(tmp_path, monkeypatch, "darwin", "arm64")
    assert "profilo mac-arm64" in capsys.readouterr().out


def test_macos_min_can_be_overridden(tmp_path, monkeypatch):
    made = run_spec(tmp_path, monkeypatch, "darwin", "x86_64", env={"STEMFORGE_MACOS_MIN": "10.15.7"})
    assert made["BUNDLE"].kwargs["info_plist"]["LSMinimumSystemVersion"] == "10.15.7"
