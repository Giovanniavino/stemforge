"""Bootstrap dell'app (§8, §9.4, §10.1).

Lo stesso eseguibile fa tre mestieri, decisi dagli argomenti:
- nessun argomento (o file audio): l'app con la sua finestra;
- `--worker` / `--prepare`: il processo figlio (D2);
- `--selftest [--report FILE] [--offline]`: il collaudo del pacchetto (§10.5).

Sequenza del primo avvio: controllo pesi -> download con barra ->
calibrazione -> finestra principale. Mai una finestra vuota mentre si
scaricano 700 MB in silenzio.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
import tempfile
from pathlib import Path
from typing import Callable

_LOG_MAX_BYTES = 5 * 1024 * 1024  # rotazione a 5 MB x 3 (§10.1)
_LOG_BACKUPS = 3


def _log_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / "StemForge"
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "StemForge" / "logs"
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


def _paths_from_argv(args: list[str]) -> list[Path]:
    # -psn_... è l'argomento che i macOS più vecchi aggiungono al lancio dal Finder
    return [Path(arg) for arg in args if not arg.startswith("-")]


# -- collaudo (§10.5) -------------------------------------------------------


def _ui_check() -> str:
    """L'interfaccia si costruisce dentro il pacchetto: plugin Qt, stile,
    finestra principale e lettore di anteprima."""
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtWidgets import QApplication

    from stemforge.ui.main_window import MainWindow
    from stemforge.ui.result_view import ResultView
    from stemforge.ui.theme import STYLESHEET

    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setStyleSheet(STYLESHEET)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        window = MainWindow(out_dir=Path(tmp))
        window.show()
        app.processEvents()
        preview = ResultView()
        preview._ensure_player()
        app.processEvents()
        window.close()
    return "finestra principale e lettore di anteprima costruiti"


def _selftest(args: list[str]) -> int:
    from stemforge.worker import selftest

    report: Path | None = None
    if "--report" in args:
        index = args.index("--report")
        if index + 1 < len(args):
            report = Path(args[index + 1])
    return selftest.run(
        report,
        network="--offline" not in args,
        extra=[("interfaccia", _ui_check)],
    )


# -- app --------------------------------------------------------------------


def _make_app(argv: list[str]):
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication

    class StemForgeApp(QApplication):
        """Riceve i file di "Apri con" del Finder (QFileOpenEvent, §9.1),
        anche quelli che arrivano prima che la finestra esista."""

        def __init__(self, args: list[str]) -> None:
            super().__init__(args)
            self._pending: list[Path] = []
            self._handler: Callable[[list[Path]], None] | None = None

        def set_file_handler(self, handler: Callable[[list[Path]], None]) -> None:
            self._handler = handler
            if self._pending:
                pending, self._pending = self._pending, []
                handler(pending)

        def event(self, event) -> bool:
            if event.type() == QEvent.Type.FileOpen:
                path = Path(event.file())
                if self._handler is not None:
                    self._handler([path])
                else:
                    self._pending.append(path)
                return True
            return super().event(event)

    return StemForgeApp(argv)


def main() -> int:
    # nel bundle PyInstaller l'app rilancia sé stessa come worker (D2)
    if "--worker" in sys.argv or "--prepare" in sys.argv:
        from stemforge.worker.runner import main as worker_main

        return worker_main()
    if "--selftest" in sys.argv:
        return _selftest(sys.argv)

    from stemforge.ui.main_window import MainWindow
    from stemforge.ui.theme import STYLESHEET

    _setup_logging()
    app = _make_app(sys.argv)
    app.setApplicationName("StemForge")
    app.setStyleSheet(STYLESHEET)
    window = MainWindow(out_dir=_default_out_dir())
    window.show()
    window.run_first_start_if_needed()
    app.set_file_handler(window.open_files)
    initial = _paths_from_argv(sys.argv[1:])
    if initial:
        window.open_files(initial)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
