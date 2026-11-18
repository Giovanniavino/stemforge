"""Lingua del worker (§8.6) e messaggi d'errore che dicono cosa fare (§10.1)."""

from __future__ import annotations

import errno
import string

import pytest

from stemforge.engine.contract import BackendUnavailable
from stemforge.engine.errors import (
    InsufficientDiskError,
    NonFiniteAudioError,
    TooLongError,
    UnsupportedFormatError,
)
from stemforge.worker import catalog, i18n
from stemforge.worker.messages import is_disk_full, prepare_message, user_message


def _fields(template: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(template) if name}


def test_both_catalogs_have_the_same_keys():
    assert set(catalog.IT) == set(catalog.EN)


@pytest.mark.parametrize("key", sorted(catalog.IT))
def test_same_placeholders_in_both_languages(key):
    assert _fields(catalog.IT[key]) == _fields(catalog.EN[key]), key


@pytest.mark.parametrize("key", sorted(catalog.IT))
def test_english_is_not_italian(key):
    # un testo copiato e non tradotto sarebbe "un italiano a metà" (§8.6)
    if _fields(catalog.IT[key]) and len(catalog.IT[key]) < 30:
        return  # etichette brevi fatte quasi solo di segnaposto
    assert catalog.IT[key] != catalog.EN[key], key


def test_locale_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv(i18n.LOCALE_ENV, "en")
    assert i18n.t("err.memory").startswith("Not enough memory")
    monkeypatch.setenv(i18n.LOCALE_ENV, "it")
    assert i18n.t("err.memory").startswith("Memoria insufficiente")
    monkeypatch.delenv(i18n.LOCALE_ENV)
    assert i18n.current_locale() == "it", "il default è l'italiano"
    monkeypatch.setenv(i18n.LOCALE_ENV, "fr")
    assert i18n.current_locale() == "it", "una lingua non supportata ripiega sul default"


def test_t_never_raises(monkeypatch, caplog):
    # un errore nel tradurre un errore nasconderebbe quello vero
    assert i18n.t("chiave.inesistente") == "chiave.inesistente"
    assert "{name}" in i18n.t("err.corrupt")  # parametro mancante: testo grezzo
    assert caplog.records, "i bachi di traduzione finiscono nel log"


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({"LANG": "it_IT.UTF-8"}, "it"),
        ({"LANG": "en_US.UTF-8"}, "en"),
        ({"LANG": "de_DE.UTF-8"}, "en"),  # altre lingue: l'inglese, lingua franca
        ({"LC_ALL": "fr_FR.UTF-8", "LANG": "it_IT.UTF-8"}, "en"),  # LC_ALL vince
        ({"LC_ALL": "C", "LANG": "it_IT.UTF-8"}, "it"),  # "C" non è una lingua
    ],
)
def test_system_locale_follows_posix_precedence(env, expected):
    assert i18n.system_locale(env) == expected


def test_normalize_accepts_windows_and_bcp47_names():
    assert i18n.normalize("Italian_Italy") == "it"
    assert i18n.normalize("en-GB") == "en"
    assert i18n.normalize("") is None
    assert i18n.normalize("ja_JP") is None


# -- da un'eccezione al messaggio per l'utente (§10.1) ------------------------

USER_ERRORS = [
    (UnsupportedFormatError("err.corrupt", name="a.wav"), ("danneggiato", "damaged")),
    (UnsupportedFormatError("err.drm", name="a.m4p"), ("DRM", "DRM")),
    (UnsupportedFormatError("err.unsupported", name="a.xyz"), ("Convertilo", "Convert")),
    (UnsupportedFormatError("err.ffmpeg_missing", name="a.m4a"), ("WAV", "WAV")),
    (TooLongError("err.too_long", name="a.wav", minutes=31), ("30 minuti", "30 minutes")),
    (NonFiniteAudioError("err.non_finite", name="a.wav"), ("NaN", "NaN")),
    (InsufficientDiskError("err.disk_precheck", folder="/x", needed=10, free=1),
     ("Libera spazio", "Free up space")),
    (OSError(errno.ENOSPC, "No space left on device"), ("Libera spazio", "Free up space")),
    (MemoryError(), ("Veloce", "Fast")),
    (RuntimeError("DefaultCPUAllocator: not enough memory"), ("Veloce", "Fast")),
    (BackendUnavailable("rete"), ("connessione", "internet connection")),
    (ValueError("boh"), ("diagnostica", "diagnostics")),
]


@pytest.mark.parametrize(("exc", "hints"), USER_ERRORS, ids=lambda v: type(v).__name__)
@pytest.mark.parametrize("lang", ["it", "en"])
def test_every_error_tells_what_to_do_in_the_right_language(exc, hints, lang, monkeypatch):
    monkeypatch.setenv(i18n.LOCALE_ENV, lang)
    message = user_message(exc)
    hint = hints[0] if lang == "it" else hints[1]
    assert hint in message, message
    assert "Traceback" not in message and "{" not in message
    other = catalog.EN if lang == "it" else catalog.IT
    assert message not in other.values(), "testo nella lingua sbagliata"


def test_windows_disk_full_codes_are_recognised():
    full = OSError(28, "disk full")
    assert is_disk_full(full)
    win = OSError(errno.EIO, "write error")
    win.winerror = 112  # ERROR_DISK_FULL
    assert is_disk_full(win)
    assert not is_disk_full(OSError(errno.EACCES, "denied"))
    assert not is_disk_full(RuntimeError("ENOSPC"))


def test_a_plain_runtime_error_is_not_out_of_memory(monkeypatch):
    monkeypatch.setenv(i18n.LOCALE_ENV, "it")
    assert user_message(RuntimeError("shape mismatch")) == i18n.t("err.generic")


def test_prepare_offline_message(monkeypatch):
    import urllib.error

    monkeypatch.setenv(i18n.LOCALE_ENV, "en")
    assert "internet" in prepare_message(urllib.error.URLError("no route"))
    wrapped = BackendUnavailable("x")
    wrapped.__cause__ = urllib.error.URLError("no route")
    assert "internet" in prepare_message(wrapped)


# -- la CLI sceglie la lingua (--lang o sistema) -----------------------------


def test_cli_lang_option_sets_the_process_locale(monkeypatch):
    from stemforge import cli

    monkeypatch.delenv(i18n.LOCALE_ENV, raising=False)
    args = cli.build_parser().parse_args(["x.wav", "--lang", "en"])
    assert cli.apply_language(args.lang) == "en"
    assert i18n.current_locale() == "en"


def test_cli_without_lang_follows_the_system(monkeypatch):
    import os

    from stemforge import cli

    # delenv prima: così monkeypatch ripristina la variabile a fine test
    monkeypatch.delenv(i18n.LOCALE_ENV, raising=False)
    monkeypatch.setattr(i18n, "system_locale", lambda env=None: "en")
    assert cli.apply_language(None) == "en"
    assert os.environ[i18n.LOCALE_ENV] == "en"


def test_cli_reports_missing_file_in_english(monkeypatch, tmp_path, capsys):
    from stemforge import cli

    monkeypatch.setenv(i18n.LOCALE_ENV, "it")
    code = cli.main([str(tmp_path / "manca.wav"), "--lang", "en"])
    err = capsys.readouterr().err
    assert code == 1
    assert "file not found" in err and "error summary" in err
