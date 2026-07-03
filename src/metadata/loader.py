"""
Metadata loader.

The loader is the only place in the codebase that knows how to find and
read a store's ``metadata.json``.  Everything else asks the loader.

Loading is two-stage:

  1. Read the file and parse it as a :class:`StoreMetadata` dataclass.
  2. Validate the parsed object against the schema rules (see
     :mod:`src.metadata.validator`).

A failure in either stage raises :class:`MetadataLoadError`.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from .schema import StoreMetadata
from .validator import (
    MetadataValidationError,
    ValidationIssue,
    validate_store_metadata,
)


logger = logging.getLogger(__name__)


# Default store folder is the env override, falling back to "brigade_road".
DEFAULT_STORE_DATASET = os.getenv("STORE_DATASET", "brigade_road")


class MetadataLoadError(RuntimeError):
    """Raised when a store's metadata cannot be loaded.

    Wraps both I/O errors and validation errors so callers can catch a
    single exception type.
    """

    def __init__(
        self,
        message: str,
        *,
        path: Optional[Path] = None,
        issues: Optional[list[ValidationIssue]] = None,
    ) -> None:
        super().__init__(message)
        self.path = path
        self.issues = issues or []

    def __str__(self) -> str:
        if not self.issues:
            return super().__str__()
        bullets = "\n".join(f"  - {issue}" for issue in self.issues)
        return f"{super().__str__()}\n{bullets}"


def resolve_metadata_path(
    data_dir: Path | str,
    store_id: Optional[str] = None,
) -> Path:
    """Return the absolute path to ``metadata.json`` for a store.

    Lookup order:

    1. ``data_dir/<store_id>/metadata.json``
    2. ``data_dir/store_metadata.json`` (legacy single-store shim)
    """

    data = Path(data_dir)
    if store_id:
        candidate = data / store_id / "metadata.json"
        if candidate.exists():
            return candidate

    legacy = data / "store_metadata.json"
    if legacy.exists():
        return legacy

    raise MetadataLoadError(
        f"No metadata.json found under {data} for store_id={store_id!r}. "
        f"Expected either {data / (store_id or '<store_id>') / 'metadata.json'} "
        f"or {legacy}."
    )


def load_store_metadata(
    data_dir: Path | str,
    store_id: Optional[str] = None,
    *,
    validate: bool = True,
    strict: bool = True,
    check_source_files: bool = True,
) -> StoreMetadata:
    """Load (and optionally validate) a store's metadata.

    Args:
        data_dir: Root data directory (e.g. ``.../data``).
        store_id: Store folder name.  Defaults to ``STORE_DATASET`` env
            or ``"brigade_road"``.
        validate: If true (default), structural validation runs and a
            bad file raises :class:`MetadataLoadError` with the list of
            issues.
        strict: If true (default), unknown roles/zone_types/keys fail
            validation.  If false, only missing required keys fail.

    Returns:
        A fully-populated :class:`StoreMetadata`.
    """

    data = Path(data_dir)
    if store_id is None:
        store_id = DEFAULT_STORE_DATASET

    metadata_path = resolve_metadata_path(data, store_id)

    try:
        raw = json.loads(metadata_path.read_text())
    except FileNotFoundError as exc:
        raise MetadataLoadError(
            f"Metadata file not found: {metadata_path}", path=metadata_path
        ) from exc
    except json.JSONDecodeError as exc:
        raise MetadataLoadError(
            f"Metadata file is not valid JSON ({metadata_path}): {exc.msg} "
            f"at line {exc.lineno} col {exc.colno}",
            path=metadata_path,
        ) from exc

    try:
        metadata = StoreMetadata.from_dict(raw)
    except (KeyError, ValueError, TypeError) as exc:
        raise MetadataLoadError(
            f"Metadata schema mismatch in {metadata_path}: {exc}",
            path=metadata_path,
        ) from exc

    if validate:
        # Use the resolved metadata file's parent directory for camera file checks.
        # This avoids mismatches when the store's internal store_id differs
        # from the folder name (e.g. store_metadata.json has ST1008 but lives
        # in the brigade_road/ folder).
        _data_dir: Path | None = metadata_path.parent if check_source_files else None
        issues = validate_store_metadata(metadata, strict=strict, data_dir=_data_dir)
        if issues:
            raise MetadataLoadError(
                f"Metadata validation failed for {metadata_path} "
                f"(store_id={metadata.store_id!r})",
                path=metadata_path,
                issues=issues,
            )

    logger.info(
        "loaded_store_metadata store_id=%s cameras=%d zones=%d path=%s",
        metadata.store_id,
        len(metadata.cameras),
        len(metadata.zones),
        metadata_path,
    )

    return metadata


def load_metadata_from_path(
    path: Path | str,
    *,
    validate: bool = True,
    strict: bool = True,
) -> StoreMetadata:
    """Load metadata from an explicit file path (no store_id resolution)."""

    p = Path(path)
    try:
        raw = json.loads(p.read_text())
    except json.JSONDecodeError as exc:
        raise MetadataLoadError(
            f"Metadata file is not valid JSON ({p}): {exc.msg} "
            f"at line {exc.lineno} col {exc.colno}",
            path=p,
        ) from exc

    metadata = StoreMetadata.from_dict(raw)
    if validate:
        issues = validate_store_metadata(metadata, strict=strict)
        if issues:
            raise MetadataLoadError(
                f"Metadata validation failed for {p}", path=p, issues=issues
            )
    return metadata
