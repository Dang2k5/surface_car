from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from agent.graph.state import QCState

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def camera_evidence(state: QCState) -> list[dict[str, str]]:
    """Normalize legacy single-image state and the multi-camera API payload."""
    evidence = state.get("camera_evidence") or []
    if evidence:
        return [
            {
                "camera_id": str(item.get("camera_id") or "unknown_camera"),
                "image_url": str(item.get("image_url") or ""),
                "image_path": str(item.get("image_path") or ""),
            }
            for item in evidence
        ]
    image_paths = state.get("image_paths") or []
    return [{
        "camera_id": str(state.get("camera_id") or "unknown_camera"),
        "image_url": str(state.get("image_url") or ""),
        "image_path": str(image_paths[0]) if image_paths else "",
    }]


def resolve_image_source(image_path: str | None, image_url: str) -> str:
    if image_path:
        path = Path(image_path)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return str(path.resolve())

    parsed = urlparse(image_url)
    url_path = parsed.path
    static_roots = {"/assets/uploads/": PROJECT_ROOT / "data" / "uploads"}
    for prefix, root in static_roots.items():
        if url_path.startswith(prefix):
            candidate = (root / url_path.removeprefix(prefix)).resolve()
            if not candidate.is_relative_to(root.resolve()):
                raise ValueError("Image path escapes the configured evidence directory")
            return str(candidate)
    if parsed.scheme in {"http", "https"}:
        return image_url
    raise ValueError(f"Unsupported image source: {image_url}")


def primary_image_source(state: QCState) -> str:
    """Resolve the primary (first) camera's image source for single-image consumers."""
    evidence = camera_evidence(state)[0]
    return resolve_image_source(evidence["image_path"] or None, evidence["image_url"])


def resolve_local_path(source: str) -> Path | None:
    """Return a local filesystem Path for `source` if it is not a remote http(s) URL."""
    parsed = urlparse(source)
    if parsed.scheme in {"http", "https"}:
        return None
    return Path(source)


__all__: tuple[str, ...] = (
    "camera_evidence",
    "resolve_image_source",
    "primary_image_source",
    "resolve_local_path",
)
