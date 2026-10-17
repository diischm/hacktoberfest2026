import pytest
from django.core.management import call_command


def test_manage_py_check_passes():
    call_command("check", fail_level="WARNING")


@pytest.mark.django_db
def test_no_missing_migrations():
    # Exits with an error if a model changed without `makemigrations` being run.
    call_command("makemigrations", "--check", "--dry-run", verbosity=0)
