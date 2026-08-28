from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.accounts.models import Employee
from apps.catalog.models import UOM, Item
from apps.core.services.numbering import create_document_sequence
from apps.organizations.models import LegalEntity, OrganizationMembership
from apps.production.models import (
    ProductionDirectExtraCost,
    ProductionEntryState,
    ProductionLaborCost,
    ProductionStage,
    ProductionTariff,
    ProductionWageMethod,
)
from apps.production.selectors.wip import (
    material_issue_candidates,
    output_wip,
    production_completion_readiness,
    warehouse_receipt_candidates,
)
from apps.production.services.production import (
    add_draft_reject_line,
    add_draft_work_line,
    add_handover_line,
    create_direct_extra_cost,
    create_draft_reject_entry,
    create_draft_work_entry,
    create_handover_draft,
    mark_handover_ready,
    post_direct_extra_cost,
    post_reject_entry,
    post_work_entry,
    reverse_direct_extra_cost,
    reverse_handover_line,
    reverse_reject_line,
    reverse_work_line,
)
from apps.purchasing.models import WorkOrderState, WorkOrderType
from apps.purchasing.services.work_orders import (
    add_material_allocation,
    add_work_order_output,
    approve_work_order,
    create_draft_work_order,
    submit_work_order,
)

User = get_user_model()


def _foundation(code="PROD", outputs=2):
    entity = LegalEntity.objects.create(code=code, name=f"{code} Entity")
    user = User.objects.create_user(f"{code.lower()}@example.com", "password")
    OrganizationMembership.objects.create(user=user, legal_entity=entity)
    uom = UOM.objects.create(
        code=f"{code}PCS", name="Pieces", dimension="COUNT", effective_from=date(2026, 1, 1)
    )
    items = [
        Item.objects.create(
            legal_entity=entity,
            code=f"{code}OUT{i}",
            name=f"Output {i}",
            uom=uom,
            production_eligible=True,
            effective_from=date(2026, 1, 1),
        )
        for i in range(outputs)
    ]
    material = Item.objects.create(
        legal_entity=entity,
        code=f"{code}MAT",
        name="Material",
        uom=uom,
        inventory_eligible=True,
        effective_from=date(2026, 1, 1),
    )
    create_document_sequence(
        legal_entity=entity,
        document_type="WORK_ORDER",
        name="SPK",
        prefix="SPK",
        format_template="{prefix}-{yyyymmdd}-{seq}",
        padding=3,
        effective_from=date(2026, 1, 1),
    )
    work_order = create_draft_work_order(
        legal_entity=entity,
        document_date=date(2026, 8, 27),
        work_order_type=WorkOrderType.INTERNAL,
        actor=user,
    )
    output_lines = [
        add_work_order_output(work_order, item=item, target_quantity="100", actor=user)
        for item in items
    ]
    add_material_allocation(
        work_order,
        output=output_lines[0],
        material_item=material,
        planned_quantity="12",
        reference_cost=None,
        actor=user,
    )
    submit_work_order(work_order, actor=user)
    approve_work_order(work_order, actor=user)
    return entity, user, work_order, output_lines


def _post_work(entity, user, order, output_quantities, stage, key):
    entry = create_draft_work_entry(
        legal_entity=entity,
        work_order=order,
        production_date=date(2026, 8, 27),
        stage=stage,
        actor=user,
    )
    for output, quantity in output_quantities:
        add_draft_work_line(entry, output=output, quantity=quantity, actor=user)
    return post_work_entry(entry, actor=user, idempotency_key=key)


def _post_reject(entity, user, order, output_quantities, key):
    entry = create_draft_reject_entry(
        legal_entity=entity, work_order=order, production_date=date(2026, 8, 27), actor=user
    )
    for output, stage, quantity in output_quantities:
        add_draft_reject_line(
            entry, output=output, stage=stage, quantity=quantity, reason="Defect", actor=user
        )
    return post_reject_entry(entry, actor=user, idempotency_key=key)


def _ready_handover(entity, user, order, output_quantities, key):
    handover = create_handover_draft(
        legal_entity=entity,
        work_order=order,
        handover_date=date(2026, 8, 27),
        actor=user,
    )
    for output, quantity in output_quantities:
        add_handover_line(handover, output=output, quantity=quantity, actor=user)
    return mark_handover_ready(handover, actor=user, idempotency_key=key)


@pytest.mark.django_db
def test_internal_source_and_item_level_wip_formulae_and_material_contract():
    entity, user, order, (output_a, output_b) = _foundation()
    _post_work(entity, user, order, [(output_a, "100")], ProductionStage.CUT, "cut")
    _post_work(entity, user, order, [(output_a, "40")], ProductionStage.SEW, "sew")
    _post_reject(entity, user, order, [(output_a, ProductionStage.CUT, "10")], "reject-cut")
    summary = output_wip(output_a)
    assert summary.available_sewing == Decimal("50")
    assert output_wip(output_b).available_sewing == Decimal("0")
    candidates = material_issue_candidates(user, work_order=order)
    assert candidates[0]["source_key"].startswith("PROD_MATERIAL_REQ|")
    assert candidates[0]["reference_cost"] is None
    assert candidates[0]["state"] == "ACTIVE"


@pytest.mark.django_db
def test_sew_qc_and_same_output_multiline_are_aggregated_atomically():
    entity, user, order, (output_a, output_b) = _foundation("AGG")
    _post_work(
        entity, user, order, [(output_a, "100"), (output_b, "10")], ProductionStage.CUT, "cut"
    )
    entry = create_draft_work_entry(
        legal_entity=entity,
        work_order=order,
        production_date=date(2026, 8, 27),
        stage=ProductionStage.SEW,
        actor=user,
    )
    add_draft_work_line(entry, output=output_a, quantity="30", actor=user)
    add_draft_work_line(entry, output=output_a, quantity="71", actor=user)
    with pytest.raises(ValidationError):
        post_work_entry(entry, actor=user, idempotency_key="bad-sew")
    assert entry.state == ProductionEntryState.DRAFT
    _post_work(entity, user, order, [(output_a, "70")], ProductionStage.SEW, "sew")
    _post_work(entity, user, order, [(output_a, "30")], ProductionStage.QC_PACKING, "qc")
    _post_reject(entity, user, order, [(output_a, ProductionStage.SEW, "5")], "reject-sew")
    assert output_wip(output_a).available_qc == Decimal("35")
    with pytest.raises(ValidationError):
        _post_work(entity, user, order, [(output_a, "36")], ProductionStage.QC_PACKING, "bad-qc")
    _post_reject(entity, user, order, [(output_a, ProductionStage.QC_PACKING, "6")], "reject-qc")
    assert output_wip(output_a).qc_ready_quantity == Decimal("24")


@pytest.mark.django_db
def test_reject_and_reversal_are_output_specific_and_sibling_safe():
    entity, user, order, (output_a, output_b) = _foundation("REV")
    entry = _post_work(
        entity, user, order, [(output_a, "20"), (output_b, "30")], ProductionStage.CUT, "cut"
    )
    first, second = entry.lines.order_by("sequence")
    reversal = reverse_work_line(
        first, reason="Input salah", actor=user, idempotency_key="reverse-a"
    )
    assert reversal.original_line_id == first.pk
    assert entry.lines.filter(pk=second.pk).exists()
    assert output_wip(output_a).cut_quantity == Decimal("0")
    assert output_wip(output_b).cut_quantity == Decimal("30")
    reject = _post_reject(entity, user, order, [(output_b, ProductionStage.CUT, "10")], "rej")
    reject_line = reject.lines.get()
    reverse_reject_line(reject_line, reason="Recheck", actor=user, idempotency_key="reverse-reject")
    assert output_wip(output_b).available_sewing == Decimal("30")


@pytest.mark.django_db
def test_work_reversal_cannot_overconsume_downstream_and_is_idempotent():
    entity, user, order, (output_a, _) = _foundation("SAFE")
    cut = _post_work(entity, user, order, [(output_a, "20")], ProductionStage.CUT, "cut")
    _post_work(entity, user, order, [(output_a, "15")], ProductionStage.SEW, "sew")
    with pytest.raises(ValidationError):
        reverse_work_line(cut.lines.get(), reason="Too much", actor=user, idempotency_key="unsafe")
    entity2, user2, order2, (other, _) = _foundation("IDEM")
    posted = _post_work(entity2, user2, order2, [(other, "8")], ProductionStage.CUT, "same")
    assert post_work_entry(posted, actor=user2, idempotency_key="same") == posted


@pytest.mark.django_db
def test_source_eligibility_rejects_subcontract_nonapproved_void_and_cross_entity():
    entity, user, order, (output_a, _) = _foundation("SRC")
    order.work_order_type = WorkOrderType.SUBCONTRACT
    order.save(update_fields=("work_order_type",))
    with pytest.raises(ValidationError):
        create_draft_work_entry(
            legal_entity=entity,
            work_order=order,
            production_date=date.today(),
            stage=ProductionStage.CUT,
            actor=user,
        )
    order.work_order_type = WorkOrderType.INTERNAL
    order.state = WorkOrderState.DRAFT
    order.save(update_fields=("work_order_type", "state"))
    with pytest.raises(ValidationError):
        create_draft_work_entry(
            legal_entity=entity,
            work_order=order,
            production_date=date.today(),
            stage=ProductionStage.CUT,
            actor=user,
        )
    other_entity, _, _, _ = _foundation("SRC2")
    with pytest.raises(ValidationError):
        create_draft_work_entry(
            legal_entity=other_entity,
            work_order=order,
            production_date=date.today(),
            stage=ProductionStage.CUT,
            actor=user,
        )
    assert output_a.pk


@pytest.mark.django_db
def test_production_namespace_home_sidebar_and_permission_boundary(client):
    entity, user, _, _ = _foundation("UI")
    assert reverse("production:wip-list") == "/production/"
    client.force_login(user)
    assert client.get(reverse("production:wip-list")).status_code == 403
    hidden = client.get(reverse("home:home"))
    assert hidden.status_code == 200
    assert b"WIP Produksi" not in hidden.content
    user.user_permissions.add(Permission.objects.get(codename="view_productionworkentry"))
    response = client.get(reverse("home:home"))
    assert (
        response.status_code == 200
        and b"Produksi" in response.content
        and b"WIP Produksi" in response.content
    )
    assert client.get(reverse("production:wip-list")).status_code == 200


@pytest.mark.django_db
def test_superuser_home_renders_production_sidebar(client):
    admin = User.objects.create_superuser("production-admin@example.com", "password")
    client.force_login(admin)
    response = client.get(reverse("home:home"))
    assert response.status_code == 200
    assert b"<summary>Produksi</summary>" in response.content


@pytest.mark.django_db
def test_partial_handover_is_item_safe_and_exposes_costless_warehouse_candidate():
    entity, user, order, (output_a, output_b) = _foundation("HO")
    _post_work(
        entity, user, order, [(output_a, "100"), (output_b, "20")], ProductionStage.CUT, "cut"
    )
    _post_work(
        entity, user, order, [(output_a, "100"), (output_b, "20")], ProductionStage.SEW, "sew"
    )
    _post_work(
        entity, user, order, [(output_a, "100"), (output_b, "20")], ProductionStage.QC_PACKING, "qc"
    )
    _post_reject(entity, user, order, [(output_a, ProductionStage.QC_PACKING, "10")], "rej-qc")
    _ready_handover(entity, user, order, [(output_a, "30")], "handover-1")
    assert output_wip(output_a).available_handover == Decimal("60")
    _ready_handover(entity, user, order, [(output_a, "40")], "handover-2")
    assert output_wip(output_a).available_handover == Decimal("20")
    with pytest.raises(ValidationError):
        _ready_handover(entity, user, order, [(output_a, "21")], "handover-over")
    with pytest.raises(ValidationError):
        _ready_handover(entity, user, order, [(output_b, "21")], "handover-item-safe")
    candidate = warehouse_receipt_candidates(user, work_order=order)[0]
    assert candidate["source_key"].startswith("PROD_HANDOVER|")
    assert candidate["unit_cost"] is None
    assert candidate["cost_status"] == "UNAVAILABLE"


@pytest.mark.django_db
def test_handover_multiline_aggregate_is_atomic_and_sibling_reversal_is_safe():
    entity, user, order, (output_a, output_b) = _foundation("HOREV")
    _post_work(
        entity, user, order, [(output_a, "20"), (output_b, "30")], ProductionStage.CUT, "cut"
    )
    _post_work(
        entity, user, order, [(output_a, "20"), (output_b, "30")], ProductionStage.SEW, "sew"
    )
    _post_work(
        entity, user, order, [(output_a, "20"), (output_b, "30")], ProductionStage.QC_PACKING, "qc"
    )
    draft = create_handover_draft(
        legal_entity=entity, work_order=order, handover_date=date(2026, 8, 27), actor=user
    )
    add_handover_line(draft, output=output_a, quantity="12", actor=user)
    add_handover_line(draft, output=output_a, quantity="10", actor=user)
    with pytest.raises(ValidationError):
        mark_handover_ready(draft, actor=user, idempotency_key="handover-bad")
    assert draft.state == "DRAFT"
    ready = _ready_handover(entity, user, order, [(output_a, "20"), (output_b, "30")], "ready")
    first, sibling = ready.lines.order_by("sequence")
    reversal = reverse_handover_line(
        first, reason="Koreksi output A", actor=user, idempotency_key="reverse-handover-a"
    )
    assert reversal.original_line_id == first.pk
    assert ready.lines.filter(pk=sibling.pk).exists()
    assert output_wip(output_a).available_handover == Decimal("20")
    assert output_wip(output_b).available_handover == Decimal("0")
    assert (
        reverse_handover_line(
            first, reason="Koreksi output A", actor=user, idempotency_key="reverse-handover-a"
        )
        == reversal
    )


@pytest.mark.django_db
def test_completion_readiness_is_per_output_and_qc_reversal_respects_handover():
    entity, user, order, (output_a, output_b) = _foundation("COMP")
    _post_work(
        entity, user, order, [(output_a, "100"), (output_b, "50")], ProductionStage.CUT, "cut"
    )
    _post_work(
        entity, user, order, [(output_a, "100"), (output_b, "50")], ProductionStage.SEW, "sew"
    )
    qc = _post_work(
        entity, user, order, [(output_a, "100"), (output_b, "50")], ProductionStage.QC_PACKING, "qc"
    )
    _ready_handover(entity, user, order, [(output_a, "100"), (output_b, "49")], "handover")
    readiness = production_completion_readiness(order)
    assert not readiness["is_production_ready"]
    assert readiness["progress"] == "IN_PROGRESS"
    assert output_wip(output_b).target_variance == Decimal("-51")
    with pytest.raises(ValidationError):
        reverse_work_line(
            qc.lines.order_by("sequence").first(),
            reason="Terlalu besar",
            actor=user,
            idempotency_key="qc-unsafe",
        )
    _ready_handover(entity, user, order, [(output_b, "1")], "handover-last")
    assert production_completion_readiness(order)["is_production_ready"]


@pytest.mark.django_db
def test_handover_routes_and_sidebar_are_permission_aware(client):
    entity, user, order, _ = _foundation("HOSMOKE")
    handover = create_handover_draft(
        legal_entity=entity, work_order=order, handover_date=date(2026, 8, 27), actor=user
    )
    assert reverse("production:wip-list") == "/production/"
    assert reverse("production:handover-list") == "/production/handover/"
    assert reverse("production:handover-detail", args=[handover.pk]).endswith(f"/{handover.pk}/")
    client.force_login(user)
    assert client.get(reverse("production:handover-list")).status_code == 403
    user.user_permissions.add(Permission.objects.get(codename="view_productionwarehousehandover"))
    response = client.get(reverse("home:home"))
    assert response.status_code == 200
    assert b"Setor Gudang" in response.content
    assert b"WIP Produksi" not in response.content
    assert client.get(reverse("production:handover-list")).status_code == 200
    assert client.get(reverse("production:handover-detail", args=[handover.pk])).status_code == 200


@pytest.mark.django_db
def test_qc_reject_and_handover_share_the_same_available_wip():
    entity, user, order, (output_a, _) = _foundation("HOREJ")
    _post_work(entity, user, order, [(output_a, "100")], ProductionStage.CUT, "cut")
    _post_work(entity, user, order, [(output_a, "100")], ProductionStage.SEW, "sew")
    _post_work(entity, user, order, [(output_a, "100")], ProductionStage.QC_PACKING, "qc")
    _ready_handover(entity, user, order, [(output_a, "90")], "handover")
    _post_reject(entity, user, order, [(output_a, ProductionStage.QC_PACKING, "10")], "reject")
    assert output_wip(output_a).available_handover == Decimal("0")
    with pytest.raises(ValidationError):
        _ready_handover(entity, user, order, [(output_a, "1")], "handover-over")


@pytest.mark.django_db
def test_piece_rate_labor_is_snapshotted_and_missing_tariff_is_blocked():
    entity, user, order, (output_a, _) = _foundation("COST")
    employee = Employee.objects.create(
        legal_entity=entity, employee_code="OP-1", display_name="Operator"
    )
    entry = create_draft_work_entry(
        legal_entity=entity,
        work_order=order,
        production_date=date(2026, 8, 27),
        stage=ProductionStage.CUT,
        actor=user,
    )
    entry.employee = employee
    entry.wage_method = ProductionWageMethod.PIECE_RATE
    entry.save(update_fields=("employee", "wage_method"))
    add_draft_work_line(entry, output=output_a, quantity="10", actor=user)
    with pytest.raises(ValidationError):
        post_work_entry(entry, actor=user, idempotency_key="missing-tariff")
    tariff = ProductionTariff.objects.create(
        legal_entity=entity,
        stage=ProductionStage.CUT,
        item=output_a.item,
        wage_method=ProductionWageMethod.PIECE_RATE,
        rate_per_unit="2500",
        effective_from=date(2026, 1, 1),
    )
    post_work_entry(entry, actor=user, idempotency_key="labor")
    labor = ProductionLaborCost.objects.get(source_line=entry.lines.get())
    assert labor.amount == Decimal("25000") and labor.tariff_id == tariff.pk
    tariff.rate_per_unit = Decimal("9999")
    tariff.save(update_fields=("rate_per_unit",))
    labor.refresh_from_db()
    assert labor.amount == Decimal("25000")


@pytest.mark.django_db
def test_direct_extra_cost_is_output_specific_posted_and_reversible():
    entity, user, order, (output_a, output_b) = _foundation("EXTRA")
    cost = create_direct_extra_cost(
        legal_entity=entity,
        work_order=order,
        output=output_a,
        cost_date=date(2026, 8, 27),
        category="MEAL_OPERATOR",
        description="Meal",
        amount=Decimal("50000"),
        actor=user,
    )
    post_direct_extra_cost(cost, actor=user, idempotency_key="extra-post")
    assert (
        ProductionDirectExtraCost.objects.filter(output=output_a, reversed_at__isnull=True).count()
        == 1
    )
    assert ProductionDirectExtraCost.objects.filter(output=output_b).count() == 0
    reversal = reverse_direct_extra_cost(
        cost, reason="Correction", actor=user, idempotency_key="extra-reverse"
    )
    assert reversal.original_id == cost.pk
    assert ProductionDirectExtraCost.objects.get(pk=cost.pk).reversed_at is not None
    assert (
        reverse_direct_extra_cost(
            cost, reason="Correction", actor=user, idempotency_key="extra-reverse"
        )
        == reversal
    )
