from django.contrib import admin

from apps.organizations.admin import ServiceManagedMasterAdmin

from .models import BusinessPartner, PartnerRole


@admin.register(BusinessPartner)
class BusinessPartnerAdmin(ServiceManagedMasterAdmin):
    list_display = ("code", "display_name", "legal_entity", "is_active", "updated_at")
    list_filter = ("is_active", "legal_entity")
    search_fields = ("code", "display_name", "legal_name", "email", "phone", "npwp")
    list_select_related = ("legal_entity",)


@admin.register(PartnerRole)
class PartnerRoleAdmin(ServiceManagedMasterAdmin):
    list_display = ("partner", "role_type", "is_active", "effective_from", "effective_to")
    list_filter = ("role_type", "is_active")
    search_fields = ("partner__code", "partner__display_name")
    list_select_related = ("partner",)
