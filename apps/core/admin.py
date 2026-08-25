from django.contrib import admin

from .models import (
    AuditEvent,
    DocumentNumberAllocation,
    DocumentSequence,
    DocumentSequenceState,
    IdempotencyRecord,
)


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


@admin.register(DocumentSequence)
class DocumentSequenceAdmin(ReadOnlyFoundationAdmin):
    list_display = (
        "legal_entity",
        "document_type",
        "prefix",
        "reset_mode",
        "is_active",
        "effective_from",
    )
    list_filter = ("reset_mode", "is_active", "legal_entity")
    search_fields = ("document_type", "name", "prefix")
    list_select_related = ("legal_entity",)


@admin.register(DocumentSequenceState)
class DocumentSequenceStateAdmin(ReadOnlyFoundationAdmin):
    list_display = ("sequence", "period_key", "last_value", "updated_at")
    search_fields = ("sequence__document_type", "period_key")
    list_select_related = ("sequence",)


@admin.register(DocumentNumberAllocation)
class DocumentNumberAllocationAdmin(ReadOnlyFoundationAdmin):
    list_display = ("number", "document_type", "legal_entity", "business_date", "allocated_at")
    list_filter = ("document_type", "legal_entity")
    search_fields = ("number", "request_key")
    list_select_related = ("legal_entity", "sequence", "allocated_by")
    date_hierarchy = "allocated_at"
