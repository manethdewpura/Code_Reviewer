from __future__ import annotations

from pathlib import Path


DEFAULT_EXTENSIONS: set[str] = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".go",
    ".cs",
    ".php",
    ".rb",
    ".rs",
    ".sql",
    ".sh",
}


def list_project_files(project_root: str, *, extensions: set[str] | None = None) -> list[str]:
    """List source files under a project folder.

    Args:
        project_root: Root directory to scan.
        extensions: File extensions to include (defaults to common source extensions).

    Returns:
        Sorted list of absolute file paths (as strings).
    """
    root = Path(project_root).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"Project root not found or not a directory: {root}")

    exts = extensions or DEFAULT_EXTENSIONS
    files: list[str] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in exts:
            continue
        if any(part in {".git", ".venv", "node_modules", "dist", "build", "__pycache__"} for part in p.parts):
            continue
        files.append(str(p))

    return sorted(files)


def read_code_file(path: str, *, max_chars: int = 200_000) -> str:
    """Reads source code from file.

    Args:
        path: Absolute or relative file path.
        max_chars: Hard cap to keep prompts/tooling safe.

    Returns:
        File content as UTF-8 (errors replaced).
    """
    p = Path(path).expanduser().resolve()
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(f"File not found: {p}")
    data = p.read_text(encoding="utf-8", errors="replace")
    return data[:max_chars]

