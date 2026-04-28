#!/usr/bin/env python3
"""Prepare the local ECG Images Dataset scaffold used by dl-service.

This helper creates the expected folder structure under `datasets/ecg-images/`
and can optionally copy images from an existing source directory that already
contains class subfolders.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}
DEFAULT_CLASSES = ["normal", "abnormal", "afib"]


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def dataset_root() -> Path:
    return project_root() / "datasets" / "ecg-images"


def normalize_class_name(name: str) -> str:
    normalized = name.strip().lower().replace("_", " ").replace("-", " ")
    return " ".join(normalized.split())


def ensure_structure(root: Path, class_names: list[str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for class_name in class_names:
        class_dir = root / class_name
        class_dir.mkdir(parents=True, exist_ok=True)
        gitkeep = class_dir / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.touch()

    readme = root / "README.md"
    if not readme.exists():
        readme.write_text(
            "# ECG Images Dataset\n\n"
            "Place ECG images in one folder per class. Default folders are:\n"
            "- normal\n"
            "- abnormal\n"
            "- afib\n\n"
            "Supported formats: PNG, JPG/JPEG, BMP, WEBP, TIFF.\n",
            encoding="utf-8",
        )


def copy_from_source(source_root: Path, target_root: Path) -> int:
    copied = 0
    if not source_root.exists() or not source_root.is_dir():
        return copied

    for class_dir in sorted(path for path in source_root.iterdir() if path.is_dir()):
        target_class = normalize_class_name(class_dir.name)
        if not target_class:
            continue

        destination_dir = target_root / target_class
        destination_dir.mkdir(parents=True, exist_ok=True)

        for image_path in sorted(class_dir.rglob("*")):
            if not image_path.is_file() or image_path.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
                continue
            destination = destination_dir / image_path.name
            shutil.copy2(image_path, destination)
            copied += 1

    return copied


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare ECG dataset folders for dl-service")
    parser.add_argument(
        "--source",
        type=Path,
        help="Optional source directory that already contains class subfolders",
    )
    parser.add_argument(
        "--classes",
        nargs="*",
        default=DEFAULT_CLASSES,
        help="Class folders to create under datasets/ecg-images",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    root = dataset_root()
    class_names = [normalize_class_name(name) for name in args.classes if normalize_class_name(name)]
    if not class_names:
        class_names = list(DEFAULT_CLASSES)

    ensure_structure(root, class_names)

    copied = 0
    if args.source:
        copied = copy_from_source(args.source, root)

    print(f"ECG dataset scaffold ready at {root}")
    print(f"Classes: {', '.join(class_names)}")
    print(f"Seeded files copied: {copied}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())