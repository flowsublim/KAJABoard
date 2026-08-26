from django.contrib import admin

from apps.purchasing.models import PurchaseCategory


@admin.register(PurchaseCategory)
class PurchaseCategoryAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "legal_entity",
        "accounting_treatment",
        "cost_center",
        "snapshot_production",
        "is_active",
    )
    list_filter = ("legal_entity", "accounting_treatment", "snapshot_production", "is_active")
    search_fields = ("code", "name", "default_accounting_mapping_key")
    readonly_fields = ("id", "code_normalized", "created_at", "updated_at")
