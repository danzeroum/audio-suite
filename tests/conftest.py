"""Shared pytest fixtures and helpers."""

from __future__ import annotations

import sys
from pathlib import Path

# Increase recursion limit to avoid scipy/numpy recursion issues on CI
sys.setrecursionlimit(10000)

import numpy as np
import pytest

# Ensure the package is importable when running from the repo root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from audio_suite.decode import decode
from audio_suite.models import PCM

FIXTURES = ROOT / "tests" / "fixtures" / "generated"


def fixture_path(name: str) -> Path:
    return FIXTURES / name


def load_fixture(name: str) -> PCM:
    return decode(fixture_path(name))


@pytest.fixture
def sine_1k() -> PCM:
    return load_fixture("sine_1k_mono.wav")


@pytest.fixture
def sine_1k_stereo() -> PCM:
    return load_fixture("sine_1k_stereo.wav")


@pytest.fixture
def silence() -> PCM:
    return load_fixture("silence.wav")


@pytest.fixture
def clipped() -> PCM:
    return load_fixture("clipped.wav")


@pytest.fixture
def click_500ms() -> PCM:
    return load_fixture("click_500ms.wav")


@pytest.fixture
def dropout_50ms() -> PCM:
    return load_fixture("dropout_50ms.wav")


@pytest.fixture
def phase_inverted() -> PCM:
    return load_fixture("phase_inverted.wav")


@pytest.fixture
def louder_left() -> PCM:
    return load_fixture("louder_left.wav")


@pytest.fixture
def loop_clean() -> PCM:
    return load_fixture("loop_clean.wav")


@pytest.fixture
def loop_disc() -> PCM:
    return load_fixture("loop_discontinuous.wav")


@pytest.fixture
def white_noise() -> PCM:
    return load_fixture("white_noise.wav")


@pytest.fixture
def pink_noise() -> PCM:
    return load_fixture("pink_noise.wav")


@pytest.fixture
def speech_like() -> PCM:
    return load_fixture("speech_like.wav")


@pytest.fixture
def aliasing() -> PCM:
    return load_fixture("aliasing.wav")
