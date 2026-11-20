"""I workflow della CI rispettano le regole di BUILD_SPEC §9.6 e della Fase 1.

actionlint (job "workflows" di ci.yml) controlla la sintassi; qui si
controlla cio' che actionlint non sa: le decisioni del progetto. Un
runner ritirato, un'action rimasta su Node 20, un permesso di scrittura
di troppo o una release che si pubblica da sola si scoprono al push.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

import stemforge  # noqa: E402
from stemforge.engine import paths  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
GH = ROOT / ".github"
WORKFLOWS = GH / "workflows"
ACTIONS = GH / "actions"

# Ultima versione maggiore di ogni action ufficiale, tutte su Node 24
# (verificato sulle release il 20-11-2026). Alzarle e' una scelta: va
# fatta qui E nei workflow, insieme.
CURRENT_MAJORS = {
    "actions/checkout": "v7",
    "actions/setup-python": "v7",
    "actions/cache": "v6",
    "actions/upload-artifact": "v7",
    "actions/download-artifact": "v8",
}
# Etichette documentate in actions/runner-images. Mai "-latest" (cambia
# sistema da sola: ubuntu-latest passa a 26.04 dal 19-10-2026) e mai
# macos-14 (ritirato: run 42651651029 del 09-11-2026).
RUNNERS = {
    "ubuntu-24.04", "windows-2022", "windows-2025",
    "macos-15", "macos-15-intel", "macos-26", "macos-26-intel",
}
PROFILES = {"legacy-intel", "mac-arm64", "win-x64", "linux-x64"}


def _load(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"{path.name}: non e' un documento YAML"
    return data


def _workflow(name: str) -> dict:
    return _load(WORKFLOWS / name)


def _triggers(workflow: dict) -> dict:
    # PyYAML (YAML 1.1) legge la chiave "on" come il booleano True
    return workflow.get("on", workflow.get(True))


def _all_files() -> list[Path]:
    return sorted([*WORKFLOWS.glob("*.yml"), *ACTIONS.glob("*/action.yml")])


def _steps(path: Path) -> list[dict]:
    data = _load(path)
    if "jobs" in data:
        return [s for job in data["jobs"].values() for s in job.get("steps", [])]
    return data["runs"].get("steps", [])


def test_every_yaml_parses():
    files = _all_files()
    assert {"ci.yml", "release.yml"} <= {p.name for p in files}
    for path in files:
        _load(path)


def test_uses_only_official_actions_at_current_major():
    found: set[str] = set()
    for path in _all_files():
        for step in _steps(path):
            uses = step.get("uses")
            if uses is None:
                continue
            if uses.startswith("./"):
                assert (ROOT / uses / "action.yml").is_file(), f"{path.name}: {uses} non esiste"
                continue
            action, _, ref = uses.partition("@")
            found.add(action)
            assert action in CURRENT_MAJORS, (
                f"{path.name}: {uses}: solo action ufficiali (nessuna terza parte "
                "vede i secrets di firma)"
            )
            assert ref == CURRENT_MAJORS[action], (
                f"{path.name}: {uses}: atteso @{CURRENT_MAJORS[action]}"
            )
    assert found == set(CURRENT_MAJORS), f"action attese ma non usate: {set(CURRENT_MAJORS) - found}"


def _runs_on(job: dict) -> list[str]:
    raw = job["runs-on"]
    if "${{" not in raw:
        return [raw]
    matrix = job["strategy"]["matrix"]
    return [entry["os"] for entry in matrix.get("include", [])] or ["ubuntu-24.04"]


def test_runners_are_explicit_and_supported():
    for name in ("ci.yml", "release.yml"):
        for job_id, job in _workflow(name)["jobs"].items():
            for label in _runs_on(job):
                assert label in RUNNERS, f"{name}:{job_id}: runner {label!r} non ammesso"


def test_every_job_has_a_timeout():
    for name in ("ci.yml", "release.yml"):
        for job_id, job in _workflow(name)["jobs"].items():
            assert job.get("timeout-minutes"), f"{name}:{job_id}: senza timeout-minutes"


def test_ci_covers_all_profiles_and_both_torch_stacks():
    jobs = _workflow("ci.yml")["jobs"]
    profiles = {e["profile"] for e in jobs["test"]["strategy"]["matrix"]["include"]}
    assert profiles == PROFILES
    stacks = {e["stack"] for e in jobs["compat"]["strategy"]["matrix"]["include"]}
    assert stacks == {"legacy", "modern"}
    commands = " ".join(s.get("run", "") for s in jobs["compat"]["steps"])
    assert "-m compat" in commands


def test_release_triggers():
    on = _triggers(_workflow("release.yml"))
    assert on["push"]["tags"] == ["v*"]
    assert "workflow_dispatch" in on
    assert on["schedule"], "manca il giro settimanale (§9.6)"


def test_release_permissions_are_minimal():
    workflow = _workflow("release.yml")
    assert workflow["permissions"] == {}, "nessun permesso di default"
    for job_id, job in workflow["jobs"].items():
        perms = job.get("permissions")
        assert perms is not None, f"{job_id}: permessi non dichiarati"
        expected = {"contents": "write"} if job_id == "publish" else {"contents": "read"}
        assert perms == expected, f"{job_id}: {perms}"


def test_release_is_a_draft_and_only_on_tags():
    publish = _workflow("release.yml")["jobs"]["publish"]
    assert publish["if"] == "github.ref_type == 'tag'"
    script = " ".join(s.get("run", "") for s in publish["steps"])
    assert "--draft" in script and "SHA256SUMS.txt" in script
    assert "packaging/release-notes.md" in script
    assert (ROOT / "packaging" / "release-notes.md").is_file()
    needs = set(publish["needs"])
    assert {"macos", "windows", "linux", "verify-macos", "verify-windows", "verify-linux"} <= needs


def test_release_builds_every_profile_with_lgpl_ffmpeg():
    workflow = _workflow("release.yml")
    assert workflow["env"]["STEMFORGE_REQUIRE_FFMPEG"] == "1"
    jobs = workflow["jobs"]
    built = {e["profile"] for e in jobs["macos"]["strategy"]["matrix"]["include"]}
    built |= {jobs["windows"]["env"]["STEMFORGE_PROFILE"], jobs["linux"]["env"]["STEMFORGE_PROFILE"]}
    assert built == PROFILES
    assert jobs["linux"]["container"]["image"].startswith("quay.io/pypa/manylinux_2_28_x86_64")
    for job_id in ("macos", "windows", "linux"):
        steps = jobs[job_id]["steps"]
        setup = [s for s in steps if s.get("uses") == "./.github/actions/setup-stemforge"]
        assert setup and setup[0]["with"]["forbid-pyav"] == "true", f"{job_id}: PyAV non vietato (D9)"
        script = " ".join(s.get("run", "") for s in steps)
        assert "-m slow" in script, f"{job_id}: senza test lenti (§9.6)"
        assert "-m frozen" in script, f"{job_id}: senza batteria frozen (§10.6)"
        assert "run_selftest.py" in script, f"{job_id}: senza --selftest (§10.5)"


def test_tag_check_reads_the_real_version():
    """Il job "version" estrae __version__ con sed: la riga deve avere
    esattamente la forma che quel sed riconosce."""
    script = _workflow("release.yml")["jobs"]["version"]["steps"][1]["run"]
    assert 'GITHUB_REF_NAME" != "v$version"' in script
    text = (ROOT / "src" / "stemforge" / "__init__.py").read_text(encoding="utf-8")
    found = re.findall(r'^__version__ = "([^"]*)"', text, re.M)
    assert found == [stemforge.__version__]


def _expand(template: str, env: dict[str, str]) -> str:
    """Le tre forme di shell usate da model-cache, nient'altro."""
    template = re.sub(r'\$\(cygpath -u "\$(\w+)"\)', lambda m: env[m.group(1)], template)
    template = re.sub(
        r"\$\{(\w+):-([^}]*)\}",
        lambda m: env.get(m.group(1)) or m.group(2), template,
    )
    return re.sub(r"\$(\w+)", lambda m: env[m.group(1)], template)


def test_model_cache_matches_engine_paths(monkeypatch):
    """La cache dei pesi deve stare dove l'app li cerca: altrimenti ogni
    job riscarica ~1 GB senza che niente fallisca. Si confronta sul
    sistema dove gira il test: la CI lo esegue su tutti e quattro."""
    monkeypatch.delenv("STEMFORGE_MODELS", raising=False)
    text = (ACTIONS / "model-cache" / "action.yml").read_text(encoding="utf-8")
    runner_os = {"darwin": "macOS", "win32": "Windows"}.get(sys.platform, "Linux")
    branch = "*" if runner_os == "Linux" else runner_os
    match = re.search(rf'^\s*{re.escape(branch)}\) dir="(.*)" ;;\s*$', text, re.M)
    assert match, f"model-cache: nessun ramo per {runner_os}"
    env = {**os.environ, "HOME": str(Path.home())}
    expected = Path(paths.models_dir())
    assert Path(_expand(match.group(1), env)) == expected
