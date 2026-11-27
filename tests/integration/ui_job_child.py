"""Worker finto per i test di reattività: pipeline vera, backend finto.

Lanciato dal WorkerBridge al posto del worker (test_ui_responsiveness.py):
legge il job da stdin e parla il protocollo vero su stdout, come runner.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

# il conftest del pacchetto test non è importabile da uno script figlio
sys.path.insert(0, str(Path(__file__).parent))
from conftest import FakeDemucs  # noqa: E402

from stemforge.model.job import SeparationJob  # noqa: E402
from stemforge.worker import protocol  # noqa: E402
from stemforge.worker.pipeline import run_job  # noqa: E402

CHUNK_DELAY_S = 0.05  # ~1 s di job: abbastanza avanzamento da osservare


def main() -> int:
    job = SeparationJob.from_json(sys.stdin.readline())
    fake = FakeDemucs(chunk_delay_s=CHUNK_DELAY_S)
    cache = {("demucs4", model, "cpu", job.quality): fake
             for model in ("htdemucs_ft", "htdemucs_6s")}
    run_job(job, lambda m: protocol.write_message(sys.stdout, m), backends=cache)
    return 0


if __name__ == "__main__":
    sys.exit(main())
