from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.catalog.models import Item
from apps.core.models import DocumentNumberAllocation, TimeStampedModel, UUIDPrimaryKeyModel
from apps.organizations.models import CostCenter, LegalEntity
from apps.partners.models import BusinessPartner
from apps.purchasing.models import PurchaseCategory


class ProjectState(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    ACTIVE = "ACTIVE", "Active"
    ON_HOLD = "ON_HOLD", "On hold"
    COMPLETED = "COMPLETED", "Completed"
    CANCELLED = "CANCELLED", "Cancelled"


class ProjectBudgetCategory(models.TextChoices):
    MATERIAL = "MATERIAL", "Material"
    PURCHASING = "PURCHASING", "Purchasing"
    MAKLUN = "MAKLUN", "Maklun"
    INTERNAL_PRODUCTION = "INTERNAL_PRODUCTION", "Internal production"
    LABOR = "LABOR", "Labor"
    FREIGHT = "FREIGHT", "Freight"
    PACKAGING = "PACKAGING", "Packaging"
    CPO_FEE = "CPO_FEE", "CPO fee"
    SALES_FEE = "SALES_FEE", "Sales fee"
    DIRECT_OVERHEAD = "DIRECT_OVERHEAD", "Direct overhead"
    ALLOCATED_OVERHEAD = "ALLOCATED_OVERHEAD", "Allocated overhead"
    OTHER = "OTHER", "Other"


class Project(UUIDPrimaryKeyModel, TimeStampedModel):
    """Contract/project metadata and budget ownership; it does not own downstream costs."""

    legal_entity = models.ForeignKey(LegalEntity, on_delete=models.PROTECT, related_name="projects")
    document_allocation = models.OneToOneField(
        DocumentNumberAllocation, on_delete=models.PROTECT, related_name="project"
    )
    code = models.CharField(max_length=120)
    name = models.CharField(max_length=255)
    customer = models.ForeignKey(BusinessPartner, on_delete=models.PROTECT, related_name="projects")
    project_type = models.CharField(max_length=80, blank=True)
    contract_reference = models.CharField(max_length=120, blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="owned_projects",
    )
    start_date = models.DateField()
    target_date = models.DateField(null=True, blank=True)
    state = models.CharField(
        max_length=20, choices=ProjectState.choices, default=ProjectState.DRAFT
    )
    currency = models.CharField(max_length=3, default="IDR")
    budget_total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    target_margin_percent = models.DecimalField(
        max_digits=7, decimal_places=4, null=True, blank=True
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="created_projects",
    )
    activated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="activated_projects",
    )
    activated_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="cancelled_projects",
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-start_date", "-created_at")
        permissions = [
            ("activate_project", "Can activate project"),
            ("hold_project", "Can hold or release project"),
            ("complete_project", "Can complete project"),
            ("cancel_project", "Can cancel project"),
            ("link_project_salesorder", "Can link project Sales Orders"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("legal_entity", "code"), name="project_entity_code_unique"
            ),
            models.CheckConstraint(
                condition=Q(budget_total__gte=0), name="project_budget_total_nonneg"
            ),
            models.CheckConstraint(
                condition=Q(target_date__isnull=True) | Q(target_date__gte=models.F("start_date")),
                name="project_target_date_valid",
            ),
            models.CheckConstraint(
                condition=Q(target_margin_percent__isnull=True)
                | (Q(target_margin_percent__gte=0) & Q(target_margin_percent__lte=100)),
                name="project_target_margin_valid",
            ),
        ]
        indexes = [
            models.Index(fields=("legal_entity", "state", "start_date"), name="project_list_idx"),
            models.Index(fields=("customer", "state", "target_date"), name="project_customer_idx"),
        ]

    def __str__(self) -> str:
        return self.code


class ProjectSalesOrder(UUIDPrimaryKeyModel, TimeStampedModel):
    """One explicit primary Project allocation for a Sales Order; no speculative line split."""

    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="sales_order_links")
    sales_order = models.OneToOneField(
        "sales.SalesOrder", on_delete=models.PROTECT, related_name="project_link"
    )
    linked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="linked_project_sales_orders",
    )
    linked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=("project", "sales_order"), name="project_so_link_idx")]

    def __str__(self) -> str:
        return f"{self.project.code} / {self.sales_order.document_number}"


class ProjectBudgetLine(UUIDPrimaryKeyModel, TimeStampedModel):
    """Structured budget input; real committed and actual cost stay in source domains."""

    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="budget_lines")
    category = models.CharField(max_length=32, choices=ProjectBudgetCategory.choices)
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    cost_center = models.ForeignKey(
        CostCenter,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="project_budget_lines",
    )
    purchase_category = models.ForeignKey(
        PurchaseCategory,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="project_budget_lines",
    )
    item = models.ForeignKey(
        Item,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="project_budget_lines",
    )
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("category", "created_at")
        constraints = [
            models.CheckConstraint(condition=Q(amount__gte=0), name="project_budget_line_nonneg"),
        ]
        indexes = [
            models.Index(
                fields=("project", "category", "is_active"), name="project_budget_line_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.project.code} / {self.category}"


class ProjectForecastLine(UUIDPrimaryKeyModel, TimeStampedModel):
    """Explicit Project-owned planning model representing management's expected
    total cost by category.
    """

    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="forecast_lines")
    category = models.CharField(max_length=32, choices=ProjectBudgetCategory.choices)
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    cost_center = models.ForeignKey(
        CostCenter,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="project_forecast_lines",
    )
    purchase_category = models.ForeignKey(
        PurchaseCategory,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="project_forecast_lines",
    )
    item = models.ForeignKey(
        Item,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="project_forecast_lines",
    )
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("category", "created_at")
        constraints = [
            models.CheckConstraint(condition=Q(amount__gte=0), name="project_forecast_line_nonneg"),
        ]
        indexes = [
            models.Index(
                fields=("project", "category", "is_active"), name="project_forecast_line_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.project.code} / {self.category} / {self.amount}"
