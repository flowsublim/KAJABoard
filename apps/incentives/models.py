import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class IncentiveType(models.TextChoices):
    CPO_FEE = "CPO_FEE", "CPO Finished Goods Fee"
    SALES_COMMISSION = "SALES_COMMISSION", "Sales Commission / Sales Fee"


class IncentiveTriggerType(models.TextChoices):
    FINISHED_GOODS_ACCEPTED = "FINISHED_GOODS_ACCEPTED", "Finished Goods Accepted"
    INVOICE_POSTED = "INVOICE_POSTED", "Invoice Posted"
    INVOICE_PAID = "INVOICE_PAID", "Invoice Paid"
    PROJECT_CLOSED = "PROJECT_CLOSED", "Project Closed"
    APPROVED_CUSTOM_EVENT = "APPROVED_CUSTOM_EVENT", "Approved Custom Event"


class IncentiveCalculationMethod(models.TextChoices):
    PER_UNIT = "PER_UNIT", "Per Unit"
    PERCENT_REVENUE = "PERCENT_REVENUE", "% Revenue"
    PERCENT_MARGIN_PROFIT = "PERCENT_MARGIN_PROFIT", "% Margin/Profit"
    FIXED = "FIXED", "Fixed"
    TIERED = "TIERED", "Tiered"
    APPROVED_FORMULA = "APPROVED_FORMULA", "Approved Formula"


class IncentiveAccrualState(models.TextChoices):
    ESTIMATED = "ESTIMATED", "Estimated"
    ACCRUED = "ACCRUED", "Accrued"
    APPROVED = "APPROVED", "Approved"
    PAYABLE = "PAYABLE", "Payable"
    PAID = "PAID", "Paid"
    REVERSED = "REVERSED", "Reversed"


class BeneficiaryKind(models.TextChoices):
    EMPLOYEE = "EMPLOYEE", "Employee"
    PARTNER = "PARTNER", "Business Partner"
    CUSTOM = "CUSTOM", "Custom Beneficiary"


class IncentiveRule(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    legal_entity = models.ForeignKey(
        "organizations.LegalEntity",
        on_delete=models.PROTECT,
        related_name="incentive_rules",
    )
    code = models.CharField(max_length=64, db_index=True)
    name = models.CharField(max_length=255)
    incentive_type = models.CharField(
        max_length=32,
        choices=IncentiveType.choices,
        db_index=True,
    )
    trigger_type = models.CharField(
        max_length=32,
        choices=IncentiveTriggerType.choices,
        db_index=True,
    )
    calculation_method = models.CharField(
        max_length=32,
        choices=IncentiveCalculationMethod.choices,
    )
    rate_value = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal("0.0000"),
    )
    currency = models.CharField(max_length=3, default="IDR")
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    item = models.ForeignKey(
        "catalog.Item",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="incentive_rules",
        help_text="Optional Item/SKU scope. Unscoped rules have item=None.",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-effective_from", "code"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(rate_value__gte=0),
                name="incentive_rule_rate_non_negative",
            ),
            models.UniqueConstraint(
                fields=["legal_entity", "code"],
                name="unique_incentive_rule_code_per_entity",
            ),
        ]
        indexes = [
            models.Index(
                fields=["legal_entity", "incentive_type", "trigger_type", "is_active"],
                name="idx_inc_rule_lookup",
            ),
            models.Index(
                fields=["legal_entity", "item"],
                name="idx_inc_rule_item",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} — {self.name} ({self.get_incentive_type_display()})"

    def clean(self):
        errors = {}
        if self.effective_to and self.effective_to < self.effective_from:
            errors["effective_to"] = "effective_to must be greater than or equal to effective_from."
        if self.rate_value is not None and self.rate_value < 0:
            errors["rate_value"] = "rate_value cannot be negative."
        if self.item_id and self.item.legal_entity_id != self.legal_entity_id:
            errors["item"] = "Item legal entity must match rule legal entity."
        if errors:
            raise ValidationError(errors)

    def is_effective_on(self, target_date) -> bool:
        if not self.is_active:
            return False
        if target_date < self.effective_from:
            return False
        if self.effective_to and target_date > self.effective_to:
            return False
        return True


class IncentiveAccrual(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    legal_entity = models.ForeignKey(
        "organizations.LegalEntity",
        on_delete=models.PROTECT,
        related_name="incentive_accruals",
    )
    incentive_type = models.CharField(
        max_length=32,
        choices=IncentiveType.choices,
        db_index=True,
    )
    source_key = models.CharField(max_length=255, unique=True, db_index=True)
    source_module = models.CharField(max_length=32)
    source_type = models.CharField(max_length=64)
    source_document_id = models.CharField(max_length=64)
    source_line_id = models.CharField(max_length=64, blank=True)
    source_reference = models.CharField(max_length=255, blank=True)
    accrual_date = models.DateField(db_index=True)

    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="incentive_accruals",
    )
    item = models.ForeignKey(
        "catalog.Item",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="incentive_accruals",
    )

    rule = models.ForeignKey(
        IncentiveRule,
        on_delete=models.PROTECT,
        related_name="accruals",
    )
    rule_code_snapshot = models.CharField(max_length=64)
    trigger_snapshot = models.CharField(max_length=32)
    calculation_method_snapshot = models.CharField(max_length=32)
    rate_snapshot = models.DecimalField(max_digits=18, decimal_places=4)
    currency_snapshot = models.CharField(max_length=3, default="IDR")

    basis_quantity = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        null=True,
        blank=True,
    )
    basis_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
    )

    beneficiary_type = models.CharField(
        max_length=32,
        choices=BeneficiaryKind.choices,
    )
    beneficiary_id = models.CharField(max_length=64, db_index=True)
    beneficiary_code_snapshot = models.CharField(max_length=64, blank=True)
    beneficiary_name_snapshot = models.CharField(max_length=255)

    amount = models.DecimalField(max_digits=18, decimal_places=2)
    state = models.CharField(
        max_length=32,
        choices=IncentiveAccrualState.choices,
        default=IncentiveAccrualState.ACCRUED,
        db_index=True,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-accrual_date", "-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gte=0),
                name="incentive_accrual_amount_non_negative",
            ),
        ]
        indexes = [
            models.Index(
                fields=["legal_entity", "incentive_type", "state"],
                name="idx_inc_accrual_state",
            ),
            models.Index(
                fields=["legal_entity", "accrual_date"],
                name="idx_inc_accrual_date",
            ),
            models.Index(
                fields=["project", "incentive_type"],
                name="idx_inc_accrual_proj",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.source_key} — {self.currency_snapshot} {self.amount} ({self.state})"

    def clean(self):
        errors = {}
        if self.amount is not None:
            if self.amount < 0:
                errors["amount"] = "Amount cannot be negative."
            if self.amount % Decimal("1") != Decimal("0"):
                errors["amount"] = "Incentive accrual amount must be whole Rupiah."
        if self.rule_id and self.rule.legal_entity_id != self.legal_entity_id:
            errors["rule"] = "Rule legal entity must match accrual legal entity."
        if self.item_id and self.item.legal_entity_id != self.legal_entity_id:
            errors["item"] = "Item legal entity must match accrual legal entity."
        if self.project_id and self.project.legal_entity_id != self.legal_entity_id:
            errors["project"] = "Project legal entity must match accrual legal entity."
        if errors:
            raise ValidationError(errors)


class IncentiveAccrualReversal(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    accrual = models.OneToOneField(
        IncentiveAccrual,
        on_delete=models.PROTECT,
        related_name="reversal",
    )
    reason = models.TextField()
    reversed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
    )
    reversed_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-reversed_at"]

    def __str__(self) -> str:
        return f"Reversal of {self.accrual.source_key}: {self.reason[:30]}"
