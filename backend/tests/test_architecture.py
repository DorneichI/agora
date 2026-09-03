"""Structural checks on app/'s actual layout, not its runtime behavior.

These assert that rules backend/CLAUDE.md documents in prose are actually true of the
code, so a violation fails the test suite instead of silently drifting. This file's first
test exists because two raw queries (app/leagues/routers/invites.py,
app/gameplay/routers/predictions.py) bypassed their domain's repository.py despite the
documented convention -- found while auditing the project's structure.
"""

import ast
import importlib
import inspect
from pathlib import Path

import pytest
from sqlmodel import SQLModel

APP_DIR = Path(__file__).resolve().parent.parent / "app"


def _domains_with_repository() -> list[Path]:
    """Every app/<domain>/ package that owns a repository.py. Per backend/CLAUDE.md's
    "Domain modules" section, once a package has its own repository.py, that's the one
    place allowed to hold a raw query against this domain's tables -- so its router(s)
    must go through it instead of querying directly."""
    return sorted((p.parent for p in APP_DIR.glob("*/repository.py")), key=lambda p: p.name)


def _router_files_for_domain(domain_dir: Path) -> list[Path]:
    single = domain_dir / "router.py"
    if single.exists():
        return [single]
    routers_dir = domain_dir / "routers"
    if routers_dir.is_dir():
        return sorted(
            p for p in routers_dir.glob("*.py") if p.name not in {"__init__.py", "_shared.py"}
        )
    return []


def _raw_execute_call_lines(file_path: Path) -> list[int]:
    """Line numbers of every `<something>.execute(...)` call in file_path. Scoped to the
    `.execute` attribute name specifically -- in this codebase that name is only ever used
    for session.execute(...), so it's a reliable signal without needing to resolve which
    variable the session is bound to."""
    tree = ast.parse(file_path.read_text(), filename=str(file_path))
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "execute"
    ]


@pytest.mark.parametrize("domain_dir", _domains_with_repository(), ids=lambda p: p.name)
def test_domain_routers_never_query_directly(domain_dir: Path) -> None:
    violations = {
        str(router_file.relative_to(APP_DIR.parent)): lines
        for router_file in _router_files_for_domain(domain_dir)
        if (lines := _raw_execute_call_lines(router_file))
    }
    assert not violations, (
        f"Router file(s) call .execute(...) directly instead of going through "
        f"app/{domain_dir.name}/repository.py: {violations}. Move the query into "
        f"repository.py and call that function from the router instead -- see "
        f"backend/CLAUDE.md's 'Domain modules' section."
    )


def _model_modules() -> list[str]:
    """Every module the '*Read schema pairing' convention applies to: app/models/*.py
    (excluding __init__.py) plus every app/<domain>/models.py."""
    modules = [
        f"app.models.{f.stem}" for f in (APP_DIR / "models").glob("*.py") if f.stem != "__init__"
    ]
    modules += [f"app.{f.parent.name}.models" for f in APP_DIR.glob("*/models.py")]
    return sorted(modules)


@pytest.mark.parametrize("module_path", _model_modules())
def test_every_table_model_has_a_read_pair(module_path: str) -> None:
    module = importlib.import_module(module_path)
    table_model_names = {
        name
        for name, obj in inspect.getmembers(module, inspect.isclass)
        if issubclass(obj, SQLModel) and obj.__module__ == module_path and hasattr(obj, "__table__")
    }
    missing = sorted(name for name in table_model_names if not hasattr(module, f"{name}Read"))
    assert not missing, (
        f"{module_path}: table model(s) {missing} have no matching *Read schema -- see "
        f"backend/CLAUDE.md's 'Response schemas' convention."
    )
