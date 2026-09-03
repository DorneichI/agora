import pytest

from scripts.new_domain import InvalidDomainNameError, scaffold_domain


def test_scaffold_domain_creates_all_five_files(tmp_path):
    (tmp_path / "app").mkdir()

    created = scaffold_domain(tmp_path, "widgets")

    domain_dir = tmp_path / "app" / "widgets"
    assert {p.name for p in created} == {
        "__init__.py",
        "models.py",
        "repository.py",
        "deps.py",
        "router.py",
    }
    assert (domain_dir / "__init__.py").read_text() == ""
    assert "APIRouter" in (domain_dir / "router.py").read_text()
    assert "widgets_router" in (domain_dir / "router.py").read_text()


def test_scaffold_domain_rejects_invalid_name(tmp_path):
    (tmp_path / "app").mkdir()

    with pytest.raises(InvalidDomainNameError):
        scaffold_domain(tmp_path, "Widgets-2")


def test_scaffold_domain_refuses_to_overwrite_existing_package(tmp_path):
    (tmp_path / "app" / "widgets").mkdir(parents=True)

    with pytest.raises(FileExistsError):
        scaffold_domain(tmp_path, "widgets")
