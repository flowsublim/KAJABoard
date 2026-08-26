from django.contrib import admin

from apps.tax.models import TaxRegistration


@admin.register(TaxRegistration)
class TaxRegistrationAdmin(admin.ModelAdmin):
    list_display = (
        "subject",
        "registration_status",
        "tax_classification_key",
        "effective_from",
        "effective_to",
        "is_active",
    )
    list_filter = ("registration_status", "tax_classification_key", "is_active")
    search_fields = (
        "legal_entity__code",
        "legal_entity__name",
        "business_partner__code",
        "business_partner__display_name",
        "tax_classification_key",
    )
    readonly_fields = ("id", "created_at", "updated_at")
