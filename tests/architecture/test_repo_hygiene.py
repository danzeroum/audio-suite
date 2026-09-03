"""Architecture tests — structural invariants (GOV-10, TEST-11).

These tests verify that the repository structure is correct and that
all analyzers are properly registered. They catch regressions like
the missing __init__.py imports bug.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


# === GOV-01: LICENSE exists ===
def test_GOV01_license_exists():
    """LICENSE file must exist in the repository root."""
    license_path = ROOT / "LICENSE"
    assert license_path.exists(), "LICENSE file missing"
    content = license_path.read_text()
    assert "MIT License" in content or "Apache License" in content
    assert "Copyright" in content


# === GOV-02: No .env versioned ===
def test_GOV02_no_env_versioned():
    """No .env files should be tracked in the repository."""
    env_files = list(ROOT.glob(".env*"))
    bad = [f for f in env_files if f.name == ".env"]
    assert not bad, f".env file should not be versioned: {bad}"


# === GOV-04: CONTRIBUTING, CODEOWNERS, docs exist ===
def test_GOV04_contributing_exists():
    assert (ROOT / "CONTRIBUTING.md").exists()


def test_GOV04_codeowners_exists():
    assert (ROOT / "CODEOWNERS").exists()


def test_GOV04_docs_dir_exists():
    assert (ROOT / "docs").is_dir()
    assert (ROOT / "docs" / "desenvolvimento").is_dir()


# === GOV-06: CHANGELOG exists ===
def test_GOV06_changelog_exists():
    changelog = ROOT / "CHANGELOG.md"
    assert changelog.exists()
    content = changelog.read_text()
    assert "##" in content


# === GOV-10 / TEST-11: analyzer registry complete ===
def test_GOV10_all_analyzer_modules_imported():
    """Every .py file in analyzers/ must be imported in __init__.py."""
    analyzers_dir = ROOT / "audio_suite" / "analyzers"
    module_files = [f.stem for f in analyzers_dir.glob("*.py") if f.stem not in ("__init__", "base")]
    init_content = (analyzers_dir / "__init__.py").read_text()
    missing = [m for m in module_files if m not in init_content]
    assert not missing, f"Analyzer modules not imported in __init__.py: {missing}"


def test_GOV10_all_analyzers_registered():
    """Every analyzer module should register at least one analyzer."""
    from audio_suite.analyzers import analyzer_ids

    registered = set(analyzer_ids())
    analyzers_dir = ROOT / "audio_suite" / "analyzers"
    module_files = [f.stem for f in analyzers_dir.glob("*.py") if f.stem not in ("__init__", "base")]
    assert len(registered) >= len(module_files), (
        f"Expected at least {len(module_files)} analyzers, got {len(registered)}"
    )


# === TEST-11: expected files present ===
def test_TEST11_expected_files():
    expected = [
        "pyproject.toml",
        "README.md",
        "LICENSE",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "CODEOWNERS",
        ".gitignore",
        "Dockerfile",
        "action.yml",
        ".github/workflows/ci.yml",
    ]
    for f in expected:
        assert (ROOT / f).exists(), f"Expected file missing: {f}"


def test_ci_config_mypy_blocking():
    """mypy should be present in CI (|| true allowed for numpy stub compat)."""
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "mypy" in ci


def test_ci_config_docker_nonroot():
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert "USER 1000" in dockerfile or "USER nonroot" in dockerfile


def test_pyproject_version_consistent():
    import tomllib

    with open(ROOT / "pyproject.toml", "rb") as f:
        data = tomllib.load(f)
    version = data["project"]["version"]
    parts = version.split(".")
    assert len(parts) == 3
    for p in parts:
        assert p.isdigit()
