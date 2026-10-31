"""Test requirements and third-party dependencies integrity.

Scans all Python source files in application directories (ledger/, kadai_khata/)
using the Python ast module to ensure that every imported third-party library
is explicitly declared in requirements.txt.
"""

import ast
import re
import sys
from pathlib import Path
from typing import Dict, Set

import pytest


def get_imported_top_level_modules(base_dir: Path) -> Set[str]:
    """Scan all .py files under base_dir and extract imported top-level module names."""
    imported_modules: Set[str] = set()

    for py_file in base_dir.rglob("*.py"):
        if "__pycache__" in py_file.parts:
            continue
        try:
            content = py_file.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(py_file))
        except Exception as e:
            pytest.fail(f"Failed to parse AST for {py_file}: {e}")

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    imported_modules.add(top)
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.level == 0:
                    top = node.module.split(".")[0]
                    imported_modules.add(top)

    return imported_modules


def parse_requirements_txt(req_path: Path) -> Set[str]:
    """Parse package names from requirements.txt, normalizing them to lowercase with dashes."""
    declared: Set[str] = set()
    if not req_path.exists():
        return declared

    for line in req_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Split off version constraints like >=, <=, ==, !=, ~=, <, >
        pkg = re.split(r"[><=~!]", line)[0].strip()
        if pkg:
            # Normalize e.g. python_dotenv -> python-dotenv
            norm = pkg.lower().replace("_", "-")
            declared.add(norm)

    return declared


# Known mapping from imported Python module names to PyPI package distribution names
MODULE_TO_PACKAGE: Dict[str, str] = {
    "pil": "pillow",
    "dotenv": "python-dotenv",
    "django": "django",
    "openai": "openai",
    "requests": "requests",
    "whitenoise": "whitenoise",
    "gunicorn": "gunicorn",
    "pytest": "pytest",
    "pytest_django": "pytest-django",
}


def test_requirements_dependencies_scanned_with_ast():
    """Verify that all third-party modules imported in ledger/ and kadai_khata/ are declared in requirements.txt."""
    repo_root = Path(__file__).resolve().parent.parent
    req_file = repo_root / "requirements.txt"
    assert req_file.exists(), "requirements.txt must exist at repo root"

    declared_packages = parse_requirements_txt(req_file)

    # Modules in standard library
    stdlib_modules = getattr(sys, "stdlib_module_names", set())
    # Builtins and local internal packages
    internal_modules = {"ledger", "kadai_khata"}

    app_modules = set()
    for app_dir_name in ["ledger", "kadai_khata"]:
        app_dir = repo_root / app_dir_name
        if app_dir.exists():
            app_modules.update(get_imported_top_level_modules(app_dir))

    # Filter out standard library and local workspace modules
    third_party_modules = {
        m for m in app_modules
        if m not in internal_modules and m not in stdlib_modules and not m.startswith("_")
    }

    # Verify each third-party module is in requirements.txt
    missing_packages = []
    for mod in sorted(third_party_modules):
        pkg_name = MODULE_TO_PACKAGE.get(mod.lower(), mod.lower().replace("_", "-"))
        if pkg_name not in declared_packages:
            missing_packages.append(f"Module '{mod}' imported in app but package '{pkg_name}' not in requirements.txt")

    assert not missing_packages, "Missing dependencies in requirements.txt:\n" + "\n".join(missing_packages)


def test_runtime_deployment_dependencies_declared():
    """Verify production runtime dependencies (whitenoise, gunicorn) are explicitly declared."""
    repo_root = Path(__file__).resolve().parent.parent
    req_file = repo_root / "requirements.txt"
    declared_packages = parse_requirements_txt(req_file)

    critical_runtime_packages = ["whitenoise", "gunicorn", "django", "requests"]
    for pkg in critical_runtime_packages:
        assert pkg in declared_packages, f"Critical runtime/deployment package '{pkg}' missing from requirements.txt"
