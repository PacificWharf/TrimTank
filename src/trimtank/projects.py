"""Project and filesystem helpers for TrimTank."""

from __future__ import annotations

import json
import os
import string
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MANIFEST_FILENAME = "manifest.json"
MANIFEST_SCHEMA = "trimtank.project"
MANIFEST_SCHEMA_VERSION = 1


INVALID_FOLDER_NAME_CHARACTERS = set('<>:"/\\|?*')


def get_filesystem_roots() -> list[dict[str, str]]:
    candidates: list[tuple[str, Path]] = []

    if os.name == "nt":
        for letter in string.ascii_uppercase:
            drive = Path(f"{letter}:\\")
            if drive.exists():
                candidates.append((f"{letter}:\\", drive))
    else:
        candidates.append(("/", Path("/")))

    home = Path.home()
    if home.exists():
        candidates.append(("Home", home))

    current = Path.cwd()
    if current.exists():
        candidates.append(("Current folder", current))

    roots: list[dict[str, str]] = []
    seen: set[str] = set()
    for name, path in candidates:
        normalized = _path_key(path)
        if normalized in seen:
            continue
        seen.add(normalized)
        roots.append({"name": name, "path": str(_resolve_path(path))})

    return roots


def browse_directory(path: str | None = None) -> dict[str, Any]:
    target = _resolve_existing_directory(path)
    directories: list[dict[str, str]] = []

    for entry in target.iterdir():
        try:
            if not entry.is_dir():
                continue
        except OSError:
            continue

        directories.append({"name": entry.name, "path": str(_resolve_path(entry))})

    directories.sort(key=lambda item: item["name"].casefold())
    parent = target.parent if target.parent != target else None

    return {
        "path": str(target),
        "parent": str(parent) if parent is not None else None,
        "directories": directories,
    }


def create_directory(parent_path: str, name: str) -> Path:
    parent = _resolve_existing_directory(parent_path)
    folder_name = _validate_folder_name(name)
    target = parent / folder_name

    if target.exists():
        raise FileExistsError(f"Folder already exists: {target}")

    target.mkdir()
    return _resolve_path(target)


def inspect_project(path: str) -> dict[str, Any]:
    target = _resolve_path(_path_from_input(path))
    manifest_path = target / MANIFEST_FILENAME

    exists = target.exists()
    is_directory = target.is_dir() if exists else False
    can_create = False
    can_open = False
    project: dict[str, Any] | None = None
    manifest = {
        "status": "missing",
        "path": str(manifest_path),
        "detail": "No manifest.json file was found.",
    }

    if exists and not is_directory:
        manifest["detail"] = "The selected path is not a folder."
    elif not exists:
        parent = target.parent
        can_create = parent.exists() and parent.is_dir()
        if can_create:
            manifest["detail"] = "The folder does not exist yet."
        else:
            manifest["detail"] = "The parent folder does not exist."
    elif manifest_path.exists():
        manifest = _read_manifest_summary(manifest_path)
        if manifest["status"] == "valid":
            can_open = True
            project = manifest.get("project")
    else:
        can_create = True

    return {
        "path": str(target),
        "exists": exists,
        "is_directory": is_directory,
        "manifest": manifest,
        "project": project,
        "can_open": can_open,
        "can_create": can_create,
    }


def create_project(path: str, name: str | None = None) -> dict[str, Any]:
    target = _resolve_path(_path_from_input(path))

    if target.exists() and not target.is_dir():
        raise NotADirectoryError(f"Path is not a folder: {target}")

    if not target.exists():
        parent = target.parent
        if not parent.exists() or not parent.is_dir():
            raise FileNotFoundError(f"Parent folder does not exist: {parent}")
        target.mkdir()

    manifest_path = target / MANIFEST_FILENAME
    if manifest_path.exists():
        raise FileExistsError(f"Manifest already exists: {manifest_path}")

    manifest = _new_manifest(target, name)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return open_project(str(target))


def open_project(path: str) -> dict[str, Any]:
    inspected = inspect_project(path)
    if not inspected["can_open"]:
        status = inspected["manifest"]["status"]
        raise ValueError(f"Folder is not a valid TrimTank project: {status}")

    return {
        "path": inspected["path"],
        "manifest": inspected["manifest"],
        "project": inspected["project"],
    }


def _new_manifest(path: Path, name: str | None) -> dict[str, Any]:
    timestamp = _utc_now()
    project_name = name.strip() if name and name.strip() else path.name
    if not project_name:
        project_name = "TrimTank Project"

    return {
        "schema": MANIFEST_SCHEMA,
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "created_at": timestamp,
        "updated_at": timestamp,
        "project": {
            "name": project_name,
        },
        "sources": {},
        "outputs": {},
    }


def _read_manifest_summary(manifest_path: Path) -> dict[str, Any]:
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "status": "invalid",
            "path": str(manifest_path),
            "detail": f"manifest.json is not valid JSON: {exc.msg}",
        }
    except OSError as exc:
        return {
            "status": "unreadable",
            "path": str(manifest_path),
            "detail": str(exc),
        }

    errors = _validate_manifest(data)
    if errors:
        return {
            "status": "invalid",
            "path": str(manifest_path),
            "detail": " ".join(errors),
        }

    project = data["project"]
    return {
        "status": "valid",
        "path": str(manifest_path),
        "detail": "Valid TrimTank project manifest.",
        "schema": data["schema"],
        "schema_version": data["schema_version"],
        "project": {
            "name": project.get("name") or manifest_path.parent.name,
        },
    }


def _validate_manifest(data: Any) -> list[str]:
    if not isinstance(data, dict):
        return ["manifest.json must contain a JSON object."]

    errors: list[str] = []
    if data.get("schema") != MANIFEST_SCHEMA:
        errors.append(f"schema must be {MANIFEST_SCHEMA!r}.")
    if data.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        errors.append(f"schema_version must be {MANIFEST_SCHEMA_VERSION}.")
    if not isinstance(data.get("project"), dict):
        errors.append("project must be an object.")

    return errors


def _path_from_input(path: str) -> Path:
    if not path or not path.strip():
        raise ValueError("A folder path is required.")
    return Path(path.strip()).expanduser()


def _resolve_existing_directory(path: str | None) -> Path:
    target = _resolve_path(_path_from_input(path) if path and path.strip() else Path.home())

    if not target.exists():
        raise FileNotFoundError(f"Folder does not exist: {target}")
    if not target.is_dir():
        raise NotADirectoryError(f"Path is not a folder: {target}")

    return target


def _resolve_path(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _path_key(path: Path) -> str:
    value = str(_resolve_path(path))
    return value.casefold() if os.name == "nt" else value


def _validate_folder_name(name: str) -> str:
    folder_name = name.strip()
    if not folder_name:
        raise ValueError("Folder name is required.")
    if folder_name in {".", ".."}:
        raise ValueError("Folder name cannot be . or ..")
    if any(character in INVALID_FOLDER_NAME_CHARACTERS for character in folder_name):
        raise ValueError("Folder name contains invalid characters.")

    return folder_name


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

