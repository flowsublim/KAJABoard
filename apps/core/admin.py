from django.contrib import admin

from .models import AuditEvent, IdempotencyRecord


class ReadOnlyFoundationAdmin(admin.ModelAdmin):
    """Inspection-only admin for records controlled by application services."""

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AuditEvent)
class AuditEventAdmin(ReadOnlyFoundationAdmin):
    list_display = ("created_at", "action", "target_type", "target_id", "actor")
    search_fields = ("action", "target_type", "target_id", "reference", "idempotency_key")
    list_filter = ("action", "target_type", "source")
    date_hierarchy = "created_at"


@admin.register(IdempotencyRecord)
class IdempotencyRecordAdmin(ReadOnlyFoundationAdmin):
    list_display = ("namespace", "key", "status", "started_at", "finished_at")
    search_fields = ("namespace", "key", "request_hash", "result_reference")
    list_filter = ("namespace", "status")
    date_hierarchy = "started_at"
