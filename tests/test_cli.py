"""Testes da CLI."""
import pytest
import subprocess
import json
import os

def test_cli_help():
    result = subprocess.run(
        ["python", "-m", "engine.cli", "--help"],
        capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "validate" in result.stdout

def test_cli_missing_args():
    result = subprocess.run(
        ["python", "-m", "engine.cli"],
        capture_output=True, text=True
    )
    assert result.returncode != 0
