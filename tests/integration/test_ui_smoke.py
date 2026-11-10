"""Smoke test della UI in modalità offscreen: le quattro schermate si
costruiscono, la stima è viva, le dipendenze §5.3 valgono nei widget."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from stemforge.model.stem import StemKind as K  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def italian(qapp):
    """L'utente è italiano: questi test leggono i testi come li vede lui.
    La lingua sorgente nel codice è l'inglese (ui/i18n.py)."""
    from stemforge.ui import i18n

    assert i18n.apply_language("it"), "manca resources/i18n/stemforge_it.qm"
    yield
    i18n.apply_language(i18n.SOURCE_LANGUAGE)


def test_picker_estimate_scales_and_dependencies(qapp, italian, tmp_path: Path):
    from stemforge.ui.stem_picker import StemPicker

    picker = StemPicker(out_dir=tmp_path)
    picker.set_source(tmp_path / "brano.wav", duration=240.0)

    # default: 4 classici in `best`
    assert set(picker._wanted()) == {K.VOCALS, K.DRUMS, K.BASS, K.OTHER}
    assert picker._quality.currentData() == "best"
    full_estimate = picker._estimate.text()
    assert "passate" in full_estimate or "passata" in full_estimate

    # "Solo voce": un click, preset balanced, stima visibilmente più bassa
    picker._select_vocals_only()
    assert picker._wanted() == (K.VOCALS,)
    assert picker._quality.currentData() == "balanced"
    solo_estimate = picker._estimate.text()
    assert solo_estimate != full_estimate

    # spuntare un derivato seleziona la dipendenza (§5.3)
    picker._boxes[K.DRUMS].setChecked(False)
    picker._drum_group._boxes[K.KICK].setChecked(True)
    assert picker._boxes[K.DRUMS].isChecked()

    job = picker._current_job()
    assert job is not None
    assert K.KICK in job.wanted


def test_all_screens_construct(qapp, tmp_path: Path):
    from stemforge.ui.drop_zone import DropZone, _collect_audio_files
    from stemforge.ui.progress_view import ProgressView
    from stemforge.ui.result_view import ResultView

    DropZone()
    progress = ProgressView()
    progress.reset()
    progress.set_phase("Separazione — passata 1 di 2", 1, 2)
    progress.set_progress(0.5)
    progress.stop()
    ResultView()

    # filtro dei formati al drop (§8.1): rifiuto inline, cartelle accettate
    (tmp_path / "a.wav").touch()
    (tmp_path / "b.txt").touch()
    accepted, rejected = _collect_audio_files([tmp_path / "a.wav", tmp_path / "b.txt"])
    assert [p.name for p in accepted] == ["a.wav"]
    assert rejected == 1


def test_prepare_failure_leads_to_usable_drop_zone(qapp, tmp_path: Path):
    """Regressione dal campo: primo avvio fallito -> l'app resta usabile.

    Prima del fix, il fallimento della preparazione instradava sullo
    StemPicker senza nessun file impostato: vicolo cieco senza modo di
    scegliere un brano.
    """
    from stemforge.ui.main_window import MainWindow

    window = MainWindow(out_dir=tmp_path)
    window._preparing = True
    window._stack.setCurrentWidget(window._progress)

    window._on_failed("Serve la connessione a internet.", "detail")

    assert window._stack.currentWidget() is window._drop
    assert "connessione" in window._drop._message.text()
    assert not window._preparing

    # e un errore senza alcun job in corso non porta mai al picker
    window._on_failed("File corrotto.", "detail")
    assert window._stack.currentWidget() is window._drop


def test_unadopted_derived_options_are_hidden(qapp, tmp_path: Path):
    # §12-M6: un derivato senza modello vero non si mostra affatto
    from stemforge.ui.stem_picker import StemPicker
    from stemforge.worker import planning

    options = planning.derived_options()
    picker = StemPicker(out_dir=tmp_path)
    assert picker._drum_group.isVisibleTo(picker) == options.drum_detail
    assert picker._vocal_group.isVisibleTo(picker) == (options.vocal_split or options.dereverb)


def test_open_with_routes_files_and_queues_during_jobs(qapp, tmp_path: Path):
    """"Apri con" (Finder / Esplora file): con l'app ferma il file arriva
    alla scelta strumenti; con un job in corso entra in coda."""
    from stemforge.ui.main_window import MainWindow

    song = tmp_path / "brano.wav"
    song.touch()
    window = MainWindow(out_dir=tmp_path)
    window.open_files([song, tmp_path / "note.txt"])
    assert window._stack.currentWidget() is window._picker

    window._preparing = True  # finché si prepara, niente cambio schermata
    other = tmp_path / "altro.wav"
    other.touch()
    window.open_files([other])
    assert window._queue == [other]
    assert window._stack.currentWidget() is window._picker


def test_bridge_does_not_overwrite_real_error(qapp, italian):
    """Regressione dal campo: l'Error del worker seguito da exit 1 non
    deve produrre un secondo `failed` generico che sovrascrive il vero
    motivo nell'UI."""
    from stemforge.ui.bridge import WorkerBridge
    from stemforge.worker import protocol

    bridge = WorkerBridge()
    received: list[str] = []
    bridge.failed.connect(lambda message, detail: received.append(message))

    bridge._dispatch(protocol.Error(message="Motivo vero.", detail="tb"))
    bridge._on_finished(1, None)  # il worker esce con 1 dopo l'Error

    assert received == ["Motivo vero."]

    # un crash duro senza Error mantiene invece il fallback generico
    bridge._error_reported = False
    bridge._stderr_tail = "Traceback ..."
    bridge._on_finished(1, None)
    assert len(received) == 2 and "interrotto" in received[1]


def test_result_view_lists_manifest(qapp, tmp_path: Path, mix_44k, fake_backends):
    from stemforge.model.job import SeparationJob
    from stemforge.ui.result_view import ResultView
    from stemforge.worker.pipeline import run_job

    cache, _fake = fake_backends()
    job = SeparationJob(
        source=mix_44k, wanted=(K.VOCALS, K.OTHER), quality="balanced",
        out_dir=tmp_path / "out", device="cpu",
    )
    result = run_job(job, emit=lambda m: None, backends=cache)
    view = ResultView()
    view.show_result(result.out_dir, result.out_dir / "manifest.json", warnings=[])
    from PySide6.QtCore import Qt

    assert view.list.count() == 2
    first_path = view.list.item(0).data(Qt.ItemDataRole.UserRole)
    assert Path(first_path).exists()
