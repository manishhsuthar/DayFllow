#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    """Run administrative tasks."""
    # The test suite gets its own settings module so that production settings can
    # stay fail-closed (no secret key, no allowed hosts, no Postgres -> refuse to
    # start) without making `manage.py test` require a wall of environment
    # variables. An explicit DJANGO_SETTINGS_MODULE always wins.
    if "test" in sys.argv[1:2]:
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings_test")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
