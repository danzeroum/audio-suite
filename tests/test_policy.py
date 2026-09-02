"""Testes da policy engine."""
import pytest
from pathlib import Path
import tempfile
import os

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.policy import load_policy_profile, apply_policy

def test_apply_policy_pass():
    findings = [
        {"id": "X", "name": "x", "status": "pass", "severity": "info"}
    ]
    assert apply_policy(findings, {}) == "pass"

def test_apply_policy_fail():
    findings = [
        {"id": "X", "name": "x", "status": "fail", "severity": "error"}
    ]
    assert apply_policy(findings, {}) == "fail"

def test_apply_policy_indeterminate():
    findings = [
        {"id": "X", "name": "x", "status": "indeterminate", "severity": "info"}
    ]
    assert apply_policy(findings, {}) == "indeterminate"

def test_load_profile_valid():
    """Carrega um profile YAML mínimo válido."""
    yaml_content = """
name: test_profile
owner: test
description: test profile
checks:
  - id: X
    analyzer: loudness
    params: {}
    severity: info
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        path = Path(f.name)
    try:
        policy = load_policy_profile(path)
        assert policy["name"] == "test_profile"
        assert "_profile_sha256" in policy
    finally:
        os.unlink(path)
