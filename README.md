<h1 align="center">StemForge</h1>

<p align="center">
  <em>Split a song into its tracks. Drag them into the project you already have open. Done.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/macOS-10.15%2B%20Intel%20%C2%B7%2011%2B%20Apple%20Silicon-black" alt="macOS">
  <img src="https://img.shields.io/badge/Windows-10%20%2F%2011%20x64-blue" alt="Windows">
  <img src="https://img.shields.io/badge/Linux-x64%20AppImage-orange" alt="Linux">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="license">
</p>

<p align="center"><a href="docs/it/README.md">Guida in italiano</a></p>

---

Drop in a song, tick the instruments you want, hit **Separate**. Then drag
the stems straight into the Ableton project — or any DAW — you already have
open.

No plugin to install, no new project to open, no import step. No account,
no cloud: everything runs on your computer.

```
  song.mp3  ─→  pick your instruments  ─→  drag  ─→  your project
```

**Contents** —
[Which file to download](#which-file-to-download) ·
[Requirements](#requirements) ·
[Install](#install) ·
[First launch](#first-launch) ·
[Usage](#usage) ·
[How long it takes](#how-long-it-takes) ·
[The app won't open](#the-app-wont-open) ·
[FAQ](#faq) ·
[Troubleshooting](#troubleshooting) ·
[Diagnostics](#export-diagnostics) ·
[Support](#support-and-donations) ·
[Development](#development)

## Which file to download

Every release on the [Releases page](https://github.com/Giovanniavino/stemforge/releases)
contains one file per kind of computer. Pick the row that matches yours:

| Your computer | Download | Acceleration |
|---|---|---|
| Mac with Apple chip (M1, M2, M3, M4…), macOS 11 Big Sur or later | `StemForge-<version>-macos-arm64.dmg` | Apple GPU, after a correctness check |
| Mac with Intel processor, macOS 10.15 Catalina or later | `StemForge-<version>-macos-x86_64.dmg` | CPU only |
| PC with Windows 10 (1809 or later) or Windows 11, 64-bit | `StemForge-<version>-windows-x64-setup.exe` | CPU only |
| PC with Linux x64 (Ubuntu 20.04, Debian 11, Fedora 29 or later) | `StemForge-<version>-linux-x86_64.AppImage` | CPU only |

Not sure which Mac you have? Apple menu  → **About This Mac**: "Chip Apple
M…" means Apple Silicon, "Processor Intel…" means Intel. The Intel build
also runs on Apple Silicon through Rosetta, but slower and without the GPU:
take the `arm64` file.

Windows on ARM runs the x64 build through Windows' own emulation.

Each release also contains `SHA256SUMS.txt`, to check that the file you
downloaded is exactly the one published ([how](#check-the-sha-256)).

## Requirements

| Profile | Minimum system |
|---|---|
| Mac Intel (`legacy-intel`) | macOS 10.15 Catalina, any Intel Mac that runs it (a 2012 Mac mini is enough) |
| Mac Apple Silicon (`mac-arm64`) | macOS 11 Big Sur — every Apple Silicon Mac |
| Windows (`win-x64`) | Windows 10 version 1809 or Windows 11, x64 |
| Linux (`linux-x64`) | glibc 2.28 or newer (Ubuntu 20.04, Debian 11, Fedora 29 and later), x64 |

- **Disk:** about 1 GB for the separation models (downloaded once), plus
  room for your stems: a 24-bit stereo stem takes about 15 MB per minute of
  audio. StemForge checks the free space *before* it starts.
- **Memory:** 8 GB of RAM is comfortable. With less, close other apps or
  pick the `Fast` preset.
- **Internet:** only once, on first launch, to download the models.

Linux is a second-tier platform: it is built and tested automatically, but
it gets less hands-on testing than macOS and Windows.

## Install

**Mac** — open the `.dmg` and drag **StemForge** into **Applications**.
The first time, macOS will warn you that the developer can't be verified:
see [The app won't open](#the-app-wont-open).

**Mac mini and other old Intel Macs (alternative)** — the
`StemForge-Installer.zip` package builds the app directly on your Mac; it
is the route that has run on a 2012 Mac mini for months, and it stays
until the Intel DMG has been checked on that machine. Unzip it,
double-click **"Installa StemForge.command"** and follow the Terminal
(the scripts speak Italian). It needs an internet connection during
installation: it downloads the official Python and the libraries, each
verified by SHA-256. **"Aggiorna StemForge.command"** updates an
installation made this way.

**Windows** — run `StemForge-<version>-windows-x64-setup.exe`. No
administrator rights are needed (the installer offers "install for all
users" if you want it). You get a Start menu entry, an optional desktop
icon and an "Open with" entry for audio files — your default player is
left alone.

**Linux** — make the file executable and run it:

```bash
chmod +x StemForge-<version>-linux-x86_64.AppImage
./StemForge-<version>-linux-x86_64.AppImage
```

## First launch

The first launch does three things, each with its own progress bar — never
a blank window:

1. **Downloads the separation models** (about 1 GB, once) from the official
   Demucs server, `dl.fbaipublicfiles.com`. Every file is checked against a
   fixed SHA-256: a download interrupted halfway is detected and fetched
   again. Without a connection the app tells you so: it needs the network
   this one time, then it works offline forever.
2. **Checks the GPU — Apple Silicon only.** Before StemForge trusts the
   Apple GPU it separates the same short synthetic audio on the GPU and on
   the CPU and compares the results. Only if they match is the GPU used;
   otherwise StemForge stays on the CPU, which is slower but always correct.
   If the GPU ever fails during a job, that pass is redone on the CPU with a
   notice.
3. **Calibrates:** *"Measuring this computer's speed to give you honest
   estimates."* A short benchmark measures how fast your machine separates
   audio. Every time estimate you will see comes from this measurement,
   and it keeps improving with every song you separate.

## Usage

1. **Drop a song** into the window (or choose a file): `wav`, `mp3`,
   `flac`, `ogg`, `m4a`, `aiff`, `aif`. Several files or whole folders work
   too.
2. **Tick the instruments**: vocals, drums, bass, guitar, piano, other,
   instrumental. Two shortcuts at the top: **Everything** and **Vocals
   only**. The time estimate updates with every tick — *asking for less
   costs less.*
3. Press **Separate**. You can cancel at any time: the work stops within a
   second and no half-written files are left behind.
4. When it's done, **select the stems and drag them into your DAW**: one
   track per file, sample-aligned with the original. You can preview each
   stem before dragging, or open the folder (**Show in Finder** on macOS,
   **Show in File Explorer** on Windows, **Show in Folder** on Linux).

Stems land in `~/Music/StemForge/<song name>/` as 24-bit WAV (or FLAC),
with the same sample rate and exactly the same length in samples as your
original, plus a `manifest.json`. No normalization, no limiting, no fades:
the stems add back up to the mix.

**Quality presets:** `Best` *(default — always the full model ensemble,
no shortcuts)*, `Balanced` *(faster: runs only the parts of the model you
asked for)*, `Fast` *(previews)*. **Vocals only** switches to `Balanced`
on its own.

Drum detail (kick, snare, toms, hi-hat, cymbals), lead/backing vocals and
vocal de-reverb appear in the app only once their models pass the quality
bar: an option that doesn't sound good isn't shown.

The interface is in English and Italian (it follows your system; you can
also pick the language on the start screen, and the choice is kept), works
fully from the keyboard (Enter = Separate, Esc = Cancel/Back,
Cmd/Ctrl+O = choose file) and with VoiceOver / NVDA.

## How long it takes

There is no single number: separation runs on your CPU (or, on Apple
Silicon, on a verified GPU), and machines differ enormously. What
StemForge promises instead:

- **Before you start, it tells you how long it will take on *your*
  computer** — from the first-launch calibration, never from a number
  measured on someone else's machine. The estimate is deliberately 15% on
  the pessimistic side, and next to it you see how many passes will run
  (e.g. *"~14 min · 4 passes"*).
- **Time scales with what you ask for.** In `Balanced`, vocals alone take
  about a quarter of the time of all four base stems; vocals + drums about
  half. Drum and vocal detail add short extra passes on top.
- **`Best` costs more, on purpose**: roughly three times the full
  `Balanced` separation. On an old Intel Mac that can mean more than an
  hour for one song — the app says so up front, and `Balanced` is one
  click away.

Absolute times measured on the reference Intel Mac (CPU) will be published
here once measured on that machine.

## The app won't open

StemForge is not signed with a paid Apple or Microsoft certificate yet, so
the system warns you the first time. That warning is expected; what
matters is that the file is the one we published —
[check the SHA-256](#check-the-sha-256) first. You only have to do this
once.

### macOS 10.15 Catalina to 14 Sonoma

1. Open the **Applications** folder in Finder.
2. **Control-click** (or right-click) **StemForge** → **Open**.
3. In the dialog, click **Open** again.

If there is no **Open** button: try to open the app once, then go to
**System Preferences / System Settings → Security & Privacy (Privacy &
Security) → General**, and click **Open Anyway** next to the StemForge
message.

### macOS 15 Sequoia and later

Control-click → Open no longer bypasses the warning.

1. Double-click StemForge. When macOS says it was not opened, click **Done**.
2. Open **System Settings → Privacy & Security** and scroll down to
   **Security**.
3. Next to *"StemForge" was blocked…* click **Open Anyway**, confirm with
   your password or Touch ID, then click **Open**.

### "StemForge is damaged and can't be opened" (macOS)

This can happen when a download tool strips or alters the signature.
First check the SHA-256. If it matches, remove the download quarantine
flag in Terminal, then open the app as above:

```bash
xattr -dr com.apple.quarantine /Applications/StemForge.app
```

### Windows — SmartScreen

1. On the blue *"Windows protected your PC"* screen, click **More info**.
2. Click **Run anyway**.

If your browser blocks the download ("isn't commonly downloaded"), open
the download list, choose **Keep** → **Keep anyway**.

### Linux — the AppImage doesn't start

- Make sure it is executable: `chmod +x StemForge-*.AppImage`.
- If it complains about **FUSE**, install your distribution's FUSE package,
  or start it without FUSE: `./StemForge-<version>-linux-x86_64.AppImage --appimage-extract-and-run`.

### Check the SHA-256

Download `SHA256SUMS.txt` from the same release and compare:

| System | Command | Compare with |
|---|---|---|
| macOS | `shasum -a 256 ~/Downloads/StemForge-*.dmg` | the line for that file in `SHA256SUMS.txt` |
| Windows (PowerShell) | `Get-FileHash $HOME\Downloads\StemForge-*-setup.exe -Algorithm SHA256` | same |
| Linux | `sha256sum -c SHA256SUMS.txt --ignore-missing` (in the download folder) | prints `OK` |

If the value differs, **don't open the file**: download it again from the
Releases page.

## FAQ

**Does it send my music anywhere?** No. Separation happens entirely on
your computer. The only network connection StemForge ever makes is the
one-time model download. No account, no telemetry, no auto-update. See
[PRIVACY.md](PRIVACY.md).

**Which DAWs does it work with?** Any DAW that accepts files dragged from
the desktop: StemForge uses the operating system's own drag & drop, with
no code specific to any DAW. The targets are Ableton Live, Logic Pro, FL
Studio, Reaper, Cubase, Studio One and Bitwig, on every system where they
exist. Drag & drop cannot be tested automatically: each DAW is checked by
hand with a checklist, and the release notes say which combinations have
been checked for that version.

**Why isn't it a VST/AU plugin?** A plugin runs on the DAW's audio thread,
with a few milliseconds per buffer and a hard ban on allocating memory.
Neural separation needs minutes and gigabytes of RAM. The two are
fundamentally incompatible: every product offering separation "inside a
plugin" in fact processes offline and hands back files, exactly like
StemForge.

**Will it use my NVIDIA / AMD / Intel GPU on Windows or Linux?** Not in
this version. A GPU build of PyTorch weighs about 2.5 GB, more than the
2 GB per-file limit of GitHub releases, and would be a huge download for
everyone without that GPU. AMD/Intel acceleration on Windows (DirectML)
cannot run the models' core operation. Only the Apple Silicon GPU is used,
and only after it has proven to give the same result as the CPU.

**Why is it so slow on my old Mac?** Quality comes first: the default
preset gives the best stems the models can produce. Choose `Balanced` or
**Vocals only** when you are in a hurry.

**What about long files?** Files over 15 minutes are processed in blocks
that join seamlessly; files over 30 minutes are refused with an
explanation.

**Mono, surround, odd sample rates?** Mono stays mono. 5.1/7.1 files are
mixed down to stereo (with a notice) and the stems are stereo. Any sample
rate goes in, and the stems come out at that same rate.

**Can it make drum kits, slices, loops, or remove reverb from a mix?** No:
StemForge separates and delivers stems, and nothing else. Slicing, kits,
effects and editing belong in your DAW or sampler.

**Is it free?** Yes, and open source under the MIT license. If it is
useful to you, see [Support and donations](#support-and-donations).

## Troubleshooting

| Message or symptom | What to do |
|---|---|
| "Not enough memory" | Close other apps, or use the `Fast` preset. The job can be started again. |
| "Not enough disk space" | StemForge checks before starting, from what you asked for: free the space it indicates, or ask for fewer stems. |
| The model download fails | Check the connection; a firewall or proxy must let you reach `dl.fbaipublicfiles.com`. Then retry. A file damaged by an interrupted download is recognised by its SHA-256 and downloaded again. |
| A file is refused when dropped | The format isn't supported, or it isn't audio. DRM-protected files (e.g. `.m4p` purchases from the old iTunes Store, Apple Music downloads) cannot be read. |
| "Almost silent" notice on a stem | That instrument is (nearly) absent from the song. The file is written anyway. |
| One song in a batch fails | The others carry on; you get a summary at the end. |
| "The file is longer than 30 minutes" | Split it in your DAW or audio editor first: StemForge refuses files over 30 minutes. |
| The estimate was wrong | It improves with every completed job. If it is far off, [export diagnostics](#export-diagnostics) and open an issue. |
| Dragging into the DAW does nothing | Drag the stems into a track area/arrangement, not onto a plugin. Or use **Show in Finder/Explorer** and drag from there. |

Where StemForge keeps its files:

| | Models and calibration | Log |
|---|---|---|
| macOS | `~/Library/Application Support/StemForge/` | `~/Library/Logs/StemForge/` |
| Windows | `%LOCALAPPDATA%\StemForge\` | `%LOCALAPPDATA%\StemForge\logs\` |
| Linux | `~/.local/share/stemforge/` (or `$XDG_DATA_HOME/stemforge/`) | `~/.local/state/stemforge/` |

**Uninstall** — macOS: drag StemForge from Applications to the Trash, and
delete the two folders above if you want the ~1 GB back. Windows: Settings
→ Apps → StemForge → Uninstall; the uninstaller asks whether to delete the
models and calibration too. Linux: delete the AppImage and the folders
above.

## Export diagnostics

If something goes wrong, StemForge can put everything needed to understand
it into one file — nothing is sent anywhere:

1. On the start screen, click **Export diagnostics** (on macOS also
   **Help → Export diagnostics**).
2. Choose where to save the zip.
3. Look inside if you like: it contains the log, the StemForge version,
   your system, the result of the built-in self-test (offline), and the
   GPU check results. **The log contains the names of the songs you
   processed** — you decide whether and to whom to send it.
4. Attach it to a [bug report](https://github.com/Giovanniavino/stemforge/issues/new/choose).

Advanced: the same self-test can be run from a terminal, writing its result
to a file:

```bash
# macOS
/Applications/StemForge.app/Contents/MacOS/StemForge --selftest --offline --report ~/Desktop/selftest.txt
# Linux
./StemForge-<version>-linux-x86_64.AppImage --selftest --offline --report ~/selftest.txt
```

On Windows (Command Prompt, from the installation folder — by default
`%LOCALAPPDATA%\Programs\StemForge`):
`StemForge.exe --selftest --offline --report "%USERPROFILE%\Desktop\selftest.txt"`.
Without `--offline` the self-test also checks the HTTPS connection to the
model server.

## Support and donations

- **Bugs and questions:** [GitHub Issues](https://github.com/Giovanniavino/stemforge/issues/new/choose).
  Please attach the diagnostics file.
- **Donations:** StemForge is free and will stay free. Donation links are
  not set up yet; when they are, they will appear here and as the
  **Sponsor** button of the repository.

## Development

Contributions are welcome — read **[CONTRIBUTING.md](CONTRIBUTING.md)**
first: environments, build profiles, tests and the hard rules. The full
specification, with every decision and the reasoning behind it, is in
**[BUILD_SPEC.md](BUILD_SPEC.md)** (Italian).

From source, the same pipeline runs headless:

```bash
stemforge song.mp3 --stems vocals,drums,bass,other
stemforge song.mp3 --stems vocals --quality balanced   # about 1/4 of the time
stemforge song.mp3 --stems vocals,drums --dry-run      # print the plan and the estimate
```

Other options: `--format wav|flac`, `--device auto|cpu|…`, `--out FOLDER`,
`--dereverb`.

## Signed distribution

*(Referred to as "Distribuzione firmata" in the build scripts.)*

Releases are not signed with paid certificates yet (BUILD_SPEC §9.3): the
macOS app is signed ad-hoc and the user follows
[The app won't open](#the-app-wont-open). The pipeline is ready to sign
as soon as credentials exist:

- **macOS** (first priority: from macOS 15 an unsigned app can only be
  opened from System Settings): an Apple Developer Program membership and
  a *Developer ID Application* certificate. `packaging/notarize.sh` signs
  from the inside out with the hardened runtime and a timestamp (never
  `--deep`), notarizes with `notarytool`, staples the DMG, and refuses to
  build if any model weight with a non-commercial or unverified license is
  referenced. It reads `APPLE_SIGNING_IDENTITY`, `APPLE_ID`,
  `APPLE_TEAM_ID` and `APPLE_APP_PASSWORD` (an app-specific password);
  in CI they come from repository secrets, together with the certificate
  itself, under the names used by the release workflow.
- **Windows**: an Authenticode code-signing certificate; `signtool` then
  signs `StemForge.exe` and the installer, and SmartScreen stops warning
  once the certificate has built a reputation.

Until then every release publishes `SHA256SUMS.txt`.

## Built on

[Demucs](https://github.com/facebookresearch/demucs) by Alexandre Défossez
and Meta AI Research · [PyTorch](https://pytorch.org) ·
[Qt for Python](https://www.qt.io/qt-for-python) ·
[libsndfile](https://libsndfile.github.io/libsndfile/) ·
[FFmpeg](https://ffmpeg.org) (LGPL build). Every bundled component and its
license is listed in [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES).

## Ideas

Ideas that are not in the specification are collected here instead of
being built (BUILD_SPEC §11, rule 10). None recorded yet.

## License

MIT — see [LICENSE](LICENSE). Third-party components keep their own
licenses: see [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES).
