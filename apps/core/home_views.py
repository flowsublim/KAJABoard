from dataclasses import dataclass

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import reverse

from apps.organizations.selectors import accessible_legal_entities
from apps.sales.models import SalesDeliveryState, SalesInvoiceState, SalesOrderState
from apps.sales.selectors import sales_deliveries, sales_invoices, sales_orders


@dataclass(frozen=True)
class HomeModule:
    title: str
    description: str
    url: str
    group: str


def _has_any_permission(user, *permissions: str) -> bool:
    return any(user.has_perm(permission) for permission in permissions)


def _first_permitted_url(user, choices: tuple[tuple[str, str], ...]) -> str:
    for permission, url_name in choices:
        if user.has_perm(permission):
            return reverse(url_name)
    raise ValueError("A Home module requires at least one permitted destination.")


def _module_cards(user) -> tuple[HomeModule, ...]:
    modules: list[HomeModule] = []
    sales_permissions = (
        ("sales.view_salesorder", "sales:order-list"),
        ("sales.view_salesdelivery", "sales:delivery-list"),
        ("sales.view_salesinvoice", "sales:invoice-list"),
    )
    if _has_any_permission(user, *(permission for permission, _ in sales_permissions)):
        modules.append(
            HomeModule(
                title="Sales",
                description="Sales Order, Surat Jalan, dan sumber Invoice.",
                url=_first_permitted_url(user, sales_permissions),
                group="OPERASIONAL",
            )
        )

    master_permissions = (
        ("organizations.view_legalentity", "organizations:master-list"),
        ("organizations.view_businessunit", "organizations:master-list"),
        ("organizations.view_department", "organizations:master-list"),
        ("organizations.view_costcenter", "organizations:master-list"),
        ("organizations.view_warehouse", "organizations:master-list"),
    )
    if _has_any_permission(user, *(permission for permission, _ in master_permissions)):
        modules.append(
            HomeModule(
                title="Organisasi",
                description="Entitas legal, unit bisnis, departemen, dan konfigurasi organisasi.",
                url=reverse("organizations:workspace"),
                group="MASTER & KONFIGURASI",
            )
        )
    if user.has_perm("partners.view_businesspartner"):
        modules.append(
            HomeModule(
                title="Partners",
                description="Identitas Business Partner dan peran pelanggan/vendor.",
                url=reverse("partners:list"),
                group="MASTER & KONFIGURASI",
            )
        )
    catalog_choices = (
        ("catalog.view_item", "catalog:list", {"master_type": "items"}),
        ("catalog.view_itemcategory", "catalog:list", {"master_type": "categories"}),
        ("catalog.view_uom", "catalog:list", {"master_type": "uoms"}),
    )
    for permission, url_name, url_kwargs in catalog_choices:
        if user.has_perm(permission):
            modules.append(
                HomeModule(
                    title="Catalog",
                    description="Item, SKU, kategori, dan unit pengukuran.",
                    url=reverse(url_name, kwargs=url_kwargs),
                    group="MASTER & KONFIGURASI",
                )
            )
            break
    channel_choices = (
        ("channels.view_store", "channels:store-list"),
        ("channels.view_externalskumap", "channels:mapping-list"),
    )
    if _has_any_permission(user, *(permission for permission, _ in channel_choices)):
        modules.append(
            HomeModule(
                title="Channels & Stores",
                description="Store, channel, dan pemetaan external SKU.",
                url=_first_permitted_url(user, channel_choices),
                group="MASTER & KONFIGURASI",
            )
        )
    finance_choices = (
        ("finance.view_coaaccount", "finance:account-list"),
        ("finance.view_coamapping", "finance:mapping-list"),
    )
    if _has_any_permission(user, *(permission for permission, _ in finance_choices)):
        modules.append(
            HomeModule(
                title="Finance Configuration",
                description="Chart of Accounts dan mapping akuntansi.",
                url=_first_permitted_url(user, finance_choices),
                group="MASTER & KONFIGURASI",
            )
        )
    simple_modules = (
        (
            "purchasing.view_purchasecategory",
            "Purchasing Configuration",
            "Kategori pembelian dan perlakuan akuntansi.",
            "purchasing:category-list",
        ),
        (
            "tax.view_taxregistration",
            "Tax Configuration",
            "Identitas dan registrasi pajak.",
            "tax:registration-list",
        ),
        (
            "data_exchange.view_importbatch",
            "Data Exchange",
            "Batch import master dan validasi sumber data.",
            "data_exchange:import-list",
        ),
    )
    for permission, title, description, url_name in simple_modules:
        if user.has_perm(permission):
            modules.append(
                HomeModule(
                    title=title,
                    description=description,
                    url=reverse(url_name),
                    group="MASTER & KONFIGURASI",
                )
            )
    return tuple(modules)


def _summary_cards(user) -> tuple[dict[str, object], ...]:
    summaries: list[dict[str, object]] = []
    if user.has_perm("sales.view_salesorder"):
        summaries.append(
            {
                "label": "Sales Order terbuka",
                "value": sales_orders(user)
                .filter(state__in=(SalesOrderState.CONFIRMED, SalesOrderState.ON_HOLD))
                .count(),
                "url": reverse("sales:order-list"),
            }
        )
    if user.has_perm("sales.view_salesdelivery"):
        summaries.append(
            {
                "label": "Surat Jalan aktif",
                "value": sales_deliveries(user)
                .filter(state__in=(SalesDeliveryState.DRAFT, SalesDeliveryState.POSTED))
                .count(),
                "url": reverse("sales:delivery-list"),
            }
        )
    if user.has_perm("sales.view_salesinvoice"):
        summaries.append(
            {
                "label": "Sumber Invoice aktif",
                "value": sales_invoices(user)
                .filter(state__in=(SalesInvoiceState.DRAFT, SalesInvoiceState.CONFIRMED))
                .count(),
                "url": reverse("sales:invoice-list"),
            }
        )
    return tuple(summaries)


@login_required
def home(request):
    modules = _module_cards(request.user)
    return render(
        request,
        "core/home.html",
        {
            "entity_count": accessible_legal_entities(request.user).filter(is_active=True).count(),
            "operational_modules": tuple(
                module for module in modules if module.group == "OPERASIONAL"
            ),
            "configuration_modules": tuple(
                module for module in modules if module.group == "MASTER & KONFIGURASI"
            ),
            "summary_cards": _summary_cards(request.user),
        },
    )
