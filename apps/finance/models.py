from django.db import models
from django.db.models import Q

from apps.core.models import EffectivePeriodModel, TimeStampedModel, UUIDPrimaryKeyModel
from apps.organizations.models import LegalEntity


class AccountType(models.TextChoices):
    ASSET = "ASSET", "Asset"
    LIABILITY = "LIABILITY", "Liability"
    EQUITY = "EQUITY", "Equity"
    REVENUE = "REVENUE", "Revenue"
    EXPENSE = "EXPENSE", "Expense"
    COGS = "COGS", "COGS"
    OTHER = "OTHER", "Other"


class NormalBalance(models.TextChoices):
    DEBIT = "DEBIT", "Debit"
    CREDIT = "CREDIT", "Credit"


class COAAccount(UUIDPrimaryKeyModel, TimeStampedModel, EffectivePeriodModel):
    """Chart of accounts master only; no journal or ledger rows are created in Phase 2C."""

    legal_entity = models.ForeignKey(
        LegalEntity,
        on_delete=models.PROTECT,
        related_name="coa_accounts",
    )
    account_code = models.CharField(max_length=40)
    account_code_normalized = models.CharField(max_length=40, editable=False)
    account_name = models.CharField(max_length=150)
    account_type = models.CharField(max_length=20, choices=AccountType.choices)
    report_group = models.CharField(max_length=80, blank=True)
    report_subgroup = models.CharField(max_length=80, blank=True)
    normal_balance = models.CharField(max_length=10, choices=NormalBalance.choices)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="children",
    )
    is_header = models.BooleanField(default=False)
    is_posting_allowed = models.BooleanField(default=True)
    manual_journal_allowed = models.BooleanField(default=False)
    is_cash_bank = models.BooleanField(default=False)
    is_control_account = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("legal_entity__code", "account_code")
        constraints = [
            models.UniqueConstraint(
                fields=("legal_entity", "account_code_normalized", "effective_from"),
                name="finance_coa_entity_code_start_unique",
            ),
            models.CheckConstraint(
                condition=Q(effective_to__isnull=True)
                | Q(effective_to__gte=models.F("effective_from")),
                name="finance_coaaccount_effective_period_valid",
            ),
            models.CheckConstraint(
                condition=Q(is_header=False) | Q(is_posting_allowed=False),
                name="finance_coa_header_not_posting",
            ),
        ]
        indexes = [
            models.Index(
                fields=("legal_entity", "account_code_normalized", "is_active"),
                name="finance_coa_lookup_idx",
            ),
            models.Index(fields=("parent", "is_active"), name="finance_coa_parent_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.account_code} - {self.account_name}"


class MappingDimensionType(models.TextChoices):
    DEFAULT = "DEFAULT", "Default"
    STORE = "STORE", "Store"
    PURCHASE_CATEGORY = "PURCHASE_CATEGORY", "Purchase category"
    COST_CENTER = "COST_CENTER", "Cost center"
    PAYMENT_METHOD = "PAYMENT_METHOD", "Payment method"
    TAX = "TAX", "Tax"
    BUSINESS_UNIT = "BUSINESS_UNIT", "Business unit"
    PROJECT = "PROJECT", "Project"


class DCDirection(models.TextChoices):
    DEBIT = "DEBIT", "Debit"
    CREDIT = "CREDIT", "Credit"


class COAMapping(UUIDPrimaryKeyModel, TimeStampedModel, EffectivePeriodModel):
    """Finance-owned mapping row evaluated by the read-only resolver."""

    legal_entity = models.ForeignKey(
        LegalEntity,
        on_delete=models.PROTECT,
        related_name="coa_mappings",
    )
    module_code = models.CharField(max_length=40)
    event_code = models.CharField(max_length=80)
    dimension_type = models.CharField(max_length=30, choices=MappingDimensionType.choices)
    dimension_value = models.CharField(max_length=120)
    dimension_value_normalized = models.CharField(max_length=120, editable=False)
    line_role = models.CharField(max_length=80)
    dc = models.CharField(max_length=10, choices=DCDirection.choices)
    account = models.ForeignKey(
        COAAccount,
        on_delete=models.PROTECT,
        related_name="coa_mappings",
    )
    priority = models.IntegerField(default=100)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = (
            "legal_entity__code",
            "module_code",
            "event_code",
            "line_role",
            "-priority",
        )
        constraints = [
            models.UniqueConstraint(
                fields=(
                    "legal_entity",
                    "module_code",
                    "event_code",
                    "dimension_type",
                    "dimension_value_normalized",
                    "line_role",
                    "dc",
                    "priority",
                    "effective_from",
                ),
                name="finance_mapping_scope_start_unique",
            ),
            models.CheckConstraint(
                condition=Q(effective_to__isnull=True)
                | Q(effective_to__gte=models.F("effective_from")),
                name="finance_coamapping_effective_period_valid",
            ),
        ]
        indexes = [
            models.Index(
                fields=(
                    "legal_entity",
                    "module_code",
                    "event_code",
                    "line_role",
                    "dc",
                    "is_active",
                ),
                name="finance_mapping_resolve_idx",
            ),
            models.Index(
                fields=("dimension_type", "dimension_value_normalized"),
                name="finance_mapping_dimension_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.module_code}/{self.event_code}/{self.line_role}/{self.dc}"


class JournalState(models.TextChoices):
    POSTED = "POSTED", "Posted"
    REVERSED = "REVERSED", "Reversed"


class JournalEntry(UUIDPrimaryKeyModel, TimeStampedModel):
    legal_entity = models.ForeignKey(LegalEntity, on_delete=models.PROTECT, related_name="journals")
    journal_number = models.CharField(max_length=80)
    accounting_date = models.DateField()
    event_code = models.CharField(max_length=80)
    source_module = models.CharField(max_length=40)
    source_document_type = models.CharField(max_length=80)
    source_document_id = models.CharField(max_length=80)
    source_key = models.CharField(max_length=255)
    source_reference = models.JSONField(default=dict, blank=True)
    state = models.CharField(
        max_length=12, choices=JournalState.choices, default=JournalState.POSTED
    )
    currency = models.CharField(max_length=12, default="IDR")
    total_debit = models.DecimalField(max_digits=20, decimal_places=0)
    total_credit = models.DecimalField(max_digits=20, decimal_places=0)
    description = models.TextField(blank=True)
    posted_at = models.DateTimeField()
    posted_by = models.ForeignKey("accounts.User", null=True, on_delete=models.PROTECT)
    reversal_of = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversal"
    )
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("legal_entity", "source_key"), name="finance_journal_source_uq"
            ),
            models.CheckConstraint(
                condition=Q(total_debit=models.F("total_credit")), name="finance_journal_balanced"
            ),
        ]
        permissions = [
            ("view_gl", "Can view general ledger"),
            ("post_journal", "Can post journal"),
            ("reverse_journal", "Can reverse journal"),
            ("view_ar", "Can view accounts receivable"),
            ("view_ap", "Can view accounts payable"),
            ("view_reconciliation", "Can view finance reconciliation"),
        ]


class JournalLine(UUIDPrimaryKeyModel, TimeStampedModel):
    journal = models.ForeignKey(JournalEntry, on_delete=models.PROTECT, related_name="lines")
    sequence = models.PositiveIntegerField()
    line_role = models.CharField(max_length=80)
    account = models.ForeignKey(COAAccount, on_delete=models.PROTECT)
    account_code_snapshot = models.CharField(max_length=40)
    account_name_snapshot = models.CharField(max_length=150)
    debit = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    credit = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    mapping_snapshot = models.JSONField(default=dict)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("journal", "sequence"), name="finance_journal_line_seq_uq"
            ),
            models.CheckConstraint(
                condition=(Q(debit__gt=0, credit=0) | Q(credit__gt=0, debit=0)),
                name="finance_journal_line_one_side",
            ),
        ]


class ReceivableEntry(UUIDPrimaryKeyModel, TimeStampedModel):
    journal = models.OneToOneField(
        JournalEntry, on_delete=models.PROTECT, related_name="receivable"
    )
    legal_entity = models.ForeignKey(LegalEntity, on_delete=models.PROTECT)
    accounting_date = models.DateField()
    original_amount = models.DecimalField(max_digits=20, decimal_places=0)
    open_amount = models.DecimalField(max_digits=20, decimal_places=0)
    currency = models.CharField(max_length=12, default="IDR")
    store = models.ForeignKey("channels.Store", null=True, blank=True, on_delete=models.PROTECT)
    partner = models.ForeignKey(
        "partners.BusinessPartner", null=True, blank=True, on_delete=models.PROTECT
    )


class PayableEntry(UUIDPrimaryKeyModel, TimeStampedModel):
    journal = models.OneToOneField(JournalEntry, on_delete=models.PROTECT, related_name="payable")
    legal_entity = models.ForeignKey(LegalEntity, on_delete=models.PROTECT)
    accounting_date = models.DateField()
    original_amount = models.DecimalField(max_digits=20, decimal_places=0)
    open_amount = models.DecimalField(max_digits=20, decimal_places=0)
    currency = models.CharField(max_length=12, default="IDR")
    partner = models.ForeignKey(
        "partners.BusinessPartner", null=True, blank=True, on_delete=models.PROTECT
    )
