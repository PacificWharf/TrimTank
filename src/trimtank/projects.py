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
INPUTS_DIRNAME = "inputs"
TRAINING_DIRNAME = "training"
CHECKPOINTS_DIRNAME = "checkpoints"
PROJECT_DIRECTORIES = (INPUTS_DIRNAME, TRAINING_DIRNAME, CHECKPOINTS_DIRNAME)
SUPPORTED_IMAGE_EXTENSIONS = (".bmp", ".gif", ".jpeg", ".jpg", ".png", ".webp")
REVIEW_STATUSES = ("keep", "reject", "duplicate", "unsure")
UNREVIEWED_STATUS = "unreviewed"
IMAGE_STATUSES = (UNREVIEWED_STATUS, *REVIEW_STATUSES)


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
    folders = _project_folder_summary(target) if is_directory else {}
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
            missing_folders = _missing_project_directories(folders)
            if missing_folders:
                names = ", ".join(missing_folders)
                manifest["detail"] = f"Missing required project folders: {names}."
            else:
                can_open = True
                project = manifest.get("project")
    else:
        can_create = True

    return {
        "path": str(target),
        "exists": exists,
        "is_directory": is_directory,
        "folders": folders,
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

    _ensure_project_directories(target)
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
        "folders": inspected["folders"],
        "manifest": inspected["manifest"],
        "project": inspected["project"],
    }


def list_project_images(path: str) -> dict[str, Any]:
    project = open_project(path)
    project_path = Path(project["path"])
    manifest = _read_manifest(project_path / MANIFEST_FILENAME)
    inputs_path = project_path / INPUTS_DIRNAME

    images: list[dict[str, Any]] = []
    for entry in sorted(inputs_path.iterdir(), key=lambda item: item.name.casefold()):
        if not _is_supported_image(entry):
            continue

        record = manifest["training"].get(entry.name, {})
        status = _record_status(record)
        images.append(
            {
                "filename": entry.name,
                "status": status,
                "size": entry.stat().st_size,
            }
        )

    return {
        "project": project,
        "inputs_path": str(inputs_path),
        "images": images,
        "statuses": {
            "default": UNREVIEWED_STATUS,
            "review": list(REVIEW_STATUSES),
            "all": list(IMAGE_STATUSES),
        },
        "counts": _status_counts(images),
    }


def update_image_status(path: str, filename: str, status: str) -> dict[str, Any]:
    normalized_status = status.strip().casefold()
    if normalized_status not in IMAGE_STATUSES:
        allowed = ", ".join(IMAGE_STATUSES)
        raise ValueError(f"Status must be one of: {allowed}.")

    project = open_project(path)
    project_path = Path(project["path"])
    source_path = get_source_image_path(str(project_path), filename)
    manifest_path = project_path / MANIFEST_FILENAME
    manifest = _read_manifest(manifest_path)
    training = manifest["training"]
    record = training.get(source_path.name)

    if normalized_status == UNREVIEWED_STATUS:
        if record is None:
            pass
        elif not isinstance(record, dict):
            raise ValueError(f"Training record for {source_path.name} must be an object.")
        else:
            record.pop("status", None)
            if not record:
                training.pop(source_path.name)
    else:
        if record is None:
            record = {}
            training[source_path.name] = record
        elif not isinstance(record, dict):
            raise ValueError(f"Training record for {source_path.name} must be an object.")

        record["status"] = normalized_status

    manifest["updated_at"] = _utc_now()
    _write_manifest(manifest_path, manifest)

    return {
        "filename": source_path.name,
        "status": _record_status(training.get(source_path.name, {})),
        "counts": list_project_images(str(project_path))["counts"],
    }


def get_source_image_path(path: str, filename: str) -> Path:
    project = open_project(path)
    project_path = Path(project["path"])
    safe_filename = _validate_source_filename(filename)
    source_path = project_path / INPUTS_DIRNAME / safe_filename

    if not source_path.exists():
        raise FileNotFoundError(f"Source image does not exist: {safe_filename}")
    if not source_path.is_file() or not _is_supported_image(source_path):
        raise ValueError(f"Source file is not a supported image: {safe_filename}")

    return source_path


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
        "training": {},
    }


def _read_manifest_summary(manifest_path: Path) -> dict[str, Any]:
    try:
        data = _read_manifest(manifest_path)
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
    except ValueError as exc:
        return {
            "status": "invalid",
            "path": str(manifest_path),
            "detail": str(exc),
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
    if not isinstance(data.get("training"), dict):
        errors.append("training must be an object.")

    return errors


def _read_manifest(manifest_path: Path) -> dict[str, Any]:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors = _validate_manifest(data)
    if errors:
        raise ValueError(" ".join(errors))

    return data


def _write_manifest(manifest_path: Path, data: dict[str, Any]) -> None:
    errors = _validate_manifest(data)
    if errors:
        raise ValueError(" ".join(errors))

    temporary_path = manifest_path.with_suffix(f"{manifest_path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(manifest_path)


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


def _validate_source_filename(filename: str) -> str:
    source_filename = filename.strip()
    if not source_filename:
        raise ValueError("Source filename is required.")
    if source_filename in {".", ".."}:
        raise ValueError("Source filename cannot be . or ..")
    if Path(source_filename).name != source_filename:
        raise ValueError("Source filename must not include a folder path.")
    if "/" in source_filename or "\\" in source_filename:
        raise ValueError("Source filename must not include a folder path.")

    return source_filename


def _is_supported_image(path: Path) -> bool:
    try:
        return path.is_file() and path.suffix.casefold() in SUPPORTED_IMAGE_EXTENSIONS
    except OSError:
        return False


def _record_status(record: Any) -> str:
    if isinstance(record, dict):
        status = record.get("status")
        if isinstance(status, str) and status in REVIEW_STATUSES:
            return status

    return UNREVIEWED_STATUS


def _status_counts(images: list[dict[str, Any]]) -> dict[str, int]:
    counts = {status: 0 for status in IMAGE_STATUSES}
    counts["total"] = len(images)

    for image in images:
        status = image.get("status")
        if status in counts:
            counts[status] += 1

    return counts


def _ensure_project_directories(path: Path) -> None:
    for dirname in PROJECT_DIRECTORIES:
        directory = path / dirname
        if directory.exists() and not directory.is_dir():
            raise NotADirectoryError(f"Project path is not a folder: {directory}")
        directory.mkdir(exist_ok=True)


def _project_folder_summary(path: Path) -> dict[str, dict[str, object]]:
    folders: dict[str, dict[str, object]] = {}
    for dirname in PROJECT_DIRECTORIES:
        directory = path / dirname
        folders[dirname] = {
            "path": str(directory),
            "exists": directory.exists(),
            "is_directory": directory.is_dir() if directory.exists() else False,
        }

    return folders


def _missing_project_directories(folders: dict[str, dict[str, object]]) -> list[str]:
    return [
        dirname
        for dirname in PROJECT_DIRECTORIES
        if not folders.get(dirname, {}).get("is_directory")
    ]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
