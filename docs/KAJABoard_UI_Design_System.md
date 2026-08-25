# KAJABoard UI Design System

> **AUTHORITATIVE UPDATE (25 August 2026): OWNER APPROVED FOR PHASE 0 CLOSURE.** Actual UI/print evidence was audited. Sections 16-17 define the accepted workflow controls; visual styling remains a later design decision.

**Current authoritative status:** ACCEPTED - PHASE 0 CLOSED; PHASE 1 NOT STARTED.  

**Phase:** 0 — UX and interaction baseline  
**Status:** DRAFT FOR REVIEW  
**Frontend baseline:** Django Templates + HTMX + limited Alpine.js + Bootstrap 5/Tabler + KAJA design tokens

## 1. Design goals

KAJABoard should feel modern, clean, responsive, quick-action oriented, keyboard-friendly where useful, mobile-friendly for monitoring/approval, and dense-but-readable on desktop for Finance and reconciliation. The old GAS layout may change completely, but no accepted business capability, validation, state, exception, print, or lineage may disappear.

Principles:

1. show the business state and next valid action, not technical endpoint names;
2. surface ownership—“waiting for Warehouse” and “Finance posting failed” are distinct from “saved”;
3. prevent errors before posting and explain server rejections in plain language;
4. preserve context with document lineage and source links;
5. make exceptions actionable, never hide them in totals;
6. use progressive disclosure for complex accounting/stock detail;
7. optimize routine entry without weakening validation, permission, approval, or audit;
8. never present a report refresh as a posting action.

## 2. Shell and navigation

### Desktop

- collapsible left sidebar grouped by business domain;
- top bar with global search, legal entity/business unit context where applicable, notifications, My Work, and user menu;
- breadcrumb and page title with document number/state;
- contextual quick actions based on permission and current state;
- content width supports dense tables and reconciliation work;
- optional right offcanvas for activity, approval, attachments, and lineage.

### Mobile

- offcanvas or compact bottom navigation for frequent destinations;
- touch targets and actions sized for approval/monitoring;
- tables adapt to cards/priority columns rather than unusable horizontal compression;
- sticky primary action when safe;
- destructive/reversal actions remain deliberate and never become swipe-only gestures.

### Information architecture

| Navigation group | Primary capabilities |
|---|---|
| My Work | assigned approvals, pending Warehouse/Finance/QC actions, repair items, overdue tasks |
| Sales | orders, deliveries, invoices, Customer 360, projects, prints |
| Purchasing | purchases, SPK, material send, maklun receipt, vendor views |
| Production | WIP, work entry, handover, HPP, rejects |
| Warehouse | inbound/outbound queue, stock, packing, opname, adjustments, reconciliation |
| Quality | inspection queue, decisions, returns, evidence |
| Omnichannel / POS | imports, mappings, orders/demand, settlement, payout, returns, reconciliation, POS |
| Finance | journals, AR/AP, payment, cash/bank, marketplace controls, fixed assets, closing |
| Reports / Analytics | financial, operational, project, store, customer/vendor/SKU views and archives |
| Master / Settings | organization, partners, catalog, cost centers, purchase categories, stores, mappings, COA/COA Mapping, tax, permissions |

Navigation is role- and data-scope-aware. Hiding a link is not authorization; server checks remain mandatory.

## 3. Design tokens

Exact KAJA brand palette, typeface, logo use, and visual asset rules were not provided. They are intentionally not invented.

| Token group | Required semantic roles | Baseline rule |
|---|---|---|
| Color | canvas, surface, text primary/muted, border, brand primary/secondary, info, success, warning, danger, focus, disabled | Define as CSS custom properties; meet accessible contrast; semantic state color cannot be the only cue. Exact values `UNRESOLVED`. |
| Typography | display/page title, section heading, body, label, table, numeric/monospace identifiers | Use a legible web-safe/approved brand stack; tabular numerals for quantities/money; exact family `UNRESOLVED`. |
| Spacing | 4/8-based compact scale | Dense ERP tables may use compact spacing; forms retain adequate touch/reading space. |
| Radius/shadow | card/input/modal hierarchy | Keep restrained and consistent; avoid decorative noise. |
| Motion | loading, reveal, transition | Short and functional; respect reduced-motion preferences. |
| Focus | keyboard focus ring | Always visible and not conveyed only by color. |
| Status | draft/pending/posted/reversed/error/hold/approved | Badge includes text/icon; state vocabulary comes from Workflow Matrix. |

Bootstrap/Tabler variables should be overridden through KAJA tokens rather than scattered hardcoded styles.

## 4. Page anatomy

```text
Breadcrumb
Page title + document number + owned state badges
Primary actions / overflow actions
Context summary (partner/project/store/period/warehouse)
Alerts, exceptions, or blocking validation
Main content tabs/sections
Line items or work queue
Totals / reconciliation summary
Activity, approval, lineage, attachments
Sticky action area where appropriate
```

Document pages distinguish:

- source state (for example Sales invoice `POSTED`);
- Warehouse state (for example issue `PENDING` or `POSTED`);
- Finance state (for example AR `OPEN/PARTIAL/SETTLED`);
- exceptions/repair status.

One generic “Success” badge must not conceal a failed required downstream effect.

## 5. Core components

| Component | Required behavior |
|---|---|
| Data table | Server pagination/filter/sort; sticky key columns/header where useful; selectable rows; column priority; empty/loading/error state; no unbounded payload. |
| Status badge | Controlled value, text plus semantic color/icon; tooltip/description for uncommon states. |
| Summary/KPI card | Label, value, period/filter, comparison where meaningful, freshness/as-of, drill-down; never unexplained total. |
| Form field | Persistent label, help, required indicator, server error near field, preserved input after failure; type-appropriate widget. |
| Line editor | Stable line identity; add/edit/remove explicit; row errors retained; sibling lines never disappear when one line is corrected. |
| Modal | Short focused confirmation/detail only; not a hidden multi-step transaction. |
| Offcanvas | Filters, activity, attachments, lineage, quick supporting details. |
| Tabs | Distinct information views; state/action cannot be hidden only in an inaccessible tab. |
| Toast | Non-critical confirmation only; critical errors persist in page/repair queue. |
| Alert / exception banner | Clear cause, affected source, safe next action, permission/owner, link to repair/details. |
| Timeline | State transitions, approvals, posting, reversal, comments, attachments, actor/time/reason. |
| Lineage panel | Clickable upstream/downstream documents, owned effect state, source IDs. |
| File upload | Drag/drop and browse, type/size rules, checksum metadata, validation progress, preview, warning/error download. |
| Reconciliation panel | Source total vs control total, difference, status, tolerance, explanation, drill-down and approved resolution. |
| Money/quantity display | IDR and quantity precision separated; whole-Rupiah accounting display, UOM-aware decimals, aligned/tabular numerals. |

## 6. Form and posting pattern

Use a two-level action pattern:

- `Save Draft` preserves incomplete work without ledger effects.
- `Submit`, `Approve`, `Post`, `Accept`, or `Pay` names the real controlled transition.

For an effective action:

1. display a pre-post summary of document, lines, quantities/amounts, date/period, warehouse/store/project, and downstream effects;
2. show blocking errors separately from warnings;
3. require reason/approval reference for overrides, reversals, adjustments, reopen, and critical variance;
4. disable duplicate submit locally but rely on server idempotency;
5. return the durable result and source/movement/journal reference;
6. if a required owned effect is pending or fails, show explicit pending/repair state and responsible team.

Generic buttons such as `Process` or `Update Status` should be avoided when a business verb can name the outcome.

## 7. Workflow-specific patterns

### 7.1 Sales and partial delivery

- Order detail shows ordered, posted delivered, remaining, reserved/ready, invoiced, and Finance payment state by stable line.
- Delivery builder selects source lines and caps qty at current remaining; server revalidates under lock.
- Multiple Surat Jalan remain visible in lineage.
- Invoice builder shows allowed source basis and prevents unsupported lines.
- Customer 360 separates commercial, Finance, operations, and relationship sections.

### 7.2 Purchasing treatment

- Purchase line makes Accounting Treatment visible; behavior is not inferred from category name.
- `ASSET` reveals asset class/context and explicitly states “does not enter stock.”
- `EXPENSE`/`SERVICE` requires Cost Center.
- Production-overhead eligibility indicator explains the three-part rule and cannot be toggled into an invalid combination.
- `MAKLUN` reveals SPK/vendor/material-output context.

### 7.3 Production WIP

- Work entry groups by SPK output Item, not only aggregate SPK.
- Each stage shows available-before, entered qty, remaining-after and reject quantities.
- Multi-line input preserves stable row identity and row-level errors.
- Close-SPK review lists each output's target, accepted handover, rejects, remaining WIP, and blocking reason.
- HPP detail expands into material/labor/extra/overhead/subcontract/other sources with allocation and reversal state.

### 7.4 Warehouse

- Work queues are separated by source type and state: inbound, outbound, packing, returns, adjustments, opname.
- Posting preview shows actual Item/variant, warehouse/location, on-hand/reserved/available, requested qty, cost/value and source.
- Manual mutation is presented as typed `Adjustment`, `Internal Consumption`, or `Opening Stock`, not a generic free-form stock write.
- Opname shows system qty, count, variance, reason, approval and posted variance movement.

### 7.5 Quality and returns

- Inspection records offered/inspected/accepted/rejected/rework/hold quantities and evidence.
- PASS/HOLD/REJECT/REWORK are explicit actions with consequences.
- Return detail distinguishes registered, item received, QC state, stock state, Finance adjustment and reconciliation.
- The UI must never imply stock has returned merely because a return file is imported.

### 7.6 Omnichannel import and mappings

- Upload flow: file → mapping/parse → validation preview → confirm → result/reconciliation.
- Preview displays external Store/SKU/product/variation, matched canonical IDs, raw qty, conversion and internal qty.
- Unmapped Store/SKU rows are actionable and cannot silently post stock/revenue.
- Order detail displays order-created and completion times with separate semantic labels.
- Operational charts and revenue charts clearly show which date basis is used.

### 7.7 Settlement and payout

- Settlement review aggregates by Store + Order and expands structured fee roles.
- Show recognized AR, settlement clearing, net marketplace balance, fees, difference and matching status.
- Never label settlement import as revenue recognition.
- Payout screen shows marketplace balance source and target bank, distinct from customer/marketplace AR.

### 7.8 POS

- Search/select actual internal Item; category/subcategory is only a browsing aid.
- Show price snapshot, qty, line total, stock availability, tender and total.
- Submit produces one clear receipt/result only after required stock/Finance effects are durable, or a non-final repair state.
- Large touch targets and keyboard/scanner-friendly flow may be added after actual operating hardware/workflow is confirmed.

### 7.9 Finance and closing

- Journal preview shows source, date/period, dimensions, mapping resolution, Debit/Credit and balance before Post.
- Account mapping errors identify missing Event/Line Role/dimension without exposing a misleading fallback.
- AR/AP views show source, original/open amount, due/overdue, allocations, payment lineage.
- Period-close workspace is checklist-driven with reconciliation evidence, blockers, approval and reopen history.
- Reports offer filter/as-of/definition version/export and drill-down; refresh never posts.

## 8. Tables, filters, search, and bulk action

- Default filters must be visible and removable; “as of” and period basis are always shown for financial/stock reports.
- Persist safe user preferences without changing business semantics.
- Global search returns only records permitted by data scope and labels source/module/state clearly.
- Bulk actions operate only on homogeneous eligible rows, show count/total/effect preview, and return row-level outcomes.
- Bulk posting/import still uses per-source idempotency and validation.
- Export respects current filters and permissions and includes report metadata.

## 9. Validation, error, and repair language

Errors should answer: what happened, which record/line, why it is blocked, which owner can resolve it, and what safe next step exists.

Examples:

| Avoid | Prefer |
|---|---|
| “Invalid data” | “Delivery line KAJA-001 requests 8; only 5 remain after posted Surat Jalan.” |
| “Stock error” | “Warehouse JKT has 3 available; packing requests 4. Reduce quantity or resolve the shortage.” |
| “Mapping missing” | “No active COA Mapping for OMNI_SETTLEMENT / ADMIN_FEE / Store KIRAL-SHOPEE on 25 Aug 2026. Finance must configure it before posting.” |
| “Save failed” | “POS receipt was not posted. No stock issue or Finance event was committed. Retry with the same receipt key.” |
| “Closed” | “August 2026 is LOCKED. Normal posting is blocked; request an approved prior-period correction.” |

Never expose stack traces, secrets, filesystem paths, or raw database errors to users.

## 10. Accessibility and localization

- Keyboard navigation and visible focus for routine desktop workflows.
- Semantic headings, labels, table headers, buttons and live regions for HTMX updates.
- Color is supplemented by text/icon; minimum accessible contrast must be verified.
- Touch targets remain usable on mobile.
- Respect reduced motion and browser zoom.
- Use Asia/Jakarta display timezone unless a confirmed per-user policy replaces it.
- Dates, currency and numbers are consistently localized; labels make order date, completion date, settlement date, posting date, and due date unambiguous.
- User-facing business language may be Bahasa Indonesia; canonical code/state values remain stable internally. Final terminology glossary is unresolved.

## 11. Empty, loading, stale, and offline states

| State | Required presentation |
|---|---|
| Empty | Explain whether no data exists or filters hide it; offer permitted next action. |
| Loading | Keep context; use small progress indicators/skeletons; prevent duplicate action locally. |
| Error | Persistent actionable message with safe retry and source key; do not imply success. |
| Stale/concurrent | Tell user data changed, refresh authoritative values, preserve draft input where safe. |
| Import partial failure | Counts and downloadable row errors; successful/failed rows explicit. |
| Repair required | Dedicated queue with owner, source, attempted effect, retry/correction action and audit. |
| Offline | No v1 offline posting is assumed; block effective actions cleanly and preserve only safe client draft if later approved. |

## 12. Print and export

Required Sales prints: Proforma Invoice, Invoice, Surat Jalan, Shipping Label, SOA. Purchasing retains SPK print/PDF. Reports export XLSX/PDF and may include Summary, Detail, Supporting Schedule, and Report Info.

Print/export rules:

- company/brand/letterhead/bank display data comes from master snapshots/configuration;
- document number, status, source references, dates, page numbering and generated metadata are explicit;
- draft/void/reversed copies are visibly marked;
- financial archive includes company, period, filters, generated by/time, app and definition versions;
- authorization is checked at generation and download;
- layouts may be redesigned after representative accepted outputs are supplied.

## 13. Django Admin boundary

Django Admin may serve technical/low-frequency configuration during early phases with strict permissions and audit. It is not the primary operational UI and should not expose unsafe bulk delete, direct posted-field edit, or bypassable state/account mapping behavior.

## 14. UX acceptance checklist

- All permitted next actions correspond to legal state transitions.
- Ownership/pending/repair status is visible across source, Warehouse, QC, and Finance.
- Required business validations appear both proactively and from authoritative server responses.
- Stable line identity survives multi-row edits and errors.
- No generic delete is offered for posted history.
- Reversal/adjustment explains impact and requires reason/approval where needed.
- Tables are bounded, filterable, readable, and responsive.
- Important numbers show date basis/as-of and drill down to source.
- Imports provide preview and results; no silent partial success.
- Reports and dashboard refreshes have no posting side effects.
- Desktop Finance/reconciliation and mobile approval/monitoring scenarios are tested.
- Permission and data scope apply to navigation, query results, detail, actions, export and attachment download.

## 15. UNRESOLVED design decisions

| ID | Missing decision/evidence | Affected UI | Stock impact | Accounting impact | Recommended interpretation |
|---|---|---|---|---|---|
| U-UI-001 | Actual legacy UI/JS/CSS/print files and accepted screenshots are absent. | All modules | Hidden stock actions may be missed. | Hidden posting/payment actions may be missed. | Obtain source and walkthrough recordings; make an action-to-use-case inventory before accepting redesign. |
| U-UI-002 | KAJA brand palette, typography, logo/brand variants and print identity are not supplied. | Shell, documents, reports | None. | Formal document identity. | Create approved token/brand appendix; do not invent exact brand values. |
| U-UI-003 | Roles, devices, screen sizes, transaction volumes, barcode/scanner/printer use and connectivity constraints are unknown. | Navigation, POS, Warehouse, Production | Entry speed/duplicate risk. | POS/tender/print risk. | Conduct role-based workflow observation and device inventory. |
| U-UI-004 | Bahasa Indonesia terminology and canonical labels for states/actions need business approval. | All | Misinterpreted movement action. | Misinterpreted post/reversal action. | Approve bilingual/canonical terminology glossary with state matrix. |
| U-UI-005 | Exact print samples and legally/operationally required fields are absent. | Sales/Purchasing/Finance exports | Delivery evidence. | Invoice/SOA/tax evidence. | Freeze accepted sample outputs and map each field to source/snapshot. |
| U-UI-006 | Approval thresholds and segregation determine which actions/buttons appear. | All critical workflows | Unauthorized stock effects. | Unauthorized payment/journal/close. | Finalize authorization matrix before interactive prototypes are accepted. |
| U-UI-007 | Accessibility target standard is not explicitly named. | All | None directly. | None directly. | Use WCAG 2.2 AA as recommended implementation target, subject to approval. |

## 16. Actual-evidence UI and document delta

The existing design system supports the evidence, with these required extensions:

| Legacy interaction | Required target interaction |
|---|---|
| Portal card/module launcher with HMAC session heartbeat | Accessible app launcher; session-expiry/refresh notice; no client-side authorization assumption |
| Sales modal entry for PO/SJ/invoice and quick-add masters | Step-aware line editor with stable line IDs, server remaining validation, source lineage and permissioned quick-add |
| `Tarik Sisa` advisory delivery population | Show ordered/delivered/remaining per line; submit remains server-authoritative |
| Invoice pulls PO or SJ/manual | Default delivered-not-invoiced source; direct SO option appears only with permission and requires reason/audit; proforma visibly marked non-posting/no AR |
| Purchasing SPK line generator and Sales PO pull | Preserve material-output pairing visibly; never generate an output row without required material/disposition context |
| Production stage entry and live WIP | Per-output availability card showing Cut/Sew/QC/Handover and reject deductions; cross-item totals cannot mask shortage |
| Warehouse PR summary + lazy detail | Summary by Item with drill-down by date/store/source; raw-fallback/freshness warning is visible |
| Warehouse manual movement/opname/audit | Separate Internal Usage, Adjustment and Stocktake screens; mandatory reason/approval; preview book/physical/variance |
| Omni import preview/mapping | Batch preview with schema/channel, raw and normalized MarketplaceStatusMap result, rejected rows, Order+SKU+Variation, three quantities and valid Waktu Selesai |
| POS item/subcategory menu | Search/select actual Item only; show item/SKU/variant, availability, price/cost snapshots, explicit tender, cash session and retry-safe posting state |
| Return QC camera scanner | Camera + manual fallback, session, duplicate/source match, PASS/HOLD/REJECT/REWORK; legacy unmapped rows show raw value and review-only state |
| Finance compact dashboard/heavy tabs | Lazy report loading with source/ledger reconciliation banner; refresh never posts |
| Bank statement modal and candidate matching | Upload verification summary; one-to-many allocation; unmatched/partial/matched totals; immutable audit trail |

### 16.1 Required print/document inventory

| Document/report | Evidence | Target requirement |
|---|---|---|
| Sales PO/proforma | Sales print templates | A4, company snapshot, customer, lines, totals, terms, source ID |
| Invoice | Sales print templates | A4, posting/payment projection clearly distinguished |
| Surat Jalan | Sales print templates | A4, delivered lines, source order, acknowledgement fields |
| Shipping label | Sales print templates | 4x6 layout, delivery/customer/expedition references |
| Statement of Account | Sales print templates | Finance-owned balance/payment facts with source drill-down |
| SPK/maklun/work detail | Purchasing print templates | Material-output pairs, supplier/subcontract, quantities, approved photo handling |
| Production payroll recap | Production UI print | PIC, period, tariff snapshot, quantities, wage total and approval/audit |
| Retail/POS receipt | Omni UI | actual Item, qty, price, total, tender, transaction/source key |
| Financial reports | Finance UI | P&L, balance sheet, COGM/COGS, cash flow, AR, AP with period/as-of labels and ledger source |

### 16.2 Evidence-specific UI controls

- Never offer subcategory-only POS posting or ambiguous item display names.
- Distinguish `Saved`, `Warehouse pending`, `Warehouse posted`, `Finance pending`, `Finance posted`, and repair-needed states.
- Provide idempotent retry feedback using the original result; do not create a new document number on network retry.
- Print/report previews are read-only. Data repair/rebuild/close actions require separate permissioned confirmation, dry-run summary where practical, and audit reason.
- Legacy inline notifications may be replaced by accessible toast/inline errors, but scanner and posting failures must remain visible until resolved.
- Purchase staging must show the explicit mapped treatment and block `UNMAPPED` rows without guessing from category text.
- POS draft cancellation, posted reversal and separate return are distinct actions. A cash close view shows expected cash, actual cash and variance before closing the session.
- Revaluation/correction UI always links the original movement/document/period and shows the authorized open correction period; it never offers historical overwrite.
- Production shared-cost UI must disclose allocation rule/version and item results. The exact formula is deferred to the Production/HPP design gate.

Brand palette, final component styling, device-specific optimization and exact legal document formatting are **DEFERRED IMPLEMENTATION DETAILS**. They do not change the accepted foundation architecture or block Phase 1.

## 17. Evidence-based phase gate

**PHASE 0 GATE = PASS. Owner/Stakeholder Acceptance: APPROVED FOR PHASE 0 CLOSURE.** UI workflow requirements are sufficient for Phase 1 foundation work. No frontend implementation has started.

## 18. Historical provisional phase gate (superseded)

This document is a design-system baseline, not a frontend implementation. No UI should be built until the Phase 0 source/action audit and business review are complete. Exact branding, terminology, print layouts, and role/device workflows remain open decisions.
