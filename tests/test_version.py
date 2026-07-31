import tomllib
from pathlib import Path

import mnemos


def test_version_matches_pyproject() -> None:
    """The package version and the packaging metadata must not drift apart."""
    pyproject = Path(__file__).parent.parent / "pyproject.toml"
    with pyproject.open("rb") as handle:
        declared = tomllib.load(handle)["tool"]["poetry"]["version"]

    assert mnemos.__version__ == declared
