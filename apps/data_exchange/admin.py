from django.contrib import admin

from apps.data_exchange.models import ImportBatch, ImportRowResult


class ImportRowResultInline(admin.TabularInline):
    model = ImportRowResult
    extra = 0
    readonly_fields = (
        "row_number",
        "status",
        "messages",
        "target_reference",
        "created_at",
        "updated_at",
    )
    can_delete = False


@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    list_display = (
        "import_type",
        "source_filename",
        "legal_entity",
        "status",
        "total_rows",
        "success_rows",
        "failed_rows",
        "replay_count",
    )
    list_filter = ("legal_entity", "import_type", "status")
    search_fields = ("source_filename", "checksum")
    readonly_fields = ("id", "checksum", "created_at", "updated_at", "confirmed_at")
    inlines = [ImportRowResultInline]
