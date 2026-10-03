"""AP22 (GAI-304, ADR 0037): documented hoa responses that keep their bytes unchanged.

Generated from the observed handler results of the integration tests (generator in the AO08
and AP22 work notes). Every model is a ``TolerantRawJsonOut``: the declared fields document
the response for OpenAPI, the handler value is delivered unchanged, a mismatch is only logged.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from mhvp.accounting.write_responses import TolerantRawJsonOut as _DocOut


class HoaAcquisitionRuleListRulesOut(_DocOut):
    items: list[dict[str, Any]] | None = None
    variants: list[dict[str, Any]] | None = None
    note: str | None = None


class HoaMeetingsTallyOut(_DocOut):
    principle: str | None = None
    yes: str | None = None
    no: str | None = None
    abstain: str | None = None
    excluded: int | None = None
    majority: str | None = None
    rule: dict[str, Any] | None = None
    checks: dict[str, Any] | None = None
    proposal: str | None = None
    manual_check: bool | None = None
    channels: dict[str, Any] | None = None


class HoaAllocationProposalGetAllocationProposalSettingOut(_DocOut):
    enabled: bool | None = None
    note: str | None = None


class HoaAssetsListAssetReportsOutItem(_DocOut):
    id: uuid.UUID | None = None
    legal_entity_id: uuid.UUID | None = None
    ledger_id: uuid.UUID | None = None
    as_of: date | None = None
    status: str | None = None
    reserve_opening: str | None = None
    reserve_withdrawals: str | None = None
    reserve_interest: str | None = None
    manual_items: list[Any] | None = None
    snapshot: Any = None
    snapshot_hash: str | None = None
    issued_at: datetime | None = None
    note: Any = None
    draft_notice: Any = None


class HoaAssetsAssetReportProvisionsOut(_DocOut):
    report_id: uuid.UUID | None = None
    status: str | None = None
    items: list[dict[str, Any]] | None = None
    note: str | None = None
    dispatch_note: str | None = None


class HoaBoardSectionOut(_DocOut):
    engagement_id: uuid.UUID | None = None
    auditor_contact_ids: list[str] | None = None
    access: list[dict[str, Any]] | None = None
    notes: list[dict[str, Any]] | None = None


class HoaMeetingsAuditItemHistoryOutItem(_DocOut):
    item_version: int | None = None
    changes: dict[str, Any] | None = None
    actor_user_id: uuid.UUID | None = None
    occurred_at: datetime | None = None


class HoaBoardListAuditsOutItem(_DocOut):
    id: uuid.UUID | None = None
    legal_entity_id: uuid.UUID | None = None
    statement_id: Any = None
    period_from: date | None = None
    period_to: date | None = None
    purpose: str | None = None
    sampling: str | None = None
    status: str | None = None


class HoaMeetingsGetAuditOut(_DocOut):
    id: uuid.UUID | None = None
    authorization_text: str | None = None
    data_as_of: date | None = None
    legal_entity_id: uuid.UUID | None = None
    statement_id: Any = None
    period_from: date | None = None
    period_to: date | None = None
    purpose: str | None = None
    sampling: str | None = None
    population: dict[str, Any] | None = None
    status: str | None = None
    overall_status: str | None = None
    outdated_reasons: dict[str, Any] | None = None
    items: list[dict[str, Any]] | None = None


class HoaBoardAuditCandidatesOut(_DocOut):
    period_from: date | None = None
    period_to: date | None = None
    total: int | None = None
    truncated: bool | None = None
    items: list[Any] | None = None


class HoaBoardListReportsOutItem(_DocOut):
    id: uuid.UUID | None = None
    engagement_id: uuid.UUID | None = None
    version: int | None = None
    content: dict[str, Any] | None = None
    board_statement: dict[str, Any] | None = None
    created_at: datetime | None = None
    confirmed_by_name: Any = None
    confirmed_at: Any = None
    confirmation_note: Any = None


class HoaFinanceListClaimsOutItem(_DocOut):
    id: uuid.UUID | None = None
    legal_entity_id: uuid.UUID | None = None
    ledger_id: uuid.UUID | None = None
    title: str | None = None
    description: Any = None
    damage_date: date | None = None
    reported_on: Any = None
    insurer: Any = None
    policy_reference: Any = None
    claim_number: Any = None
    deductible: str | None = None
    status: str | None = None
    regress_party: Any = None
    measure_id: Any = None
    resolution_id: Any = None
    note: Any = None


class HoaFinanceGetClaimOut(_DocOut):
    id: uuid.UUID | None = None
    legal_entity_id: uuid.UUID | None = None
    ledger_id: uuid.UUID | None = None
    title: str | None = None
    description: Any = None
    damage_date: date | None = None
    reported_on: Any = None
    insurer: Any = None
    policy_reference: Any = None
    claim_number: Any = None
    deductible: str | None = None
    status: str | None = None
    regress_party: Any = None
    measure_id: Any = None
    resolution_id: Any = None
    note: Any = None
    items: list[Any] | None = None
    totals: dict[str, Any] | None = None
    net_burden_booked: str | None = None
    owner_payments_booked: str | None = None
    document_ids: list[Any] | None = None
    note_text: str | None = None


class HoaReserveSplitReservePaymentsOut(_DocOut):
    ledger_id: str | None = None
    year: int | None = None
    mode: str | None = None
    source: str | None = None
    statement_id: str | None = None
    paid_unassigned: str | None = None
    reserves: list[dict[str, Any]] | None = None
    note: str | None = None


class HoaFinanceListLoansOutItem(_DocOut):
    id: uuid.UUID | None = None
    legal_entity_id: uuid.UUID | None = None
    ledger_id: uuid.UUID | None = None
    lender: str | None = None
    reference: Any = None
    principal: str | None = None
    interest_rate_percent: str | None = None
    term_months: Any = None
    instalment: Any = None
    start_date: date | None = None
    end_date: Any = None
    purpose: str | None = None
    resolution_id: Any = None
    measure_id: Any = None
    account_id: Any = None
    status: str | None = None
    note: Any = None


class HoaFinanceGetLoanOut(_DocOut):
    id: uuid.UUID | None = None
    legal_entity_id: uuid.UUID | None = None
    ledger_id: uuid.UUID | None = None
    lender: str | None = None
    reference: Any = None
    principal: str | None = None
    interest_rate_percent: str | None = None
    term_months: Any = None
    instalment: Any = None
    start_date: date | None = None
    end_date: Any = None
    purpose: str | None = None
    resolution_id: Any = None
    measure_id: Any = None
    account_id: Any = None
    status: str | None = None
    note: Any = None
    items: list[Any] | None = None
    totals: dict[str, Any] | None = None
    balance_booked: str | None = None
    account_balance: Any = None
    account_difference: Any = None
    document_ids: list[Any] | None = None
    note_text: str | None = None


class HoaAssetsLoanAnnualOut(_DocOut):
    loan_id: str | None = None
    lender: str | None = None
    reference: str | None = None
    year: int | None = None
    components: dict[str, Any] | None = None
    fees_booked: str | None = None
    residual_booked: str | None = None
    residual_schedule: str | None = None
    schedule_available: bool | None = None
    note_text: str | None = None


class HoaMeetingsListRulesOutItem(_DocOut):
    id: uuid.UUID | None = None
    label: str | None = None
    principle: str | None = None
    share_of_votes_cast: Decimal | None = None
    strictly_greater: bool | None = None
    min_mea_share_of_all: Decimal | None = None
    unanimous: bool | None = None
    source: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    requires_approval: bool | None = None
    approval_status: str | None = None
    created_by: uuid.UUID | None = None
    approved_by: Any = None
    approved_at: Any = None


class HoaMajorityListSubjectRulesOutItem(_DocOut):
    id: uuid.UUID | None = None
    legal_entity_id: uuid.UUID | None = None
    subject_kind: str | None = None
    majority_type: str | None = None
    custom_numerator: Any = None
    custom_denominator: Any = None
    counting_basis: str | None = None
    source: str | None = None
    created_by: uuid.UUID | None = None
    approved_by: Any = None
    approved_at: Any = None
    rule_text: str | None = None


class HoaFinanceListMeasuresOutItem(_DocOut):
    id: uuid.UUID | None = None
    legal_entity_id: uuid.UUID | None = None
    ledger_id: uuid.UUID | None = None
    title: str | None = None
    description: Any = None
    kind: str | None = None
    kind_basis: Any = None
    cost_frame: str | None = None
    resolution_id: Any = None
    status: str | None = None
    planned_start: Any = None
    planned_end: Any = None
    account_id: Any = None
    note: Any = None


class HoaFinanceGetMeasureOut(_DocOut):
    id: uuid.UUID | None = None
    legal_entity_id: uuid.UUID | None = None
    ledger_id: uuid.UUID | None = None
    title: str | None = None
    description: Any = None
    kind: str | None = None
    kind_basis: Any = None
    cost_frame: str | None = None
    resolution_id: Any = None
    status: str | None = None
    planned_start: Any = None
    planned_end: Any = None
    account_id: Any = None
    note: Any = None
    financing: list[Any] | None = None
    financed_total: str | None = None
    financing_gap: str | None = None
    loan_ids: list[Any] | None = None
    claim_ids: list[Any] | None = None
    document_ids: list[Any] | None = None
    note_text: str | None = None


class HoaMeetingRulesGetMeetingSettingsOut(_DocOut):
    invitation_weeks: int | None = None
    virtual_meetings_enabled: bool | None = None
    virtual_basis_term_lock_enabled: bool | None = None
    virtual_basis_transition_date: Any = None
    note: str | None = None


class HoaMeetingsListMeetingsOutItem(_DocOut):
    id: uuid.UUID | None = None
    legal_entity_id: uuid.UUID | None = None
    kind: str | None = None
    mode: str | None = None
    scheduled_at: datetime | None = None
    location: Any = None
    invited_at: date | None = None
    voting_principle: str | None = None
    status: str | None = None
    minutes_document_id: Any = None
    minutes_draft_document_id: Any = None
    resolution_deadline_at: Any = None
    resolution_deadline_source: Any = None
    virtual_basis_resolution_id: Any = None
    virtual_basis_valid_until: Any = None
    invitation_weeks: int | None = None
    latest_invitation_at: date | None = None
    invitation_short_notice: bool | None = None
    invitation_short_notice_reason: Any = None
    has_dial_in: bool | None = None
    ends_at: Any = None
    origin_meeting_id: Any = None
    invitation_template_id: Any = None
    proxy_template_id: Any = None
    ballot_template_id: Any = None
    public_description: Any = None
    internal_description: Any = None
    close_requested_by: Any = None
    close_requested_at: Any = None
    closed_by: Any = None
    closed_at: Any = None


class HoaMeetingsGetMeetingOut(_DocOut):
    id: uuid.UUID | None = None
    legal_entity_id: uuid.UUID | None = None
    kind: str | None = None
    mode: str | None = None
    scheduled_at: datetime | None = None
    location: Any = None
    invited_at: date | None = None
    voting_principle: str | None = None
    status: str | None = None
    minutes_document_id: uuid.UUID | None = None
    minutes_draft_document_id: Any = None
    resolution_deadline_at: Any = None
    resolution_deadline_source: Any = None
    virtual_basis_resolution_id: uuid.UUID | None = None
    virtual_basis_valid_until: date | None = None
    invitation_weeks: int | None = None
    latest_invitation_at: date | None = None
    invitation_short_notice: bool | None = None
    invitation_short_notice_reason: str | None = None
    has_dial_in: bool | None = None
    ends_at: Any = None
    origin_meeting_id: Any = None
    invitation_template_id: Any = None
    proxy_template_id: Any = None
    ballot_template_id: Any = None
    public_description: Any = None
    internal_description: Any = None
    close_requested_by: uuid.UUID | None = None
    close_requested_at: datetime | None = None
    closed_by: uuid.UUID | None = None
    closed_at: datetime | None = None
    invitation_notice: str | None = None
    short_notice_note: str | None = None
    virtual_basis: dict[str, Any] | None = None
    virtual_basis_term_notice: Any = None
    virtual_basis_deadlines: dict[str, Any] | None = None
    agenda: list[dict[str, Any]] | None = None
    represented: int | None = None
    proxies: int | None = None
    disruptions: list[dict[str, Any]] | None = None


class HoaMeetingRulesAttendanceListOut(_DocOut):
    meeting_id: uuid.UUID | None = None
    mode: str | None = None
    counts: dict[str, Any] | None = None
    rows: list[dict[str, Any]] | None = None


class HoaMeetingsMeetingMembersOutItem(_DocOut):
    contract_id: uuid.UUID | None = None
    unit_number: str | None = None
    party_id: uuid.UUID | None = None
    party_name: str | None = None
    present: bool | None = None
    proxy: bool | None = None
    channel: str | None = None
    votes: dict[str, Any] | None = None
    vote_channels: dict[str, Any] | None = None


class HoaOnlineMeetingOnlineOverviewOut(_DocOut):
    enabled: bool | None = None
    note: str | None = None
    has_conference_link: bool | None = None
    confirmations: list[dict[str, Any]] | None = None
    proxies: list[dict[str, Any]] | None = None
    speaker_requests: list[Any] | None = None
    items: list[dict[str, Any]] | None = None
    proxy_conflict_mode: str | None = None
    conflict_note: str | None = None
    vote_conflicts: list[dict[str, Any]] | None = None
    admissibility: dict[str, Any] | None = None


class HoaPortalCircularPortalVotesOutItem(_DocOut):
    id: uuid.UUID | None = None
    agenda_item_id: uuid.UUID | None = None
    contract_id: uuid.UUID | None = None
    choice: str | None = None
    cast_at: datetime | None = None
    portal_user_id: uuid.UUID | None = None
    wording_sha256: str | None = None


class HoaOnlineMeetingGetOnlineSettingOut(_DocOut):
    enabled: bool | None = None
    proxy_conflict_mode: str | None = None
    proxy_conflict_modes: list[dict[str, Any]] | None = None
    note: str | None = None
    conflict_note: str | None = None


class HoaPlanChangeGetPlanChangeSettingOut(_DocOut):
    mode: str | None = None
    modes: list[str] | None = None
    note: str | None = None


class HoaPlanChangePlanDifferencesOut(_DocOut):
    rows: list[dict[str, Any]] | None = None
    total: str | None = None
    plan_id: uuid.UUID | None = None
    valid_from: date | None = None
    mode: str | None = None
    drafts: list[dict[str, Any]] | None = None
    note: str | None = None


class HoaPortalCircularGetSettingOut(_DocOut):
    enabled: bool | None = None
    note: str | None = None


class HoaPortalCircularPortalVotesByEntityOutItem(_DocOut):
    id: uuid.UUID | None = None
    agenda_item_id: uuid.UUID | None = None
    contract_id: uuid.UUID | None = None
    choice: str | None = None
    cast_at: datetime | None = None
    portal_user_id: uuid.UUID | None = None
    wording_sha256: str | None = None
    item_title: str | None = None
    meeting_id: uuid.UUID | None = None


class HoaReservePlanGetReservePolicyOut(_DocOut):
    opening_lock_mode: str | None = None
    note: str | None = None


class HoaReservesGetReserveOut(_DocOut):
    id: uuid.UUID | None = None
    ledger_id: uuid.UUID | None = None
    legal_entity_id: uuid.UUID | None = None
    name: str | None = None
    purpose: Any = None
    account_id: Any = None
    bank_account_id: Any = None
    resolution_id: Any = None
    active: bool | None = None
    opening_balance: str | None = None
    opening_year: int | None = None


class HoaReservesGetReserveDevelopmentOut(_DocOut):
    reserve: dict[str, Any] | None = None
    years: list[dict[str, Any]] | None = None
    note: str | None = None


class HoaReservePlanListOpeningChangesOutItem(_DocOut):
    id: uuid.UUID | None = None
    reserve_id: uuid.UUID | None = None
    mode: str | None = None
    changes: dict[str, Any] | None = None
    reason: str | None = None
    status: str | None = None
    requested_by: uuid.UUID | None = None
    requested_at: datetime | None = None
    decided_by: Any = None
    decided_at: Any = None


class HoaReservePlanListReservePlansOutItem(_DocOut):
    id: uuid.UUID | None = None
    reserve_id: uuid.UUID | None = None
    year: int | None = None
    economic_plan_id: uuid.UUID | None = None
    planned_contribution: str | None = None
    resolution_id: uuid.UUID | None = None
    status: str | None = None
    tax_classification: Any = None
    tax_classification_status: str | None = None
    tax_note: str | None = None
    note: Any = None
    resolved_at: datetime | None = None
    plan_item_amount: str | None = None
    deviation: str | None = None


class HoaAcquisitionListAcquisitionsOut(_DocOut):
    items: list[dict[str, Any]] | None = None
    note: str | None = None


class HoaPackageStatementPackageOut(_DocOut):
    statement: dict[str, Any] | None = None
    cost_items: list[dict[str, Any]] | None = None
    missing_receipts: list[str] | None = None
    key_figures: dict[str, Any] | None = None
    section_35a: dict[str, Any] | None = None
    units: list[dict[str, Any]] | None = None
    reserve: dict[str, Any] | None = None
    asset_report: dict[str, Any] | None = None
    reconciliation: dict[str, Any] | None = None
    plan: Any = None
    resolution: dict[str, Any] | None = None
    audit_reports: list[Any] | None = None
    blocking: list[dict[str, Any]] | None = None
    releasable: bool | None = None
    note: str | None = None


class HoaAssetsPatchAssetReportOut(_DocOut):
    id: uuid.UUID | None = None
    legal_entity_id: uuid.UUID | None = None
    ledger_id: uuid.UUID | None = None
    as_of: date | None = None
    status: str | None = None
    reserve_opening: str | None = None
    reserve_withdrawals: str | None = None
    reserve_interest: str | None = None
    manual_items: list[dict[str, Any]] | None = None
    snapshot: Any = None
    snapshot_hash: Any = None
    issued_at: Any = None
    note: Any = None
    draft_notice: str | None = None


class HoaMeetingsPatchAuditItemOut(_DocOut):
    id: uuid.UUID | None = None
    journal_entry_id: Any = None
    document_id: uuid.UUID | None = None
    amount: Decimal | None = None
    status: str | None = None
    note: str | None = None
    question: str | None = None
    answer: str | None = None
    risk_note: str | None = None
    version: int | None = None


class HoaReservesPatchReserveOut(_DocOut):
    id: uuid.UUID | None = None
    ledger_id: uuid.UUID | None = None
    legal_entity_id: uuid.UUID | None = None
    name: str | None = None
    purpose: Any = None
    account_id: Any = None
    bank_account_id: Any = None
    resolution_id: Any = None
    active: bool | None = None
    opening_balance: str | None = None
    opening_year: int | None = None
    opening_change: dict[str, Any] | None = None


class HoaMeetingsAnnounceOut(_DocOut):
    id: uuid.UUID | None = None
    number: int | None = None
    status: str | None = None
    votes: dict[str, Any] | None = None
    majority_check: Any = None


class HoaMeetingsCastVoteOut(_DocOut):
    id: uuid.UUID | None = None
    channel: str | None = None
    proxy_id: Any = None
    counted: bool | None = None
    conflict: bool | None = None
    conflict_id: uuid.UUID | None = None
    conflict_status: str | None = None
    hint: str | None = None


class HoaAssetsCreateAssetReportOut(_DocOut):
    id: uuid.UUID | None = None
    legal_entity_id: uuid.UUID | None = None
    ledger_id: uuid.UUID | None = None
    as_of: date | None = None
    status: str | None = None
    reserve_opening: str | None = None
    reserve_withdrawals: str | None = None
    reserve_interest: str | None = None
    manual_items: list[dict[str, Any]] | None = None
    snapshot: Any = None
    snapshot_hash: Any = None
    issued_at: Any = None
    note: Any = None
    draft_notice: str | None = None


class HoaAssetsCalculateAssetReportOut(_DocOut):
    id: uuid.UUID | None = None
    legal_entity_id: uuid.UUID | None = None
    ledger_id: uuid.UUID | None = None
    as_of: date | None = None
    status: str | None = None
    reserve_opening: str | None = None
    reserve_withdrawals: str | None = None
    reserve_interest: str | None = None
    manual_items: list[dict[str, Any]] | None = None
    snapshot: dict[str, Any] | None = None
    snapshot_hash: str | None = None
    issued_at: Any = None
    note: Any = None
    draft_notice: str | None = None


class HoaAssetsTransitionAssetReportOut(_DocOut):
    id: uuid.UUID | None = None
    legal_entity_id: uuid.UUID | None = None
    ledger_id: uuid.UUID | None = None
    as_of: date | None = None
    status: str | None = None
    reserve_opening: str | None = None
    reserve_withdrawals: str | None = None
    reserve_interest: str | None = None
    manual_items: list[dict[str, Any]] | None = None
    snapshot: dict[str, Any] | None = None
    snapshot_hash: str | None = None
    issued_at: datetime | None = None
    note: Any = None
    draft_notice: Any = None


class HoaBoardCreateBoardAccessOut(_DocOut):
    id: uuid.UUID | None = None
    account_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    invitation_token: str | None = None


class HoaBoardRevokeBoardAccessOut(_DocOut):
    id: uuid.UUID | None = None
    account_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    account_status: str | None = None
    created_at: datetime | None = None
    revoked_at: datetime | None = None


class HoaBoardAnswerBoardNoteOut(_DocOut):
    id: uuid.UUID | None = None
    engagement_id: uuid.UUID | None = None
    audit_item_id: uuid.UUID | None = None
    cost_item_id: Any = None
    kind: str | None = None
    text: str | None = None
    answer: str | None = None
    created_at: datetime | None = None
    answered_at: datetime | None = None


class HoaMeetingsCreateAuditOut(_DocOut):
    id: uuid.UUID | None = None
    population: dict[str, Any] | None = None
    snapshot_hash: str | None = None


class HoaMeetingsAddAuditItemOut(_DocOut):
    id: uuid.UUID | None = None
    journal_entry_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None
    amount: Decimal | None = None
    status: str | None = None
    note: Any = None
    question: Any = None
    answer: Any = None
    risk_note: Any = None
    version: int | None = None


class HoaMeetingsCreateReportOut(_DocOut):
    id: uuid.UUID | None = None
    version: int | None = None
    content: dict[str, Any] | None = None


class HoaMeetingsConfirmReportOut(_DocOut):
    version: int | None = None
    confirmed_by_name: str | None = None
    confirmed_at: datetime | None = None
    note: str | None = None


class HoaMeetingsCircularOut(_DocOut):
    id: uuid.UUID | None = None
    number: int | None = None
    status: str | None = None
    missing: int | None = None
    late: int | None = None
    tally: Any = None
    majority_check: Any = None
    majority_basis: str | None = None


class HoaFinanceCreateClaimOut(_DocOut):
    id: uuid.UUID | None = None
    legal_entity_id: uuid.UUID | None = None
    ledger_id: uuid.UUID | None = None
    title: str | None = None
    description: Any = None
    damage_date: date | None = None
    reported_on: Any = None
    insurer: Any = None
    policy_reference: Any = None
    claim_number: Any = None
    deductible: str | None = None
    status: str | None = None
    regress_party: Any = None
    measure_id: Any = None
    resolution_id: Any = None
    note: Any = None


class HoaFinanceAddClaimItemOut(_DocOut):
    id: uuid.UUID | None = None
    kind: str | None = None
    booking_date: date | None = None
    amount: str | None = None
    journal_entry_id: Any = None
    entry_status: Any = None
    booked: bool | None = None
    note: Any = None
    contract_id: uuid.UUID | None = None


class HoaFinanceCreateLoanOut(_DocOut):
    id: uuid.UUID | None = None
    legal_entity_id: uuid.UUID | None = None
    ledger_id: uuid.UUID | None = None
    lender: str | None = None
    reference: str | None = None
    principal: str | None = None
    interest_rate_percent: str | None = None
    term_months: int | None = None
    instalment: str | None = None
    start_date: date | None = None
    end_date: Any = None
    purpose: str | None = None
    resolution_id: Any = None
    measure_id: Any = None
    account_id: uuid.UUID | None = None
    status: str | None = None
    note: Any = None


class HoaFinanceAddLoanItemOut(_DocOut):
    id: uuid.UUID | None = None
    kind: str | None = None
    booking_date: date | None = None
    amount: str | None = None
    journal_entry_id: uuid.UUID | None = None
    entry_status: str | None = None
    booked: bool | None = None
    note: Any = None


class HoaMeetingsCreateRuleOut(_DocOut):
    id: uuid.UUID | None = None
    legal_entity_id: uuid.UUID | None = None
    label: str | None = None
    principle: str | None = None
    share_of_votes_cast: Decimal | None = None
    strictly_greater: bool | None = None
    min_mea_share_of_all: Decimal | None = None
    unanimous: bool | None = None
    source: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    requires_approval: bool | None = None
    approval_status: str | None = None
    created_by: uuid.UUID | None = None
    approved_by: Any = None
    approved_at: Any = None


class HoaMajorityCreateSubjectRuleOut(_DocOut):
    id: uuid.UUID | None = None
    legal_entity_id: uuid.UUID | None = None
    subject_kind: str | None = None
    majority_type: str | None = None
    custom_numerator: Any = None
    custom_denominator: Any = None
    counting_basis: str | None = None
    source: str | None = None
    created_by: uuid.UUID | None = None
    approved_by: Any = None
    approved_at: Any = None
    rule_text: str | None = None


class HoaFinanceCreateMeasureOut(_DocOut):
    id: uuid.UUID | None = None
    legal_entity_id: uuid.UUID | None = None
    ledger_id: uuid.UUID | None = None
    title: str | None = None
    description: Any = None
    kind: str | None = None
    kind_basis: Any = None
    cost_frame: str | None = None
    resolution_id: Any = None
    status: str | None = None
    planned_start: Any = None
    planned_end: Any = None
    account_id: Any = None
    note: Any = None


class HoaMeetingsCreateMeetingOut(_DocOut):
    id: uuid.UUID | None = None
    legal_entity_id: uuid.UUID | None = None
    kind: str | None = None
    mode: str | None = None
    scheduled_at: datetime | None = None
    location: str | None = None
    invited_at: Any = None
    voting_principle: str | None = None
    status: str | None = None
    minutes_document_id: Any = None
    minutes_draft_document_id: Any = None
    resolution_deadline_at: Any = None
    resolution_deadline_source: Any = None
    virtual_basis_resolution_id: uuid.UUID | None = None
    virtual_basis_valid_until: date | None = None
    invitation_weeks: int | None = None
    latest_invitation_at: date | None = None
    invitation_short_notice: bool | None = None
    invitation_short_notice_reason: Any = None
    has_dial_in: bool | None = None
    ends_at: Any = None
    origin_meeting_id: Any = None
    invitation_template_id: Any = None
    proxy_template_id: Any = None
    ballot_template_id: Any = None
    public_description: Any = None
    internal_description: Any = None
    close_requested_by: Any = None
    close_requested_at: Any = None
    closed_by: Any = None
    closed_at: Any = None
    virtual_basis_term_notice: str | None = None


class HoaMeetingsAddAgendaOut(_DocOut):
    id: uuid.UUID | None = None
    position: int | None = None
    majority: str | None = None
    voting_principle: Any = None


class HoaOnlineMeetingCloseVotingOut(_DocOut):
    id: uuid.UUID | None = None
    voting_opened_at: datetime | None = None
    voting_closed_at: datetime | None = None
    voting_state: str | None = None


class HoaOnlineMeetingOpenVotingOut(_DocOut):
    id: uuid.UUID | None = None
    voting_opened_at: datetime | None = None
    voting_closed_at: Any = None
    voting_state: str | None = None


class HoaMeetingsAttendanceOut(_DocOut):
    id: uuid.UUID | None = None
    represented: bool | None = None


class HoaMeetingsRequestCloseOut(_DocOut):
    id: uuid.UUID | None = None
    legal_entity_id: uuid.UUID | None = None
    kind: str | None = None
    mode: str | None = None
    scheduled_at: datetime | None = None
    location: Any = None
    invited_at: date | None = None
    voting_principle: str | None = None
    status: str | None = None
    minutes_document_id: uuid.UUID | None = None
    minutes_draft_document_id: Any = None
    resolution_deadline_at: Any = None
    resolution_deadline_source: Any = None
    virtual_basis_resolution_id: Any = None
    virtual_basis_valid_until: Any = None
    invitation_weeks: Any = None
    latest_invitation_at: Any = None
    invitation_short_notice: bool | None = None
    invitation_short_notice_reason: Any = None
    has_dial_in: bool | None = None
    ends_at: Any = None
    origin_meeting_id: Any = None
    invitation_template_id: Any = None
    proxy_template_id: Any = None
    ballot_template_id: Any = None
    public_description: Any = None
    internal_description: Any = None
    close_requested_by: uuid.UUID | None = None
    close_requested_at: datetime | None = None
    closed_by: Any = None
    closed_at: Any = None
    note: str | None = None


class HoaMeetingsConfirmCloseOut(_DocOut):
    id: uuid.UUID | None = None
    legal_entity_id: uuid.UUID | None = None
    kind: str | None = None
    mode: str | None = None
    scheduled_at: datetime | None = None
    location: Any = None
    invited_at: date | None = None
    voting_principle: str | None = None
    status: str | None = None
    minutes_document_id: uuid.UUID | None = None
    minutes_draft_document_id: Any = None
    resolution_deadline_at: Any = None
    resolution_deadline_source: Any = None
    virtual_basis_resolution_id: Any = None
    virtual_basis_valid_until: Any = None
    invitation_weeks: Any = None
    latest_invitation_at: Any = None
    invitation_short_notice: bool | None = None
    invitation_short_notice_reason: Any = None
    has_dial_in: bool | None = None
    ends_at: Any = None
    origin_meeting_id: Any = None
    invitation_template_id: Any = None
    proxy_template_id: Any = None
    ballot_template_id: Any = None
    public_description: Any = None
    internal_description: Any = None
    close_requested_by: uuid.UUID | None = None
    close_requested_at: datetime | None = None
    closed_by: uuid.UUID | None = None
    closed_at: datetime | None = None
    note: str | None = None


class HoaMeetingsWithdrawCloseOut(_DocOut):
    id: uuid.UUID | None = None
    legal_entity_id: uuid.UUID | None = None
    kind: str | None = None
    mode: str | None = None
    scheduled_at: datetime | None = None
    location: Any = None
    invited_at: date | None = None
    voting_principle: str | None = None
    status: str | None = None
    minutes_document_id: Any = None
    minutes_draft_document_id: Any = None
    resolution_deadline_at: Any = None
    resolution_deadline_source: Any = None
    virtual_basis_resolution_id: Any = None
    virtual_basis_valid_until: Any = None
    invitation_weeks: Any = None
    latest_invitation_at: Any = None
    invitation_short_notice: bool | None = None
    invitation_short_notice_reason: Any = None
    has_dial_in: bool | None = None
    ends_at: Any = None
    origin_meeting_id: Any = None
    invitation_template_id: Any = None
    proxy_template_id: Any = None
    ballot_template_id: Any = None
    public_description: Any = None
    internal_description: Any = None
    close_requested_by: Any = None
    close_requested_at: Any = None
    closed_by: Any = None
    closed_at: Any = None


class HoaMeetingsDisruptionOut(_DocOut):
    id: uuid.UUID | None = None
    legal_entity_id: uuid.UUID | None = None
    kind: str | None = None
    mode: str | None = None
    scheduled_at: datetime | None = None
    location: Any = None
    invited_at: date | None = None
    voting_principle: str | None = None
    status: str | None = None
    minutes_document_id: Any = None
    minutes_draft_document_id: Any = None
    resolution_deadline_at: Any = None
    resolution_deadline_source: Any = None
    virtual_basis_resolution_id: uuid.UUID | None = None
    virtual_basis_valid_until: date | None = None
    invitation_weeks: Any = None
    latest_invitation_at: Any = None
    invitation_short_notice: bool | None = None
    invitation_short_notice_reason: Any = None
    has_dial_in: bool | None = None
    ends_at: Any = None
    origin_meeting_id: Any = None
    invitation_template_id: Any = None
    proxy_template_id: Any = None
    ballot_template_id: Any = None
    public_description: Any = None
    internal_description: Any = None
    close_requested_by: Any = None
    close_requested_at: Any = None
    closed_by: Any = None
    closed_at: Any = None
    event_id: uuid.UUID | None = None


class HoaMeetingsInviteOut(_DocOut):
    id: uuid.UUID | None = None
    legal_entity_id: uuid.UUID | None = None
    kind: str | None = None
    mode: str | None = None
    scheduled_at: datetime | None = None
    location: str | None = None
    invited_at: date | None = None
    voting_principle: str | None = None
    status: str | None = None
    minutes_document_id: Any = None
    minutes_draft_document_id: Any = None
    resolution_deadline_at: Any = None
    resolution_deadline_source: Any = None
    virtual_basis_resolution_id: uuid.UUID | None = None
    virtual_basis_valid_until: date | None = None
    invitation_weeks: int | None = None
    latest_invitation_at: date | None = None
    invitation_short_notice: bool | None = None
    invitation_short_notice_reason: str | None = None
    has_dial_in: bool | None = None
    ends_at: Any = None
    origin_meeting_id: Any = None
    invitation_template_id: Any = None
    proxy_template_id: Any = None
    ballot_template_id: Any = None
    public_description: Any = None
    internal_description: Any = None
    close_requested_by: Any = None
    close_requested_at: Any = None
    closed_by: Any = None
    closed_at: Any = None
    short_notice: bool | None = None


class HoaMeetingsProtocolDraftOut(_DocOut):
    meeting_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None
    minutes_document_id: Any = None
    title: str | None = None
    filename: str | None = None
    status: str | None = None
    missing: list[str] | None = None
    note: str | None = None


class HoaOnlineMeetingResolveVoteConflictOut(_DocOut):
    id: uuid.UUID | None = None
    meeting_id: uuid.UUID | None = None
    agenda_item_id: uuid.UUID | None = None
    contract_id: uuid.UUID | None = None
    vote_id: uuid.UUID | None = None
    mode: str | None = None
    first_source: str | None = None
    first_choice: str | None = None
    second_source: str | None = None
    second_choice: str | None = None
    second_proxy_id: uuid.UUID | None = None
    second_channel: str | None = None
    attempted_at: datetime | None = None
    status: str | None = None
    resolution: str | None = None
    decision_note: str | None = None
    decided_at: datetime | None = None


class HoaPlanChangeApprovePlanDifferenceOut(_DocOut):
    id: uuid.UUID | None = None
    plan_id: uuid.UUID | None = None
    unit_id: uuid.UUID | None = None
    contract_id: uuid.UUID | None = None
    component: str | None = None
    period_month: date | None = None
    posted_amount: str | None = None
    new_amount: str | None = None
    difference: str | None = None
    mode: str | None = None
    proposed_due: date | None = None
    status: str | None = None
    created_by: uuid.UUID | None = None
    decided_by: uuid.UUID | None = None
    decided_at: datetime | None = None


class HoaPlanChangeRejectPlanDifferenceOut(_DocOut):
    id: uuid.UUID | None = None
    plan_id: uuid.UUID | None = None
    unit_id: uuid.UUID | None = None
    contract_id: uuid.UUID | None = None
    component: str | None = None
    period_month: date | None = None
    posted_amount: str | None = None
    new_amount: str | None = None
    difference: str | None = None
    mode: str | None = None
    proposed_due: date | None = None
    status: str | None = None
    created_by: uuid.UUID | None = None
    decided_by: uuid.UUID | None = None
    decided_at: datetime | None = None


class HoaPlanChangeDraftPlanDifferencesOut(_DocOut):
    created: int | None = None
    mode: str | None = None
    proposed_due: date | None = None


class HoaReservePlanDeriveReservePlansOutItem(_DocOut):
    id: uuid.UUID | None = None
    reserve_id: uuid.UUID | None = None
    year: int | None = None
    economic_plan_id: uuid.UUID | None = None
    planned_contribution: str | None = None
    resolution_id: Any = None
    status: str | None = None
    tax_classification: Any = None
    tax_classification_status: str | None = None
    tax_note: str | None = None
    note: Any = None
    resolved_at: Any = None
    plan_item_amount: str | None = None
    deviation: str | None = None


class HoaReservePlanApproveOpeningChangeOut(_DocOut):
    id: uuid.UUID | None = None
    reserve_id: uuid.UUID | None = None
    mode: str | None = None
    changes: dict[str, Any] | None = None
    reason: str | None = None
    status: str | None = None
    requested_by: uuid.UUID | None = None
    requested_at: datetime | None = None
    decided_by: uuid.UUID | None = None
    decided_at: datetime | None = None


class HoaReservePlanResolveReservePlanOut(_DocOut):
    id: uuid.UUID | None = None
    reserve_id: uuid.UUID | None = None
    year: int | None = None
    economic_plan_id: uuid.UUID | None = None
    planned_contribution: str | None = None
    resolution_id: uuid.UUID | None = None
    status: str | None = None
    tax_classification: Any = None
    tax_classification_status: str | None = None
    tax_note: str | None = None
    note: Any = None
    resolved_at: datetime | None = None
    plan_item_amount: str | None = None
    deviation: str | None = None


class HoaReservePlanCreateReservePlanOut(_DocOut):
    id: uuid.UUID | None = None
    reserve_id: uuid.UUID | None = None
    year: int | None = None
    economic_plan_id: Any = None
    planned_contribution: str | None = None
    resolution_id: Any = None
    status: str | None = None
    tax_classification: Any = None
    tax_classification_status: str | None = None
    tax_note: str | None = None
    note: Any = None
    resolved_at: Any = None


class HoaAcquisitionReleaseOut(_DocOut):
    contract_id: uuid.UUID | None = None
    contract_number: str | None = None
    unit_number: str | None = None
    acquisition_kind: str | None = None
    case_label: str | None = None
    special_succession_liability: bool | None = None
    start_date: date | None = None
    title_transfer_date: date | None = None
    allocation_proposal: str | None = None
    status: str | None = None
    allocation_variant: str | None = None
    requested_by: uuid.UUID | None = None
    requested_at: datetime | None = None
    released_by: uuid.UUID | None = None
    released_at: datetime | None = None
    release_note: str | None = None


class HoaAcquisitionRequestReleaseOut(_DocOut):
    contract_id: uuid.UUID | None = None
    contract_number: str | None = None
    unit_number: str | None = None
    acquisition_kind: str | None = None
    case_label: str | None = None
    special_succession_liability: bool | None = None
    start_date: date | None = None
    title_transfer_date: date | None = None
    allocation_proposal: str | None = None
    status: str | None = None
    allocation_variant: str | None = None
    requested_by: uuid.UUID | None = None
    requested_at: datetime | None = None
    released_by: Any = None
    released_at: Any = None
    release_note: Any = None


class HoaMeetingRulesPutMeetingSettingsOut(_DocOut):
    invitation_weeks: int | None = None
    virtual_meetings_enabled: bool | None = None
    virtual_basis_term_lock_enabled: bool | None = None
    virtual_basis_transition_date: Any = None
    note: str | None = None


class HoaMeetingRulesPutDialInOut(_DocOut):
    id: uuid.UUID | None = None
    dial_in_url: str | None = None
    dial_in_access: str | None = None


class HoaReserveSplitPutSplitSettingOut(_DocOut):
    mode: str | None = None
    modes: list[str] | None = None
    note: str | None = None


class HoaReservePlanPutReservePolicyOut(_DocOut):
    opening_lock_mode: str | None = None
    note: str | None = None
