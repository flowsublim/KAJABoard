"""Tests for Phase 9B1: Generic Incentive Engine Core."""

import datetime
from decimal import Decimal

import pytest
from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.catalog.models import UOM, Item
from apps.finance.models import (
    JournalEntry,
    JournalLine,
    LiquidityEntry,
    Payment,
)
from apps.incentives.models import (
    BeneficiaryKind,
    IncentiveAccrual,
    IncentiveAccrualState,
    IncentiveCalculationMethod,
    IncentiveRule,
    IncentiveTriggerType,
    IncentiveType,
)
from apps.incentives.selectors import (
    evaluate_incentive,
    resolve_incentive_rule,
)
from apps.incentives.services import (
    accrue_incentive,
    approve_incentive_accrual,
    create_incentive_rule,
    reverse_incentive_accrual,
    update_incentive_rule,
)
from apps.organizations.models import LegalEntity
from apps.projects.models import ProjectBudgetCategory
from apps.projects.selectors.profitability import PENDING_SOURCE, project_profitability
from apps.projects.services import create_draft_project
from apps.warehouse.models import StockMovement

User = get_user_model()


@pytest.fixture
def incentive_data():
    entity = LegalEntity.objects.create(code="E9B1", name="Entity 9B1")
    user = User.objects.create_user("user9b1@example.com", "password")

    uom = UOM.objects.create(code="PCS9B1", name="Pieces 9B1", dimension="COUNT")
    item_a = Item.objects.create(
        legal_entity=entity, code="ITEM-A", name="Product A", uom=uom, sales_eligible=True
    )
    item_b = Item.objects.create(
        legal_entity=entity, code="ITEM-B", name="Product B", uom=uom, sales_eligible=True
    )

    beneficiary = {
        "beneficiary_type": BeneficiaryKind.EMPLOYEE,
        "beneficiary_id": "EMP-001",
        "beneficiary_code": "SPV-01",
        "beneficiary_name": "Supervisor Ahmad",
    }

    return {
        "entity": entity,
        "user": user,
        "uom": uom,
        "item_a": item_a,
        "item_b": item_b,
        "beneficiary": beneficiary,
    }


# =========================================================================
# 1. Incentive app loads cleanly
# =========================================================================
def test_1_incentive_app_loads_cleanly():
    app_config = apps.get_app_config("incentives")
    assert app_config is not None
    assert app_config.name == "apps.incentives"


# =========================================================================
# 2. Effective-dated rule resolves on valid date
# =========================================================================
@pytest.mark.django_db
def test_2_effective_dated_rule_resolves_on_valid_date(incentive_data):
    entity = incentive_data["entity"]
    user = incentive_data["user"]

    rule = create_incentive_rule(
        legal_entity=entity,
        code="RULE-CPO-01",
        name="CPO Base Fee",
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        calculation_method=IncentiveCalculationMethod.PER_UNIT,
        rate_value=Decimal("500.0000"),
        effective_from=datetime.date(2026, 1, 1),
        effective_to=datetime.date(2026, 12, 31),
        actor=user,
    )

    status, resolved = resolve_incentive_rule(
        legal_entity=entity,
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        target_date=datetime.date(2026, 6, 15),
    )
    assert status == "RESOLVED"
    assert resolved == rule


# =========================================================================
# 3. Rule outside effective period does not resolve
# =========================================================================
@pytest.mark.django_db
def test_3_rule_outside_effective_period_does_not_resolve(incentive_data):
    entity = incentive_data["entity"]

    create_incentive_rule(
        legal_entity=entity,
        code="RULE-CPO-02",
        name="CPO 2026 Fee",
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        calculation_method=IncentiveCalculationMethod.PER_UNIT,
        rate_value=Decimal("500.0000"),
        effective_from=datetime.date(2026, 1, 1),
        effective_to=datetime.date(2026, 12, 31),
    )

    # Before effective_from
    status_before, rule_before = resolve_incentive_rule(
        legal_entity=entity,
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        target_date=datetime.date(2025, 12, 31),
    )
    assert status_before == "PENDING_RULE"
    assert rule_before is None

    # After effective_to
    status_after, rule_after = resolve_incentive_rule(
        legal_entity=entity,
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        target_date=datetime.date(2027, 1, 1),
    )
    assert status_after == "PENDING_RULE"
    assert rule_after is None


# =========================================================================
# 4. Inactive rule does not resolve
# =========================================================================
@pytest.mark.django_db
def test_4_inactive_rule_does_not_resolve(incentive_data):
    entity = incentive_data["entity"]

    create_incentive_rule(
        legal_entity=entity,
        code="RULE-INACTIVE",
        name="Inactive Fee",
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        calculation_method=IncentiveCalculationMethod.PER_UNIT,
        rate_value=Decimal("500.0000"),
        effective_from=datetime.date(2026, 1, 1),
        is_active=False,
    )

    status, rule = resolve_incentive_rule(
        legal_entity=entity,
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        target_date=datetime.date(2026, 6, 15),
    )
    assert status == "PENDING_RULE"
    assert rule is None


# =========================================================================
# 5. Overlapping rules for same exact context are blocked/ambiguous
# =========================================================================
@pytest.mark.django_db
def test_5_overlapping_rules_are_blocked_and_ambiguous(incentive_data):
    entity = incentive_data["entity"]

    create_incentive_rule(
        legal_entity=entity,
        code="RULE-DUP-1",
        name="Rule 1",
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        calculation_method=IncentiveCalculationMethod.PER_UNIT,
        rate_value=Decimal("500.0000"),
        effective_from=datetime.date(2026, 1, 1),
        effective_to=datetime.date(2026, 12, 31),
    )

    # Creating overlapping rule via service is blocked
    with pytest.raises(ValidationError):
        create_incentive_rule(
            legal_entity=entity,
            code="RULE-DUP-2",
            name="Rule 2",
            incentive_type=IncentiveType.CPO_FEE,
            trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
            calculation_method=IncentiveCalculationMethod.PER_UNIT,
            rate_value=Decimal("600.0000"),
            effective_from=datetime.date(2026, 6, 1),
            effective_to=datetime.date(2026, 12, 31),
        )

    # If an overlap somehow bypasses service validation, selector rejects as AMBIGUOUS_RULE
    IncentiveRule.objects.create(
        legal_entity=entity,
        code="RULE-DUP-DIRECT",
        name="Rule Direct",
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        calculation_method=IncentiveCalculationMethod.PER_UNIT,
        rate_value=Decimal("600.0000"),
        effective_from=datetime.date(2026, 6, 1),
        effective_to=datetime.date(2026, 12, 31),
        is_active=True,
    )
    status, rule = resolve_incentive_rule(
        legal_entity=entity,
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        target_date=datetime.date(2026, 7, 1),
    )
    assert status == "AMBIGUOUS_RULE"
    assert rule is None


# =========================================================================
# 6. Rule snapshot remains unchanged after master rule later changes
# =========================================================================
@pytest.mark.django_db
def test_6_rule_snapshot_remains_unchanged_after_master_changes(incentive_data):
    entity = incentive_data["entity"]
    user = incentive_data["user"]
    beneficiary = incentive_data["beneficiary"]

    rule = create_incentive_rule(
        legal_entity=entity,
        code="RULE-RATE-CHANGE",
        name="Rate to change",
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        calculation_method=IncentiveCalculationMethod.PER_UNIT,
        rate_value=Decimal("500.0000"),
        effective_from=datetime.date(2026, 1, 1),
    )

    accrual = accrue_incentive(
        legal_entity=entity,
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        business_date=datetime.date(2026, 3, 1),
        source_module="WAREHOUSE",
        source_type="WarehouseReceipt",
        source_document_id="WR-001",
        basis_quantity=Decimal("100"),
        beneficiary=beneficiary,
        actor=user,
    )

    assert accrual.rate_snapshot == Decimal("500.0000")
    assert accrual.amount == Decimal("50000.00")

    # Master rule changes rate to 750
    update_incentive_rule(rule, rate_value=Decimal("750.0000"), actor=user)
    rule.refresh_from_db()
    assert rule.rate_value == Decimal("750.0000")

    # Historical accrual remains unchanged
    accrual.refresh_from_db()
    assert accrual.rate_snapshot == Decimal("500.0000")
    assert accrual.amount == Decimal("50000.00")


# =========================================================================
# 7. PER_UNIT calculation: quantity × rate exact
# =========================================================================
@pytest.mark.django_db
def test_7_per_unit_calculation_exact(incentive_data):
    entity = incentive_data["entity"]
    beneficiary = incentive_data["beneficiary"]

    create_incentive_rule(
        legal_entity=entity,
        code="RULE-PER-UNIT",
        name="Per Unit Rule",
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        calculation_method=IncentiveCalculationMethod.PER_UNIT,
        rate_value=Decimal("1250.0000"),
        effective_from=datetime.date(2026, 1, 1),
    )

    res = evaluate_incentive(
        legal_entity=entity,
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        business_date=datetime.date(2026, 2, 1),
        basis_quantity=Decimal("40"),
        beneficiary=beneficiary,
    )

    assert res.status == "READY"
    assert res.calculated_amount == Decimal("50000")  # 40 * 1250 = 50,000


# =========================================================================
# 8. FIXED calculation exact
# =========================================================================
@pytest.mark.django_db
def test_8_fixed_calculation_exact(incentive_data):
    entity = incentive_data["entity"]
    beneficiary = incentive_data["beneficiary"]

    create_incentive_rule(
        legal_entity=entity,
        code="RULE-FIXED",
        name="Fixed Rule",
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.PROJECT_CLOSED,
        calculation_method=IncentiveCalculationMethod.FIXED,
        rate_value=Decimal("250000.0000"),
        effective_from=datetime.date(2026, 1, 1),
    )

    res = evaluate_incentive(
        legal_entity=entity,
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.PROJECT_CLOSED,
        business_date=datetime.date(2026, 2, 1),
        beneficiary=beneficiary,
    )

    assert res.status == "READY"
    assert res.calculated_amount == Decimal("250000")


# =========================================================================
# 9. Fractional-Rupiah result is blocked explicitly, not silently rounded
# =========================================================================
@pytest.mark.django_db
def test_9_fractional_rupiah_result_blocked(incentive_data):
    entity = incentive_data["entity"]
    beneficiary = incentive_data["beneficiary"]

    create_incentive_rule(
        legal_entity=entity,
        code="RULE-FRACTIONAL",
        name="Fractional Rule",
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        calculation_method=IncentiveCalculationMethod.PER_UNIT,
        rate_value=Decimal("333.3333"),
        effective_from=datetime.date(2026, 1, 1),
    )

    # 1 * 333.3333 = 333.3333 (fractional Rupiah)
    res = evaluate_incentive(
        legal_entity=entity,
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        business_date=datetime.date(2026, 2, 1),
        basis_quantity=Decimal("1"),
        beneficiary=beneficiary,
    )

    assert res.status == "NON_WHOLE_RUPIAH_RESULT"
    assert res.calculated_amount is None
    assert "fractional Rupiah" in res.reason


# =========================================================================
# 10. Unsupported calculation method is explicit, not guessed
# =========================================================================
@pytest.mark.django_db
def test_10_unsupported_calculation_method_is_explicit(incentive_data):
    entity = incentive_data["entity"]
    beneficiary = incentive_data["beneficiary"]

    create_incentive_rule(
        legal_entity=entity,
        code="RULE-UNSUPPORTED",
        name="Tiered Rule",
        incentive_type=IncentiveType.SALES_COMMISSION,
        trigger_type=IncentiveTriggerType.INVOICE_PAID,
        calculation_method=IncentiveCalculationMethod.TIERED,
        rate_value=Decimal("0.0500"),
        effective_from=datetime.date(2026, 1, 1),
    )

    res = evaluate_incentive(
        legal_entity=entity,
        incentive_type=IncentiveType.SALES_COMMISSION,
        trigger_type=IncentiveTriggerType.INVOICE_PAID,
        business_date=datetime.date(2026, 2, 1),
        beneficiary=beneficiary,
    )

    assert res.status == "UNSUPPORTED_METHOD"
    assert res.calculated_amount is None
    assert "not supported in Phase 9B1" in res.reason


# =========================================================================
# 11. Missing rule returns PENDING_RULE
# =========================================================================
@pytest.mark.django_db
def test_11_missing_rule_returns_pending_rule(incentive_data):
    entity = incentive_data["entity"]
    beneficiary = incentive_data["beneficiary"]

    res = evaluate_incentive(
        legal_entity=entity,
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        business_date=datetime.date(2026, 2, 1),
        basis_quantity=Decimal("50"),
        beneficiary=beneficiary,
    )

    assert res.status == "PENDING_RULE"
    assert res.rule is None


# =========================================================================
# 12. Missing beneficiary returns PENDING_BENEFICIARY
# =========================================================================
@pytest.mark.django_db
def test_12_missing_beneficiary_returns_pending_beneficiary(incentive_data):
    entity = incentive_data["entity"]

    create_incentive_rule(
        legal_entity=entity,
        code="RULE-NO-BEN",
        name="Rule",
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        calculation_method=IncentiveCalculationMethod.PER_UNIT,
        rate_value=Decimal("500.0000"),
        effective_from=datetime.date(2026, 1, 1),
    )

    res = evaluate_incentive(
        legal_entity=entity,
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        business_date=datetime.date(2026, 2, 1),
        basis_quantity=Decimal("50"),
        beneficiary=None,
    )

    assert res.status == "PENDING_BENEFICIARY"


# =========================================================================
# 13. Explicit beneficiary snapshot is persisted
# =========================================================================
@pytest.mark.django_db
def test_13_explicit_beneficiary_snapshot_persisted(incentive_data):
    entity = incentive_data["entity"]
    user = incentive_data["user"]
    beneficiary = incentive_data["beneficiary"]

    create_incentive_rule(
        legal_entity=entity,
        code="RULE-BEN-SNAP",
        name="Rule",
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        calculation_method=IncentiveCalculationMethod.PER_UNIT,
        rate_value=Decimal("500.0000"),
        effective_from=datetime.date(2026, 1, 1),
    )

    accrual = accrue_incentive(
        legal_entity=entity,
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        business_date=datetime.date(2026, 3, 1),
        source_module="WAREHOUSE",
        source_type="WarehouseReceipt",
        source_document_id="WR-SNAP",
        basis_quantity=Decimal("10"),
        beneficiary=beneficiary,
        actor=user,
    )

    assert accrual.beneficiary_type == BeneficiaryKind.EMPLOYEE
    assert accrual.beneficiary_id == "EMP-001"
    assert accrual.beneficiary_code_snapshot == "SPV-01"
    assert accrual.beneficiary_name_snapshot == "Supervisor Ahmad"


# =========================================================================
# 14. Accrual amount is whole Rupiah
# =========================================================================
@pytest.mark.django_db
def test_14_accrual_amount_is_whole_rupiah(incentive_data):
    entity = incentive_data["entity"]
    user = incentive_data["user"]
    beneficiary = incentive_data["beneficiary"]

    create_incentive_rule(
        legal_entity=entity,
        code="RULE-WHOLE",
        name="Rule",
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        calculation_method=IncentiveCalculationMethod.PER_UNIT,
        rate_value=Decimal("1500.0000"),
        effective_from=datetime.date(2026, 1, 1),
    )

    accrual = accrue_incentive(
        legal_entity=entity,
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        business_date=datetime.date(2026, 3, 1),
        source_module="WAREHOUSE",
        source_type="WarehouseReceipt",
        source_document_id="WR-WHOLE",
        basis_quantity=Decimal("3"),
        beneficiary=beneficiary,
        actor=user,
    )

    assert accrual.amount == Decimal("4500.00")
    assert accrual.amount % Decimal("1") == Decimal("0")


# =========================================================================
# 15. Accrual source identity is deterministic
# =========================================================================
@pytest.mark.django_db
def test_15_accrual_source_identity_is_deterministic(incentive_data):
    entity = incentive_data["entity"]
    user = incentive_data["user"]
    beneficiary = incentive_data["beneficiary"]

    create_incentive_rule(
        legal_entity=entity,
        code="RULE-DET",
        name="Rule",
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        calculation_method=IncentiveCalculationMethod.PER_UNIT,
        rate_value=Decimal("1000.0000"),
        effective_from=datetime.date(2026, 1, 1),
    )

    accrual = accrue_incentive(
        legal_entity=entity,
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        business_date=datetime.date(2026, 3, 1),
        source_module="WAREHOUSE",
        source_type="WarehouseReceipt",
        source_document_id="WR-DET-001",
        source_line_id="L-1",
        basis_quantity=Decimal("5"),
        beneficiary=beneficiary,
        actor=user,
    )

    expected_key = "CPO_FEE|WAREHOUSE|WarehouseReceipt|WR-DET-001|L-1"
    assert accrual.source_key == expected_key


# =========================================================================
# 16. Same idempotency/source retry creates only one accrual
# =========================================================================
@pytest.mark.django_db
def test_16_same_idempotency_retry_creates_one_accrual(incentive_data):
    entity = incentive_data["entity"]
    user = incentive_data["user"]
    beneficiary = incentive_data["beneficiary"]

    create_incentive_rule(
        legal_entity=entity,
        code="RULE-RETRY",
        name="Rule",
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        calculation_method=IncentiveCalculationMethod.PER_UNIT,
        rate_value=Decimal("1000.0000"),
        effective_from=datetime.date(2026, 1, 1),
    )

    accrual1 = accrue_incentive(
        legal_entity=entity,
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        business_date=datetime.date(2026, 3, 1),
        source_module="WAREHOUSE",
        source_type="WarehouseReceipt",
        source_document_id="WR-RETRY",
        basis_quantity=Decimal("10"),
        beneficiary=beneficiary,
        actor=user,
    )

    count_before = IncentiveAccrual.objects.count()

    accrual2 = accrue_incentive(
        legal_entity=entity,
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        business_date=datetime.date(2026, 3, 1),
        source_module="WAREHOUSE",
        source_type="WarehouseReceipt",
        source_document_id="WR-RETRY",
        basis_quantity=Decimal("10"),
        beneficiary=beneficiary,
        actor=user,
    )

    assert accrual1.pk == accrual2.pk
    assert IncentiveAccrual.objects.count() == count_before


# =========================================================================
# 17. Same key with materially different payload is rejected
# =========================================================================
@pytest.mark.django_db
def test_17_same_key_different_payload_is_rejected(incentive_data):
    entity = incentive_data["entity"]
    user = incentive_data["user"]
    beneficiary = incentive_data["beneficiary"]

    create_incentive_rule(
        legal_entity=entity,
        code="RULE-MISMATCH",
        name="Rule",
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        calculation_method=IncentiveCalculationMethod.PER_UNIT,
        rate_value=Decimal("1000.0000"),
        effective_from=datetime.date(2026, 1, 1),
    )

    accrue_incentive(
        legal_entity=entity,
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        business_date=datetime.date(2026, 3, 1),
        source_module="WAREHOUSE",
        source_type="WarehouseReceipt",
        source_document_id="WR-SAME-KEY",
        basis_quantity=Decimal("10"),
        beneficiary=beneficiary,
        actor=user,
    )

    # Different quantity for same source_key must raise ValidationError
    with pytest.raises(ValidationError):
        accrue_incentive(
            legal_entity=entity,
            incentive_type=IncentiveType.CPO_FEE,
            trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
            business_date=datetime.date(2026, 3, 1),
            source_module="WAREHOUSE",
            source_type="WarehouseReceipt",
            source_document_id="WR-SAME-KEY",
            basis_quantity=Decimal("999"),  # Mismatched payload
            beneficiary=beneficiary,
            actor=user,
        )


# =========================================================================
# 18. Rule effective date uses source/accrual business date, not master date
# =========================================================================
@pytest.mark.django_db
def test_18_rule_effective_date_uses_business_date(incentive_data):
    entity = incentive_data["entity"]
    user = incentive_data["user"]
    beneficiary = incentive_data["beneficiary"]

    # Rule effective only in Q1 2026
    create_incentive_rule(
        legal_entity=entity,
        code="RULE-Q1",
        name="Q1 Rule",
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        calculation_method=IncentiveCalculationMethod.PER_UNIT,
        rate_value=Decimal("500.0000"),
        effective_from=datetime.date(2026, 1, 1),
        effective_to=datetime.date(2026, 3, 31),
    )

    # Business date in Q1 resolves
    accrual = accrue_incentive(
        legal_entity=entity,
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        business_date=datetime.date(2026, 2, 15),
        source_module="WAREHOUSE",
        source_type="WarehouseReceipt",
        source_document_id="WR-Q1",
        basis_quantity=Decimal("10"),
        beneficiary=beneficiary,
        actor=user,
    )
    assert accrual.rule_code_snapshot == "RULE-Q1"

    # Business date outside Q1 fails
    with pytest.raises(ValidationError):
        accrue_incentive(
            legal_entity=entity,
            incentive_type=IncentiveType.CPO_FEE,
            trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
            business_date=datetime.date(2026, 5, 1),
            source_module="WAREHOUSE",
            source_type="WarehouseReceipt",
            source_document_id="WR-Q2",
            basis_quantity=Decimal("10"),
            beneficiary=beneficiary,
            actor=user,
        )


# =========================================================================
# 19. Accrual starts ACCRUED
# =========================================================================
@pytest.mark.django_db
def test_19_accrual_starts_accrued(incentive_data):
    entity = incentive_data["entity"]
    user = incentive_data["user"]
    beneficiary = incentive_data["beneficiary"]

    create_incentive_rule(
        legal_entity=entity,
        code="RULE-START-STATE",
        name="Rule",
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        calculation_method=IncentiveCalculationMethod.PER_UNIT,
        rate_value=Decimal("500.0000"),
        effective_from=datetime.date(2026, 1, 1),
    )

    accrual = accrue_incentive(
        legal_entity=entity,
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        business_date=datetime.date(2026, 2, 1),
        source_module="WAREHOUSE",
        source_type="WarehouseReceipt",
        source_document_id="WR-INIT",
        basis_quantity=Decimal("10"),
        beneficiary=beneficiary,
        actor=user,
    )
    assert accrual.state == IncentiveAccrualState.ACCRUED


# =========================================================================
# 20. ACCRUED -> APPROVED works through service
# =========================================================================
@pytest.mark.django_db
def test_20_accrued_to_approved_works_through_service(incentive_data):
    entity = incentive_data["entity"]
    user = incentive_data["user"]
    beneficiary = incentive_data["beneficiary"]

    create_incentive_rule(
        legal_entity=entity,
        code="RULE-APPROVE",
        name="Rule",
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        calculation_method=IncentiveCalculationMethod.PER_UNIT,
        rate_value=Decimal("500.0000"),
        effective_from=datetime.date(2026, 1, 1),
    )

    accrual = accrue_incentive(
        legal_entity=entity,
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        business_date=datetime.date(2026, 2, 1),
        source_module="WAREHOUSE",
        source_type="WarehouseReceipt",
        source_document_id="WR-APP",
        basis_quantity=Decimal("10"),
        beneficiary=beneficiary,
        actor=user,
    )

    approved = approve_incentive_accrual(accrual, actor=user)
    assert approved.state == IncentiveAccrualState.APPROVED


# =========================================================================
# 21. Illegal state transition is rejected
# =========================================================================
@pytest.mark.django_db
def test_21_illegal_state_transition_is_rejected(incentive_data):
    entity = incentive_data["entity"]
    user = incentive_data["user"]
    beneficiary = incentive_data["beneficiary"]

    create_incentive_rule(
        legal_entity=entity,
        code="RULE-TRANS",
        name="Rule",
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        calculation_method=IncentiveCalculationMethod.PER_UNIT,
        rate_value=Decimal("500.0000"),
        effective_from=datetime.date(2026, 1, 1),
    )

    accrual = accrue_incentive(
        legal_entity=entity,
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        business_date=datetime.date(2026, 2, 1),
        source_module="WAREHOUSE",
        source_type="WarehouseReceipt",
        source_document_id="WR-ILLEGAL",
        basis_quantity=Decimal("10"),
        beneficiary=beneficiary,
        actor=user,
    )

    approve_incentive_accrual(accrual, actor=user)

    # Approving already APPROVED accrual must fail
    with pytest.raises(ValidationError):
        approve_incentive_accrual(accrual, actor=user)


# =========================================================================
# 22. Reversal requires reason
# =========================================================================
@pytest.mark.django_db
def test_22_reversal_requires_reason(incentive_data):
    entity = incentive_data["entity"]
    user = incentive_data["user"]
    beneficiary = incentive_data["beneficiary"]

    create_incentive_rule(
        legal_entity=entity,
        code="RULE-REV-REASON",
        name="Rule",
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        calculation_method=IncentiveCalculationMethod.PER_UNIT,
        rate_value=Decimal("500.0000"),
        effective_from=datetime.date(2026, 1, 1),
    )

    accrual = accrue_incentive(
        legal_entity=entity,
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        business_date=datetime.date(2026, 2, 1),
        source_module="WAREHOUSE",
        source_type="WarehouseReceipt",
        source_document_id="WR-REV-REASON",
        basis_quantity=Decimal("10"),
        beneficiary=beneficiary,
        actor=user,
    )

    # Empty reason fails
    with pytest.raises(ValidationError):
        reverse_incentive_accrual(accrual, actor=user, reason="")

    # Whitespace-only reason fails
    with pytest.raises(ValidationError):
        reverse_incentive_accrual(accrual, actor=user, reason="   ")


# =========================================================================
# 23. Reversal retains original rate/basis/beneficiary/amount snapshots
# =========================================================================
@pytest.mark.django_db
def test_23_reversal_retains_original_snapshots(incentive_data):
    entity = incentive_data["entity"]
    user = incentive_data["user"]
    beneficiary = incentive_data["beneficiary"]

    create_incentive_rule(
        legal_entity=entity,
        code="RULE-REV-SNAP",
        name="Rule",
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        calculation_method=IncentiveCalculationMethod.PER_UNIT,
        rate_value=Decimal("500.0000"),
        effective_from=datetime.date(2026, 1, 1),
    )

    accrual = accrue_incentive(
        legal_entity=entity,
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        business_date=datetime.date(2026, 2, 1),
        source_module="WAREHOUSE",
        source_type="WarehouseReceipt",
        source_document_id="WR-REV-SNAP",
        basis_quantity=Decimal("20"),
        beneficiary=beneficiary,
        actor=user,
    )

    reversed_accrual = reverse_incentive_accrual(
        accrual, actor=user, reason="Receipt cancelled due to QC defect"
    )

    assert reversed_accrual.state == IncentiveAccrualState.REVERSED
    assert reversed_accrual.rate_snapshot == Decimal("500.0000")
    assert reversed_accrual.basis_quantity == Decimal("20")
    assert reversed_accrual.amount == Decimal("10000.00")
    assert reversed_accrual.beneficiary_id == "EMP-001"
    assert reversed_accrual.beneficiary_name_snapshot == "Supervisor Ahmad"
    assert hasattr(reversed_accrual, "reversal")
    assert reversed_accrual.reversal.reason == "Receipt cancelled due to QC defect"


# =========================================================================
# 24. Reversal cannot create duplicate reversal
# =========================================================================
@pytest.mark.django_db
def test_24_cannot_create_duplicate_reversal(incentive_data):
    entity = incentive_data["entity"]
    user = incentive_data["user"]
    beneficiary = incentive_data["beneficiary"]

    create_incentive_rule(
        legal_entity=entity,
        code="RULE-DUP-REV",
        name="Rule",
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        calculation_method=IncentiveCalculationMethod.PER_UNIT,
        rate_value=Decimal("500.0000"),
        effective_from=datetime.date(2026, 1, 1),
    )

    accrual = accrue_incentive(
        legal_entity=entity,
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        business_date=datetime.date(2026, 2, 1),
        source_module="WAREHOUSE",
        source_type="WarehouseReceipt",
        source_document_id="WR-DUP-REV",
        basis_quantity=Decimal("10"),
        beneficiary=beneficiary,
        actor=user,
    )

    reverse_incentive_accrual(accrual, actor=user, reason="First reversal")

    with pytest.raises(ValidationError):
        reverse_incentive_accrual(accrual, actor=user, reason="Second reversal")


# =========================================================================
# 25. Evaluation creates zero IncentiveAccrual rows
# =========================================================================
@pytest.mark.django_db
def test_25_evaluation_creates_zero_accrual_rows(incentive_data):
    entity = incentive_data["entity"]
    beneficiary = incentive_data["beneficiary"]

    create_incentive_rule(
        legal_entity=entity,
        code="RULE-ZERO-WRITE",
        name="Rule",
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        calculation_method=IncentiveCalculationMethod.PER_UNIT,
        rate_value=Decimal("500.0000"),
        effective_from=datetime.date(2026, 1, 1),
    )

    count_before = IncentiveAccrual.objects.count()

    evaluate_incentive(
        legal_entity=entity,
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        business_date=datetime.date(2026, 2, 1),
        basis_quantity=Decimal("100"),
        beneficiary=beneficiary,
    )

    assert IncentiveAccrual.objects.count() == count_before


# =========================================================================
# 26. Evaluation/accrual/reversal create zero accounting or stock records
# =========================================================================
@pytest.mark.django_db
def test_26_zero_accounting_or_stock_records_created(incentive_data):
    entity = incentive_data["entity"]
    user = incentive_data["user"]
    beneficiary = incentive_data["beneficiary"]

    create_incentive_rule(
        legal_entity=entity,
        code="RULE-BOUNDARY",
        name="Rule",
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        calculation_method=IncentiveCalculationMethod.PER_UNIT,
        rate_value=Decimal("500.0000"),
        effective_from=datetime.date(2026, 1, 1),
    )

    counts_before = {
        "JournalEntry": JournalEntry.objects.count(),
        "JournalLine": JournalLine.objects.count(),
        "Payment": Payment.objects.count(),
        "LiquidityEntry": LiquidityEntry.objects.count(),
        "StockMovement": StockMovement.objects.count(),
    }

    # Evaluate
    evaluate_incentive(
        legal_entity=entity,
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        business_date=datetime.date(2026, 2, 1),
        basis_quantity=Decimal("100"),
        beneficiary=beneficiary,
    )

    # Accrue
    accrual = accrue_incentive(
        legal_entity=entity,
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        business_date=datetime.date(2026, 2, 1),
        source_module="WAREHOUSE",
        source_type="WarehouseReceipt",
        source_document_id="WR-BOUNDARY",
        basis_quantity=Decimal("100"),
        beneficiary=beneficiary,
        actor=user,
    )

    # Approve
    approve_incentive_accrual(accrual, actor=user)

    # Reverse
    reverse_incentive_accrual(accrual, actor=user, reason="Boundary test reversal")

    counts_after = {
        "JournalEntry": JournalEntry.objects.count(),
        "JournalLine": JournalLine.objects.count(),
        "Payment": Payment.objects.count(),
        "LiquidityEntry": LiquidityEntry.objects.count(),
        "StockMovement": StockMovement.objects.count(),
    }

    assert counts_before == counts_after


# =========================================================================
# 27. No source beneficiary is inferred from created_by/posted_by/current user
# =========================================================================
@pytest.mark.django_db
def test_27_no_beneficiary_inferred_from_user(incentive_data):
    entity = incentive_data["entity"]
    user = incentive_data["user"]

    create_incentive_rule(
        legal_entity=entity,
        code="RULE-NO-INFER",
        name="Rule",
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        calculation_method=IncentiveCalculationMethod.PER_UNIT,
        rate_value=Decimal("500.0000"),
        effective_from=datetime.date(2026, 1, 1),
    )

    # Accruing with empty beneficiary must fail, never silently assigning actor
    with pytest.raises(ValidationError):
        accrue_incentive(
            legal_entity=entity,
            incentive_type=IncentiveType.CPO_FEE,
            trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
            business_date=datetime.date(2026, 2, 1),
            source_module="WAREHOUSE",
            source_type="WarehouseReceipt",
            source_document_id="WR-NO-INFER",
            basis_quantity=Decimal("100"),
            beneficiary=None,
            actor=user,
        )


# =========================================================================
# 28. Phase 9A CPO_FEE and SALES_FEE remain PENDING_SOURCE
# =========================================================================
@pytest.mark.django_db
def test_28_phase_9a_profitability_categories_remain_pending_source(incentive_data):
    entity = incentive_data["entity"]
    user = incentive_data["user"]

    from apps.partners.models import BusinessPartner, PartnerRole, PartnerRoleType

    customer = BusinessPartner.objects.create(
        legal_entity=entity, code="CUST-9B1", display_name="Cust 9B1"
    )
    PartnerRole.objects.create(partner=customer, role_type=PartnerRoleType.CUSTOMER)

    from apps.core.services.numbering import create_document_sequence

    create_document_sequence(
        legal_entity=entity,
        document_type="PROJECT",
        name="PROJECT",
        prefix="PRJ",
        format_template="{prefix}-{yyyymmdd}-{seq}",
        padding=3,
    )

    project = create_draft_project(
        legal_entity=entity,
        customer=customer,
        name="Project 9B1",
        start_date=timezone.localdate(),
        actor=user,
        idempotency_key="prj-9b1-init",
    )

    prof = project_profitability(project)
    # Both remain strictly PENDING_SOURCE in Phase 9B1
    assert prof.actual_categories[ProjectBudgetCategory.CPO_FEE].availability == PENDING_SOURCE
    assert prof.actual_categories[ProjectBudgetCategory.SALES_FEE].availability == PENDING_SOURCE


# =========================================================================
# 29. legacy/smb_gas remains untouched
# =========================================================================
def test_29_legacy_smb_gas_remains_untouched():
    import hashlib
    import pathlib

    root = pathlib.Path("legacy/smb_gas")
    files = sorted([f for f in root.rglob("*") if f.is_file()])
    assert len(files) == 50

    lines = []
    for f in files:
        rel_path = f.relative_to(root).as_posix()
        content = f.read_bytes()
        file_bytes = len(content)
        file_sha256 = hashlib.sha256(content).hexdigest().upper()
        lines.append(f"{rel_path}|{file_bytes}|{file_sha256}")

    aggregate_input = "\n".join(lines).encode("utf-8")
    aggregate_hash = hashlib.sha256(aggregate_input).hexdigest().upper()
    assert aggregate_hash == "66F614E4A728F3A7EB8811A39C58EB6F88B16BB4C554DFF96114C569FB6031C2"


# =========================================================================
# Item-scoped rules tests
# =========================================================================
@pytest.mark.django_db
def test_item_scoped_rule_selection(incentive_data):
    entity = incentive_data["entity"]
    item_a = incentive_data["item_a"]
    item_b = incentive_data["item_b"]

    # Rule specific to Item A
    rule_a = create_incentive_rule(
        legal_entity=entity,
        code="RULE-ITEM-A",
        name="Rule Item A",
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        calculation_method=IncentiveCalculationMethod.PER_UNIT,
        rate_value=Decimal("800.0000"),
        effective_from=datetime.date(2026, 1, 1),
        item=item_a,
    )

    # Resolving for Item A returns rule_a
    status_a, resolved_a = resolve_incentive_rule(
        legal_entity=entity,
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        target_date=datetime.date(2026, 2, 1),
        item=item_a,
    )
    assert status_a == "RESOLVED"
    assert resolved_a == rule_a

    # Resolving for Item B (no rule for B) returns PENDING_RULE (no silent fallback)
    status_b, resolved_b = resolve_incentive_rule(
        legal_entity=entity,
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        target_date=datetime.date(2026, 2, 1),
        item=item_b,
    )
    assert status_b == "PENDING_RULE"
    assert resolved_b is None

    # Unscoped resolution does not resolve Item A rule
    status_unscoped, resolved_unscoped = resolve_incentive_rule(
        legal_entity=entity,
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        target_date=datetime.date(2026, 2, 1),
        item=None,
    )
    assert status_unscoped == "PENDING_RULE"
    assert resolved_unscoped is None


# =========================================================================
# LegalEntity consistency tests
# =========================================================================
@pytest.mark.django_db
def test_legal_entity_consistency_enforced(incentive_data):
    entity = incentive_data["entity"]
    user = incentive_data["user"]
    uom = incentive_data["uom"]
    beneficiary = incentive_data["beneficiary"]

    other_entity = LegalEntity.objects.create(code="OTHER", name="Other Entity")
    other_item = Item.objects.create(
        legal_entity=other_entity,
        code="OTHER-ITEM",
        name="Other Item",
        uom=uom,
        sales_eligible=True,
    )

    # 1. IncentiveRule rejects item from different legal entity
    with pytest.raises(ValidationError):
        create_incentive_rule(
            legal_entity=entity,
            code="RULE-DIFF-ENTITY",
            name="Rule Diff Entity",
            incentive_type=IncentiveType.CPO_FEE,
            trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
            calculation_method=IncentiveCalculationMethod.PER_UNIT,
            rate_value=Decimal("500.0000"),
            effective_from=datetime.date(2026, 1, 1),
            item=other_item,
        )

    # Valid rule for entity
    create_incentive_rule(
        legal_entity=entity,
        code="RULE-SAME-ENTITY",
        name="Rule Same Entity",
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        calculation_method=IncentiveCalculationMethod.PER_UNIT,
        rate_value=Decimal("500.0000"),
        effective_from=datetime.date(2026, 1, 1),
    )

    # 2. Evaluation rejects item from different legal entity
    res_item = evaluate_incentive(
        legal_entity=entity,
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        business_date=datetime.date(2026, 2, 1),
        basis_quantity=Decimal("10"),
        beneficiary=beneficiary,
        item=other_item,
    )
    assert res_item.status == "INVALID_CONTEXT"
    assert "Item legal entity must match" in res_item.reason

    # 3. Accrual rejects item from different legal entity
    with pytest.raises(ValidationError) as exc_item:
        accrue_incentive(
            legal_entity=entity,
            incentive_type=IncentiveType.CPO_FEE,
            trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
            business_date=datetime.date(2026, 2, 1),
            source_module="WAREHOUSE",
            source_type="WarehouseReceipt",
            source_document_id="WR-DIFF-ITEM",
            basis_quantity=Decimal("10"),
            beneficiary=beneficiary,
            item=other_item,
            actor=user,
        )
    assert "Item legal entity must match" in str(exc_item.value)

    # 4. Accrual directly created rejects mismatched rule legal entity
    other_rule = create_incentive_rule(
        legal_entity=other_entity,
        code="RULE-OTHER",
        name="Rule Other",
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        calculation_method=IncentiveCalculationMethod.PER_UNIT,
        rate_value=Decimal("500.0000"),
        effective_from=datetime.date(2026, 1, 1),
    )
    mismatched_accrual = IncentiveAccrual(
        legal_entity=entity,
        incentive_type=IncentiveType.CPO_FEE,
        source_key="TEST-MISMATCH-RULE",
        source_module="WAREHOUSE",
        source_type="WarehouseReceipt",
        source_document_id="WR-01",
        accrual_date=datetime.date(2026, 2, 1),
        rule=other_rule,
        rule_code_snapshot=other_rule.code,
        trigger_snapshot=other_rule.trigger_type,
        calculation_method_snapshot=other_rule.calculation_method,
        rate_snapshot=other_rule.rate_value,
        currency_snapshot=other_rule.currency,
        beneficiary_type=BeneficiaryKind.EMPLOYEE,
        beneficiary_id="EMP-01",
        beneficiary_name_snapshot="Test",
        amount=Decimal("5000.00"),
        created_by=user,
    )
    with pytest.raises(ValidationError) as exc_rule:
        mismatched_accrual.clean()
    assert "Rule legal entity must match accrual legal entity" in str(exc_rule.value)
