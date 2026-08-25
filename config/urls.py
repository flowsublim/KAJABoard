"""Top-level URL configuration."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("accounts/", include("django.contrib.auth.urls")),
    path("admin/", admin.site.urls),
    path("health/", include("apps.core.urls", namespace="health")),
    path("settings/numbering/", include("apps.core.numbering_urls", namespace="numbering")),
    path("settings/channels/", include("apps.channels.urls", namespace="channels")),
    path("partners/", include("apps.partners.urls", namespace="partners")),
    path("catalog/", include("apps.catalog.urls", namespace="catalog")),
    path("", include("apps.organizations.urls", namespace="organizations")),
]
