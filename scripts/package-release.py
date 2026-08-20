import argparse
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).parents[1]
RELEASE_METADATA = {
    "product": "AIShop Hermes Workbench",
    "version": "0.1.0-alpha",
    "license": "AGPL-3.0-only",
    "source_url": "https://github.com/atyunfeng/aishop-hermes-workbench",
}
INCLUDE_ROOTS = (
    ".github",
    ".gitignore",
    "CHANGELOG.md",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "NOTICE",
    "PRIVACY.md",
    "README.md",
    "SECURITY.md",
    "THIRD_PARTY_NOTICES.md",
    "TRADEMARKS.md",
    "pyproject.toml",
    "uv.lock",
    "package.json",
    "package-lock.json",
    "hermes-plugin",
    "desktop-plugin",
    "android-worker",
    "packages",
    "tests",
    "demo-video",
    "docs/demo-runbook.md",
    "docs/real-device-validation.md",
    "scripts",
    "artifacts/aishop-worker-debug.apk",
)
EXCLUDED_PARTS = {
    ".gradle",
    ".kotlin",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "node_modules",
}
EXCLUDED_SUFFIXES = {".pyc", ".db", ".db-shm", ".db-wal"}
ZIP_TIMESTAMP = (2026, 8, 20, 0, 0, 0)


def release_files() -> list[Path]:
    files: list[Path] = []
    for relative in INCLUDE_ROOTS:
        candidate = ROOT / relative
        if not candidate.exists():
            raise FileNotFoundError(f"release input is missing: {relative}")
        candidates = candidate.rglob("*") if candidate.is_dir() else (candidate,)
        files.extend(
            item
            for item in candidates
            if item.is_file()
            and not EXCLUDED_PARTS.intersection(item.relative_to(ROOT).parts)
            and item.suffix not in EXCLUDED_SUFFIXES
        )
    return sorted(set(files), key=lambda item: item.as_posix())


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the AIShop Phase 1 Windows bundle")
    parser.add_argument(
        "--output", default=str(ROOT / "artifacts" / "AIShop-Hermes-Workbench-phase1.zip")
    )
    arguments = parser.parse_args()
    output = Path(arguments.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    files = release_files()
    manifest = {
        **RELEASE_METADATA,
        "phase": 1,
        "files": [
            {
                "path": item.relative_to(ROOT).as_posix(),
                "size": item.stat().st_size,
                "sha256": hashlib.sha256(item.read_bytes()).hexdigest(),
            }
            for item in files
        ],
    }
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for item in files:
            info = zipfile.ZipInfo(item.relative_to(ROOT).as_posix(), ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            permissions = 0o755 if item.stat().st_mode & 0o111 else 0o644
            info.external_attr = permissions << 16
            archive.writestr(info, item.read_bytes())
        info = zipfile.ZipInfo("SHA256SUMS.json", ZIP_TIMESTAMP)
        info.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(info, json.dumps(manifest, ensure_ascii=False, indent=2).encode())
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix + ".sha256").write_text(f"{digest}  {output.name}\n")
    print(json.dumps({"bundle": str(output), "sha256": digest, "files": len(files)}))


if __name__ == "__main__":
    main()
