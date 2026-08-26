from django.contrib import admin

from apps.finance.models import COAAccount, COAMapping


@admin.register(COAAccount)
class COAAccountAdmin(admin.ModelAdmin):
    list_display = (
        "account_code",
        "account_name",
        "legal_entity",
        "account_type",
        "normal_balance",
        "is_posting_allowed",
        "is_active",
    )
    list_filter = ("legal_entity", "account_type", "normal_balance", "is_active")
    search_fields = ("account_code", "account_name", "report_group", "report_subgroup")
    readonly_fields = ("id", "account_code_normalized", "created_at", "updated_at")


@admin.register(COAMapping)
class COAMappingAdmin(admin.ModelAdmin):
    list_display = (
        "module_code",
        "event_code",
        "dimension_type",
        "dimension_value",
        "line_role",
        "dc",
        "account",
        "priority",
        "is_active",
    )
    list_filter = ("legal_entity", "module_code", "dimension_type", "dc", "is_active")
    search_fields = ("module_code", "event_code", "line_role", "dimension_value")
    readonly_fields = ("id", "dimension_value_normalized", "created_at", "updated_at")
