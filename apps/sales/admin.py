from django.contrib import admin

from apps.sales.models import (
    SalesDelivery,
    SalesDeliveryLine,
    SalesInvoice,
    SalesInvoiceLine,
    SalesOrder,
    SalesOrderLine,
)


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


class SalesDeliveryLineInline(admin.TabularInline):
    model = SalesDeliveryLine
    extra = 0
    readonly_fields = (
        "source_sales_order_number_snapshot",
        "item_code_snapshot",
        "item_name_snapshot",
        "uom_code_snapshot",
        "ordered_quantity_snapshot",
    )


@admin.register(SalesDelivery)
class SalesDeliveryAdmin(admin.ModelAdmin):
    list_display = ("document_number", "legal_entity", "customer", "delivery_date", "state")
    list_filter = ("legal_entity", "state")
    search_fields = ("document_number", "customer_name_snapshot", "expedition_reference")
    readonly_fields = ("document_allocation", "document_number", "posted_at", "cancelled_at")
    inlines = [SalesDeliveryLineInline]


class SalesInvoiceLineInline(admin.TabularInline):
    model = SalesInvoiceLine
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


@admin.register(SalesInvoice)
class SalesInvoiceAdmin(admin.ModelAdmin):
    list_display = (
        "document_number",
        "legal_entity",
        "customer",
        "invoice_date",
        "document_kind",
        "source_mode",
        "state",
        "grand_total",
    )
    list_filter = ("legal_entity", "document_kind", "source_mode", "state", "currency")
    search_fields = ("document_number", "customer_name_snapshot")
    readonly_fields = ("document_allocation", "document_number", "confirmed_at", "cancelled_at")
    inlines = [SalesInvoiceLineInline]
