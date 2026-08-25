from django.contrib import admin

from apps.organizations.admin import ServiceManagedMasterAdmin

from .models import UOM, Item, ItemCategory


@admin.register(UOM)
class UOMAdmin(ServiceManagedMasterAdmin):
    list_display = ("code", "name", "dimension", "decimal_places", "is_active")
    list_filter = ("dimension", "is_active")
    search_fields = ("code", "name")


@admin.register(ItemCategory)
class ItemCategoryAdmin(ServiceManagedMasterAdmin):
    list_display = ("code", "name", "parent", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")
    list_select_related = ("parent",)


@admin.register(Item)
class ItemAdmin(ServiceManagedMasterAdmin):
    list_display = ("code", "name", "item_kind", "uom", "legal_entity", "is_active")
    list_filter = (
        "item_kind",
        "sales_eligible",
        "purchase_eligible",
        "production_eligible",
        "inventory_eligible",
        "is_active",
    )
    search_fields = ("code", "name")
    list_select_related = ("legal_entity", "uom", "category", "subcategory", "parent_item")
