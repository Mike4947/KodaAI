import os
from collections import Counter
from dataclasses import dataclass, field

import pathspec

from backend.config import settings

BUILTIN_IGNORES = [
    ".git",
    "node_modules",
    "dist",
    "build",
    ".next",
    "__pycache__",
    ".venv",
    "venv",
    ".tox",
    "coverage",
    ".pytest_cache",
    "target",
    "vendor",
    ".idea",
    ".vscode",
]

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".svg",
    ".woff", ".woff2", ".ttf", ".eot",
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
    ".exe", ".dll", ".so", ".dylib", ".bin",
    ".pdf", ".doc", ".docx",
    ".pyc", ".pyo", ".class", ".o", ".a",
    ".mp3", ".mp4", ".avi", ".mov", ".wav",
    ".db", ".sqlite", ".sqlite3",
    ".lock",  # large lockfiles still readable but skip binary locks
}

STACK_MARKERS = {
    "package.json": "Node.js",
    "pyproject.toml": "Python",
    "requirements.txt": "Python",
    "Cargo.toml": "Rust",
    "go.mod": "Go",
    "pom.xml": "Java/Maven",
    "build.gradle": "Java/Gradle",
    "Gemfile": "Ruby",
    "composer.json": "PHP",
    "Dockerfile": "Docker",
}


@dataclass
class FileEntry:
    path: str
    lines: int
    size: int


@dataclass
class RepoIndex:
    root: str
    files: list[FileEntry] = field(default_factory=list)
    extensions: Counter = field(default_factory=Counter)
    stacks: list[str] = field(default_factory=list)
    total_files: int = 0
    total_lines: int = 0

    def tree_summary(self, max_lines: int = 200) -> str:
        lines = [
            f"Repository root: {self.root}",
            f"Detected stacks: {', '.join(self.stacks) or 'unknown'}",
            f"Total files indexed: {self.total_files}",
            f"Total lines: {self.total_lines}",
            f"Top extensions: {', '.join(f'{ext}({c})' for ext, c in self.extensions.most_common(10))}",
            "",
            "File listing (path | lines):",
        ]
        for f in sorted(self.files, key=lambda x: x.path)[:500]:
            lines.append(f"  {f.path} ({f.lines} lines)")
        if len(self.files) > 500:
            lines.append(f"  ... and {len(self.files) - 500} more files")
        summary = "\n".join(lines)
        if len(summary.splitlines()) > max_lines:
            return "\n".join(summary.splitlines()[:max_lines]) + "\n... (truncated)"
        return summary


def _load_gitignore_spec(repo_root: str) -> pathspec.PathSpec | None:
    gitignore_path = os.path.join(repo_root, ".gitignore")
    if not os.path.isfile(gitignore_path):
        return None
    try:
        with open(gitignore_path, encoding="utf-8", errors="ignore") as f:
            return pathspec.PathSpec.from_lines("gitwildmatch", f)
    except OSError:
        return None


def _should_skip(rel_path: str, spec: pathspec.PathSpec | None) -> bool:
    parts = rel_path.replace("\\", "/").split("/")
    for part in parts:
        if part in BUILTIN_IGNORES:
            return True
    if spec and spec.match_file(rel_path.replace("\\", "/")):
        return True
    ext = os.path.splitext(rel_path)[1].lower()
    if ext in BINARY_EXTENSIONS:
        return True
    return False


def _count_lines(path: str) -> int:
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def index_repo(repo_root: str) -> RepoIndex:
    repo_root = os.path.abspath(repo_root)
    spec = _load_gitignore_spec(repo_root)
    index = RepoIndex(root=repo_root)

    for marker, stack in STACK_MARKERS.items():
        if os.path.isfile(os.path.join(repo_root, marker)):
            index.stacks.append(stack)

    for dirpath, dirnames, filenames in os.walk(repo_root):
        rel_dir = os.path.relpath(dirpath, repo_root)
        if rel_dir == ".":
            rel_dir = ""

        # Prune ignored directories in-place
        dirnames[:] = [
            d for d in dirnames
            if d not in BUILTIN_IGNORES
            and not (spec and spec.match_file(os.path.join(rel_dir, d).replace("\\", "/") + "/"))
        ]

        for filename in filenames:
            rel_path = os.path.join(rel_dir, filename) if rel_dir else filename
            rel_path = rel_path.replace("\\", "/")

            if _should_skip(rel_path, spec):
                continue

            full_path = os.path.join(dirpath, filename)
            try:
                size = os.path.getsize(full_path)
            except OSError:
                continue

            if size > settings.max_file_size_bytes:
                continue

            lines = _count_lines(full_path)
            ext = os.path.splitext(filename)[1].lower() or "(no ext)"
            index.extensions[ext] += 1
            index.files.append(FileEntry(path=rel_path, lines=lines, size=size))
            index.total_lines += lines

    index.total_files = len(index.files)
    return index
