from django.db.models import Q

from apps.data_exchange.models import ImportBatch, ImportRowResult
from apps.organizations.selectors import accessible_legal_entities


def import_batches(user, *, search="", import_type="", include_finished=True):
    queryset = ImportBatch.objects.select_related("legal_entity", "uploaded_by").filter(
        legal_entity__in=accessible_legal_entities(user)
    )
    if import_type:
        queryset = queryset.filter(import_type=import_type)
    if not include_finished:
        queryset = queryset.exclude(status="IMPORTED")
    if search:
        queryset = queryset.filter(
            Q(source_filename__icontains=search)
            | Q(checksum__icontains=search)
            | Q(import_type__icontains=search)
        )
    return queryset


def import_rows(user, *, batch):
    queryset = ImportRowResult.objects.select_related("batch", "batch__legal_entity").filter(
        batch__legal_entity__in=accessible_legal_entities(user)
    )
    return queryset.filter(batch=batch)
