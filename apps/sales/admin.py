from django.contrib import admin

from apps.sales.models import SalesOrder, SalesOrderLine


class SalesOrderLineInline(admin.TabularInline):
    model = SalesOrderLine
    extra = 0
    readonly_fields = (
        "item_code_snapshot",
        "item_name_snapshot",
        "uom_code_snapshot",
        "line_amount",
        "line_discount_amount",
        "line_tax_amount",
        "line_total",
    )


@admin.register(SalesOrder)
class SalesOrderAdmin(admin.ModelAdmin):
    list_display = (
        "document_number",
        "legal_entity",
        "customer",
        "document_date",
        "state",
        "grand_total",
    )
    list_filter = ("legal_entity", "state", "currency")
    search_fields = ("document_number", "customer_po_reference", "customer_name_snapshot")
    readonly_fields = ("document_allocation", "document_number", "confirmed_at", "cancelled_at")
    inlines = [SalesOrderLineInline]
