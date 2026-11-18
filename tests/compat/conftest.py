"""Test di compatibilita' fra le due pile torch (BUILD_SPEC D7).

Girano identici con torch 2.2.2 (legacy-intel) e torch 2.10 (profili
moderni): ``pytest -m compat`` in entrambi gli ambienti. Fanno parte anche
del giro veloce. Il marker si registra qui e non in pyproject.toml: la
sezione pytest di pyproject appartiene a un'altra area.
"""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "compat: API torch/torchaudio usate dal motore, identiche fra torch 2.2.2 e 2.10 (D7)",
    )
