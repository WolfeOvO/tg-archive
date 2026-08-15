"""Locate built frontend assets in source and container layouts."""

from pathlib import Path


def find_frontend_dist(module_dir: Path) -> Path:
    candidates = (
        module_dir / "frontend" / "dist",
        module_dir.parent / "frontend" / "dist",
    )
    return next((candidate for candidate in candidates if candidate.exists()), candidates[-1])
