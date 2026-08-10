"""Bootstrap dell'app (§8, §9.4, §10.1).

Sequenza del primo avvio: controllo pesi -> download con barra ->
calibrazione -> finestra principale. Mai una finestra vuota mentre si
scaricano 700 MB in silenzio.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from stemforge.ui.main_window import MainWindow
from stemforge.ui.theme import STYLESHEET

_LOG_MAX_BYTES = 5 * 1024 * 1024  # rotazione a 5 MB x 3 (§10.1)
_LOG_BACKUPS = 3


def _log_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / "StemForge"
    if os.name == "nt":
        return Path(os.environ["LOCALAPPDATA"]) / "StemForge" / "logs"
    return Path.home() / ".local" / "state" / "stemforge"


def _setup_logging() -> None:
    log_dir = _log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        log_dir / "stemforge.log",
        maxBytes=_LOG_MAX_BYTES,
        backupCount=_LOG_BACKUPS,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)


def _default_out_dir() -> Path:
    return Path.home() / "Music" / "StemForge"


def main() -> int:
    # nel bundle PyInstaller l'app rilancia sé stessa come worker (D2)
    if "--worker" in sys.argv or "--prepare" in sys.argv:
        from stemforge.worker.runner import main as worker_main

        return worker_main()

    _setup_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("StemForge")
    app.setStyleSheet(STYLESHEET)
    window = MainWindow(out_dir=_default_out_dir())
    window.show()
    window.run_first_start_if_needed()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
