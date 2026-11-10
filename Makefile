# StemForge — comandi di sviluppo, test e build (BUILD_SPEC §3, §9, §10.6)
#
# GNU make su macOS, Linux e Git Bash su Windows (dove make non c'e',
# "mingw32-make" di Strawberry Perl o MSYS2 va bene, oppure si copiano i
# comandi stampati da "make -n <target>").
#
# Il profilo di build (§2.1) si deduce dalla macchina; si forza con
#   make <target> PROFILE=legacy-intel|mac-arm64|win-x64|linux-x64
# VPY=<python> usa un ambiente gia' pronto invece di .venv.
#
#   make dev              venv dal lock del profilo (hash, solo wheel)
#   make test             giro veloce: tutto tranne slow/fuzz/chaos/soak/frozen
#   make test-slow        Demucs vero su CPU (scarica i pesi la prima volta)
#   make test-compat      il motore con il torch di QUESTO ambiente (§10.6)
#   make test-fuzz | test-chaos | test-soak    famiglie su richiesta
#   make test-frozen      la batteria contro l'app impacchettata (FROZEN_EXE=...)
#   make lock | lock-check    rigenera | verifica i lock dei profili
#   make ffmpeg           FFmpeg LGPL del profilo (D9, packaging/ffmpeg/)
#   make build            app PyInstaller del profilo (build-release: FFmpeg obbligatorio)
#   make check-min-os     macOS minimo di ogni binario dell'app (solo Mac)
#   make selftest         --selftest sull'app costruita
#   make package          pacchetto del profilo: DMG, installer Inno Setup, AppImage
#   make installer        zip "Installa StemForge.command" del Mac mini (§9.5)
#   make notarize         firma Developer ID + notarizzazione (credenziali in env)

ifeq ($(OS),Windows_NT)
  DETECTED_PROFILE := win-x64
else
  UNAME_S := $(shell uname -s)
  UNAME_M := $(shell uname -m)
  ifeq ($(UNAME_S),Darwin)
    DETECTED_PROFILE := $(if $(filter arm64,$(UNAME_M)),mac-arm64,legacy-intel)
  else
    DETECTED_PROFILE := linux-x64
  endif
endif
PROFILE ?= $(DETECTED_PROFILE)

LOCK_legacy-intel := requirements-macos-x86_64.lock
LOCK_mac-arm64    := requirements-macos-arm64.lock
LOCK_win-x64      := requirements-windows-x64.lock
LOCK_linux-x64    := requirements-linux-x64.lock
LOCK := $(LOCK_$(PROFILE))
ifeq ($(LOCK),)
  $(error profilo sconosciuto "$(PROFILE)": legacy-intel, mac-arm64, win-x64, linux-x64)
endif

# PySide6 6.4 (legacy-intel) richiede Python < 3.12 (§2.2)
PYVER := $(if $(filter legacy-intel,$(PROFILE)),3.11,3.12)
MACOS_MIN_legacy-intel := 10.15
MACOS_MIN_mac-arm64    := 11.0
DMG_ARCH_legacy-intel  := x86_64
DMG_ARCH_mac-arm64     := arm64

VENV ?= .venv
ifeq ($(OS),Windows_NT)
  PY_BASE ?= py -$(PYVER)
  VPY ?= $(VENV)/Scripts/python.exe
else
  PY_BASE ?= python$(PYVER)
  VPY ?= $(VENV)/bin/python
endif

# Python puro pubblicato solo come sorgente (packaging/gen_locks.py,
# SDIST_ALLOWLIST): si installa senza compilatore, tutto il resto e' wheel.
SDIST_ONLY := antlr4-python3-runtime,demucs,dora-search
DIST := packaging/dist
WORK := packaging/build
VERSION := $(shell sed -n 's/^__version__ = "\(.*\)"/\1/p' src/stemforge/__init__.py)

APP_EXE_legacy-intel := $(DIST)/StemForge.app/Contents/MacOS/StemForge
APP_EXE_mac-arm64    := $(DIST)/StemForge.app/Contents/MacOS/StemForge
APP_EXE_win-x64      := $(DIST)/StemForge/StemForge.exe
APP_EXE_linux-x64    := $(DIST)/StemForge/StemForge
APP_EXE := $(APP_EXE_$(PROFILE))
FROZEN_EXE ?= $(APP_EXE)
SELFTEST_ARGS ?=
REQUIRE_FFMPEG ?= 0
ISCC ?= iscc
PYTEST := "$(VPY)" -m pytest tests -q

.PHONY: dev test test-slow test-compat test-fuzz test-chaos test-soak test-frozen \
	lock lock-check ffmpeg build build-release check-min-os selftest package \
	package-legacy-intel package-mac-arm64 package-win-x64 package-linux-x64 \
	installer sign notarize clean profile

profile:
	@echo "profilo $(PROFILE) | lock $(LOCK) | python $(PYVER) | versione $(VERSION)"

dev:
	$(PY_BASE) -m venv $(VENV)
	"$(VPY)" -m pip install --upgrade pip "setuptools>=69" wheel
	"$(VPY)" -m pip install --require-hashes --only-binary :all: \
		--no-binary $(SDIST_ONLY) -r $(LOCK)
	"$(VPY)" -m pip install --no-deps --no-build-isolation -e .
	"$(VPY)" -m pip install -r packaging/requirements-build.txt

# -- famiglie di test (§10.6): "-m" sulla riga di comando vince su addopts

test:
	$(PYTEST)

test-slow:
	$(PYTEST) -m slow -s

test-compat:
	$(PYTEST) -m compat

test-fuzz:
	$(PYTEST) -m fuzz

test-chaos:
	$(PYTEST) -m chaos

test-soak:
	$(PYTEST) -m soak -s

test-frozen:
	@test -e "$(FROZEN_EXE)" || { echo "app impacchettata assente: $(FROZEN_EXE) (make build, o FROZEN_EXE=...)" >&2; exit 1; }
	STEMFORGE_FROZEN_EXE="$(FROZEN_EXE)" $(PYTEST) -m frozen

# -- lock e build ------------------------------------------------------------

lock:
	"$(VPY)" packaging/gen_locks.py

lock-check:
	"$(VPY)" packaging/gen_locks.py --check

# win-x64 si compila su Linux/WSL con mingw-w64 (packaging/ffmpeg/build.sh)
ffmpeg:
	bash packaging/ffmpeg/build.sh $(PROFILE)

build:
	STEMFORGE_PROFILE=$(PROFILE) STEMFORGE_REQUIRE_FFMPEG=$(REQUIRE_FFMPEG) \
		"$(VPY)" -m PyInstaller packaging/stemforge.spec --noconfirm \
		--distpath $(DIST) --workpath $(WORK)

build-release:
	$(MAKE) build REQUIRE_FFMPEG=1

check-min-os:
	"$(VPY)" packaging/macos/check_min_os.py $(DIST)/StemForge.app $(MACOS_MIN_$(PROFILE))

selftest:
	"$(VPY)" packaging/ci/run_selftest.py "$(APP_EXE)" $(WORK)/selftest.json $(SELFTEST_ARGS)

package: package-$(PROFILE)

package-legacy-intel package-mac-arm64:
	sh packaging/macos/make_dmg.sh $(DIST)/StemForge.app \
		dist/StemForge-$(VERSION)-macos-$(DMG_ARCH_$(PROFILE)).dmg

package-win-x64:
	"$(VPY)" packaging/windows/make_ico.py
	"$(ISCC)" /DAppVersion=$(VERSION) packaging/windows/stemforge.iss

# dentro manylinux_2_28 (CI) o con packaging/linux/rootless_container.py
package-linux-x64:
	STEMFORGE_REQUIRE_FFMPEG=$(REQUIRE_FFMPEG) bash packaging/linux/build_appimage.sh

# pacchetto inviabile all'utente del Mac mini: zip con doppio-click che
# costruisce l'app nativamente sul suo Mac (funziona anche dal dev-box)
installer:
	"$(VPY)" packaging/make_installer.py

# firma ad-hoc per uso personale (§9.3): identita' "-" e' il default dello spec
sign: build

# distribuzione a terzi: Developer ID + gate licenze (§9.3)
notarize:
	sh packaging/notarize.sh $(DIST)/StemForge.app \
		dist/StemForge-$(VERSION)-macos-$(DMG_ARCH_$(PROFILE)).dmg

clean:
	rm -rf $(WORK) $(DIST) src/stemforge.egg-info
