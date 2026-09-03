"""One-off developer script: scaffold a new app/<domain>/ package.

Usage (from backend/):
    uv run python -m scripts.new_domain <domain_name>

Generates the four files backend/CLAUDE.md's "Domain modules" section documents
(models.py, repository.py, deps.py, router.py) plus an empty __init__.py, all under
app/<domain_name>/. Only creates the files -- it does not wire app/main.py or add an
import-linter contract, since both require a judgment call (what should this domain be
allowed to import, and in what order should its router run relative to others) that a
script can't make safely. The two reminders printed by _main() exist so neither step gets
forgotten -- this exact kind of missed wiring step is what motivated writing this script.

deps.py is generated with no functions in it -- not every domain ends up needing one (e.g.
app/gameplay/ has no deps.py; nothing in gameplay so far needs a domain-specific FastAPI
dependency). Delete it if this domain turns out not to need one either.
"""

import re
import sys
from pathlib import Path

DOMAIN_NAME_PATTERN = re.compile(r"\A[a-z][a-z_]*\Z")

BACKEND_DIR = Path(__file__).resolve().parent.parent


class InvalidDomainNameError(Exception):
    pass


def scaffold_domain(backend_dir: Path, domain_name: str) -> list[Path]:
    """Creates app/<domain_name>/{__init__,models,repository,deps,router}.py under
    backend_dir. Raises InvalidDomainNameError if domain_name isn't lowercase letters and
    underscores (the shape every other app/<domain>/ package uses), or FileExistsError
    (from Path.mkdir) if the package already exists."""
    if not DOMAIN_NAME_PATTERN.match(domain_name):
        raise InvalidDomainNameError(
            f"{domain_name!r} is not a valid domain name -- use lowercase letters and "
            "underscores only, e.g. 'standings' or 'race_results'."
        )

    domain_dir = backend_dir / "app" / domain_name
    domain_dir.mkdir(parents=True)

    files = {
        "__init__.py": "",
        "models.py": (
            f'"""SQLModel table(s) and their *Read pairs for app.{domain_name}.\n\n'
            "Every table model needs a matching <Name>Read class in this same file, "
            "excluding SoftDeleteMixin's bookkeeping columns from the API response -- see "
            'backend/CLAUDE.md\'s "Response schemas" convention. tests/test_architecture.py '
            'enforces this automatically.\n"""\n'
        ),
        "repository.py": (
            f'"""Every raw session.execute(select(...)) query app.{domain_name}\'s '
            'router(s)/deps need -- see backend/CLAUDE.md\'s "Domain modules" section. '
            "tests/test_architecture.py fails if a router in this package queries directly "
            'instead of calling a function defined here.\n"""\n'
        ),
        "deps.py": (
            f'"""FastAPI dependencies specific to app.{domain_name} (e.g. require_*/get_* '
            "functions that don't belong in the shared app/deps.py). Delete this file if "
            'this domain ends up not needing one.\n"""\n'
        ),
        "router.py": (
            f'"""FastAPI router(s) for app.{domain_name}. Wire this into app/main.py as:\n\n'
            f"    from app.{domain_name}.router import router as {domain_name}_router\n"
            f"    app.include_router({domain_name}_router)\n\n"
            "If this file grows past 400 lines (backend/CLAUDE.md's file-length limit) or "
            "starts covering more than one resource, split it into a routers/ package "
            'instead -- see backend/CLAUDE.md\'s "Domain modules" section for that split.\n'
            '"""\n\n'
            "from fastapi import APIRouter\n\n"
            "router = APIRouter()\n"
        ),
    }

    created = []
    for filename, content in files.items():
        path = domain_dir / filename
        path.write_text(content)
        created.append(path)
    return created


def _main(domain_name: str) -> None:
    try:
        created = scaffold_domain(BACKEND_DIR, domain_name)
    except InvalidDomainNameError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    except FileExistsError:
        print(f"app/{domain_name}/ already exists -- pick a different name.", file=sys.stderr)
        sys.exit(1)

    print(f"Created app/{domain_name}/ with:")
    for path in created:
        print(f"  {path.relative_to(BACKEND_DIR)}")
    print()
    print("Two steps this script deliberately leaves to you (see this file's docstring):")
    print(f"  1. Wire app/main.py -- import {domain_name}_router and app.include_router(...) it.")
    print(
        "  2. Decide this domain's import-linter contract in pyproject.toml -- what may it "
        "import, and may other domains import it? See backend/CLAUDE.md's 'Domain modules' "
        "section for the independence/forbidden contracts already in place as examples."
    )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: uv run python -m scripts.new_domain <domain_name>", file=sys.stderr)
        sys.exit(1)
    _main(sys.argv[1])
