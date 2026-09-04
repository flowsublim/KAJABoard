"""Shared test helper for verifying legacy/smb_gas integrity across platforms."""

from __future__ import annotations

import hashlib
import pathlib

OFFICIAL_LEGACY_SMB_GAS_SHA256 = "66F614E4A728F3A7EB8811A39C58EB6F88B16BB4C554DFF96114C569FB6031C2"
OFFICIAL_LEGACY_SMB_GAS_FILE_COUNT = 50


def compute_legacy_smb_gas_aggregate_hash(
    root_path: str | pathlib.Path = "legacy/smb_gas",
    *,
    _force_lf: bool = False,
) -> tuple[int, str]:
    """Compute deterministic aggregate SHA-256 hash for legacy SMB GAS files.

    Normalizes working-tree files across platforms to match the official baseline
    evidence manifest convention:
    - Path sorting: case-insensitive part ordering matching WindowsPath and the manifest.
    - Text newline convention:
      - README.md uses LF (\\n).
      - All 49 legacy source files (.gs, .html, .txt) use CRLF (\\r\\n).
    """
    root = pathlib.Path(root_path)
    files = sorted(
        [f for f in root.rglob("*") if f.is_file()],
        key=lambda p: tuple(part.casefold() for part in p.parts),
    )
    lines: list[str] = []
    for f in files:
        rel_path = f.relative_to(root).as_posix()
        raw = f.read_bytes()
        if _force_lf:
            raw = raw.replace(b"\r\n", b"\n")
        if rel_path == "README.md":
            content = raw.replace(b"\r\n", b"\n")
        else:
            content = raw.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        file_bytes = len(content)
        file_sha256 = hashlib.sha256(content).hexdigest().upper()
        lines.append(f"{rel_path}|{file_bytes}|{file_sha256}")

    aggregate_input = "\n".join(lines).encode("utf-8")
    aggregate_hash = hashlib.sha256(aggregate_input).hexdigest().upper()
    return len(files), aggregate_hash


def verify_legacy_smb_gas_integrity(
    root_path: str | pathlib.Path = "legacy/smb_gas",
) -> None:
    """Assert that legacy/smb_gas has exactly 50 files and the official aggregate SHA-256."""
    file_count, aggregate_hash = compute_legacy_smb_gas_aggregate_hash(root_path)
    assert file_count == OFFICIAL_LEGACY_SMB_GAS_FILE_COUNT
    assert aggregate_hash == OFFICIAL_LEGACY_SMB_GAS_SHA256
