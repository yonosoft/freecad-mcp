"""Run the repository's portable, pure-Python quality checks."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

CHECKS = (
    ("Compile", ("-m", "compileall", "-q", "src", "tests", "scripts")),
    ("Ruff lint", ("-m", "ruff", "check", ".")),
    ("Ruff formatting", ("-m", "ruff", "format", "--check", ".")),
    ("Mypy", ("-m", "mypy")),
    ("Pytest", ("-m", "pytest")),
)


def _print_environment() -> None:
    """Print environment information before checks."""
    print("\n=== Environment ===")
    print(f"Python executable: {sys.executable}")
    print(f"Python version: {sys.version}")
    for tool, args in (
        ("Ruff", ("-m", "ruff", "--version")),
        ("Mypy", ("-m", "mypy", "--version")),
        ("Pytest", ("-m", "pytest", "--version")),
    ):
        try:
            result = subprocess.run(
                (sys.executable, *args),
                capture_output=True,
                text=True,
                check=True,
            )
            print(f"{tool} version: {result.stdout.strip()}")
        except subprocess.CalledProcessError:
            print(f"{tool} version: (not installed or error)")
    print()


def main() -> int:
    """Run checks in order and stop at the first failure."""
    repository_root = Path(__file__).resolve().parent.parent

    _print_environment()

    for heading, arguments in CHECKS:
        print(f"\n=== {heading} ===", flush=True)
        result = subprocess.run((sys.executable, *arguments), cwd=repository_root, check=False)
        if result.returncode:
            print(f"{heading} failed with exit code {result.returncode}.", file=sys.stderr)
            return result.returncode

    print("\nAll Python quality checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
