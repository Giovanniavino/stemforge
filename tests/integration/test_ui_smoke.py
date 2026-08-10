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


def test_picker_estimate_scales_and_dependencies(qapp, tmp_path: Path):
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
    assert view.list.count() == 2
    first_path = view.list.item(0).data(view.list.item(0).UserRole if False else 0x0100)
    assert Path(first_path).exists()
