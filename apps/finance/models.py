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
