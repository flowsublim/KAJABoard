from django.contrib import admin

from .models import (
    BusinessUnit,
    CostCenter,
    Department,
    LegalEntity,
    OrganizationMembership,
    Warehouse,
)


class ServiceManagedMasterAdmin(admin.ModelAdmin):
    """Inspection admin; master writes must pass through audited application services."""

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LegalEntity)
class LegalEntityAdmin(ServiceManagedMasterAdmin):
    list_display = ("code", "name", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(OrganizationMembership)
class OrganizationMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "legal_entity", "is_active", "updated_at")
    list_filter = ("is_active", "legal_entity")
    search_fields = ("user__email", "legal_entity__code", "legal_entity__name")
    list_select_related = ("user", "legal_entity")


@admin.register(BusinessUnit)
class BusinessUnitAdmin(ServiceManagedMasterAdmin):
    list_display = ("code", "name", "legal_entity", "is_active", "effective_from")
    list_filter = ("is_active", "legal_entity")
    search_fields = ("code", "name")
    list_select_related = ("legal_entity",)


@admin.register(Department)
class DepartmentAdmin(ServiceManagedMasterAdmin):
    list_display = ("code", "name", "legal_entity", "business_unit", "is_active")
    list_filter = ("is_active", "legal_entity", "business_unit")
    search_fields = ("code", "name")
    list_select_related = ("legal_entity", "business_unit", "parent")


@admin.register(CostCenter)
class CostCenterAdmin(ServiceManagedMasterAdmin):
    list_display = (
        "code",
        "name",
        "category",
        "legal_entity",
        "is_production_overhead_eligible",
        "is_active",
    )
    list_filter = ("category", "is_production_overhead_eligible", "is_active", "legal_entity")
    search_fields = ("code", "name")
    list_select_related = ("legal_entity", "business_unit", "department")


@admin.register(Warehouse)
class WarehouseAdmin(ServiceManagedMasterAdmin):
    list_display = ("code", "name", "legal_entity", "is_default", "is_active")
    list_filter = ("is_default", "is_active", "legal_entity")
    search_fields = ("code", "name", "city")
    list_select_related = ("legal_entity", "business_unit")
