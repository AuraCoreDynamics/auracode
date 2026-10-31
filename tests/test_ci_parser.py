"""Tests for AuraCode CI workflow parser and matrix expansion."""

import tempfile
from pathlib import Path

import pytest
import yaml

from auracode.ci.parser import UnsupportedActionError, WorkflowParser


def test_parser_filters_release_and_publish_workflows() -> None:
    parser = WorkflowParser()
    assert not parser.is_test_or_build_workflow("release.yml", {"on": "push"})
    assert not parser.is_test_or_build_workflow("publish_pypi.yaml", {"on": "push"})
    assert not parser.is_test_or_build_workflow("deploy-prod.yml", {"on": "push"})
    assert parser.is_test_or_build_workflow("ci.yml", {"on": "push"})
    assert parser.is_test_or_build_workflow("test.yml", {"on": ["pull_request"]})


def test_pyyaml_on_release_in_ci_file_rejected() -> None:
    """A2.1: In YAML 1.1, unquoted 'on: release' parses as {True: 'release'}.

    Assert that a file named 'ci.yml' with 'on: release' is rejected.
    """
    raw_yaml = "name: Publish\non: release\njobs:\n  publish:\n    runs-on: ubuntu-latest\n"
    doc = yaml.safe_load(raw_yaml)
    assert doc.get("on") is None
    assert doc.get(True) == "release"

    parser = WorkflowParser()
    # Must reject despite the file name being ci.yml
    assert not parser.is_test_or_build_workflow("ci", doc)


def test_parser_parses_and_expands_matrix() -> None:
    yaml_content = """
name: CI
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ['3.12', '3.13']
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - name: Run Tests
        run: pytest tests/
"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        wf_file = Path(tmp_dir) / "ci.yml"
        wf_file.write_text(yaml_content, encoding="utf-8")

        parser = WorkflowParser()
        jobs = parser.parse_file(wf_file)

        assert len(jobs) == 2
        names = [j.name for j in jobs]
        assert "test (python-version=3.12)" in names
        assert "test (python-version=3.13)" in names

        # A2.2 Parity check: 3.12 and 3.13 cells MUST have different image digests
        job312 = next(j for j in jobs if "3.12" in j.name)
        job313 = next(j for j in jobs if "3.13" in j.name)
        assert job312.image_digest != job313.image_digest
        assert "python312" in job312.image_digest
        assert "python313" in job313.image_digest

        # Check step translation
        assert len(job312.steps) == 3
        assert job312.steps[0].name == "Checkout"
        assert "safe.directory" in job312.steps[0].run
        assert job312.steps[2].run == "pytest tests/"


def test_unsupported_action_raises_error() -> None:
    """A2.2: Unknown actions fail closed with UnsupportedActionError (NO echo shims)."""
    yaml_content = """
name: CI
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Unknown Action Step
        uses: some-thirdparty/unknown-action@v2
"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        wf_file = Path(tmp_dir) / "ci.yml"
        wf_file.write_text(yaml_content, encoding="utf-8")

        parser = WorkflowParser()
        with pytest.raises(UnsupportedActionError) as exc_info:
            parser.parse_file(wf_file)

        assert "some-thirdparty/unknown-action@v2" in str(exc_info.value)


def test_matrix_include_exclude() -> None:
    """A2.3: Verify matrix expansion handles include and exclude correctly."""
    yaml_content = """
name: Matrix
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest]
        python-version: ['3.12', '3.13']
        exclude:
          - os: macos-latest
            python-version: '3.12'
        include:
          - os: windows-latest
            python-version: '3.13'
    steps:
      - name: Run
        run: echo "OS=${{ matrix.os }} PY=${{ matrix.python-version }}"
"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        wf_file = Path(tmp_dir) / "ci.yml"
        wf_file.write_text(yaml_content, encoding="utf-8")

        parser = WorkflowParser()
        jobs = parser.parse_file(wf_file)

        # Total: (2 os * 2 py) - 1 exclude + 1 include = 4 jobs
        assert len(jobs) == 4
        # Excluded cell should not be present
        assert not any("macos-latest" in j.name and "3.12" in j.name for j in jobs)
        # Included cell should be present
        assert any("windows-latest" in j.name and "3.13" in j.name for j in jobs)


def test_parser_discovers_workflows_in_repo() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = Path(tmp_dir)
        wf_dir = repo / ".github" / "workflows"
        wf_dir.mkdir(parents=True)

        (wf_dir / "ci.yml").write_text("name: CI\non: push\njobs: {}", encoding="utf-8")
        (wf_dir / "test.yaml").write_text("name: Test\non: push\njobs: {}", encoding="utf-8")
        (wf_dir / "other.txt").write_text("ignore", encoding="utf-8")

        parser = WorkflowParser()
        discovered = parser.discover_workflows(repo)
        assert len(discovered) == 2
        file_names = [f.name for f in discovered]
        assert "ci.yml" in file_names
        assert "test.yaml" in file_names
