<h1 align="center">StemForge</h1>

<p align="center">
  <em>Split a song into its tracks. Drag them into the project. Done.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/platform-macOS%2010.15%2B%20Intel-black" alt="platform">
  <img src="https://img.shields.io/badge/python-3.12-blue" alt="python">
  <img src="https://img.shields.io/badge/milestones-M1--M3%20complete-brightgreen" alt="milestones">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="license">
</p>

---

Drop in a song, tick the instruments you want, hit **Separate**. Then drag
the stems straight into the Ableton project — or any DAW — you already have
open.

No plugin to install, no new project to open, no import step.

```
  song.mp3  ─→  pick your instruments  ─→  drag  ─→  your project
```

## What it runs on

Target: **macOS 10.15+ (Catalina), Intel Macs, CPU only** — a 2012 Mac mini
is enough.

Quality comes before speed: the default preset is `Best`, and the wait —
however long — is stated honestly up front, calibrated to how fast your Mac
actually is.

## Install

Send the user `dist/StemForge-Installer.zip`, regenerated with
`make installer`. Double-click **"Installa StemForge.command"** and it
handles the rest.

On first launch the app downloads the models (~1 GB, once). After that it
never touches the network again: no account, no telemetry.

## Usage

1. Drop a song into the window.
2. Tick the instruments. **The time estimate updates with every tick:
   asking for less costs less.**
3. Hit Separate.
4. When it's done, select the stems and drag them into your arrangement:
   one track per file, sample-aligned.

Stems land in `~/Music/StemForge/<song name>/` as 24-bit WAV or FLAC, with
a `manifest.json` next to them.

### From the command line

```bash
stemforge song.mp3 --stems vocals,drums,bass,other
stemforge song.mp3 --stems vocals --quality balanced   # ~1/4 of the time
stemforge song.mp3 --stems kick,snare --dry-run        # print the plan
```

## Tracks

**Base** — `vocals` `drums` `bass` `guitar` `piano` `other` `instrumental`

**Derived** — `kick` `snare` `toms` `hihat` `cymbals` `lead_vocals`
`backing_vocals`, plus vocal de-reverb *(landing with M6)*

Presets: `fast`, `balanced`, `best` *(default)*.

## Time scales with what you ask for

This is the design choice the whole project is built around: asking for a
single track should cost a fraction of asking for all of them, not the same
time with fewer files at the end.

| Machine | Request (`balanced`) | Time |
|---|---|---|
| x86 CPU dev box (Windows) | 30 s of audio, `vocals` only | 23 s |
| x86 CPU dev box (Windows) | 30 s of audio, 4 stems | 130 s |
| Reference Intel Mac | *to be measured on target* | — |

The measured ratio between "one track" and "everything" is **0.18**. On
`best`, times grow roughly 10x over `balanced`: that's the stated price of
maximum quality, and the in-app estimate says so before you commit.

## Status

| Milestone | |
|---|---|
| M1 · engine, planner, CLI | ✅ |
| M2 · standalone app | ✅ |
| M3 · drag & drop | ✅ |
| M4 · quality (RoFormer) | ⬜ |
| M5 · polish and notarization | ⬜ |
| M6 · derived tracks | ⬜ |

## Development

```bash
make dev        # venv + pinned dependencies (hash-verified)
make test       # fast suite (<10 s, no models)
make test-slow  # with real Demucs (downloads weights)
make build      # x86_64 .app via PyInstaller (macOS only)
```

On Windows (dev box): `py -3.12 -m venv .venv` then
`pip install -r requirements-dev-win.lock`.

The full specification, with every decision and the reasoning behind it, is
in **[BUILD_SPEC.md](BUILD_SPEC.md)**.

Hard rules enforced by tests: no file over 400 lines, dependencies flow one
way only, `model/` does no I/O, the UI never touches the engine.

## Why it isn't a VST plugin

A plugin runs on the DAW's audio thread, with a few milliseconds per buffer
and a hard ban on allocating memory. Neural separation needs tens of seconds
and gigabytes of RAM. That isn't an implementation limit — the two are
fundamentally incompatible.

Every product offering separation "inside a plugin" does exactly what
StemForge does: processes offline and hands back files.

## Built on

[Demucs](https://github.com/adefossez/demucs) by Alexandre Défossez and Meta
AI Research · [PyTorch](https://pytorch.org) · [Qt](https://www.qt.io)

## License

MIT — see [LICENSE](LICENSE).
