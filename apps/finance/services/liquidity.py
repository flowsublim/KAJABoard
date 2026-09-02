"""Finance-owned liquidity account master services."""

from django.db import transaction

from apps.finance.models import LiquidityAccount
from apps.organizations.models import LegalEntity


def liquidity_mapping_context(liquidity_account):
    return {"LIQUIDITY_ACCOUNT": liquidity_account.mapping_key}


@transaction.atomic
def create_liquidity_account(*, legal_entity, actor=None, **values):
    entity = LegalEntity.objects.select_for_update().get(pk=legal_entity.pk)
    values["code"] = " ".join(str(values["code"]).split()).upper()
    values["mapping_key"] = " ".join(str(values["mapping_key"]).split()).upper()
    account = LiquidityAccount(legal_entity=entity, **values)
    account.full_clean()
    account.save()
    return account


@transaction.atomic
def update_liquidity_account(account, *, actor=None, **values):
    """Update configuration only; posted LiquidityEntry records remain immutable."""
    account = LiquidityAccount.objects.select_for_update().get(pk=account.pk)
    values.pop("legal_entity", None)
    values.pop("code", None)
    if "mapping_key" in values:
        values["mapping_key"] = " ".join(str(values["mapping_key"]).split()).upper()
    for field, value in values.items():
        setattr(account, field, value)
    account.full_clean()
    account.save()
    return account
