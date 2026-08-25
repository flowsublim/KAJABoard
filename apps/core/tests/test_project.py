import os
import subprocess
import sys

from django.conf import settings
from django.core.management import call_command
from django.urls import URLPattern, URLResolver, get_resolver, reverse


def test_django_system_checks_pass():
    call_command("check", verbosity=0)


def test_custom_user_model_is_configured():
    assert settings.AUTH_USER_MODEL == "accounts.User"


def test_foundation_url_names_resolve_to_distinct_paths():
    urls = {
        reverse("admin:index"),
        reverse("health:liveness"),
        reverse("health:readiness"),
    }

    assert urls == {"/admin/", "/health/live/", "/health/ready/"}


def test_all_registered_url_names_are_unique_within_their_namespace():
    def named_patterns(patterns, namespaces=()):
        for pattern in patterns:
            if isinstance(pattern, URLResolver):
                namespace = namespaces + ((pattern.namespace,) if pattern.namespace else ())
                yield from named_patterns(pattern.url_patterns, namespace)
            elif isinstance(pattern, URLPattern) and pattern.name:
                yield ":".join((*namespaces, pattern.name))

    names = list(named_patterns(get_resolver().url_patterns))

    assert len(names) == len(set(names))


def test_production_settings_fail_closed_without_required_secret():
    environment = os.environ.copy()
    for variable in (
        "DJANGO_SECRET_KEY",
        "DJANGO_ALLOWED_HOSTS",
        "DJANGO_DB_ENGINE",
        "DJANGO_DB_NAME",
        "DJANGO_DB_USER",
        "DJANGO_DB_PASSWORD",
        "DJANGO_DB_HOST",
    ):
        environment.pop(variable, None)

    result = subprocess.run(
        [sys.executable, "-c", "import config.settings.production"],
        cwd=settings.BASE_DIR,
        env=environment,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode != 0
    assert "DJANGO_SECRET_KEY" in result.stderr
