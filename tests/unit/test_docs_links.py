"""I link interni della documentazione portano da qualche parte.

Ogni link relativo dei markdown del repository deve puntare a un file
esistente e, se ha un'ancora, a un titolo che esiste davvero in quel file
(con le regole con cui GitHub genera le ancore). I link esterni non si
controllano: il giro veloce non va in rete.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# cartelle che non sono documentazione del progetto
SKIPPED_DIRS = {".git", ".claude", ".venv", "build", "dist", "node_modules", "__pycache__"}

FENCE = re.compile(r"^\s*(```|~~~)")
INLINE_CODE = re.compile(r"`[^`]*`")
MD_LINK = re.compile(r"!?\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
HTML_LINK = re.compile(r"""(?:href|src)\s*=\s*["']([^"']+)["']""")
HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
EXTERNAL = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


def markdown_files(root: Path = ROOT) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*.md")
        if not SKIPPED_DIRS.intersection(part for part in path.relative_to(root).parts)
        and not any(part.startswith(".venv") for part in path.relative_to(root).parts)
    )


def _prose_lines(text: str) -> list[str]:
    """Le righe fuori dai blocchi di codice, senza il codice in linea."""
    lines: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            lines.append(INLINE_CODE.sub("", line))
    return lines


def links_in(text: str) -> list[str]:
    found: list[str] = []
    for line in _prose_lines(text):
        found.extend(MD_LINK.findall(line))
        found.extend(HTML_LINK.findall(line))
    return found


def github_slug(heading: str) -> str:
    """L'ancora che GitHub assegna a un titolo."""
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", heading)
    text = text.replace("`", "").strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def anchors_of(text: str) -> set[str]:
    anchors: set[str] = set()
    seen: dict[str, int] = {}
    for line in _heading_lines(text):
        slug = github_slug(line)
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        anchors.add(slug if count == 0 else f"{slug}-{count}")
    anchors.update(re.findall(r"""<a\s+(?:name|id)=["']([^"']+)["']""", text))
    return anchors


def _heading_lines(text: str) -> list[str]:
    headings: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        match = HEADING.match(line) if not in_fence else None
        if match:
            headings.append(match.group(2))
    return headings


def broken_links(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    problems: list[str] = []
    for target in links_in(text):
        if EXTERNAL.match(target):
            continue
        file_part, _, anchor = target.partition("#")
        destination = (path.parent / file_part).resolve() if file_part else path
        if not destination.exists():
            problems.append(f"{target}: il file non esiste")
            continue
        if anchor and destination.suffix == ".md":
            if anchor not in anchors_of(destination.read_text(encoding="utf-8")):
                problems.append(f"{target}: nessun titolo con ancora #{anchor}")
    return problems


def test_internal_links_resolve():
    report = {
        str(path.relative_to(ROOT)): problems
        for path in markdown_files()
        if (problems := broken_links(path))
    }
    assert not report, f"link interni rotti: {report}"


def test_the_checker_finds_documentation():
    names = {path.relative_to(ROOT).as_posix() for path in markdown_files()}
    assert {"README.md", "PRIVACY.md", "CONTRIBUTING.md", "docs/it/README.md"} <= names


def test_github_slug_rules():
    assert github_slug("The app won't open") == "the-app-wont-open"
    assert github_slug("Windows — SmartScreen") == "windows--smartscreen"
    assert github_slug("macOS 10.15 Catalina to 14 Sonoma") == "macos-1015-catalina-to-14-sonoma"
    assert github_slug("L'app non si apre") == "lapp-non-si-apre"
    assert github_slug("`--selftest` e [diagnostica](x.md)") == "--selftest-e-diagnostica"


def test_checker_reports_missing_files_and_anchors(tmp_path: Path):
    (tmp_path / "other.md").write_text("# Real title\n", encoding="utf-8")
    page = tmp_path / "page.md"
    page.write_text(
        "# Top\n"
        "[ok](other.md#real-title) [self](#top) [web](https://example.com/x)\n"
        "[gone](missing.md) [bad anchor](other.md#nope)\n"
        "```\n[in code](ignored.md)\n```\n"
        "`[inline](ignored2.md)`\n",
        encoding="utf-8",
    )
    assert broken_links(page) == [
        "missing.md: il file non esiste",
        "other.md#nope: nessun titolo con ancora #nope",
    ]


def test_duplicate_headings_get_numbered_anchors():
    assert anchors_of("# Same\n## Same\n") == {"same", "same-1"}
