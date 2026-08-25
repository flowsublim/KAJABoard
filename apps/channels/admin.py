from django.contrib import admin

from apps.channels.models import ExternalSKUMap, Store


class ServiceManagedAdmin(admin.ModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Store)
class StoreAdmin(ServiceManagedAdmin):
    list_display = ("code", "name", "channel", "legal_entity", "is_active")
    list_filter = ("channel", "is_active", "legal_entity")
    search_fields = ("code", "name", "external_account_id")
    list_select_related = ("legal_entity", "business_unit")


@admin.register(ExternalSKUMap)
class ExternalSKUMapAdmin(ServiceManagedAdmin):
    list_display = ("store", "external_sku", "external_variation", "item", "is_active")
    list_filter = ("store", "is_active")
    search_fields = ("external_sku", "external_product_name", "external_variation", "item__code")
    list_select_related = ("store", "item")
