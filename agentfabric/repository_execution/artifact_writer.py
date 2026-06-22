"""Contained, approval-gated artifact writer."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path, PurePosixPath


def validate_relative_path(value: str) -> None:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"unsafe artifact path: {value}")


class ArtifactWriter:
    def __init__(self, output_root: Path) -> None:
        self.output_root = output_root.resolve()

    def write(self, repository_name: str, files: dict[str, str]) -> dict[str, str]:
        validate_relative_path(repository_name)
        destination = (self.output_root / repository_name).resolve()
        if self.output_root not in destination.parents:
            raise ValueError("repository destination escapes output root")
        hashes: dict[str, str] = {}
        written: list[Path] = []
        try:
            for relative_path, content in sorted(files.items()):
                validate_relative_path(relative_path)
                target = (destination / relative_path).resolve()
                if destination != target and destination not in target.parents:
                    raise ValueError("artifact path escapes repository destination")
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    if target.read_text(encoding="utf-8") != content:
                        raise FileExistsError(f"refusing to overwrite divergent artifact: {relative_path}")
                    hashes[relative_path] = sha256(content.encode()).hexdigest()
                    continue
                target.write_text(content, encoding="utf-8")
                written.append(target)
                hashes[relative_path] = sha256(content.encode()).hexdigest()
        except Exception:
            for target in reversed(written):
                target.unlink(missing_ok=True)
            raise
        return hashes

    def rollback(self, repository_name: str, relative_paths: tuple[str, ...]) -> list[str]:
        destination = (self.output_root / repository_name).resolve()
        removed: list[str] = []
        for relative_path in sorted(relative_paths, reverse=True):
            validate_relative_path(relative_path)
            target = (destination / relative_path).resolve()
            if destination not in target.parents:
                raise ValueError("rollback path escapes repository destination")
            if target.is_file():
                target.unlink()
                removed.append(relative_path)
        for directory in sorted((item for item in destination.rglob("*") if item.is_dir()), reverse=True):
            if not any(directory.iterdir()):
                directory.rmdir()
        if destination.exists() and not any(destination.iterdir()):
            destination.rmdir()
        return removed
