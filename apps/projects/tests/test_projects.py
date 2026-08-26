from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.catalog.models import UOM, Item
from apps.core.contracts.finance import customer_finance_exposure
from apps.core.services.numbering import create_document_sequence
from apps.organizations.models import LegalEntity, OrganizationMembership
from apps.partners.models import BusinessPartner, PartnerRole, PartnerRoleType
from apps.projects.models import ProjectState
from apps.projects.selectors import project_b2b_demand_candidates, project_profitability
from apps.projects.services import (
    activate_project,
    add_project_budget_line,
    create_draft_project,
    link_sales_order,
)
from apps.sales.services import add_draft_line, confirm_sales_order, create_draft_sales_order

User = get_user_model()


@pytest.fixture
def setup_data():
    entity = LegalEntity.objects.create(code="PROJ", name="Project Entity")
    user = User.objects.create_user("project@example.com", "password")
    OrganizationMembership.objects.create(user=user, legal_entity=entity)
    customer = BusinessPartner.objects.create(
        legal_entity=entity, code="C-1", display_name="Customer"
    )
    PartnerRole.objects.create(partner=customer, role_type=PartnerRoleType.CUSTOMER)
    uom = UOM.objects.create(code="PPCS", name="Pieces", dimension="COUNT")
    item = Item.objects.create(
        legal_entity=entity, code="P-1", name="Item", uom=uom, sales_eligible=True
    )
    for code in ("PROJECT", "SALES_ORDER"):
        create_document_sequence(
            legal_entity=entity,
            document_type=code,
            name=code,
            prefix=code,
            format_template="{prefix}-{yyyymmdd}-{seq}",
            padding=3,
        )
    return entity, user, customer, item


@pytest.mark.django_db
def test_project_budget_link_and_downstream_candidate(setup_data):
    entity, user, customer, item = setup_data
    project = create_draft_project(
        legal_entity=entity,
        customer=customer,
        name="Custom",
        start_date=timezone.localdate(),
        actor=user,
        idempotency_key="project-1",
    )
    assert (
        create_draft_project(
            legal_entity=entity,
            customer=customer,
            name="Custom",
            start_date=timezone.localdate(),
            actor=user,
            idempotency_key="project-1",
        ).pk
        == project.pk
    )
    add_project_budget_line(
        project, actor=user, category="MATERIAL", description="Material", amount=Decimal("125.50")
    )
    project.refresh_from_db()
    assert project.budget_total == Decimal("125.50")
    order = create_draft_sales_order(
        legal_entity=entity, customer=customer, document_date=timezone.localdate(), actor=user
    )
    add_draft_line(order, actor=user, item=item, quantity=Decimal("2"), unit_price=Decimal("30"))
    confirm_sales_order(order, actor=user)
    link_sales_order(project, order, actor=user)
    activate_project(project, actor=user)
    project.refresh_from_db()
    candidates = project_b2b_demand_candidates(user, project=project)
    assert project.state == ProjectState.ACTIVE
    assert candidates[0].sales_order_line_id == str(order.lines.get().pk)
    profitability = project_profitability(project)
    assert profitability.committed_cost is None and not profitability.data_complete


@pytest.mark.django_db
def test_project_requires_numbering_and_finance_contract_never_fakes_zero(setup_data):
    entity, user, customer, _ = setup_data
    exposure = customer_finance_exposure(customer)
    assert not exposure.source_available and exposure.outstanding is None
    # The configured PROJECT sequence is required; removing it makes the service fail clearly.
    entity.document_sequences.filter(document_type="PROJECT").delete()
    with pytest.raises(ValidationError):
        create_draft_project(
            legal_entity=entity,
            customer=customer,
            name="No sequence",
            start_date=timezone.localdate(),
            actor=user,
        )
