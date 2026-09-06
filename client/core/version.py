"""Farabi tahta istemcisi semantic version information."""

VERSION = "0.2.0"


def major_version(version: str) -> int:
    """Return the MAJOR component of a strict MAJOR.MINOR.PATCH version."""
    parts = version.split(".")
    if len(parts) != 3 or not all(part.isdecimal() for part in parts):
        raise ValueError(f"Geçersiz semantic version: {version!r}")
    return int(parts[0])
