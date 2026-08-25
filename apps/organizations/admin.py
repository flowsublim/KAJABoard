from django.contrib import admin

from .models import LegalEntity, OrganizationMembership


@admin.register(LegalEntity)
class LegalEntityAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(OrganizationMembership)
class OrganizationMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "legal_entity", "is_active", "updated_at")
    list_filter = ("is_active", "legal_entity")
    search_fields = ("user__email", "legal_entity__code", "legal_entity__name")
    list_select_related = ("user", "legal_entity")
