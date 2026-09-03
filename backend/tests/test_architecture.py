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
import re
from pathlib import Path

import pytest
from sqlmodel import Field, SQLModel

from app.main import app

APP_DIR = Path(__file__).resolve().parent.parent / "app"

_KEBAB_SEGMENT = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")


def _domain_dirs_with_routers() -> list[Path]:
    """Every app/<domain>/ package with a router.py file or a routers/ subpackage. This
    is broader than "owns a repository.py" -- app.standings has no repository.py of its
    own (it queries via app.leagues's and app.gameplay's), but the rule this scan
    enforces ("a router must never call .execute() directly") applies to it just the
    same. This naturally excludes app/routers/ (the shared health.py/users.py module):
    it's one level shallower than these two glob patterns require."""
    single_router_dirs = {p.parent for p in APP_DIR.glob("*/router.py")}
    routers_pkg_dirs = {p.parent for p in APP_DIR.glob("*/routers") if p.is_dir()}
    return sorted(single_router_dirs | routers_pkg_dirs, key=lambda p: p.name)


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


@pytest.mark.parametrize("domain_dir", _domain_dirs_with_routers(), ids=lambda p: p.name)
def test_domain_routers_never_query_directly(domain_dir: Path) -> None:
    violations = {
        str(router_file.relative_to(APP_DIR.parent)): lines
        for router_file in _router_files_for_domain(domain_dir)
        if (lines := _raw_execute_call_lines(router_file))
    }
    assert not violations, (
        f"Router file(s) in app/{domain_dir.name}/ call .execute(...) directly: "
        f"{violations}. Route the query through a domain's repository.py instead -- "
        f"this package's own if it has one, or the relevant domain's if this package "
        f"is a cross-domain bridge like app.standings -- see backend/CLAUDE.md's "
        f"'Domain modules' section."
    )


def test_standings_is_covered_by_the_router_boundary_scan() -> None:
    """Regression guard for issue #129's gap #2: app.standings has no repository.py of
    its own, so the discovery function must not rely on repository.py's existence to
    find it."""
    domain_dirs = _domain_dirs_with_routers()
    assert (APP_DIR / "standings") in domain_dirs, (
        "app/standings/ must be discovered by the repository-boundary scan even though "
        "it has no repository.py of its own -- see backend/CLAUDE.md's 'Domain "
        "modules' section on cross-domain composition."
    )


def _model_modules() -> list[str]:
    """Every module the '*Read schema pairing' convention applies to: app/models/*.py
    (excluding __init__.py) plus every app/<domain>/models.py."""
    modules = [
        f"app.models.{f.stem}" for f in (APP_DIR / "models").glob("*.py") if f.stem != "__init__"
    ]
    modules += [f"app.{f.parent.name}.models" for f in APP_DIR.glob("*/models.py")]
    return sorted(modules)


def _is_valid_read_pair(read_cls: object) -> bool:
    """Whether a table model's *Read attribute satisfies the pairing convention. Requires a
    distinct, non-table SQLModel schema -- not missing, and not a bare alias back to the table
    model itself (e.g. `FooRead = Foo`), which would silently expose every SoftDeleteMixin
    bookkeeping column the *Read convention exists to hide."""
    return (
        read_cls is not None
        and inspect.isclass(read_cls)
        and issubclass(read_cls, SQLModel)
        and not hasattr(read_cls, "__table__")
    )


def test_read_pair_check_rejects_bare_alias_back_to_table_model() -> None:
    """Regression guard for issue #129's gap #1: a `FooRead = Foo` alias must not satisfy
    the *Read pairing convention."""

    class Widget(SQLModel, table=True):
        id: int | None = Field(default=None, primary_key=True)

    try:
        assert _is_valid_read_pair(Widget) is False, (
            "a bare FooRead = Foo alias must be flagged as invalid, not accepted as a valid "
            "*Read pair"
        )
    finally:
        SQLModel.metadata.remove(Widget.__table__)


@pytest.mark.parametrize("module_path", _model_modules())
def test_every_table_model_has_a_read_pair(module_path: str) -> None:
    module = importlib.import_module(module_path)
    table_model_names = {
        name
        for name, obj in inspect.getmembers(module, inspect.isclass)
        if issubclass(obj, SQLModel) and obj.__module__ == module_path and hasattr(obj, "__table__")
    }
    invalid = sorted(
        name
        for name in table_model_names
        if not _is_valid_read_pair(getattr(module, f"{name}Read", None))
    )
    assert not invalid, (
        f"{module_path}: table model(s) {invalid} have no matching *Read schema (or their "
        f"<Name>Read exists but is not a distinct, non-table SQLModel class) -- see "
        f"backend/CLAUDE.md's 'Response schemas' convention."
    )


def test_routes_use_kebab_case_paths() -> None:
    violations = []
    for path in app.openapi()["paths"]:
        for segment in path.split("/"):
            if not segment or segment.startswith("{"):
                continue
            if not _KEBAB_SEGMENT.fullmatch(segment):
                violations.append(path)
                break
    assert not violations, (
        f"Route path(s) not kebab-case: {violations} -- see backend/CLAUDE.md's 'Route "
        f"naming for multi-word resources' convention."
    )
