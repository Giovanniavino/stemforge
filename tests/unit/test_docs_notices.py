"""THIRD_PARTY_NOTICES copre ogni dipendenza distribuita (BUILD_SPEC §11 regola 11).

Ogni pin di ogni lock distribuito deve comparire nel file, con la sua
versione attribuita al profilo giusto; ogni voce del file deve
corrispondere a qualcosa che i lock distribuiscono davvero. Il lock di
sviluppo Windows non è distribuito e non conta.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NOTICES = ROOT / "THIRD_PARTY_NOTICES"

# lock distribuito -> profilo (BUILD_SPEC §2.2). Un lock assente si salta:
# requirements-linux-x64.lock arriva da un'altra area di lavoro.
DISTRIBUTED_LOCKS = {
    "requirements-macos-x86_64.lock": "legacy-intel",
    "requirements-macos-arm64.lock": "mac-arm64",
    "requirements-windows-x64.lock": "win-x64",
    "requirements-linux-x64.lock": "linux-x64",
}

PIN_LINE = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s;\\]+)")
SECTION_HEADER = re.compile(r"^\[([a-z0-9][a-z0-9._-]*)\]\s*$")
FIELD_LINE = re.compile(r"^  ([a-z]+)\s*:\s*(.*)$")
VERSION_GROUP = re.compile(r"([^\s|(]+)\s*\(([^)]*)\)")

# Componenti che non stanno in nessun lock ma che il pacchetto contiene o
# scarica (BUILD_SPEC §9, D9, §5.8): ognuno deve avere la sua voce.
REQUIRED_NON_PIP_SECTIONS = (
    "Qt",
    "FFmpeg — StemForge's minimal audio decoder",
    "libsndfile",
    "Demucs pretrained weights — downloaded on first launch, not inside the package",
    "Python",
    "PyInstaller bootloader and run-time hooks",
)


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _lock_pins() -> dict[tuple[str, str], set[str]]:
    """(nome, versione) -> profili che la distribuiscono."""
    pins: dict[tuple[str, str], set[str]] = {}
    for lock_name, profile in DISTRIBUTED_LOCKS.items():
        lock = ROOT / lock_name
        if not lock.exists():
            continue
        for line in lock.read_text(encoding="utf-8").splitlines():
            match = PIN_LINE.match(line)
            if match:
                key = (_normalize(match.group(1)), match.group(2))
                pins.setdefault(key, set()).add(profile)
    return pins


def _python_package_sections(text: str) -> dict[str, dict[str, str]]:
    """Le voci `[nome]` della parte 2, con i loro campi."""
    sections: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    for line in text.splitlines():
        header = SECTION_HEADER.match(line)
        if header:
            current = sections.setdefault(_normalize(header.group(1)), {})
            continue
        field = FIELD_LINE.match(line) if current is not None else None
        if field and current is not None:
            current.setdefault(field.group(1), field.group(2).strip())
        elif not line.strip():
            current = None
    return sections


def _versions_by_profile(versions_field: str) -> dict[str, set[str]]:
    """'1.0 (a, b) | 2.0 (c)' -> {'1.0': {'a', 'b'}, '2.0': {'c'}}."""
    result: dict[str, set[str]] = {}
    for group in versions_field.split("|"):
        match = VERSION_GROUP.search(group)
        if match:
            profiles = {p.strip() for p in match.group(2).split(",") if p.strip()}
            result.setdefault(match.group(1), set()).update(profiles)
    return result


def _part_two(text: str) -> str:
    """Solo la parte dei pacchetti Python: le librerie native hanno voci libere."""
    start = text.index("PART 2 — PYTHON PACKAGES")
    end = text.index("PART 3 — NATIVE LIBRARIES")
    return text[start:end]


def _sections() -> dict[str, dict[str, str]]:
    return _python_package_sections(_part_two(NOTICES.read_text(encoding="utf-8")))


def test_every_distributed_pin_is_listed_with_its_profile():
    sections = _sections()
    missing: list[str] = []
    for (name, version), profiles in sorted(_lock_pins().items()):
        entry = sections.get(name)
        if entry is None:
            missing.append(f"{name}: nessuna voce [{name}]")
            continue
        listed = _versions_by_profile(entry.get("versions", ""))
        for profile in sorted(profiles):
            if profile not in listed.get(version, set()):
                missing.append(f"{name}=={version}: manca '({profile})' nella riga versions")
    assert not missing, (
        "THIRD_PARTY_NOTICES non copre i lock distribuiti:\n  " + "\n  ".join(missing)
    )


def _present_profiles() -> set[str]:
    return {profile for lock, profile in DISTRIBUTED_LOCKS.items() if (ROOT / lock).exists()}


def _stale_entries(
    sections: dict[str, dict[str, str]],
    pins: dict[tuple[str, str], set[str]],
    present: set[str],
) -> list[str]:
    """Le voci che descrivono ciò che i lock presenti non distribuiscono.

    Un profilo il cui lock non è in questo checkout non si può smentire:
    le sue versioni si controllano quando il lock arriva (e allora le
    controlla anche test_every_distributed_pin_is_listed_with_its_profile).
    """
    distributed = {name for name, _ in pins}
    stale: list[str] = []
    for name, entry in sorted(sections.items()):
        listed = _versions_by_profile(entry.get("versions", ""))
        if name not in distributed and any(profiles & present for profiles in listed.values()):
            stale.append(f"[{name}]: in nessun lock distribuito, togliere la voce")
            continue
        for version, profiles in listed.items():
            for profile in sorted((profiles & present) - pins.get((name, version), set())):
                stale.append(f"[{name}] {version} ({profile}): il lock di quel profilo non la contiene")
    return stale


def test_no_stale_python_package_entries():
    stale = _stale_entries(_sections(), _lock_pins(), _present_profiles())
    assert not stale, "voci non più vere in THIRD_PARTY_NOTICES:\n  " + "\n  ".join(stale)


def test_stale_check_fails_on_present_profiles_only():
    sections = {
        "pkg": {"versions": "1.0 (win-x64) | 1.1 (linux-x64)"},
        "gone": {"versions": "2.0 (win-x64)"},
    }
    pins = {("pkg", "1.0"): {"win-x64"}}
    # lock linux assente: la sua versione non si può smentire, la voce
    # sparita dal lock Windows sì
    assert _stale_entries(sections, pins, {"win-x64"}) == [
        "[gone]: in nessun lock distribuito, togliere la voce"
    ]
    # lock linux presente ma senza quella versione: segnalata
    assert "[pkg] 1.1 (linux-x64): il lock di quel profilo non la contiene" in _stale_entries(
        sections, pins, {"win-x64", "linux-x64"}
    )


def test_every_entry_declares_license_and_source():
    incomplete = [
        name
        for name, entry in _sections().items()
        if not entry.get("license") or not entry.get("source")
    ]
    assert not incomplete, f"voci senza 'license' o 'source': {incomplete}"


def test_lgpl_entries_link_their_source():
    # §11 regola 11: per le LGPL, il link al sorgente
    without_link = [
        name
        for name, entry in _sections().items()
        if "LGPL" in entry.get("license", "") and "://" not in entry.get("source", "")
    ]
    assert not without_link, f"voci LGPL senza link al sorgente: {without_link}"


def test_non_pip_components_have_an_entry():
    headers = {
        line.strip()[1:-1]
        for line in NOTICES.read_text(encoding="utf-8").splitlines()
        if line.startswith("[") and line.strip().endswith("]")
    }
    missing = [name for name in REQUIRED_NON_PIP_SECTIONS if name not in headers]
    assert not missing, f"componenti del pacchetto senza voce: {missing}"


def test_parsers_detect_a_missing_profile():
    # il controllo deve poter fallire: una versione attribuita al profilo
    # sbagliato non deve passare per buona
    parsed = _versions_by_profile("1.0 (legacy-intel) | 2.0 (mac-arm64, win-x64)")
    assert parsed == {"1.0": {"legacy-intel"}, "2.0": {"mac-arm64", "win-x64"}}
    assert "linux-x64" not in parsed["2.0"]
