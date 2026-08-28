"""Top-level URL configuration."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("accounts/", include("django.contrib.auth.urls")),
    path("", include("apps.core.home_urls", namespace="home")),
    path("admin/", admin.site.urls),
    path("health/", include("apps.core.urls", namespace="health")),
    path("settings/numbering/", include("apps.core.numbering_urls", namespace="numbering")),
    path("settings/channels/", include("apps.channels.urls", namespace="channels")),
    path("settings/purchasing/", include("apps.purchasing.urls", namespace="purchasing")),
    path("settings/finance/", include("apps.finance.urls", namespace="finance")),
    path("settings/tax/", include("apps.tax.urls", namespace="tax")),
    path("settings/data-exchange/", include("apps.data_exchange.urls", namespace="data_exchange")),
    path("partners/", include("apps.partners.urls", namespace="partners")),
    path("catalog/", include("apps.catalog.urls", namespace="catalog")),
    path("sales/", include("apps.sales.urls", namespace="sales")),
    path("projects/", include("apps.projects.urls", namespace="projects")),
    path("purchasing/", include("apps.purchasing.order_urls", namespace="purchasing_operations")),
    path("production/", include("apps.production.urls", namespace="production")),
    path("warehouse/", include("apps.warehouse.urls", namespace="warehouse")),
    path("quality/", include("apps.quality.urls", namespace="quality")),
    path("", include("apps.organizations.urls", namespace="organizations")),
]
