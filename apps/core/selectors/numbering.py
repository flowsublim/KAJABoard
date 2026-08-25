from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

from apps.core.models import DocumentSequence
from apps.organizations.selectors import accessible_legal_entities


def document_sequences(user, *, include_inactive=False):
    queryset = DocumentSequence.objects.filter(
        legal_entity__in=accessible_legal_entities(user)
    ).select_related("legal_entity")
    if not include_inactive:
        queryset = queryset.filter(is_active=True)
    return queryset.order_by("legal_entity__code", "document_type", "-effective_from")


def document_sequence_for_date(
    legal_entity, document_type, *, business_date=None, for_update=False
):
    business_date = business_date or timezone.localdate()
    document_type = str(document_type).strip().upper()
    queryset = DocumentSequence.objects.filter(
        legal_entity=legal_entity,
        document_type=document_type,
        effective_from__lte=business_date,
    ).filter(Q(effective_to__isnull=True) | Q(effective_to__gte=business_date))
    if business_date >= timezone.localdate():
        queryset = queryset.filter(is_active=True)
    if for_update:
        queryset = queryset.select_for_update()
    matches = list(queryset.order_by("-effective_from")[:2])
    if not matches:
        raise ValidationError(
            {"document_type": "No effective numbering configuration exists for this date."}
        )
    if len(matches) > 1:
        raise ValidationError(
            {"document_type": "Numbering configuration is ambiguous for this date."}
        )
    return matches[0]
