"""RAM disponibile e lunghezza dei blocchi (BUILD_SPEC §6.1 punto 3, §5.7 regola 6).

Una macchina da 4 GB non deve andare in swap: la lunghezza dei blocchi
si adatta alla RAM disponibile letta da engine/device.py. Qui la RAM è
finta e iniettata; la lettura vera si prova sulla piattaforma corrente.
"""

from __future__ import annotations

import ctypes
import os
import sys

import numpy as np
import pytest

from stemforge.engine import blocks, device

GB = 1_000_000_000
SR = 44100


# -- lettura della RAM ---------------------------------------------------------


MEMINFO = """MemTotal:        8048576 kB
MemFree:          512000 kB
MemAvailable:    3072000 kB
Buffers:          102400 kB
"""


def test_meminfo_uses_memavailable_not_memfree():
    # MemFree ignora la cache dei file che il kernel restituisce subito
    assert device.parse_meminfo(MEMINFO) == 3072000 * 1024
    assert device.parse_meminfo("MemTotal: 1 kB\n") is None
    assert device.parse_meminfo("MemAvailable: tanti kB\n") is None


def test_linux_reader_reads_the_given_meminfo(tmp_path):
    path = tmp_path / "meminfo"
    path.write_text(MEMINFO, encoding="ascii")
    assert device._linux_available(path) == 3072000 * 1024


class FakeLibc:
    """sysctlbyname come quello di macOS: scrive il valore nel buffer passato."""

    def __init__(self, values: dict[str, int]):
        self.values = values

    def sysctlbyname(self, name, value_ref, size_ref, new, new_size):
        key = name.decode()
        if key not in self.values:
            return -1
        value_ref._obj.value = self.values[key]
        return 0


PAGE = 4096
MAC_PAGES = {"vm.page_free_count": 100_000, "vm.page_speculative_count": 20_000,
             "vm.page_purgeable_count": 5_000, "vm.page_pageable_external_count": 75_000}


def test_macos_counts_free_speculative_purgeable_and_file_cache():
    libc = FakeLibc({"hw.pagesize": PAGE, **MAC_PAGES})
    assert device._macos_available(libc) == PAGE * sum(MAC_PAGES.values())


def test_macos_without_page_counters_assumes_half_of_the_ram():
    libc = FakeLibc({"hw.pagesize": PAGE, "hw.memsize": 8 * GB})
    assert device._macos_available(libc) == 4 * GB
    assert device._macos_available(FakeLibc({})) is None


@pytest.mark.parametrize("platform, expected", [
    ("win32", 1), ("darwin", 2), ("linux", 3), ("freebsd14", 3),
])
def test_each_platform_uses_its_reader(platform, expected):
    readers = {"win32": lambda: 1, "darwin": lambda: 2, "linux": lambda: 3}
    before = (sys.platform, os.name)
    assert device.available_memory_bytes(platform, readers) == expected
    assert (sys.platform, os.name) == before, "la piattaforma si inietta, non si cambia"


def _raises(exc: Exception):
    def reader():
        raise exc
    return reader


@pytest.mark.parametrize("reader", [
    _raises(OSError("niente /proc")), _raises(AttributeError("niente windll")),
    lambda: None, lambda: 0, lambda: -5,
])
def test_unreadable_ram_is_unknown_never_a_crash(reader):
    assert device.available_memory_bytes("linux", {"linux": reader}) is None


def test_real_reading_on_this_machine():
    # Windows: GlobalMemoryStatusEx via ctypes; macOS: sysctl; Linux: /proc
    value = device.available_memory_bytes()
    assert value is not None, f"RAM non leggibile su {sys.platform}"
    assert 64 * 1024 * 1024 < value < 16 * 1024**4


# -- lunghezza dei blocchi -------------------------------------------------------


def test_unknown_ram_keeps_the_historical_blocks():
    assert blocks.split_blocks(SR * 14 * 60, SR, None) == (blocks.Block(0, SR * 14 * 60, 0),)
    long = blocks.split_blocks(SR * 20 * 60, SR, None)
    assert all(b.end - b.start <= blocks.BLOCK_LENGTH_S * SR for b in long)
    assert len(long) == 5


def test_block_length_grows_with_ram_and_is_capped():
    lengths = [blocks.block_length_s(gb * GB) for gb in (0.5, 1, 2, 3, 4, 8, 64)]
    assert lengths == sorted(lengths), "più RAM, blocchi mai più corti"
    assert lengths[0] == blocks.MIN_BLOCK_S
    assert lengths[-1] == blocks.BLOCK_LENGTH_S


def test_block_fits_the_ram_it_was_sized_for():
    for available in (2 * GB, 3 * GB, 4 * GB, 6 * GB):
        seconds = blocks.block_length_s(available)
        if seconds == blocks.MIN_BLOCK_S:
            continue  # sotto il minimo non si scende: il modello stesso non ci sta
        peak = blocks.PASS_FIXED_BYTES + seconds * blocks.PASS_BYTES_PER_AUDIO_S
        assert peak <= available * blocks.RAM_FRACTION + 1
    assert blocks.block_length_s(6 * GB) > blocks.MIN_BLOCK_S


def test_a_4gb_machine_splits_even_a_short_song():
    # Mac mini con 4 GB: dopo sistema e modello restano ~1.5 GB
    available = int(1.5 * GB)
    song = SR * 6 * 60
    parts = blocks.split_blocks(song, SR, available)
    length = int(blocks.block_length_s(available) * SR)
    assert len(parts) > 1, "6 minuti non stanno in 1.5 GB in una passata sola"
    assert all(b.end - b.start <= length for b in parts)
    assert parts[0].start == 0 and parts[-1].end == song


def test_full_length_stems_come_first_on_a_4gb_mac():
    # Mac da 4 GB con 2.5 GB liberi: ~45 s di blocco a RAM nuda, ma in un
    # job vero di 20 min a 4 stem gli stem pieni (1.69 GB) lasciano il minimo
    available = int(2.5 * GB)
    assert 45 < blocks.block_length_s(available) < 46
    stems = blocks.output_bytes(4, 2, SR * 20 * 60)
    assert blocks.block_length_s(blocks.memory_for_blocks(available, stems)) == blocks.MIN_BLOCK_S


def test_plenty_of_ram_keeps_a_short_song_in_one_pass():
    assert len(blocks.split_blocks(SR * 6 * 60, SR, 32 * GB)) == 1


@pytest.mark.parametrize("available", [int(1.5 * GB), 3 * GB, None])
def test_ram_sized_blocks_still_sum_to_one(available):
    # §5.7 regola 6: le rampe complementari ricostruiscono esattamente
    rate = 1000  # i blocchi si contano in campioni: basta un sample rate basso
    rng = np.random.default_rng(seed=5)
    frames = rate * 16 * 60 + 123
    signal = rng.standard_normal((2, frames)).astype(np.float32)
    out = np.zeros_like(signal)
    parts = blocks.split_blocks(frames, rate, available)
    for block in parts:
        blocks.overlap_add(out, signal[:, block.start : block.end], block)
    assert len(parts) > 1
    assert np.max(np.abs(out - signal)) < 1e-6
