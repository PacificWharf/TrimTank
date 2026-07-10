"""Project and filesystem helpers for TrimTank."""

from __future__ import annotations

import json
import math
import os
import shutil
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
TRAINING_CONFIG_FILENAME = "kohya_dataset.toml"
DEFAULT_TRAINING_SETTINGS = {
    "trigger_token": "",
    "num_repeats": 10,
    "enable_bucket": True,
    "resolution": 1024,
    "min_bucket_reso": 256,
    "max_bucket_reso": 2048,
    "bucket_reso_steps": 64,
}


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

    project_path = Path(inspected["path"])
    manifest = _read_manifest(project_path / MANIFEST_FILENAME)

    return {
        "path": inspected["path"],
        "folders": inspected["folders"],
        "manifest": inspected["manifest"],
        "project": inspected["project"],
        "settings": _manifest_settings(manifest),
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
        crop = _record_crop(record)
        images.append(
            {
                "filename": entry.name,
                "status": status,
                "size": entry.stat().st_size,
                "crop": crop,
                "has_crop": crop is not None,
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


def update_image_crop(path: str, filename: str, crop: Any | None) -> dict[str, Any]:
    project = open_project(path)
    project_path = Path(project["path"])
    source_path = get_source_image_path(str(project_path), filename)
    manifest_path = project_path / MANIFEST_FILENAME
    manifest = _read_manifest(manifest_path)
    training = manifest["training"]
    record = training.get(source_path.name)

    if crop is None:
        if record is None:
            pass
        elif not isinstance(record, dict):
            raise ValueError(f"Training record for {source_path.name} must be an object.")
        else:
            record.pop("crop", None)
            if not record:
                training.pop(source_path.name)
    else:
        normalized_crop = _normalize_crop(crop)
        if record is None:
            record = {}
            training[source_path.name] = record
        elif not isinstance(record, dict):
            raise ValueError(f"Training record for {source_path.name} must be an object.")

        record["crop"] = normalized_crop

    manifest["updated_at"] = _utc_now()
    _write_manifest(manifest_path, manifest)
    saved_crop = _record_crop(training.get(source_path.name, {}))

    return {
        "filename": source_path.name,
        "crop": saved_crop,
        "has_crop": saved_crop is not None,
    }


def update_project_settings(path: str, settings: Any) -> dict[str, Any]:
    project = open_project(path)
    project_path = Path(project["path"])
    manifest_path = project_path / MANIFEST_FILENAME
    manifest = _read_manifest(manifest_path)
    manifest["settings"] = _normalize_training_settings(settings)
    manifest["updated_at"] = _utc_now()
    _write_manifest(manifest_path, manifest)

    return {
        "path": str(project_path),
        "settings": manifest["settings"],
        "buckets": get_project_bucket_stats(str(project_path)),
    }


def get_project_bucket_stats(path: str) -> dict[str, Any]:
    project = open_project(path)
    project_path = Path(project["path"])
    manifest = _read_manifest(project_path / MANIFEST_FILENAME)
    settings = _manifest_settings(manifest)
    buckets: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    considered = 0

    for item in _kept_training_items(project_path, manifest):
        if not item["source_path"].exists() or not _is_supported_image(item["source_path"]):
            warnings.append(f"{item['filename']}: source image is missing or unsupported.")
            continue

        dimensions = _training_item_dimensions(item)
        if dimensions is None:
            try:
                dimensions = _source_image_dimensions(item["source_path"])
            except Exception as exc:
                warnings.append(f"{item['filename']}: {exc}")
                continue

        considered += 1
        bucket = _bucket_for_dimensions(dimensions["width"], dimensions["height"], settings)
        bucket_key = f"{bucket['width']}x{bucket['height']}"
        if bucket_key not in buckets:
            buckets[bucket_key] = {
                "width": bucket["width"],
                "height": bucket["height"],
                "count": 0,
                "images": [],
            }
        buckets[bucket_key]["count"] += 1
        buckets[bucket_key]["images"].append(
            {
                "filename": item["filename"],
                "width": dimensions["width"],
                "height": dimensions["height"],
                "uses_crop": item["crop"] is not None,
            }
        )

    bucket_list = sorted(
        buckets.values(),
        key=lambda item: (item["width"] * item["height"], item["width"], item["height"]),
    )

    return {
        "path": str(project_path),
        "settings": settings,
        "total_images": considered,
        "bucket_count": len(bucket_list),
        "buckets": bucket_list,
        "warnings": warnings,
    }


def prepare_training(path: str, confirm_clear_training: bool = False) -> dict[str, Any]:
    if not confirm_clear_training:
        raise ValueError("Preparing training files requires confirmation.")

    project = open_project(path)
    project_path = Path(project["path"])
    training_path = project_path / TRAINING_DIRNAME
    manifest_path = project_path / MANIFEST_FILENAME
    manifest = _read_manifest(manifest_path)
    settings = _manifest_settings(manifest)
    trigger_token = settings["trigger_token"].strip()
    if not trigger_token:
        raise ValueError("A trigger token is required before preparing training files.")

    _require_pillow()
    _clear_directory_contents(training_path)
    _clear_prepared_records(manifest)

    generated: list[dict[str, Any]] = []
    warnings: list[str] = []

    for item in _kept_training_items(project_path, manifest):
        record = manifest["training"][item["filename"]]
        caption = _record_caption(record, trigger_token)
        record["caption"] = caption
        try:
            prepared = _prepare_training_item(
                item=item,
                output_index=len(generated) + 1,
                training_path=training_path,
                caption=caption,
                settings=settings,
            )
        except Exception as exc:
            warnings.append(f"{item['filename']}: {exc}")
            continue

        record["prepared"] = {
            "image": prepared["image"],
            "caption": prepared["caption"],
            "source": item["filename"],
            "width": prepared["width"],
            "height": prepared["height"],
            "uses_crop": item["crop"] is not None,
        }
        generated.append(prepared)

    config_path = training_path / TRAINING_CONFIG_FILENAME
    config_path.write_text(_kohya_config_text(training_path, settings), encoding="utf-8")

    manifest["settings"] = settings
    manifest["prepared_at"] = _utc_now()
    manifest["updated_at"] = manifest["prepared_at"]
    _write_manifest(manifest_path, manifest)
    bucket_stats = get_project_bucket_stats(str(project_path))

    return {
        "path": str(project_path),
        "training_path": str(training_path),
        "count": len(generated),
        "generated": generated,
        "config": TRAINING_CONFIG_FILENAME,
        "buckets": bucket_stats,
        "warnings": warnings,
    }


def list_training_outputs(path: str) -> dict[str, Any]:
    project = open_project(path)
    project_path = Path(project["path"])
    training_path = project_path / TRAINING_DIRNAME
    manifest = _read_manifest(project_path / MANIFEST_FILENAME)
    prepared_entries = _prepared_record_entries_by_image(manifest)
    outputs: list[dict[str, Any]] = []

    for image_path in sorted(training_path.glob("*.png"), key=lambda item: item.name.casefold()):
        caption_path = image_path.with_suffix(".txt")
        file_caption = (
            _normalize_caption(caption_path.read_text(encoding="utf-8"))
            if caption_path.exists()
            else ""
        )
        prepared_entry = prepared_entries.get(image_path.name)
        source = prepared_entry["source"] if prepared_entry else ""
        record = prepared_entry["record"] if prepared_entry else {}
        caption = _record_caption(record, file_caption)
        outputs.append(
            {
                "filename": image_path.name,
                "caption_filename": caption_path.name,
                "source": source,
                "caption": caption,
                "size": image_path.stat().st_size,
            }
        )

    config_path = training_path / TRAINING_CONFIG_FILENAME
    return {
        "project": project,
        "training_path": str(training_path),
        "config": {
            "filename": TRAINING_CONFIG_FILENAME,
            "exists": config_path.exists(),
            "content": config_path.read_text(encoding="utf-8") if config_path.exists() else "",
        },
        "outputs": outputs,
    }


def validate_training_handoff(path: str) -> dict[str, Any]:
    project = open_project(path)
    project_path = Path(project["path"])
    training_path = project_path / TRAINING_DIRNAME
    config_path = training_path / TRAINING_CONFIG_FILENAME
    manifest = _read_manifest(project_path / MANIFEST_FILENAME)
    settings = _manifest_settings(manifest)
    prepared_entries = _prepared_record_entries_by_image(manifest)
    png_files = {
        image_path.name: image_path
        for image_path in sorted(training_path.glob("*.png"), key=lambda item: item.name.casefold())
    }
    txt_files = {
        caption_path.name: caption_path
        for caption_path in sorted(training_path.glob("*.txt"), key=lambda item: item.name.casefold())
    }
    issues: list[dict[str, str]] = []

    def add_issue(
        check: str,
        level: str,
        message: str,
        filename: str = "",
        source: str = "",
    ) -> None:
        issue = {
            "check": check,
            "level": level,
            "message": message,
        }
        if filename:
            issue["filename"] = filename
        if source:
            issue["source"] = source
        issues.append(issue)

    if not png_files:
        add_issue("files", "error", "No prepared PNG images were found in the training folder.")

    expected_images = set(prepared_entries)
    actual_images = set(png_files)
    for filename in sorted(expected_images - actual_images, key=str.casefold):
        entry = prepared_entries[filename]
        add_issue(
            "manifest",
            "error",
            "Manifest prepared record points to a missing PNG file.",
            filename=filename,
            source=entry["source"],
        )

    for filename in sorted(actual_images - expected_images, key=str.casefold):
        add_issue(
            "manifest",
            "error",
            "Prepared PNG file is not recorded in the manifest.",
            filename=filename,
        )

    for filename, image_path in png_files.items():
        caption_path = image_path.with_suffix(".txt")
        if not caption_path.exists():
            add_issue(
                "captions",
                "error",
                "Prepared PNG does not have a matching TXT caption file.",
                filename=filename,
            )
            continue

        file_caption = _normalize_caption(caption_path.read_text(encoding="utf-8"))
        entry = prepared_entries.get(filename)
        if entry is None:
            effective_caption = file_caption
            source = ""
        else:
            source = entry["source"]
            manifest_caption = _record_caption(entry["record"], "")
            effective_caption = manifest_caption or file_caption
            if manifest_caption and file_caption != manifest_caption:
                add_issue(
                    "captions",
                    "error",
                    "TXT caption does not match the manifest caption.",
                    filename=caption_path.name,
                    source=source,
                )

        if not effective_caption:
            add_issue(
                "captions",
                "error",
                "Caption is empty.",
                filename=caption_path.name,
                source=source,
            )
        elif settings["trigger_token"] and settings["trigger_token"] not in effective_caption:
            add_issue(
                "captions",
                "warn",
                "Caption does not include the trigger token.",
                filename=caption_path.name,
                source=source,
            )

    for filename in sorted(txt_files, key=str.casefold):
        expected_image = Path(filename).with_suffix(".png").name
        if expected_image not in png_files:
            add_issue(
                "captions",
                "warn",
                "TXT caption file does not have a matching prepared PNG.",
                filename=filename,
            )

    dimension_checked = 0
    try:
        Image, _ImageOps = _pillow_modules()
    except RuntimeError as exc:
        add_issue("dimensions", "error", str(exc))
    else:
        for filename, image_path in png_files.items():
            try:
                with Image.open(image_path) as image:
                    image.load()
                    width, height = image.size
            except Exception as exc:
                add_issue(
                    "dimensions",
                    "error",
                    f"Could not read prepared PNG dimensions: {exc}",
                    filename=filename,
                )
                continue

            dimension_checked += 1
            bucket = _bucket_for_dimensions(width, height, settings)
            if width != bucket["width"] or height != bucket["height"]:
                add_issue(
                    "dimensions",
                    "error",
                    f"Image is {width} x {height}, expected bucket {bucket['width']} x {bucket['height']}.",
                    filename=filename,
                )

            step = settings["bucket_reso_steps"]
            if width % step or height % step:
                add_issue(
                    "dimensions",
                    "error",
                    f"Image dimensions are not multiples of bucket step {step}.",
                    filename=filename,
                )

            entry = prepared_entries.get(filename)
            if entry is not None:
                prepared = entry["prepared"]
                prepared_width = prepared.get("width")
                prepared_height = prepared.get("height")
                if prepared_width != width or prepared_height != height:
                    add_issue(
                        "manifest",
                        "error",
                        (
                            f"Manifest records {prepared_width} x {prepared_height}, "
                            f"but PNG is {width} x {height}."
                        ),
                        filename=filename,
                        source=entry["source"],
                    )

    if not config_path.exists():
        add_issue("config", "error", "Kohya dataset config is missing.", filename=TRAINING_CONFIG_FILENAME)
    else:
        current_config = config_path.read_text(encoding="utf-8")
        expected_config = _kohya_config_text(training_path, settings)
        for issue in _config_mismatch_issues(current_config, expected_config):
            add_issue(
                "config",
                "error",
                issue,
                filename=TRAINING_CONFIG_FILENAME,
            )

    checks = [
        _validation_check(
            "files",
            "Prepared files",
            f"{len(png_files)} PNG files in training folder.",
            issues,
        ),
        _validation_check(
            "manifest",
            "Manifest mappings",
            f"{len(prepared_entries)} prepared records in manifest.",
            issues,
        ),
        _validation_check(
            "captions",
            "Caption pairs",
            f"{len(txt_files)} TXT caption files in training folder.",
            issues,
        ),
        _validation_check(
            "dimensions",
            "Bucket dimensions",
            f"{dimension_checked} prepared images checked.",
            issues,
        ),
        _validation_check(
            "config",
            "Kohya dataset config",
            TRAINING_CONFIG_FILENAME,
            issues,
        ),
    ]
    issue_counts = _validation_issue_counts(issues)

    return {
        "path": str(project_path),
        "training_path": str(training_path),
        "config_path": str(config_path),
        "status": "ready" if issue_counts["error"] == 0 else "blocked",
        "settings": settings,
        "image_count": len(png_files),
        "prepared_count": len(prepared_entries),
        "caption_count": len(txt_files),
        "checks": checks,
        "issues": issues,
        "issue_counts": issue_counts,
        "kohya": {
            "dataset_config": str(config_path),
            "dataset_config_arg": f"--dataset_config {_quote_command_arg(str(config_path))}",
        },
    }


def get_training_image_path(path: str, filename: str) -> Path:
    project = open_project(path)
    project_path = Path(project["path"])
    safe_filename = _validate_source_filename(filename)
    if Path(safe_filename).suffix.casefold() != ".png":
        raise ValueError("Training image filename must end in .png.")

    image_path = project_path / TRAINING_DIRNAME / safe_filename
    if not image_path.exists():
        raise FileNotFoundError(f"Training image does not exist: {safe_filename}")
    if not image_path.is_file():
        raise ValueError(f"Training path is not a file: {safe_filename}")

    return image_path


def update_training_caption(path: str, filename: str, caption: str) -> dict[str, Any]:
    project = open_project(path)
    project_path = Path(project["path"])
    safe_filename = _validate_source_filename(filename)
    if Path(safe_filename).suffix.casefold() != ".png":
        raise ValueError("Training image filename must end in .png.")

    training_path = project_path / TRAINING_DIRNAME
    manifest_path = project_path / MANIFEST_FILENAME
    manifest = _read_manifest(manifest_path)
    prepared_entries = _prepared_record_entries_by_image(manifest)
    prepared_entry = prepared_entries.get(safe_filename)
    if prepared_entry is None:
        raise ValueError(f"Prepared image is not recorded in the manifest: {safe_filename}")

    normalized_caption = _normalize_caption(caption)
    record = prepared_entry["record"]
    record["caption"] = normalized_caption

    prepared = prepared_entry["prepared"]
    caption_filename = prepared.get("caption")
    if isinstance(caption_filename, str) and caption_filename.strip():
        safe_caption_filename = _validate_source_filename(caption_filename)
    else:
        safe_caption_filename = Path(safe_filename).with_suffix(".txt").name
    if Path(safe_caption_filename).suffix.casefold() != ".txt":
        raise ValueError("Prepared caption filename must end in .txt.")

    caption_path = training_path / safe_caption_filename
    caption_file_updated = False
    if caption_path.exists():
        caption_path.write_text(_caption_file_text(normalized_caption), encoding="utf-8")
        caption_file_updated = True

    manifest["updated_at"] = _utc_now()
    _write_manifest(manifest_path, manifest)

    return {
        "filename": safe_filename,
        "source": prepared_entry["source"],
        "caption_filename": safe_caption_filename,
        "caption": normalized_caption,
        "caption_file_updated": caption_file_updated,
    }


def upscale_training_outputs(path: str, confirm_overwrite: bool = False) -> dict[str, Any]:
    if not confirm_overwrite:
        raise ValueError("Upscaling training files requires confirmation.")

    project = open_project(path)
    project_path = Path(project["path"])
    training_path = project_path / TRAINING_DIRNAME
    manifest_path = project_path / MANIFEST_FILENAME
    manifest = _read_manifest(manifest_path)
    settings = _manifest_settings(manifest)
    prepared_records = _prepared_records_by_image(manifest)
    _require_pillow()

    changed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    warnings: list[str] = []

    for image_path in sorted(training_path.glob("*.png"), key=lambda item: item.name.casefold()):
        try:
            result = _upscale_training_image(image_path, settings)
        except Exception as exc:
            warnings.append(f"{image_path.name}: {exc}")
            continue

        if result["changed"]:
            prepared_record = prepared_records.get(image_path.name)
            if prepared_record is not None:
                prepared_record["width"] = result["new_width"]
                prepared_record["height"] = result["new_height"]
            changed.append(result)
        else:
            skipped.append(result)

    manifest["updated_at"] = _utc_now()
    _write_manifest(manifest_path, manifest)

    return {
        "path": str(project_path),
        "training_path": str(training_path),
        "changed_count": len(changed),
        "skipped_count": len(skipped),
        "changed": changed,
        "skipped": skipped,
        "warnings": warnings,
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


def _manifest_settings(manifest: dict[str, Any]) -> dict[str, Any]:
    return _normalize_training_settings(manifest.get("settings", {}))


def _normalize_training_settings(settings: Any) -> dict[str, Any]:
    source = settings if isinstance(settings, dict) else {}
    normalized = dict(DEFAULT_TRAINING_SETTINGS)
    normalized["trigger_token"] = str(source.get("trigger_token", "")).strip()
    normalized["num_repeats"] = _settings_int(source, "num_repeats", 10, 1, 1000)
    normalized["enable_bucket"] = bool(source.get("enable_bucket", True))
    normalized["resolution"] = _settings_int(source, "resolution", 1024, 64, 4096)
    normalized["min_bucket_reso"] = _settings_int(source, "min_bucket_reso", 256, 64, 4096)
    normalized["max_bucket_reso"] = _settings_int(source, "max_bucket_reso", 2048, 64, 4096)
    normalized["bucket_reso_steps"] = _settings_int(source, "bucket_reso_steps", 64, 1, 512)

    if normalized["min_bucket_reso"] > normalized["max_bucket_reso"]:
        raise ValueError("Minimum bucket resolution must be less than or equal to maximum.")

    step = normalized["bucket_reso_steps"]
    normalized["min_bucket_reso"] = max(
        step,
        normalized["min_bucket_reso"] - normalized["min_bucket_reso"] % step,
    )
    if normalized["max_bucket_reso"] % step:
        normalized["max_bucket_reso"] += step - normalized["max_bucket_reso"] % step

    if normalized["enable_bucket"] and normalized["min_bucket_reso"] > normalized["resolution"]:
        raise ValueError("Minimum bucket resolution must be less than or equal to target resolution.")
    if normalized["enable_bucket"] and normalized["max_bucket_reso"] < normalized["resolution"]:
        raise ValueError("Maximum bucket resolution must be greater than or equal to target resolution.")

    return normalized


def _settings_int(
    settings: dict[str, Any],
    key: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    value = settings.get(key, default)
    if isinstance(value, bool):
        raise ValueError(f"{key} must be a number.")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be a number.") from exc

    if number < minimum or number > maximum:
        raise ValueError(f"{key} must be between {minimum} and {maximum}.")

    return number


def _kept_training_items(project_path: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    training = manifest.get("training", {})
    if not isinstance(training, dict):
        return items

    for filename, record in sorted(training.items(), key=lambda item: item[0].casefold()):
        if _record_status(record) != "keep":
            continue

        try:
            safe_filename = _validate_source_filename(filename)
        except ValueError:
            continue

        items.append(
            {
                "filename": safe_filename,
                "record": record,
                "crop": _record_crop(record),
                "source_path": project_path / INPUTS_DIRNAME / safe_filename,
            }
        )

    return items


def _training_item_dimensions(item: dict[str, Any]) -> dict[str, int] | None:
    crop = item.get("crop")
    if not crop:
        return None

    return {
        "width": crop["width"],
        "height": crop["height"],
    }


def _source_image_dimensions(source_path: Path) -> dict[str, int]:
    Image, ImageOps = _pillow_modules()
    with Image.open(source_path) as image:
        image = ImageOps.exif_transpose(image)
        width, height = image.size

    return {"width": width, "height": height}


def _bucket_for_dimensions(width: int, height: int, settings: dict[str, Any]) -> dict[str, int]:
    resolution = settings["resolution"]
    if not settings["enable_bucket"]:
        return {"width": resolution, "height": resolution}

    exact_resolution = (width, height)
    bucket_resolutions = _bucket_resolutions(settings)
    if exact_resolution in set(bucket_resolutions):
        return {"width": width, "height": height}

    aspect_ratio = width / height
    bucket_width, bucket_height = min(
        bucket_resolutions,
        key=lambda size: abs((size[0] / size[1]) - aspect_ratio),
    )

    return {
        "width": bucket_width,
        "height": bucket_height,
    }


def _bucket_resolutions(settings: dict[str, Any]) -> list[tuple[int, int]]:
    resolution = settings["resolution"]
    step = settings["bucket_reso_steps"]
    min_resolution = settings["min_bucket_reso"]
    max_resolution = settings["max_bucket_reso"]
    target_area = resolution * resolution
    resolutions: set[tuple[int, int]] = set()
    square_resolution = int(math.sqrt(target_area) // step) * step
    if square_resolution > 0:
        resolutions.add((square_resolution, square_resolution))

    bucket_width = min_resolution
    while bucket_width <= max_resolution:
        bucket_height = min(
            max_resolution,
            int((target_area // bucket_width) // step) * step,
        )
        if bucket_height >= min_resolution:
            resolutions.add((bucket_width, bucket_height))
            resolutions.add((bucket_height, bucket_width))
        bucket_width += step

    return sorted(resolutions) or [(resolution, resolution)]


def _prepare_training_item(
    item: dict[str, Any],
    output_index: int,
    training_path: Path,
    caption: str,
    settings: dict[str, Any],
) -> dict[str, Any]:
    Image, ImageOps = _pillow_modules()
    source_path = item["source_path"]
    if not source_path.exists():
        raise FileNotFoundError("Source image does not exist.")
    if not _is_supported_image(source_path):
        raise ValueError("Source file is not a supported image.")

    with Image.open(source_path) as source_image:
        image = ImageOps.exif_transpose(source_image)
        image.load()
        crop = item["crop"]
        if crop is not None:
            _validate_crop_within_image(crop, image.width, image.height)
            image = image.crop(
                (
                    crop["x"],
                    crop["y"],
                    crop["x"] + crop["width"],
                    crop["y"] + crop["height"],
                )
            )

        bucket = _bucket_for_dimensions(image.width, image.height, settings)
        output = _resize_to_exact_bucket(image, bucket, Image)
        image_name = f"{output_index:03d}.png"
        caption_name = f"{output_index:03d}.txt"
        output.save(training_path / image_name, format="PNG")
        (training_path / caption_name).write_text(_caption_file_text(caption), encoding="utf-8")

    return {
        "source": item["filename"],
        "image": image_name,
        "caption": caption_name,
        "width": output.width,
        "height": output.height,
    }


def _upscale_training_image(image_path: Path, settings: dict[str, Any]) -> dict[str, Any]:
    Image, _ImageOps = _pillow_modules()
    with Image.open(image_path) as source_image:
        source_image.load()
        width, height = source_image.size
        bucket = _bucket_for_dimensions(width, height, settings)

        result = {
            "filename": image_path.name,
            "old_width": width,
            "old_height": height,
            "new_width": width,
            "new_height": height,
            "bucket_width": bucket["width"],
            "bucket_height": bucket["height"],
            "changed": False,
        }

        if width == bucket["width"] and height == bucket["height"]:
            return result

        output = _resize_to_exact_bucket(source_image, bucket, Image)
        output.save(image_path, format="PNG")
        result["new_width"] = bucket["width"]
        result["new_height"] = bucket["height"]
        result["changed"] = True
        return result


def _resize_to_exact_bucket(image: Any, bucket: dict[str, int], Image: Any) -> Any:
    target_width = bucket["width"]
    target_height = bucket["height"]
    output = image.convert("RGB")
    if output.width == target_width and output.height == target_height:
        return output

    scale = max(target_width / output.width, target_height / output.height)
    resized_width = max(target_width, math.ceil(output.width * scale))
    resized_height = max(target_height, math.ceil(output.height * scale))
    output = output.resize(
        (resized_width, resized_height),
        resample=_lanczos_resampling(Image),
    )
    left = max(0, (resized_width - target_width) // 2)
    top = max(0, (resized_height - target_height) // 2)
    return output.crop((left, top, left + target_width, top + target_height))


def _lanczos_resampling(Image: Any) -> Any:
    return getattr(getattr(Image, "Resampling", Image), "LANCZOS")


def _prepared_records_by_image(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        filename: entry["prepared"]
        for filename, entry in _prepared_record_entries_by_image(manifest).items()
    }


def _prepared_record_entries_by_image(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    training = manifest.get("training", {})
    if not isinstance(training, dict):
        return records

    for source, record in training.items():
        if not isinstance(record, dict):
            continue

        prepared = record.get("prepared")
        if isinstance(prepared, dict) and isinstance(prepared.get("image"), str):
            records[prepared["image"]] = {
                "source": source,
                "record": record,
                "prepared": prepared,
            }

    return records


def _validation_check(
    check_id: str,
    label: str,
    detail: str,
    issues: list[dict[str, str]],
) -> dict[str, str]:
    related = [issue for issue in issues if issue["check"] == check_id]
    if any(issue["level"] == "error" for issue in related):
        status = "error"
    elif any(issue["level"] == "warn" for issue in related):
        status = "warn"
    else:
        status = "ok"

    return {
        "id": check_id,
        "label": label,
        "status": status,
        "detail": detail,
    }


def _validation_issue_counts(issues: list[dict[str, str]]) -> dict[str, int]:
    counts = {
        "error": 0,
        "warn": 0,
    }
    for issue in issues:
        level = issue.get("level")
        if level in counts:
            counts[level] += 1

    return counts


def _config_mismatch_issues(current_config: str, expected_config: str) -> list[str]:
    current_lines = _normalized_config_lines(current_config)
    expected_lines = _normalized_config_lines(expected_config)
    if current_lines == expected_lines:
        return []

    issues: list[str] = []
    max_lines = max(len(current_lines), len(expected_lines))
    for index in range(max_lines):
        current_line = current_lines[index] if index < len(current_lines) else "<missing>"
        expected_line = expected_lines[index] if index < len(expected_lines) else "<missing>"
        if current_line == expected_line:
            continue

        issues.append(
            (
                f"Config line {index + 1} differs. Expected {expected_line!r}, "
                f"found {current_line!r}. Run Prepare for Training to regenerate."
            )
        )
        if len(issues) >= 6:
            remaining = sum(
                1
                for remaining_index in range(index + 1, max_lines)
                if (
                    current_lines[remaining_index]
                    if remaining_index < len(current_lines)
                    else "<missing>"
                )
                != (
                    expected_lines[remaining_index]
                    if remaining_index < len(expected_lines)
                    else "<missing>"
                )
            )
            if remaining:
                issues.append(f"{remaining} additional config differences not shown.")
            break

    return issues


def _normalized_config_lines(config_text: str) -> list[str]:
    return [line.rstrip() for line in config_text.strip().splitlines()]


def _quote_command_arg(value: str) -> str:
    return f'"{value.replace(chr(34), chr(92) + chr(34))}"'


def _validate_crop_within_image(crop: dict[str, int], width: int, height: int) -> None:
    if crop["x"] + crop["width"] > width or crop["y"] + crop["height"] > height:
        raise ValueError("Crop rectangle extends outside the source image.")


def _clear_directory_contents(path: Path) -> None:
    path.mkdir(exist_ok=True)
    for entry in path.iterdir():
        if entry.is_symlink() or entry.is_file():
            entry.unlink()
        elif entry.is_dir():
            shutil.rmtree(entry)


def _clear_prepared_records(manifest: dict[str, Any]) -> None:
    training = manifest.get("training", {})
    if not isinstance(training, dict):
        return

    for record in training.values():
        if isinstance(record, dict):
            record.pop("prepared", None)


def _kohya_config_text(training_path: Path, settings: dict[str, Any]) -> str:
    return "\n".join(
        [
            "[general]",
            'caption_extension = ".txt"',
            f"enable_bucket = {_toml_bool(settings['enable_bucket'])}",
            "bucket_no_upscale = false",
            f"bucket_reso_steps = {settings['bucket_reso_steps']}",
            f"min_bucket_reso = {settings['min_bucket_reso']}",
            f"max_bucket_reso = {settings['max_bucket_reso']}",
            'resize_interpolation = "lanczos"',
            "random_crop = false",
            "",
            "[[datasets]]",
            f"resolution = [{settings['resolution']}, {settings['resolution']}]",
            "batch_size = 1",
            "",
            "  [[datasets.subsets]]",
            f"  image_dir = {_toml_string(str(training_path))}",
            f"  num_repeats = {settings['num_repeats']}",
            f"  class_tokens = {_toml_string(settings['trigger_token'])}",
            "",
        ]
    )


def _toml_bool(value: bool) -> str:
    return "true" if value else "false"


def _toml_string(value: str) -> str:
    return json.dumps(value)


def _require_pillow() -> None:
    _pillow_modules()


def _pillow_modules() -> tuple[Any, Any]:
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:
        raise RuntimeError(
            "Pillow is required for image preparation. Install project dependencies first."
        ) from exc

    return Image, ImageOps


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
        "settings": dict(DEFAULT_TRAINING_SETTINGS),
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


def _record_crop(record: Any) -> dict[str, int] | None:
    if not isinstance(record, dict) or "crop" not in record:
        return None

    try:
        return _normalize_crop(record["crop"])
    except ValueError:
        return None


def _record_caption(record: Any, default_caption: str = "") -> str:
    if isinstance(record, dict) and "caption" in record:
        caption = record.get("caption")
        if isinstance(caption, str):
            return _normalize_caption(caption)

    return _normalize_caption(default_caption)


def _normalize_caption(caption: str) -> str:
    if not isinstance(caption, str):
        raise ValueError("Caption must be text.")

    return caption.replace("\r\n", "\n").replace("\r", "\n").strip()


def _caption_file_text(caption: str) -> str:
    normalized_caption = _normalize_caption(caption)
    if not normalized_caption:
        return ""

    return f"{normalized_caption}\n"


def _normalize_crop(crop: Any) -> dict[str, int]:
    if not isinstance(crop, dict):
        raise ValueError("Crop must be an object.")

    normalized: dict[str, int] = {}
    for key in ("x", "y", "width", "height"):
        value = crop.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Crop {key} must be a number.")
        if not math.isfinite(value):
            raise ValueError(f"Crop {key} must be finite.")
        normalized[key] = round(value)

    if normalized["x"] < 0 or normalized["y"] < 0:
        raise ValueError("Crop x and y must be zero or greater.")
    if normalized["width"] <= 0 or normalized["height"] <= 0:
        raise ValueError("Crop width and height must be greater than zero.")

    return normalized


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
