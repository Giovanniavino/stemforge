# Contributing to StemForge

Thanks for wanting to help. StemForge is small on purpose: it separates a
song into stems and hands them to the DAW by drag & drop, and nothing
else. Before writing code, please read this page and the parts of
[BUILD_SPEC.md](BUILD_SPEC.md) you are going to touch: the specification
(in Italian) is the source of truth, and every decision in it comes with
its reason.

*Puoi scrivere in italiano o in inglese: issue, pull request e messaggi
di commit vanno bene in entrambe le lingue.*

## Before you start

- **Bugs:** open an issue with the
  [bug template](.github/ISSUE_TEMPLATE/bug_report.yml) and attach the
  diagnostics file ([how](README.md#export-diagnostics)).
- **Features:** read the
  [non-goals](BUILD_SPEC.md#non-obiettivi--da-rifiutare-se-emergono-in-corso-dopera)
  first. No VST/AU plugin, no DAW project files, no slicing, pads,
  samplers, kits, effects, mixer or audio editing, no cloud, accounts,
  telemetry or auto-update, no model training. A feature that does not
  help to separate or deliver stems will be declined, however good it is.
- **Ideas not in the spec** go in the "Ideas" section at the end of the
  [README](README.md#ideas) (BUILD_SPEC §11 rule 10), not into code.

## Build profiles

One code base, four stacks (BUILD_SPEC D7, §2). The engine is identical
everywhere; only the pinned libraries differ.

| Profile | Machines | Python | torch | PySide6 | Lock file |
|---|---|---|---|---|---|
| `legacy-intel` | Intel Mac, macOS 10.15+ | 3.11 | 2.2.2 | 6.4.3 | `requirements-macos-x86_64.lock` |
| `mac-arm64` | Apple Silicon, macOS 11+ | 3.12 | 2.10.0 | 6.7.3 | `requirements-macos-arm64.lock` |
| `win-x64` | Windows 10 1809+ / 11, x64 | 3.12 | 2.10.0 | 6.7.3 | `requirements-windows-x64.lock` |
| `linux-x64` | glibc ≥ 2.28, x64 | 3.12 | 2.10.0 | 6.7.3 | `requirements-linux-x64.lock` |

- **`legacy-intel` is frozen.** Its pins never change: it is the
  configuration proven on a 2012 Mac mini. Code must use only APIs present
  in **PySide6 6.4** and **torch 2.2.2**.
- Differences between torch 2.2.2 and 2.10 live in **one** module,
  `engine/compat.py`, tested with both versions (`pytest -m compat`).
  Never fork the engine per platform.
- Pins are written once, as platform conditions in `pyproject.toml`.
  `python packaging/gen_locks.py` regenerates every lock (with `uv`);
  `python packaging/gen_locks.py --check` only verifies them against
  PyPI. Installation is always
  `pip install --require-hashes --only-binary :all: -r <lock>`: the user's
  machine never compiles anything.

## Development environments

Development happens mostly on Windows. Keep at least two environments so
that both stacks are tested:

```bash
# modern stack (mac-arm64 / win-x64 / linux-x64): Python 3.12
py -3.12 -m venv .venv-win
.venv-win/Scripts/python -m pip install --require-hashes --only-binary :all: -r requirements-windows-x64.lock
.venv-win/Scripts/python -m pip install -e . --no-deps
.venv-win/Scripts/python -m pip install -r packaging/requirements-build.txt

# legacy stack (the legacy-intel versions, as Windows wheels): Python 3.11
py -3.11 -m venv .venv-legacy
.venv-legacy/Scripts/python -m pip install --index-url https://download.pytorch.org/whl/cpu torch==2.2.2 torchaudio==2.2.2
.venv-legacy/Scripts/python -m pip install "numpy==1.26.4" PySide6==6.4.3 demucs==4.0.1 soundfile==0.14.0 certifi pytest
.venv-legacy/Scripts/python -m pip install -e . --no-deps
```

The legacy environment is not hash-locked (no lock describes Windows with
the legacy-intel pins): it exists only to run the tests against the old
APIs and is never packaged. On macOS, `make dev` creates `.venv` from the `legacy-intel` lock. On a
Mac, use the **official python.org Python** for builds: it targets old
macOS versions, and PyInstaller copies it into the app (BUILD_SPEC §9.1).

## Tests

```bash
python -m pytest tests -q            # the fast round: must stay green on every profile
python -m pytest tests -q -m slow -s # real Demucs on CPU (minutes; downloads ~1 GB once)
```

For UI tests without a display set `QT_QPA_PLATFORM=offscreen`.

Test families (BUILD_SPEC §10.6), each behind a marker:

| Marker | What | Where it runs |
|---|---|---|
| *(none)* | unit tests and integration with a fake backend | every push, every profile |
| `slow` | real Demucs on CPU: reconstruction invariant, sub-model equivalence, scalability | release, weekly |
| `compat` | the engine with torch 2.2.2 **and** 2.10 | every push |
| `fuzz` | Hypothesis on model, planner, protocol, extreme audio files | on demand |
| `chaos` | killed worker, full disk, network loss, corrupted state files | on demand |
| `soak` | 20-song batch, 29-minute song, memory and processes watched | on demand |
| `frozen` | the same battery against the packaged app | release |

Rules for tests:

- Every bug gets a **failing test first**, then the fix.
- A test that cannot fail does not count.
- Audio fixtures are **generated in code** (sines, noise, clicks). Never
  commit copyrighted material, not even a few seconds of it.
- Performance numbers measured on a GPU (CUDA) never go into the spec, the
  UI, the exit criteria or the user documentation (BUILD_SPEC D6). Times
  come from the calibration on the user's machine or from `device=cpu`,
  and the benchmark checks **ratios**, not absolute times.
- What cannot be run from your machine (a `.app`, a DMG, an AppImage, a
  drag into Logic) is **not declared verified**: it goes in the manual
  checklist or in CI on the real platform.

## The hard rules (BUILD_SPEC §11)

They exist because the previous project died of accumulation. Most are
enforced by `tests/unit/test_guards.py`, and the limits are never raised:
if a file grows, split it.

1. No file over **400 lines**.
2. No function over **50 lines**.
3. Type hints everywhere, `from __future__ import annotations` at the top.
4. No circular imports. Layers point one way:
   `ui -> worker -> engine -> model`, `export -> model`. `model/` does no
   I/O; `ui/` never imports `engine`, `export`, `torch`, `soundfile` or
   `demucs`. Platform APIs (`sys.platform`, `os.name`, `winreg`,
   `ctypes`…) only in `ui/`, `packaging/`, `engine/paths.py`,
   `engine/device.py` and `engine/ffmpeg.py`.
5. No `except: pass`. Every exception is handled or re-raised.
6. No singletons, no global state, except the logger.
7. No unnamed magic numbers: `overlap=0.1`, never `0.1`.
8. Comments explain **why**, never what.
9. No new dependency without a written justification in the commit.
10. No feature that is not in the spec (see "Ideas" above).
11. **Every distributed dependency is listed in
    [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES)** with its license and, for
    LGPL ones, a link to the source. No model weights with a
    non-commercial license in a distributed build. The test
    `tests/unit/test_docs_notices.py` fails if a lock pin is missing from
    the file.
12. Optimize only by measuring: profile first, gain ≥ 5% on the median of
    5 runs with `device=cpu`, identical result. Every attempt, kept or
    dropped, goes in `docs/OPTIMIZATION_LOG.md`.

Licensing constraints that follow from this: StemForge is MIT; Qt and
FFmpeg are used only as LGPL libraries or separate executables. **No GPL
component may enter a distributed build** — that is why PyAV, whose
FFmpeg is built `--enable-gpl`, was removed (BUILD_SPEC D9).

## Error messages

Every message shown to the user says **what to do** (BUILD_SPEC §10.1):
"Separation error" is not acceptable; "Not enough memory: close other
apps or switch to the Fast preset" is. Full tracebacks go to the log,
never to the user. Every visible string goes through `tr()` and needs an
Italian and an English text (BUILD_SPEC §8.6).

## Documentation

- `README.md` is in English, for everyone; `docs/it/` is the Italian user
  guide. Keep the two in step when you change behaviour.
- Internal links in the Markdown files are checked by
  `tests/unit/test_docs_links.py`.

## Pull requests

- One topic per pull request, with a commit message that explains *why*.
- The fast test round green on both stacks (modern and legacy).
- If you add or bump a dependency: justify it in the commit and update
  `THIRD_PARTY_NOTICES` and the lock files.
- By contributing you agree that your contribution is released under the
  [MIT License](LICENSE).
