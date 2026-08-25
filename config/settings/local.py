"""Local development settings."""

from .base import *  # noqa: F403
from .base import env_bool, env_list

DEBUG = env_bool("DJANGO_DEBUG", default=True)
ALLOWED_HOSTS = env_list(
    "DJANGO_ALLOWED_HOSTS",
    default=("127.0.0.1", "localhost", "[::1]"),
)
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")
