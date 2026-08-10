"""Processo figlio del test di annullamento: job lento con backend finto.

Lanciato da test_cancel.py con: python cancel_child.py <sorgente> <out_dir>.
Parla il protocollo vero su stdout, come il worker reale.
"""

from __future__ import annotations

import sys
from pathlib import Path

# il conftest del pacchetto test non è importabile da uno script figlio
sys.path.insert(0, str(Path(__file__).parent))
from conftest import FakeDemucs  # noqa: E402

from stemforge.model.job import SeparationJob  # noqa: E402
from stemforge.model.stem import StemKind  # noqa: E402
from stemforge.worker import protocol  # noqa: E402
from stemforge.worker.runner import run_job  # noqa: E402


def main() -> int:
    source, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    job = SeparationJob(
        source=source,
        wanted=(StemKind.VOCALS, StemKind.DRUMS),
        quality="balanced",
        out_dir=out_dir,
        device="cpu",
    )
    # ~0.6 s per chunk x 10 chunk: abbastanza lento da essere ucciso a metà
    fake = FakeDemucs(chunk_delay_s=0.6)
    cache = {("demucs4", "htdemucs_ft", "cpu", "balanced"): fake}

    def emit(message: protocol.Message) -> None:
        protocol.write_message(sys.stdout, message)

    run_job(job, emit, backends=cache)
    return 0


if __name__ == "__main__":
    sys.exit(main())
