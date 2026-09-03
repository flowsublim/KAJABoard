from django.core.exceptions import ValidationError
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
    LIQUIDITY_ACCOUNT = "LIQUIDITY_ACCOUNT", "Liquidity account"


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


class WagePayableState(models.TextChoices):
    POSTED = "POSTED", "Posted"
    REVERSED = "REVERSED", "Reversed"


class WagePayableAccrual(UUIDPrimaryKeyModel, TimeStampedModel):
    """Finance-owned payable effect of an explicitly eligible production cost source."""

    legal_entity = models.ForeignKey(LegalEntity, on_delete=models.PROTECT)
    source_module = models.CharField(max_length=40)
    source_type = models.CharField(max_length=80)
    source_id = models.CharField(max_length=80)
    source_key = models.CharField(max_length=255)
    source_reference = models.JSONField(default=dict)
    production_lineage = models.JSONField(default=dict)
    beneficiary_reference = models.CharField(max_length=120, blank=True)
    accrual_date = models.DateField()
    amount = models.DecimalField(max_digits=20, decimal_places=0)
    currency = models.CharField(max_length=12, default="IDR")
    debit_line_role = models.CharField(max_length=80)
    mapping_context = models.JSONField(default=dict, blank=True)
    journal = models.OneToOneField(
        JournalEntry, on_delete=models.PROTECT, related_name="wage_accrual"
    )
    payable_entry = models.OneToOneField(
        PayableEntry, on_delete=models.PROTECT, related_name="wage_accrual"
    )
    state = models.CharField(
        max_length=12, choices=WagePayableState.choices, default=WagePayableState.POSTED
    )
    reversal_of = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversal"
    )
    posted_by = models.ForeignKey("accounts.User", null=True, on_delete=models.PROTECT)
    posted_at = models.DateTimeField()
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("legal_entity", "source_key"), name="finance_wage_source_uq"
            ),
            models.CheckConstraint(condition=Q(amount__gt=0), name="finance_wage_amount_positive"),
        ]
        indexes = [
            models.Index(fields=("legal_entity", "accrual_date"), name="finance_wage_list_idx")
        ]
        permissions = [
            ("post_wagepayable", "Can post wage payable"),
            ("reverse_wagepayable", "Can reverse wage payable"),
        ]


class AccountingPeriodState(models.TextChoices):
    OPEN = "OPEN", "Open"
    CLOSED = "CLOSED", "Closed"


class AccountingPeriod(UUIDPrimaryKeyModel, TimeStampedModel):
    legal_entity = models.ForeignKey(
        LegalEntity, on_delete=models.PROTECT, related_name="accounting_periods"
    )
    fiscal_year = models.PositiveIntegerField()
    period_number = models.PositiveSmallIntegerField()
    start_date = models.DateField()
    end_date = models.DateField()
    state = models.CharField(
        max_length=12, choices=AccountingPeriodState.choices, default=AccountingPeriodState.OPEN
    )
    notes = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    changed_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("legal_entity", "fiscal_year", "period_number"),
                name="finance_period_number_uq",
            ),
            models.CheckConstraint(
                condition=Q(end_date__gte=models.F("start_date")), name="finance_period_dates_valid"
            ),
        ]
        indexes = [
            models.Index(
                fields=("legal_entity", "start_date", "end_date"), name="finance_period_lookup_idx"
            )
        ]
        permissions = [
            ("manage_accountingperiod", "Can manage accounting period"),
            ("close_accountingperiod", "Can close accounting period"),
        ]


class BankStatementState(models.TextChoices):
    OPEN = "OPEN", "Open"


class BankStatementLineDirection(models.TextChoices):
    IN = "IN", "In"
    OUT = "OUT", "Out"


class BankReconciliationMatchState(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    REVERSED = "REVERSED", "Reversed"


class BankStatement(UUIDPrimaryKeyModel, TimeStampedModel):
    legal_entity = models.ForeignKey(LegalEntity, on_delete=models.PROTECT)
    liquidity_account = models.ForeignKey("LiquidityAccount", on_delete=models.PROTECT)
    statement_reference = models.CharField(max_length=120)
    start_date = models.DateField()
    end_date = models.DateField()
    currency = models.CharField(max_length=12, default="IDR")
    opening_balance = models.DecimalField(max_digits=20, decimal_places=0, null=True, blank=True)
    closing_balance = models.DecimalField(max_digits=20, decimal_places=0, null=True, blank=True)
    source_reference = models.CharField(max_length=255, blank=True)
    source_checksum = models.CharField(max_length=128, blank=True)
    state = models.CharField(
        max_length=12, choices=BankStatementState.choices, default=BankStatementState.OPEN
    )
    metadata = models.JSONField(default=dict, blank=True)
    imported_by = models.ForeignKey("accounts.User", null=True, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("legal_entity", "liquidity_account", "statement_reference"),
                name="finance_bank_statement_uq",
            )
        ]
        permissions = [
            ("manage_bankstatement", "Can manage bank statement"),
            ("match_bankstatement", "Can match bank statement"),
        ]


class BankStatementLine(UUIDPrimaryKeyModel, TimeStampedModel):
    statement = models.ForeignKey(BankStatement, on_delete=models.PROTECT, related_name="lines")
    source_identity = models.CharField(max_length=255)
    transaction_date = models.DateField()
    value_date = models.DateField(null=True, blank=True)
    external_reference = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    direction = models.CharField(max_length=3, choices=BankStatementLineDirection.choices)
    amount = models.DecimalField(max_digits=20, decimal_places=0)
    running_balance = models.DecimalField(max_digits=20, decimal_places=0, null=True, blank=True)
    sequence = models.PositiveIntegerField()
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("statement", "source_identity"), name="finance_bank_line_source_uq"
            ),
            models.CheckConstraint(condition=Q(amount__gt=0), name="finance_bank_line_positive"),
        ]


class BankReconciliationMatch(UUIDPrimaryKeyModel, TimeStampedModel):
    bank_statement_line = models.ForeignKey(
        BankStatementLine, on_delete=models.PROTECT, related_name="matches"
    )
    liquidity_entry = models.ForeignKey(
        "LiquidityEntry", on_delete=models.PROTECT, related_name="bank_matches"
    )
    matched_amount = models.DecimalField(max_digits=20, decimal_places=0)
    state = models.CharField(
        max_length=12,
        choices=BankReconciliationMatchState.choices,
        default=BankReconciliationMatchState.ACTIVE,
    )
    source_key = models.CharField(max_length=255, unique=True)
    reason = models.TextField(blank=True)
    matched_by = models.ForeignKey("accounts.User", null=True, on_delete=models.PROTECT)
    reversed_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reversed_bank_matches",
    )
    reversed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(matched_amount__gt=0), name="finance_bank_match_positive"
            )
        ]


class LiquidityAccountType(models.TextChoices):
    CASH = "CASH", "Cash"
    BANK = "BANK", "Bank"


class LiquidityDirection(models.TextChoices):
    IN = "IN", "In"
    OUT = "OUT", "Out"


class PaymentDirection(models.TextChoices):
    RECEIPT = "RECEIPT", "Receipt"
    DISBURSEMENT = "DISBURSEMENT", "Disbursement"


class PaymentState(models.TextChoices):
    POSTED = "POSTED", "Posted"
    REVERSED = "REVERSED", "Reversed"


class LiquidityAccount(UUIDPrimaryKeyModel, TimeStampedModel, EffectivePeriodModel):
    """Finance-owned Cash/Bank source master; COA remains resolver-selected."""

    legal_entity = models.ForeignKey(
        LegalEntity, on_delete=models.PROTECT, related_name="liquidity_accounts"
    )
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=150)
    account_type = models.CharField(max_length=10, choices=LiquidityAccountType.choices)
    currency = models.CharField(max_length=12, default="IDR")
    mapping_key = models.CharField(max_length=120)
    bank_name = models.CharField(max_length=120, blank=True)
    bank_account_number = models.CharField(max_length=120, blank=True)
    account_holder_name = models.CharField(max_length=150, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("legal_entity", "code"), name="finance_liquidity_account_code_uq"
            ),
            models.UniqueConstraint(
                fields=("legal_entity", "mapping_key"), name="finance_liquidity_mapping_key_uq"
            ),
            models.CheckConstraint(
                condition=Q(effective_to__isnull=True)
                | Q(effective_to__gte=models.F("effective_from")),
                name="finance_liquidity_effective_period_valid",
            ),
        ]
        indexes = [
            models.Index(
                fields=("legal_entity", "account_type", "is_active"),
                name="finance_liquidity_lookup_idx",
            )
        ]
        permissions = [("manage_liquidityaccount", "Can manage liquidity accounts")]

    def clean(self):
        super().clean()
        if self.account_type == LiquidityAccountType.CASH and any(
            (self.bank_name, self.bank_account_number, self.account_holder_name)
        ):
            raise ValidationError("Bank metadata is allowed only for BANK liquidity accounts.")


class LiquidityEntry(UUIDPrimaryKeyModel, TimeStampedModel):
    """Immutable Finance Cash/Bank movement; balances are read projections."""

    legal_entity = models.ForeignKey(LegalEntity, on_delete=models.PROTECT)
    liquidity_account = models.ForeignKey(
        LiquidityAccount, on_delete=models.PROTECT, related_name="entries"
    )
    journal = models.ForeignKey(
        JournalEntry, on_delete=models.PROTECT, related_name="liquidity_entries"
    )
    transaction_date = models.DateField()
    direction = models.CharField(max_length=3, choices=LiquidityDirection.choices)
    amount = models.DecimalField(max_digits=20, decimal_places=0)
    currency = models.CharField(max_length=12, default="IDR")
    source_module = models.CharField(max_length=40)
    source_document_type = models.CharField(max_length=80)
    source_document_id = models.CharField(max_length=80)
    source_key = models.CharField(max_length=255)
    source_reference = models.JSONField(default=dict, blank=True)
    reversal_of = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversal"
    )
    posted_by = models.ForeignKey("accounts.User", null=True, on_delete=models.PROTECT)
    posted_at = models.DateTimeField()
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("legal_entity", "source_key"), name="finance_liquidity_source_uq"
            ),
            models.CheckConstraint(
                condition=Q(amount__gt=0), name="finance_liquidity_amount_positive"
            ),
        ]
        indexes = [
            models.Index(
                fields=("liquidity_account", "transaction_date"),
                name="finance_liquidity_ledger_idx",
            ),
            models.Index(
                fields=("legal_entity", "source_key"), name="finance_liquidity_source_idx"
            ),
        ]


class MarketplaceBalanceDirection(models.TextChoices):
    IN = "IN", "In"
    OUT = "OUT", "Out"


class MarketplaceSettlementState(models.TextChoices):
    POSTED = "POSTED", "Posted"
    REVERSED = "REVERSED", "Reversed"


class MarketplaceReturnTreatment(models.TextChoices):
    RECEIVABLE_CREDIT = "RECEIVABLE_CREDIT", "Receivable credit"
    MARKETPLACE_BALANCE_CREDIT = "MARKETPLACE_BALANCE_CREDIT", "Marketplace balance credit"


class MarketplaceFollowupState(models.TextChoices):
    POSTED = "POSTED", "Posted"
    REVERSED = "REVERSED", "Reversed"


class MarketplaceAdjustmentState(models.TextChoices):
    CONSUMED_IN_SETTLEMENT = "CONSUMED_IN_SETTLEMENT", "Consumed in settlement"
    REVERSED = "REVERSED", "Reversed"


class MarketplaceBalanceEntry(UUIDPrimaryKeyModel, TimeStampedModel):
    """Immutable marketplace-held-money movement; balances are read projections."""

    legal_entity = models.ForeignKey(LegalEntity, on_delete=models.PROTECT)
    store = models.ForeignKey(
        "channels.Store", on_delete=models.PROTECT, related_name="marketplace_balance_entries"
    )
    journal = models.ForeignKey(
        JournalEntry, on_delete=models.PROTECT, related_name="marketplace_balance_entries"
    )
    transaction_date = models.DateField()
    direction = models.CharField(max_length=3, choices=MarketplaceBalanceDirection.choices)
    amount = models.DecimalField(max_digits=20, decimal_places=0)
    currency = models.CharField(max_length=12, default="IDR")
    source_module = models.CharField(max_length=40)
    source_document_type = models.CharField(max_length=80)
    source_document_id = models.CharField(max_length=80)
    source_key = models.CharField(max_length=255)
    source_reference = models.JSONField(default=dict, blank=True)
    reversal_of = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversal"
    )
    posted_by = models.ForeignKey("accounts.User", null=True, on_delete=models.PROTECT)
    posted_at = models.DateTimeField()
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("legal_entity", "source_key"), name="finance_marketplace_balance_source_uq"
            ),
            models.CheckConstraint(
                condition=Q(amount__gt=0), name="finance_marketplace_balance_amount_positive"
            ),
        ]
        indexes = [
            models.Index(
                fields=("legal_entity", "store", "transaction_date"),
                name="fin_mkt_balance_ledger_idx",
            ),
            models.Index(fields=("legal_entity", "source_key"), name="fin_mkt_balance_source_idx"),
        ]
        permissions = [("view_marketplace_balance", "Can view marketplace balance")]


class MarketplaceSettlementPosting(UUIDPrimaryKeyModel, TimeStampedModel):
    """Finance-owned settlement accounting state; the Omni source remains immutable."""

    legal_entity = models.ForeignKey(
        LegalEntity, on_delete=models.PROTECT, related_name="marketplace_settlement_postings"
    )
    store = models.ForeignKey("channels.Store", on_delete=models.PROTECT)
    source_settlement_id = models.CharField(max_length=80)
    source_settlement_identity = models.CharField(max_length=500)
    settlement_date = models.DateField()
    currency = models.CharField(max_length=12, default="IDR")
    receivable = models.ForeignKey(ReceivableEntry, on_delete=models.PROTECT)
    journal = models.OneToOneField(
        JournalEntry, on_delete=models.PROTECT, related_name="marketplace_settlement_posting"
    )
    marketplace_balance_entry = models.OneToOneField(
        MarketplaceBalanceEntry,
        on_delete=models.PROTECT,
        related_name="marketplace_settlement_posting",
    )
    ar_cleared_amount = models.DecimalField(max_digits=20, decimal_places=0)
    marketplace_balance_amount = models.DecimalField(max_digits=20, decimal_places=0)
    fee_amount = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    fee_components = models.JSONField(default=dict, blank=True)
    source_reference = models.JSONField(default=dict, blank=True)
    source_lineage = models.JSONField(default=dict, blank=True)
    state = models.CharField(
        max_length=12,
        choices=MarketplaceSettlementState.choices,
        default=MarketplaceSettlementState.POSTED,
    )
    reversal_of = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversal"
    )
    posted_by = models.ForeignKey("accounts.User", null=True, on_delete=models.PROTECT)
    posted_at = models.DateTimeField()
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("legal_entity", "source_settlement_identity"),
                name="finance_marketplace_settlement_source_uq",
            ),
            models.CheckConstraint(
                condition=Q(ar_cleared_amount__gt=0),
                name="finance_marketplace_settlement_ar_positive",
            ),
            models.CheckConstraint(
                condition=Q(marketplace_balance_amount__gt=0),
                name="finance_marketplace_settlement_balance_positive",
            ),
            models.CheckConstraint(
                condition=Q(fee_amount__gte=0),
                name="finance_marketplace_settlement_fee_nonnegative",
            ),
        ]
        indexes = [
            models.Index(
                fields=("legal_entity", "store", "settlement_date"),
                name="fin_mkt_settlement_list_idx",
            )
        ]
        permissions = [
            ("view_marketplace_settlement", "Can view marketplace settlements"),
            ("post_marketplace_settlement", "Can post marketplace settlements"),
            ("reverse_marketplace_settlement", "Can reverse marketplace settlements"),
        ]


class MarketplaceReturnPosting(UUIDPrimaryKeyModel, TimeStampedModel):
    legal_entity = models.ForeignKey(LegalEntity, on_delete=models.PROTECT)
    store = models.ForeignKey("channels.Store", on_delete=models.PROTECT)
    source_return_id = models.CharField(max_length=80)
    source_return_identity = models.CharField(max_length=500)
    transaction_date = models.DateField()
    amount = models.DecimalField(max_digits=20, decimal_places=0)
    currency = models.CharField(max_length=12, default="IDR")
    receivable = models.ForeignKey(ReceivableEntry, on_delete=models.PROTECT)
    revenue_journal = models.ForeignKey(JournalEntry, on_delete=models.PROTECT)
    journal = models.OneToOneField(
        JournalEntry, on_delete=models.PROTECT, related_name="marketplace_return_posting"
    )
    marketplace_balance_entry = models.OneToOneField(
        MarketplaceBalanceEntry,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="marketplace_return_posting",
    )
    treatment = models.CharField(max_length=32, choices=MarketplaceReturnTreatment.choices)
    state = models.CharField(
        max_length=12,
        choices=MarketplaceFollowupState.choices,
        default=MarketplaceFollowupState.POSTED,
    )
    source_reference = models.JSONField(default=dict, blank=True)
    reversal_of = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversal"
    )
    posted_by = models.ForeignKey("accounts.User", null=True, on_delete=models.PROTECT)
    posted_at = models.DateTimeField()
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("legal_entity", "source_return_identity"),
                name="finance_mkt_return_source_uq",
            ),
            models.CheckConstraint(
                condition=Q(amount__gt=0), name="finance_mkt_return_amount_positive"
            ),
        ]
        indexes = [
            models.Index(
                fields=("legal_entity", "store", "transaction_date"), name="fin_mkt_return_list_idx"
            )
        ]


class MarketplaceAdjustmentPosting(UUIDPrimaryKeyModel, TimeStampedModel):
    legal_entity = models.ForeignKey(LegalEntity, on_delete=models.PROTECT)
    store = models.ForeignKey("channels.Store", on_delete=models.PROTECT)
    source_adjustment_id = models.CharField(max_length=80)
    source_adjustment_identity = models.CharField(max_length=500)
    transaction_date = models.DateField()
    signed_amount = models.DecimalField(max_digits=20, decimal_places=0)
    currency = models.CharField(max_length=12, default="IDR")
    settlement_posting = models.ForeignKey(
        MarketplaceSettlementPosting, on_delete=models.PROTECT, related_name="adjustment_postings"
    )
    journal = models.ForeignKey(
        JournalEntry, on_delete=models.PROTECT, related_name="marketplace_adjustment_postings"
    )
    state = models.CharField(
        max_length=32,
        choices=MarketplaceAdjustmentState.choices,
        default=MarketplaceAdjustmentState.CONSUMED_IN_SETTLEMENT,
    )
    source_reference = models.JSONField(default=dict, blank=True)
    reversal_of = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversal"
    )
    posted_by = models.ForeignKey("accounts.User", null=True, on_delete=models.PROTECT)
    posted_at = models.DateTimeField()
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("legal_entity", "source_adjustment_identity"),
                name="finance_mkt_adjustment_source_uq",
            )
        ]
        indexes = [
            models.Index(
                fields=("legal_entity", "store", "transaction_date"),
                name="fin_mkt_adjustment_list_idx",
            )
        ]


class MarketplacePayoutPosting(UUIDPrimaryKeyModel, TimeStampedModel):
    legal_entity = models.ForeignKey(LegalEntity, on_delete=models.PROTECT)
    store = models.ForeignKey("channels.Store", on_delete=models.PROTECT)
    source_payout_id = models.CharField(max_length=80)
    source_payout_identity = models.CharField(max_length=500)
    payout_reference = models.CharField(max_length=180)
    payout_date = models.DateField()
    amount = models.DecimalField(max_digits=20, decimal_places=0)
    currency = models.CharField(max_length=12, default="IDR")
    liquidity_account = models.ForeignKey(LiquidityAccount, on_delete=models.PROTECT)
    journal = models.OneToOneField(
        JournalEntry, on_delete=models.PROTECT, related_name="marketplace_payout_posting"
    )
    marketplace_balance_entry = models.OneToOneField(
        MarketplaceBalanceEntry, on_delete=models.PROTECT, related_name="marketplace_payout_posting"
    )
    liquidity_entry = models.OneToOneField(
        LiquidityEntry, on_delete=models.PROTECT, related_name="marketplace_payout_posting"
    )
    state = models.CharField(
        max_length=12,
        choices=MarketplaceFollowupState.choices,
        default=MarketplaceFollowupState.POSTED,
    )
    source_reference = models.JSONField(default=dict, blank=True)
    reversal_of = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversal"
    )
    posted_by = models.ForeignKey("accounts.User", null=True, on_delete=models.PROTECT)
    posted_at = models.DateTimeField()
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("legal_entity", "source_payout_identity"),
                name="finance_mkt_payout_source_uq",
            ),
            models.CheckConstraint(
                condition=Q(amount__gt=0), name="finance_mkt_payout_amount_positive"
            ),
        ]
        indexes = [
            models.Index(
                fields=("legal_entity", "store", "payout_date"), name="fin_mkt_payout_list_idx"
            )
        ]


class Payment(UUIDPrimaryKeyModel, TimeStampedModel):
    """Finance-owned immutable receipt/disbursement linked to journal and liquidity source."""

    legal_entity = models.ForeignKey(LegalEntity, on_delete=models.PROTECT, related_name="payments")
    payment_number = models.CharField(max_length=80)
    payment_date = models.DateField()
    direction = models.CharField(max_length=16, choices=PaymentDirection.choices)
    liquidity_account = models.ForeignKey(
        LiquidityAccount, on_delete=models.PROTECT, related_name="payments"
    )
    amount = models.DecimalField(max_digits=20, decimal_places=0)
    currency = models.CharField(max_length=12, default="IDR")
    partner = models.ForeignKey(
        "partners.BusinessPartner", null=True, blank=True, on_delete=models.PROTECT
    )
    store = models.ForeignKey("channels.Store", null=True, blank=True, on_delete=models.PROTECT)
    source_module = models.CharField(max_length=40)
    source_document_type = models.CharField(max_length=80)
    source_document_id = models.CharField(max_length=80)
    source_key = models.CharField(max_length=255)
    source_reference = models.JSONField(default=dict, blank=True)
    state = models.CharField(
        max_length=12, choices=PaymentState.choices, default=PaymentState.POSTED
    )
    journal = models.OneToOneField(JournalEntry, on_delete=models.PROTECT, related_name="payment")
    liquidity_entry = models.OneToOneField(
        LiquidityEntry, on_delete=models.PROTECT, related_name="payment"
    )
    reversal_of = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversal"
    )
    posted_by = models.ForeignKey("accounts.User", null=True, on_delete=models.PROTECT)
    posted_at = models.DateTimeField()
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("legal_entity", "source_key"), name="finance_payment_source_uq"
            ),
            models.CheckConstraint(
                condition=Q(amount__gt=0), name="finance_payment_amount_positive"
            ),
        ]
        indexes = [
            models.Index(
                fields=("legal_entity", "payment_date", "direction"),
                name="finance_payment_list_idx",
            )
        ]
        permissions = [
            ("post_payment", "Can post payment"),
            ("reverse_payment", "Can reverse payment"),
            ("view_cash", "Can view cash ledger"),
            ("view_bank", "Can view bank ledger"),
        ]


class PaymentAllocation(UUIDPrimaryKeyModel, TimeStampedModel):
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name="allocations")
    receivable = models.ForeignKey(
        ReceivableEntry,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payment_allocations",
    )
    payable = models.ForeignKey(
        PayableEntry,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payment_allocations",
    )
    amount = models.DecimalField(max_digits=20, decimal_places=0)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0), name="finance_payment_alloc_positive"
            ),
            models.CheckConstraint(
                condition=(
                    Q(receivable__isnull=False, payable__isnull=True)
                    | Q(receivable__isnull=True, payable__isnull=False)
                ),
                name="finance_payment_alloc_one_target",
            ),
            models.UniqueConstraint(
                fields=("payment", "receivable"), name="finance_payment_alloc_receivable_uq"
            ),
            models.UniqueConstraint(
                fields=("payment", "payable"), name="finance_payment_alloc_payable_uq"
            ),
        ]


class DepreciationMethod(models.TextChoices):
    STRAIGHT_LINE = "STRAIGHT_LINE", "Straight line"


class FixedAssetState(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    FULLY_DEPRECIATED = "FULLY_DEPRECIATED", "Fully depreciated"
    DISPOSED = "DISPOSED", "Disposed"
    REVERSED = "REVERSED", "Reversed"


class DepreciationScheduleState(models.TextChoices):
    SCHEDULED = "SCHEDULED", "Scheduled"
    POSTED = "POSTED", "Posted"
    REVERSED = "REVERSED", "Reversed"


class AssetClass(UUIDPrimaryKeyModel, TimeStampedModel, EffectivePeriodModel):
    legal_entity = models.ForeignKey(LegalEntity, on_delete=models.PROTECT)
    code = models.CharField(max_length=60)
    name = models.CharField(max_length=150)
    mapping_key = models.CharField(max_length=120)
    default_depreciation_method = models.CharField(
        max_length=30, choices=DepreciationMethod.choices, default=DepreciationMethod.STRAIGHT_LINE
    )
    default_useful_life_months = models.PositiveIntegerField()
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("legal_entity", "code"), name="finance_asset_class_code_uq"
            ),
            models.CheckConstraint(
                condition=Q(default_useful_life_months__gt=0),
                name="finance_asset_class_life_positive",
            ),
        ]


class FixedAsset(UUIDPrimaryKeyModel, TimeStampedModel):
    legal_entity = models.ForeignKey(LegalEntity, on_delete=models.PROTECT)
    asset_number = models.CharField(max_length=80)
    asset_class = models.ForeignKey(AssetClass, on_delete=models.PROTECT)
    name = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    acquisition_date = models.DateField()
    capitalization_date = models.DateField()
    acquisition_cost = models.DecimalField(max_digits=20, decimal_places=0)
    residual_value = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    useful_life_months = models.PositiveIntegerField()
    depreciation_method = models.CharField(max_length=30, choices=DepreciationMethod.choices)
    currency = models.CharField(max_length=12, default="IDR")
    source_module = models.CharField(max_length=40)
    source_document_type = models.CharField(max_length=80)
    source_document_id = models.CharField(max_length=80)
    source_key = models.CharField(max_length=255)
    source_reference = models.JSONField(default=dict, blank=True)
    capitalization_journal = models.OneToOneField(JournalEntry, on_delete=models.PROTECT)
    state = models.CharField(
        max_length=24, choices=FixedAssetState.choices, default=FixedAssetState.ACTIVE
    )
    posted_by = models.ForeignKey("accounts.User", null=True, on_delete=models.PROTECT)
    posted_at = models.DateTimeField()
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("legal_entity", "asset_number"), name="finance_fixed_asset_number_uq"
            ),
            models.UniqueConstraint(
                fields=("legal_entity", "source_key"), name="finance_fixed_asset_source_uq"
            ),
            models.CheckConstraint(
                condition=Q(acquisition_cost__gt=0), name="finance_fixed_asset_cost_positive"
            ),
            models.CheckConstraint(
                condition=Q(residual_value__gte=0), name="finance_fixed_asset_residual_nonnegative"
            ),
        ]
        permissions = [("capitalize_fixedasset", "Can capitalize fixed assets")]

    @property
    def depreciable_amount(self):
        return self.acquisition_cost - self.residual_value


class DepreciationScheduleEntry(UUIDPrimaryKeyModel, TimeStampedModel):
    fixed_asset = models.ForeignKey(
        FixedAsset, on_delete=models.PROTECT, related_name="schedule_entries"
    )
    period_date = models.DateField()
    scheduled_amount = models.DecimalField(max_digits=20, decimal_places=0)
    journal = models.OneToOneField(JournalEntry, null=True, blank=True, on_delete=models.PROTECT)
    state = models.CharField(
        max_length=16,
        choices=DepreciationScheduleState.choices,
        default=DepreciationScheduleState.SCHEDULED,
    )
    source_key = models.CharField(max_length=255)
    reversal_of = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversal"
    )
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("fixed_asset", "period_date"), name="finance_depr_asset_period_uq"
            ),
            models.UniqueConstraint(fields=("source_key",), name="finance_depr_source_uq"),
            models.CheckConstraint(
                condition=Q(scheduled_amount__gt=0), name="finance_depr_amount_positive"
            ),
        ]
        permissions = [
            ("view_depreciation", "Can view depreciation"),
            ("post_depreciation", "Can post depreciation"),
            ("reverse_depreciation", "Can reverse depreciation"),
        ]
