"""Tests: policy engine (extensão para cobertura)."""
from __future__ import annotations

from pathlib import Path

import pytest

from engine.policy import (
    apply_policy,
    load_lockfile,
    load_policy_profile,
    register_profile_in_lockfile,
    save_lockfile,
)


class TestApplyPolicyExtended:
    def test_pass_when_no_findings(self):
        assert apply_policy([], {}) == "pass"

    def test_fail_dominates_warning(self):
        findings = [
            {"status": "warning", "severity": "warning"},
            {"status": "fail", "severity": "error"},
        ]
        assert apply_policy(findings, {}) == "fail"

    def test_warning_when_only_warning(self):
        findings = [{"status": "warning", "severity": "warning"}]
        assert apply_policy(findings, {}) == "warning"

    def test_indeterminate_takes_precedence_over_warning(self):
        findings = [
            {"status": "warning", "severity": "warning"},
            {"status": "indeterminate", "severity": "error"},
        ]
        assert apply_policy(findings, {}) == "indeterminate"

    def test_needs_review_takes_precedence_over_warning(self):
        findings = [
            {"status": "warning", "severity": "warning"},
            {"status": "needs_review", "severity": "info"},
        ]
        assert apply_policy(findings, {}) == "needs_review"

    def test_pass_with_info_severity_and_pass_status(self):
        findings = [{"status": "pass", "severity": "info"}]
        assert apply_policy(findings, {}) == "pass"

    def test_not_applicable_treated_as_pass(self):
        findings = [{"status": "not_applicable", "severity": "info"}]
        assert apply_policy(findings, {}) == "pass"

    def test_fail_with_severity_warning_still_fails(self):
        """Mesmo com severity warning, status=fail → fail."""
        findings = [{"status": "fail", "severity": "error"}]
        assert apply_policy(findings, {}) == "fail"


class TestLoadPolicyProfileExtended:
    def test_loads_checks_field(self, tmp_path: Path):
        yaml_content = """
name: test_v1
owner: test
description: test
checks:
  - id: AC-01
    analyzer: loudness
    params: {target_integrated_lufs: -23.0, tolerance_lufs: 0.5}
    severity: error
  - id: AC-02
    analyzer: signal
    params: {max_true_peak_dbtp: -1.0}
    severity: error
decision_policy:
  fail_on: error
"""
        path = tmp_path / "test_v1.yaml"
        path.write_text(yaml_content)
        policy = load_policy_profile(path)
        assert len(policy["checks"]) == 2
        assert policy["checks"][0]["id"] == "AC-01"
        assert policy["_profile_sha256"] is not None
        assert policy["_profile_path"] == str(path)

    def test_empty_checks_allowed(self, tmp_path: Path):
        yaml_content = "name: empty_v1\nowner: test\ndescription: empty\nchecks: []\n"
        path = tmp_path / "empty_v1.yaml"
        path.write_text(yaml_content)
        policy = load_policy_profile(path)
        assert policy["checks"] == []

    def test_invalid_yaml_raises(self, tmp_path: Path):
        import yaml as _yaml
        path = tmp_path / "bad.yaml"
        path.write_text("not: valid: yaml: {{{")
        # yaml.scanner.ScannerError é o erro esperado para YAML malformado
        with pytest.raises(_yaml.YAMLError):
            load_policy_profile(path)

    def test_profile_not_dict_raises(self, tmp_path: Path):
        path = tmp_path / "list.yaml"
        path.write_text("- item1\n- item2\n")
        with pytest.raises(ValueError, match="objeto"):
            load_policy_profile(path)


class TestLockfileExtended:
    def test_save_and_load_lockfile(self, tmp_path: Path, monkeypatch):
        lockfile = tmp_path / "lock.yaml"
        monkeypatch.setattr("engine.policy.LOCKFILE_PATH", lockfile)

        entries = {"test_v1": "abc123", "test_v2": "def456"}
        save_lockfile(entries)

        loaded = load_lockfile()
        assert loaded == entries

    def test_load_nonexistent_returns_empty(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("engine.policy.LOCKFILE_PATH", tmp_path / "nope.yaml")
        assert load_lockfile() == {}

    def test_load_invalid_yaml_returns_empty(self, tmp_path: Path, monkeypatch):
        lockfile = tmp_path / "lock.yaml"
        lockfile.write_text("not valid yaml {{{")
        monkeypatch.setattr("engine.policy.LOCKFILE_PATH", lockfile)
        assert load_lockfile() == {}

    def test_register_multiple_profiles(self, tmp_path: Path, monkeypatch):
        lockfile = tmp_path / "lock.yaml"
        monkeypatch.setattr("engine.policy.LOCKFILE_PATH", lockfile)

        for name in ["a_v1", "b_v1", "c_v1"]:
            yaml_content = f"name: {name}\nowner: test\ndescription: test\nchecks: []\n"
            path = tmp_path / f"{name}.yaml"
            path.write_text(yaml_content)
            register_profile_in_lockfile(path)

        loaded = load_lockfile()
        assert set(loaded.keys()) == {"a_v1", "b_v1", "c_v1"}
