"""La documentazione per l'utente dice ciò che dice BUILD_SPEC v3.0.

I minimi di sistema si leggono dalla matrice di §2.1 della spec, non si
ricopiano qui: se la spec cambia un minimo, i documenti che non lo
seguono fanno fallire il test. In più: nessun numero di prestazioni
misurato su CUDA nei documenti per l'utente (D6), le istruzioni per
superare Gatekeeper e SmartScreen ci sono (§9.3), il template delle issue
chiede la diagnostica (§9.9) e FUNDING.yml non contiene link inventati.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "BUILD_SPEC.md"

# i documenti che l'utente legge per scegliere e installare il pacchetto
INSTALL_DOCS = ("README.md", "docs/it/installazione.md", "packaging/release-notes.md")
USER_DOCS = INSTALL_DOCS + (
    "PRIVACY.md",
    "docs/it/README.md",
    "docs/it/uso.md",
    "docs/it/problemi.md",
)
PROFILES = ("legacy-intel", "mac-arm64", "win-x64", "linux-x64")
# nomi dei pacchetti: make_dmg.sh, stemforge.iss, build_appimage.sh
PACKAGE_SUFFIXES = (
    "-macos-x86_64.dmg",
    "-macos-arm64.dmg",
    "-windows-x64-setup.exe",
    "-linux-x86_64.AppImage",
)
GPU_WORDS = re.compile(r"\b(cuda|nvidia|geforce|rtx)\b", re.IGNORECASE)
# un tempo o un fattore di velocità: "12 min", "30 s", "10x", "3 volte"...
SPEED_NUMBER = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:[x×]\b|×|times\b|volte\b|min\b|minut\w*|s\b|sec\w*|second\w*|h\b|or[ae]\b|hours?\b)",
    re.IGNORECASE,
)


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def spec_minimum_systems(spec_text: str) -> dict[str, str]:
    """Profilo -> cella 'Sistema minimo' della matrice di §2.1."""
    section = spec_text.split("### 2.1 Matrice delle piattaforme", 1)[1].split("###", 1)[0]
    minimums: dict[str, str] = {}
    for line in section.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and cells[0].strip("`") in PROFILES:
            minimums[cells[0].strip("`")] = cells[1]
    return minimums


def version_numbers(cell: str) -> set[str]:
    """I numeri di versione di una cella: '10.15', '1809', '2.28', '20.04'..."""
    return set(re.findall(r"\d+(?:\.\d+)*", cell))


def paragraphs(text: str) -> list[str]:
    return [block for block in re.split(r"\n\s*\n", text) if block.strip()]


def gpu_speed_claims(text: str) -> list[str]:
    """I paragrafi che nominano CUDA/NVIDIA e danno un tempo o un fattore."""
    return [
        " ".join(block.split())[:120]
        for block in paragraphs(text)
        if GPU_WORDS.search(block) and SPEED_NUMBER.search(block)
    ]


def test_spec_matrix_is_parsed():
    minimums = spec_minimum_systems(_read("BUILD_SPEC.md"))
    assert set(minimums) == set(PROFILES)
    assert "10.15" in version_numbers(minimums["legacy-intel"])
    assert "2.28" in version_numbers(minimums["linux-x64"])


def test_install_docs_state_every_minimum_of_the_spec():
    minimums = spec_minimum_systems(_read("BUILD_SPEC.md"))
    missing = [
        f"{doc}: {profile} {number}"
        for doc in INSTALL_DOCS
        for profile, cell in minimums.items()
        for number in sorted(version_numbers(cell))
        if number not in _read(doc)
    ]
    assert not missing, "minimi di sistema di §2.1 assenti:\n  " + "\n  ".join(missing)


def test_install_docs_name_the_four_packages():
    missing = [
        f"{doc}: {suffix}"
        for doc in INSTALL_DOCS
        for suffix in PACKAGE_SUFFIXES
        if suffix not in _read(doc)
    ]
    assert not missing, f"pacchetti non nominati: {missing}"


def test_profiles_are_the_spec_ones():
    for doc in ("README.md", "docs/it/installazione.md", "CONTRIBUTING.md"):
        text = _read(doc)
        assert all(f"`{profile}`" in text for profile in PROFILES), doc


def test_no_cuda_speed_numbers_in_user_docs():
    claims = {doc: found for doc in USER_DOCS if (found := gpu_speed_claims(_read(doc)))}
    assert not claims, f"numeri di prestazioni CUDA nei documenti per l'utente (D6): {claims}"


def test_gpu_claim_detector_can_fail():
    assert gpu_speed_claims("On an NVIDIA GPU a song takes 40 s.\n\nOther.")
    assert gpu_speed_claims("Con CUDA è 10-30 volte più veloce.")
    assert gpu_speed_claims("CUDA: 25x faster")
    # la dimensione di un download non è una prestazione
    assert not gpu_speed_claims("A GPU build of PyTorch weighs about 2.5 GB (NVIDIA).")
    assert not gpu_speed_claims("Vocals alone take 1/4 of the time.\n\nCUDA is not used.")


def test_unsigned_app_instructions_cover_every_system():
    # §9.3: finché non c'è firma, la guida spiega ogni versione di sistema
    english = _read("README.md")
    italian = _read("docs/it/installazione.md")
    for heading in ("macOS 10.15 Catalina to 14 Sonoma", "macOS 15 Sequoia and later",
                    "Windows — SmartScreen", "Check the SHA-256"):
        assert f"### {heading}" in english, heading
    for heading in ("macOS da 10.15 Catalina a 14 Sonoma", "macOS 15 Sequoia e successivi",
                    "Windows — SmartScreen", "Controllare lo SHA-256"):
        assert f"## {heading}" in italian, heading
    for text in (english, italian, _read("packaging/release-notes.md")):
        assert "SHA256SUMS.txt" in text


def test_license_is_mit():
    assert _read("LICENSE").startswith("MIT License")
    # vecchia forma `{ text = "MIT" }` o espressione SPDX di PEP 639
    declared = re.search(
        r'^license\s*=\s*(?:\{\s*text\s*=\s*)?"([^"]+)"', _read("pyproject.toml"), re.MULTILINE
    )
    assert declared is not None and declared.group(1) == "MIT"


def test_bug_template_asks_for_profile_and_diagnostics():
    form = yaml.safe_load(_read(".github/ISSUE_TEMPLATE/bug_report.yml"))
    fields = {item.get("id"): item for item in form["body"] if item.get("id")}
    options = " ".join(fields["profile"]["attributes"]["options"])
    assert all(profile in options for profile in PROFILES)
    assert fields["diagnostics"]["validations"]["required"] is True
    assert fields["system"]["validations"]["required"] is True


def test_feature_template_points_to_the_non_goals():
    text = _read(".github/ISSUE_TEMPLATE/feature_request.yml")
    assert "BUILD_SPEC.md#non-obiettivi" in text
    assert "## 0. Cos'è e cosa non è" in _read("BUILD_SPEC.md")


def placeholder_funding_entries(text: str) -> dict[str, object]:
    """Le voci attive di FUNDING.yml che sono segnaposto o esempi."""
    data = yaml.safe_load(text)
    links = dict(data) if isinstance(data, dict) else {}
    return {key: value for key, value in links.items() if re.search(r"[<>]|example", str(value))}


def test_funding_has_no_placeholder_link():
    # nessun account è stato fornito: le voci restano commentate finché il
    # committente non dà quelli veri
    bad = placeholder_funding_entries(_read(".github/FUNDING.yml"))
    assert not bad, f"FUNDING.yml contiene voci segnaposto attive: {bad}"


def test_funding_check_can_fail():
    assert placeholder_funding_entries("github: <github-sponsors-username>\n")
    assert placeholder_funding_entries('custom: ["https://example.com/donate"]\n')
    assert not placeholder_funding_entries("# github: <github-sponsors-username>\n")
    assert not placeholder_funding_entries("ko_fi: realname\n")
