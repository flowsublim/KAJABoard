from django.contrib import admin

from apps.omnichannel.models import (
    OmniException,
    OmniImportBatch,
    OmniImportRow,
    OmniOrder,
    OmniOrderLine,
    OmniPacking,
    OmniPackingLine,
)


class OmniImportRowInline(admin.TabularInline):
    model = OmniImportRow
    extra = 0
    can_delete = False


@admin.register(OmniImportBatch)
class OmniImportBatchAdmin(admin.ModelAdmin):
    list_display = (
        "source_filename",
        "legal_entity",
        "status",
        "row_count",
        "accepted_count",
        "rejected_count",
        "created_at",
    )
    list_filter = ("source_type", "status", "legal_entity")
    inlines = (OmniImportRowInline,)
    readonly_fields = ("file_hash", "created_at", "updated_at", "imported_at")


class OmniOrderLineInline(admin.TabularInline):
    model = OmniOrderLine
    extra = 0
    can_delete = False


@admin.register(OmniOrder)
class OmniOrderAdmin(admin.ModelAdmin):
    list_display = (
        "external_order_number",
        "marketplace",
        "external_store_name",
        "order_date",
        "normalized_status",
        "mapping_status",
    )
    list_filter = ("marketplace", "normalized_status", "mapping_status", "legal_entity")
    inlines = (OmniOrderLineInline,)
    readonly_fields = ("created_at", "updated_at")


class OmniPackingLineInline(admin.TabularInline):
    model = OmniPackingLine
    extra = 0
    can_delete = False


@admin.register(OmniPacking)
class OmniPackingAdmin(admin.ModelAdmin):
    list_display = ("packing_date", "store", "warehouse", "state", "created_at")
    list_filter = ("state", "legal_entity")
    inlines = (OmniPackingLineInline,)
    readonly_fields = ("created_at", "updated_at", "posted_at")


@admin.register(OmniException)
class OmniExceptionAdmin(admin.ModelAdmin):
    list_display = ("code", "state", "legal_entity", "order", "created_at")
    list_filter = ("code", "state", "legal_entity")
    readonly_fields = ("created_at", "updated_at")
