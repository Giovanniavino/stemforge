# StemForge — comandi di sviluppo (BUILD_SPEC §3)
# Sul Mac: make dev / test / build. Su Windows (dev-box): usare .venv\Scripts\python.exe.

PY ?= python3.11

.PHONY: dev test test-slow lock-macos build sign notarize clean

dev:
	$(PY) -m venv .venv
	.venv/bin/python -m pip install --require-hashes -r requirements-macos-x86_64.lock
	.venv/bin/python -m pip install -e . --no-deps
	.venv/bin/python -m pip install pytest pyinstaller

test:
	.venv/bin/python -m pytest tests -q

test-slow:
	.venv/bin/python -m pytest tests -q -m slow -s

lock-macos:
	.venv/bin/python packaging/gen_macos_lock.py > requirements-macos-x86_64.lock

build:
	cd packaging && ../.venv/bin/pyinstaller stemforge.spec --noconfirm

# firma ad-hoc per uso personale (§9.3): identita' "-" e' il default dello spec
sign: build

# distribuzione a terzi: Developer ID + gate licenze (§9.3)
notarize:
	sh packaging/notarize.sh packaging/dist/StemForge.app

clean:
	rm -rf packaging/build packaging/dist src/stemforge.egg-info
