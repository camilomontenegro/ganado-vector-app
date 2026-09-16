"""Guards for F19: every dependency stays pinned to what production runs.

Unpinned, a routine deploy installs whatever was published that morning. That has
already happened here: chromadb silently rewrote the committed vector store's
on-disk format, and within a week of install seven packages — numpy among them —
differed between a developer machine and production.

These tests fail the moment a pin is loosened, two pin files disagree, the
constraints file stops being referenced, or the local environment drifts from the
pins it claims to use.
"""
import importlib.metadata
import re
from pathlib import Path

import pytest
from packaging.requirements import Requirement

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNTIME = REPO_ROOT / "api" / "requirements.txt"
CONSTRAINTS = REPO_ROOT / "api" / "constraints.txt"
DEV = REPO_ROOT / "requirements-dev.txt"


def _norm(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def _requirements(path):
    """Parse a requirements file, skipping comments, blanks and -r / -c lines."""
    reqs = []
    for raw in path.read_text().splitlines():
        line = raw.split(" #", 1)[0].strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        reqs.append(Requirement(line))
    return reqs


def _exact_version(req):
    specs = list(req.specifier)
    if len(specs) != 1 or specs[0].operator != "==":
        return None
    return specs[0].version


def _constraints():
    return {_norm(r.name): _exact_version(r) for r in _requirements(CONSTRAINTS)}


@pytest.mark.parametrize("path", [RUNTIME, DEV, CONSTRAINTS], ids=lambda p: p.name)
def test_every_dependency_is_pinned_exactly(path):
    loose = [str(r) for r in _requirements(path) if _exact_version(r) is None]
    assert not loose, f"{path.name} has unpinned or range-pinned entries: {loose}"


def test_runtime_requirements_reference_the_constraints_file():
    """Render runs `pip install -r api/requirements.txt` and nothing else. If this
    line goes, the constraints silently stop applying in production."""
    lines = [l.strip() for l in RUNTIME.read_text().splitlines()]
    assert "-c constraints.txt" in lines


def test_direct_pins_agree_with_constraints():
    """Two files pinning the same package to different versions makes pip fail to
    resolve — at deploy time, on Render. Catch it here instead."""
    constraints = _constraints()
    disagreements = [
        (r.name, _exact_version(r), constraints[_norm(r.name)])
        for r in _requirements(RUNTIME)
        if _norm(r.name) in constraints and _exact_version(r) != constraints[_norm(r.name)]
    ]
    assert not disagreements, f"requirements.txt and constraints.txt disagree: {disagreements}"


def test_installed_environment_matches_the_pins():
    """A green test run means little if it ran against different versions than
    production. Every pinned package that is installed must be the pinned version.
    Fix with: pip install -r requirements-dev.txt"""
    expected = _constraints()
    for req in _requirements(RUNTIME) + _requirements(DEV):
        if req.marker is None or req.marker.evaluate():
            expected[_norm(req.name)] = _exact_version(req)

    installed = {
        _norm(d.metadata["Name"]): d.version for d in importlib.metadata.distributions()
    }
    drift = {
        name: {"pinned": version, "installed": installed[name]}
        for name, version in expected.items()
        if name in installed and installed[name] != version
    }
    assert not drift, f"installed versions differ from the pins: {drift}"
