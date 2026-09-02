from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.dateparse import parse_date

from apps.finance.forms import (
    COAAccountForm,
    COAMappingForm,
    LifecycleReasonForm,
    LiquidityAccountForm,
    PaymentActionForm,
    PaymentReversalForm,
)
from apps.finance.models import (
    COAAccount,
    COAMapping,
    JournalEntry,
    LiquidityAccount,
    LiquidityAccountType,
    MappingDimensionType,
    MarketplacePayoutPosting,
    MarketplaceSettlementPosting,
    Payment,
)
from apps.finance.selectors import (
    bank_ledger,
    cash_ledger,
    coa_accounts,
    coa_mappings,
    general_ledger,
    marketplace_balance_entries,
    marketplace_payouts,
    marketplace_settlements,
    payables,
    payments,
    receivables,
    reconciliation,
)
from apps.finance.services import (
    create_coa_account,
    create_coa_mapping,
    create_liquidity_account,
    deactivate_coa_account,
    deactivate_coa_mapping,
    post_customer_receipt,
    post_marketplace_payout,
    post_marketplace_settlement,
    post_vendor_payment,
    reactivate_coa_account,
    reactivate_coa_mapping,
    reverse_marketplace_payout,
    reverse_marketplace_settlement,
    reverse_payment,
    update_coa_account,
    update_coa_mapping,
    update_liquidity_account,
)
from apps.organizations.selectors import accessible_legal_entities


def _require(user, action, model):
    permission = f"{model._meta.app_label}.{action}_{model._meta.model_name}"
    if not user.has_perm(permission):
        raise PermissionDenied


def _model_values(form):
    fields = {field.name for field in form._meta.model._meta.fields}
    return {key: value for key, value in form.cleaned_data.items() if key in fields}


def _add_service_errors(form, error):
    if hasattr(error, "message_dict"):
        for field, errors in error.message_dict.items():
            target = field if field in form.fields else None
            for message in errors:
                form.add_error(target, message)
    else:
        for message in error.messages:
            form.add_error(None, message)


def _require_codename(user, codename):
    if not user.has_perm(f"finance.{codename}"):
        raise PermissionDenied


def _selected_entity(request):
    entities = accessible_legal_entities(request.user).order_by("code")
    requested = request.GET.get("legal_entity", "").strip()
    selected = get_object_or_404(entities, pk=requested) if requested else entities.first()
    return entities, selected


def _finance_page_context(request):
    entities, selected = _selected_entity(request)
    return {"legal_entities": entities, "selected_entity": selected}


@login_required
def journal_list(request):
    _require(request.user, "view", JournalEntry)
    entities = accessible_legal_entities(request.user)
    search = request.GET.get("q", "").strip()
    queryset = JournalEntry.objects.filter(legal_entity__in=entities).select_related(
        "legal_entity", "posted_by", "reversal_of"
    )
    if search:
        queryset = queryset.filter(
            Q(journal_number__icontains=search)
            | Q(source_key__icontains=search)
            | Q(source_reference__icontains=search)
            | Q(event_code__icontains=search)
        )
    page = Paginator(queryset.order_by("-accounting_date", "-created_at"), 25).get_page(
        request.GET.get("page")
    )
    return render(request, "finance/journal_list.html", {"page": page, "search": search})


@login_required
def journal_detail(request, pk):
    _require(request.user, "view", JournalEntry)
    journal = get_object_or_404(
        JournalEntry.objects.filter(
            legal_entity__in=accessible_legal_entities(request.user)
        ).prefetch_related("lines__account"),
        pk=pk,
    )
    return render(request, "finance/journal_detail.html", {"journal": journal})


@login_required
def general_ledger_list(request):
    _require_codename(request.user, "view_gl")
    context = _finance_page_context(request)
    selected = context["selected_entity"]
    start = parse_date(request.GET.get("start", ""))
    end = parse_date(request.GET.get("end", ""))
    event_code = request.GET.get("event_code", "").strip()
    account_id = request.GET.get("account", "").strip()
    account = None
    if selected and account_id:
        account = get_object_or_404(COAAccount, legal_entity=selected, pk=account_id)
    rows = (
        general_ledger(
            legal_entity=selected,
            start=start,
            end=end,
            account=account,
            event_code=event_code or None,
        )
        if selected
        else JournalEntry.objects.none()
    )
    context.update(
        {
            "page": Paginator(rows, 50).get_page(request.GET.get("page")),
            "accounts": (
                COAAccount.objects.filter(legal_entity=selected, is_active=True).order_by(
                    "account_code"
                )
                if selected
                else COAAccount.objects.none()
            ),
            "start": request.GET.get("start", ""),
            "end": request.GET.get("end", ""),
            "event_code": event_code,
            "selected_account": account,
        }
    )
    return render(request, "finance/general_ledger.html", context)


@login_required
def receivable_list(request):
    _require_codename(request.user, "view_ar")
    context = _finance_page_context(request)
    selected = context["selected_entity"]
    rows = receivables(legal_entity=selected) if selected else JournalEntry.objects.none()
    context["page"] = Paginator(rows, 25).get_page(request.GET.get("page"))
    return render(request, "finance/receivable_list.html", context)


@login_required
def payable_list(request):
    _require_codename(request.user, "view_ap")
    context = _finance_page_context(request)
    selected = context["selected_entity"]
    rows = payables(legal_entity=selected) if selected else JournalEntry.objects.none()
    context["page"] = Paginator(rows, 25).get_page(request.GET.get("page"))
    return render(request, "finance/payable_list.html", context)


@login_required
def finance_reconciliation(request):
    _require_codename(request.user, "view_reconciliation")
    context = _finance_page_context(request)
    selected = context["selected_entity"]
    context["result"] = reconciliation(legal_entity=selected) if selected else None
    return render(request, "finance/reconciliation.html", context)


def _operational_rows(request, *, permission, selector, template, title):
    _require_codename(request.user, permission)
    context = _finance_page_context(request)
    selected = context["selected_entity"]
    rows = selector(legal_entity=selected) if selected else JournalEntry.objects.none()
    context.update({"page": Paginator(rows, 50).get_page(request.GET.get("page")), "title": title})
    return render(request, template, context)


@login_required
def payment_list(request):
    response = _operational_rows(
        request,
        permission="view_payment",
        selector=payments,
        template="finance/payment_list.html",
        title="Payments",
    )
    response.context_data = getattr(response, "context_data", {})
    return response


@login_required
def payment_detail(request, pk):
    _require(request.user, "view", Payment)
    payment = get_object_or_404(
        Payment.objects.filter(legal_entity__in=accessible_legal_entities(request.user))
        .select_related("liquidity_account", "journal", "liquidity_entry", "partner", "store")
        .prefetch_related("allocations__receivable", "allocations__payable"),
        pk=pk,
    )
    return render(request, "finance/payment_detail.html", {"payment": payment})


def _payment_action(request, *, target):
    _require_codename(request.user, "post_payment")
    form = PaymentActionForm(request.POST or None, user=request.user, target=target)
    if request.method == "POST" and form.is_valid():
        values = form.cleaned_data
        try:
            service = post_customer_receipt if target == "receivable" else post_vendor_payment
            payment = service(
                legal_entity=values["legal_entity"],
                liquidity_account=values["liquidity_account"],
                allocations=[{target: values[target], "amount": values["amount"]}],
                payment_date=values["payment_date"],
                source_key=values["source_key"],
                actor=request.user,
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, f"{payment.payment_number} posted.")
            return redirect("finance_operations:payment-list")
    title = "Record Customer Receipt" if target == "receivable" else "Record Vendor Payment"
    return render(
        request,
        "finance/action_form.html",
        {"form": form, "title": title, "cancel_url": "finance_operations:payment-list"},
    )


@login_required
def customer_receipt_create(request):
    return _payment_action(request, target="receivable")


@login_required
def vendor_payment_create(request):
    return _payment_action(request, target="payable")


@login_required
def payment_reverse(request, pk):
    _require_codename(request.user, "reverse_payment")
    payment = get_object_or_404(
        Payment.objects.filter(legal_entity__in=accessible_legal_entities(request.user)), pk=pk
    )
    form = PaymentReversalForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        reverse_payment(payment, actor=request.user)
        messages.success(request, f"{payment.payment_number} reversed.")
        return redirect("finance_operations:payment-list")
    return render(
        request,
        "finance/action_form.html",
        {
            "form": form,
            "title": f"Reverse {payment.payment_number}",
            "cancel_url": "finance_operations:payment-list",
        },
    )


@login_required
def cash_list(request):
    return _operational_rows(
        request,
        permission="view_cash",
        selector=cash_ledger,
        template="finance/liquidity_list.html",
        title="Cash",
    )


@login_required
def bank_list(request):
    return _operational_rows(
        request,
        permission="view_bank",
        selector=bank_ledger,
        template="finance/liquidity_list.html",
        title="Bank",
    )


@login_required
def marketplace_settlement_list(request):
    return _operational_rows(
        request,
        permission="view_marketplace_settlement",
        selector=marketplace_settlements,
        template="finance/marketplace_settlement_list.html",
        title="Marketplace Settlements",
    )


@login_required
def marketplace_settlement_post(request):
    _require_codename(request.user, "post_marketplace_settlement")
    from apps.omnichannel.models import OmniSettlement

    entity = _selected_entity(request)[1]
    sources = (
        OmniSettlement.objects.filter(legal_entity=entity)
        if entity
        else OmniSettlement.objects.none()
    )
    from django import forms

    class SettlementForm(forms.Form):
        settlement = forms.ModelChoiceField(queryset=sources)

    form = SettlementForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        result = post_marketplace_settlement(form.cleaned_data["settlement"], actor=request.user)
        if isinstance(result, dict):
            form.add_error(None, result["reason"])
        else:
            messages.success(request, "Marketplace settlement posted.")
            return redirect("finance_operations:marketplace-settlement-list")
    return render(
        request,
        "master/master_form.html",
        {
            "form": form,
            "title": "Post Marketplace Settlement",
            "cancel_url": "finance_operations:marketplace-settlement-list",
        },
    )


@login_required
def marketplace_settlement_reverse(request, pk):
    _require_codename(request.user, "reverse_marketplace_settlement")
    posting = get_object_or_404(
        MarketplaceSettlementPosting.objects.filter(
            legal_entity__in=accessible_legal_entities(request.user)
        ),
        pk=pk,
    )
    form = PaymentReversalForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        reverse_marketplace_settlement(posting, actor=request.user)
        return redirect("finance_operations:marketplace-settlement-list")
    return render(
        request,
        "master/master_form.html",
        {
            "form": form,
            "title": "Reverse Marketplace Settlement",
            "cancel_url": "finance_operations:marketplace-settlement-list",
        },
    )


@login_required
def marketplace_balance_list(request):
    return _operational_rows(
        request,
        permission="view_marketplace_balance",
        selector=marketplace_balance_entries,
        template="finance/marketplace_balance_list.html",
        title="Marketplace Balance",
    )


@login_required
def marketplace_payout_list(request):
    return _operational_rows(
        request,
        permission="view_marketplace_payoutposting",
        selector=marketplace_payouts,
        template="finance/marketplace_payout_list.html",
        title="Marketplace Payouts",
    )


@login_required
def marketplace_payout_post(request):
    _require(request.user, "add", MarketplacePayoutPosting)
    from django import forms

    from apps.omnichannel.models import OmniPayoutSource

    entity = _selected_entity(request)[1]
    sources = (
        OmniPayoutSource.objects.filter(legal_entity=entity)
        if entity
        else OmniPayoutSource.objects.none()
    )

    class PayoutForm(forms.Form):
        payout_source = forms.ModelChoiceField(queryset=sources)
        liquidity_account = forms.ModelChoiceField(
            queryset=LiquidityAccount.objects.filter(
                legal_entity=entity, account_type=LiquidityAccountType.BANK, is_active=True
            )
            if entity
            else LiquidityAccount.objects.none()
        )

    form = PayoutForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            result = post_marketplace_payout(
                form.cleaned_data["payout_source"],
                liquidity_account=form.cleaned_data["liquidity_account"],
                actor=request.user,
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            if isinstance(result, dict):
                form.add_error(None, result["reason"])
            else:
                messages.success(request, "Marketplace payout posted.")
                return redirect("finance_operations:marketplace-payout-list")
    return render(
        request,
        "master/master_form.html",
        {
            "form": form,
            "title": "Post Marketplace Payout",
            "cancel_url": "finance_operations:marketplace-payout-list",
        },
    )


@login_required
def marketplace_payout_reverse(request, pk):
    _require(request.user, "change", MarketplacePayoutPosting)
    posting = get_object_or_404(
        MarketplacePayoutPosting.objects.filter(
            legal_entity__in=accessible_legal_entities(request.user)
        ),
        pk=pk,
    )
    form = PaymentReversalForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        reverse_marketplace_payout(posting, actor=request.user)
        return redirect("finance_operations:marketplace-payout-list")
    return render(
        request,
        "master/master_form.html",
        {
            "form": form,
            "title": "Reverse Marketplace Payout",
            "cancel_url": "finance_operations:marketplace-payout-list",
        },
    )


@login_required
def liquidity_account_list(request):
    _require(request.user, "view", LiquidityAccount)
    rows = (
        LiquidityAccount.objects.filter(legal_entity__in=accessible_legal_entities(request.user))
        .select_related("legal_entity")
        .order_by("legal_entity__code", "code")
    )
    return render(
        request,
        "finance/liquidity_account_list.html",
        {
            "page": Paginator(rows, 25).get_page(request.GET.get("page")),
            "can_add": request.user.has_perm("finance.add_liquidityaccount"),
            "can_change": request.user.has_perm("finance.change_liquidityaccount"),
        },
    )


@login_required
def liquidity_account_create(request):
    _require(request.user, "add", LiquidityAccount)
    form = LiquidityAccountForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            account = create_liquidity_account(actor=request.user, **_model_values(form))
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, f"{account} created.")
            return redirect("finance:liquidity-account-list")
    return render(
        request,
        "finance/action_form.html",
        {
            "form": form,
            "title": "New Liquidity Account",
            "cancel_href": reverse("finance:liquidity-account-list"),
        },
    )


@login_required
def liquidity_account_edit(request, pk):
    _require(request.user, "change", LiquidityAccount)
    account = get_object_or_404(
        LiquidityAccount.objects.filter(legal_entity__in=accessible_legal_entities(request.user)),
        pk=pk,
    )
    form = LiquidityAccountForm(request.POST or None, instance=account, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            account = update_liquidity_account(account, actor=request.user, **_model_values(form))
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, f"{account} updated.")
            return redirect("finance:liquidity-account-list")
    return render(
        request,
        "finance/action_form.html",
        {
            "form": form,
            "title": f"Edit {account}",
            "cancel_href": reverse("finance:liquidity-account-list"),
        },
    )


@login_required
def account_list(request):
    _require(request.user, "view", COAAccount)
    include_inactive = request.GET.get("inactive") == "1"
    search = request.GET.get("q", "").strip()
    page = Paginator(
        coa_accounts(request.user, include_inactive=include_inactive, search=search),
        25,
    ).get_page(request.GET.get("page"))
    return render(
        request,
        "finance/account_list.html",
        {
            "page": page,
            "search": search,
            "include_inactive": include_inactive,
            "can_add": request.user.has_perm("finance.add_coaaccount"),
            "can_change": request.user.has_perm("finance.change_coaaccount"),
        },
    )


@login_required
def account_create(request):
    _require(request.user, "add", COAAccount)
    form = COAAccountForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            account = create_coa_account(
                actor=request.user,
                reason=form.cleaned_data.get("change_reason", ""),
                **_model_values(form),
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, f"{account} created.")
            return redirect("finance:account-list")
    return render(
        request,
        "master/master_form.html",
        {"form": form, "title": "New COA Account", "cancel_url": "finance:account-list"},
    )


@login_required
def account_edit(request, pk):
    _require(request.user, "change", COAAccount)
    account = get_object_or_404(coa_accounts(request.user, include_inactive=True), pk=pk)
    form = COAAccountForm(request.POST or None, instance=account, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            account = update_coa_account(
                account,
                actor=request.user,
                reason=form.cleaned_data["change_reason"],
                **_model_values(form),
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, f"{account} updated.")
            return redirect("finance:account-list")
    return render(
        request,
        "master/master_form.html",
        {"form": form, "title": f"Edit {account}", "cancel_url": "finance:account-list"},
    )


@login_required
def account_lifecycle(request, pk):
    _require(request.user, "change", COAAccount)
    account = get_object_or_404(coa_accounts(request.user, include_inactive=True), pk=pk)
    form = LifecycleReasonForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        service = deactivate_coa_account if account.is_active else reactivate_coa_account
        account = service(account, actor=request.user, reason=form.cleaned_data["reason"])
        messages.success(
            request, f"{account} {'activated' if account.is_active else 'deactivated'}."
        )
        return redirect("finance:account-list")
    return render(
        request,
        "master/lifecycle_form.html",
        {"form": form, "object": account, "cancel_url": "finance:account-list"},
    )


@login_required
def mapping_list(request):
    _require(request.user, "view", COAMapping)
    include_inactive = request.GET.get("inactive") == "1"
    search = request.GET.get("q", "").strip()
    dimension = request.GET.get("dimension", "").strip()
    queryset = coa_mappings(request.user, include_inactive=include_inactive, search=search)
    if dimension:
        queryset = queryset.filter(dimension_type=dimension)
    page = Paginator(queryset, 25).get_page(request.GET.get("page"))
    return render(
        request,
        "finance/mapping_list.html",
        {
            "page": page,
            "search": search,
            "dimension": dimension,
            "dimensions": MappingDimensionType.choices,
            "include_inactive": include_inactive,
            "can_add": request.user.has_perm("finance.add_coamapping"),
            "can_change": request.user.has_perm("finance.change_coamapping"),
        },
    )


@login_required
def mapping_create(request):
    _require(request.user, "add", COAMapping)
    form = COAMappingForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            mapping = create_coa_mapping(
                actor=request.user,
                reason=form.cleaned_data.get("change_reason", ""),
                **_model_values(form),
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, f"{mapping} created.")
            return redirect("finance:mapping-list")
    return render(
        request,
        "master/master_form.html",
        {"form": form, "title": "New COA Mapping", "cancel_url": "finance:mapping-list"},
    )


@login_required
def mapping_edit(request, pk):
    _require(request.user, "change", COAMapping)
    mapping = get_object_or_404(coa_mappings(request.user, include_inactive=True), pk=pk)
    form = COAMappingForm(request.POST or None, instance=mapping, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            mapping = update_coa_mapping(
                mapping,
                actor=request.user,
                reason=form.cleaned_data["change_reason"],
                **_model_values(form),
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, f"{mapping} updated.")
            return redirect("finance:mapping-list")
    return render(
        request,
        "master/master_form.html",
        {"form": form, "title": f"Edit {mapping}", "cancel_url": "finance:mapping-list"},
    )


@login_required
def mapping_lifecycle(request, pk):
    _require(request.user, "change", COAMapping)
    mapping = get_object_or_404(coa_mappings(request.user, include_inactive=True), pk=pk)
    form = LifecycleReasonForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        service = deactivate_coa_mapping if mapping.is_active else reactivate_coa_mapping
        mapping = service(mapping, actor=request.user, reason=form.cleaned_data["reason"])
        messages.success(
            request, f"{mapping} {'activated' if mapping.is_active else 'deactivated'}."
        )
        return redirect("finance:mapping-list")
    return render(
        request,
        "master/lifecycle_form.html",
        {"form": form, "object": mapping, "cancel_url": "finance:mapping-list"},
    )
