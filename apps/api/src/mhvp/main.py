"""FastAPI application factory.

``uvicorn mhvp.main:app`` resolves ``app`` lazily (module ``__getattr__``), so importing this
module has no side effects and tests build their own app with :func:`create_app`.
"""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from mhvp.accounting.admin_fees import router as accounting_admin_fee_router
from mhvp.accounting.audit_export_routers import router as accounting_audit_export_router
from mhvp.accounting.chart_release_routers import router as chart_release_router
from mhvp.accounting.datev_check_routers import router as datev_check_router
from mhvp.accounting.datev_mapping_routers import router as datev_mapping_router
from mhvp.accounting.direct_debit_routers import router as direct_debit_router
from mhvp.accounting.g1_opening_routers import router as g1_opening_router
from mhvp.accounting.rent_invoice_routers import router as rent_invoice_router
from mhvp.accounting.report_routers import router as accounting_report_router
from mhvp.accounting.routers import intake_router as accounting_intake_router
from mhvp.accounting.routers import router as accounting_router
from mhvp.accounting.tax_routers import router as accounting_tax_router
from mhvp.accounting.xrechnung import router as accounting_xrechnung_router
from mhvp.ai.routers import router as ai_router
from mhvp.ai.routers_onboarding import router as ai_onboarding_router
from mhvp.automation.learning import router as rule_proposal_router
from mhvp.automation.routers import router as automation_router
from mhvp.banking.fints_routers import router as fints_router
from mhvp.banking.payment_run_routers import router as payment_run_router
from mhvp.banking.routers import finapi_router
from mhvp.banking.routers import router as banking_router
from mhvp.billing.advance_routers import router as advance_rule_router
from mhvp.billing.advance_routers import statement_router as advance_proposal_router
from mhvp.billing.ai_check_routers import router as statement_ai_check_router
from mhvp.billing.allocability_routers import router as operating_cost_type_router
from mhvp.billing.allocability_routers import statement_router as allocability_router
from mhvp.billing.consumption_info_routers import router as consumption_info_router
from mhvp.billing.heating_routers import router as heating_router
from mhvp.billing.letter_routers import router as statement_letters_router
from mhvp.billing.owner_statement_routers import router as owner_statement_router
from mhvp.billing.routers import router as billing_router
from mhvp.communication.assignment_review import router as assignment_review_router
from mhvp.communication.calendar_feed import router as calendar_feed_router
from mhvp.communication.dispatch import router as dispatch_router
from mhvp.communication.draft_attachments import router as mail_draft_attachments_router
from mhvp.communication.gmail_push import router as gmail_push_router
from mhvp.communication.postal import router as postal_router
from mhvp.communication.routers import router as mail_router
from mhvp.communication.signatures import router as mail_signature_router
from mhvp.communication.telephony import router as telephony_router
from mhvp.contacts.routers import router as contacts_router
from mhvp.contacts.routers_merge import router as contacts_merge_router
from mhvp.contacts.routers_p16 import router as contacts_p16_router
from mhvp.contracts.deposit_settlement_routers import router as deposit_settlements_router
from mhvp.contracts.routers import router as contracts_router
from mhvp.contracts.routers_p16 import router as contracts_p16_router
from mhvp.contracts.service_contract_routers import router as service_contracts_router
from mhvp.core import crypto, health
from mhvp.core.auth import oidc
from mhvp.core.auth.routers import router as auth_router
from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.health import ReadinessCheck
from mhvp.core.idempotency import IdempotencyMiddleware
from mhvp.core.logging import configure_logging
from mhvp.core.middleware import CorrelationIdMiddleware
from mhvp.core.problems import install_problem_handlers
from mhvp.core.ratelimit import RateLimitMiddleware
from mhvp.core.release_gates import ClosedReleaseGateResolver, ReleaseGateResolver
from mhvp.core.security_headers import SecurityHeadersMiddleware
from mhvp.core.storage import create_s3_client
from mhvp.core.versioning import ApiVersionMiddleware, mark_deprecated_routes
from mhvp.dataquality.routers import router as data_quality_router
from mhvp.documents.intake_routers import router as documents_intake_router
from mhvp.documents.paperless_webhook import router as paperless_webhook_router
from mhvp.documents.routers import router as documents_router
from mhvp.handover.imports import router as handover_imports_router
from mhvp.handover.portal import router as handover_portal_router
from mhvp.handover.portal import staff_router as handover_staff_portal_router
from mhvp.handover.routers import router as handover_router
from mhvp.hoa.assets import router as hoa_assets_router
from mhvp.hoa.board import router as hoa_board_router
from mhvp.hoa.finance import router as hoa_finance_router
from mhvp.hoa.inspection import router as hoa_inspection_router
from mhvp.hoa.levies import router as hoa_levies_router
from mhvp.hoa.majority import router as hoa_majority_router
from mhvp.hoa.meeting_rules import router as hoa_meeting_rules_router
from mhvp.hoa.meetings import router as hoa_meetings_router
from mhvp.hoa.package import router as hoa_package_router
from mhvp.hoa.routers import router as hoa_router
from mhvp.immoware.routers import router as immoware_router
from mhvp.imports.list_import_routers import router as list_imports_router
from mhvp.imports.migration_routers import router as migration_router
from mhvp.imports.reconciliation_routers import router as reconciliation_router
from mhvp.imports.routers import router as imports_router
from mhvp.imports.vollimport_routers import router as vollimport_router
from mhvp.imports.w3_routers import router as import_history_router
from mhvp.integrations.lexoffice_ext.routers import router as lexoffice_ext_router
from mhvp.integrations.routers import router as lexoffice_router
from mhvp.integrations.schadenstool.routers import router as schadenstool_router
from mhvp.integrations.schadenstool.webhook import router as schadenstool_webhook_router
from mhvp.letting.rentindex import router as rentindex_router
from mhvp.letting.rentlaw import platform_router as rentlaw_platform_router
from mhvp.letting.rentlaw import tenant_router as rentlaw_router
from mhvp.letting.routers import router as letting_router
from mhvp.metering.routers import router as metering_router
from mhvp.objektakte.ai_call_routers import router as objektakte_ai_call_router
from mhvp.objektakte.completeness_routers import router as objektakte_completeness_router
from mhvp.objektakte.dms_routers import router as objektakte_dms_router
from mhvp.objektakte.export_routers import router as objektakte_export_router
from mhvp.objektakte.lists_routers import router as objektakte_lists_router
from mhvp.objektakte.local_model_routers import router as objektakte_local_model_router
from mhvp.objektakte.previews_routers import router as objektakte_previews_router
from mhvp.objektakte.reconciliation_routers import router as objektakte_reconciliation_router
from mhvp.objektakte.review_routers import router as objektakte_review_router
from mhvp.objektakte.routers import router as objektakte_router
from mhvp.objektakte.routers import sync_router as objektakte_sync_router
from mhvp.objektakte.rules_routers import router as objektakte_rules_router
from mhvp.objektakte.webhook import router as objektakte_webhook_router
from mhvp.platform.gates import DbReleaseGateResolver
from mhvp.platform.licensing import router as licensing_router
from mhvp.platform.market_readiness import router as market_readiness_router
from mhvp.platform.overview import router as platform_overview_router
from mhvp.platform.routers import platform_router, tenant_router
from mhvp.portal.board import router as portal_board_router
from mhvp.portal.board_context import router as portal_board_context_router
from mhvp.portal.chat import admin as portal_chat_admin_router
from mhvp.portal.chat import router as portal_chat_router
from mhvp.portal.consumption_info import router as portal_consumption_info_router
from mhvp.portal.form_routers import admin as portal_form_admin_router
from mhvp.portal.form_routers import router as portal_form_router
from mhvp.portal.management import admin as portal_management_admin_router
from mhvp.portal.management import router as portal_management_router
from mhvp.portal.mandates import admin as portal_mandate_admin_router
from mhvp.portal.mandates import router as portal_mandate_router
from mhvp.portal.notice_routers import crm_router as notice_crm_router
from mhvp.portal.notice_routers import portal_router as notice_portal_router
from mhvp.portal.owner import router as portal_owner_router
from mhvp.portal.owner_extra import router as portal_owner_extra_router
from mhvp.portal.owner_meetings import router as portal_owner_meetings_router
from mhvp.portal.owner_overview import router as portal_owner_overview_router
from mhvp.portal.owner_statements import router as portal_owner_statements_router
from mhvp.portal.provider_einvoice import router as portal_provider_einvoice_router
from mhvp.portal.routers import admin as portal_admin_router
from mhvp.portal.routers import router as portal_router
from mhvp.privacy.routers import router as privacy_router
from mhvp.properties.routers import router as properties_router
from mhvp.properties.routers_catalogs import router as catalogs_router
from mhvp.properties.routers_creditors import router as properties_creditors_router
from mhvp.properties.routers_masterdata import router as properties_masterdata_router
from mhvp.properties.routers_p16 import router as properties_p16_router
from mhvp.properties.routers_patch import router as properties_patch_router
from mhvp.properties.routers_takeover import router as properties_takeover_router
from mhvp.properties.routers_termination import router as properties_termination_router
from mhvp.receipts.routers import router as receipts_router
from mhvp.sla.routers import router as sla_router
from mhvp.sla.whatsapp_webhook import router as whatsapp_webhook_router
from mhvp.tenant.routers import router as tenant_setup_router
from mhvp.tickets.board import portal_router as portal_board_submissions_router
from mhvp.tickets.routers import router as tickets_router
from mhvp.tickets.work_order_proposal_routers import router as work_order_proposal_router
from mhvp.workspace.deadline_routers import router as deadline_router
from mhvp.workspace.ops import router as ops_router
from mhvp.workspace.routers import router as workspace_router

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

API_PREFIX = "/api/v1"


@dataclass(slots=True)
class Resources:
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    redis: Redis
    s3: "S3Client | None"


ReadinessChecksFactory = Callable[[Settings, Resources], dict[str, ReadinessCheck]]


def default_readiness_checks(settings: Settings, resources: Resources) -> dict[str, ReadinessCheck]:
    checks = {
        "database": health.database_check(resources.engine),
        "database_role": health.database_role_check(resources.engine),
        "migrations": health.migrations_check(resources.engine, settings.alembic_config),
        "redis": health.redis_check(resources.redis),
        "object_storage": health.object_storage_check(settings, resources.s3),
    }
    if settings.clamav_mode != "off":
        checks["clamav"] = health.clamav_check(settings)
    return checks


def create_app(
    settings: Settings | None = None,
    *,
    readiness_checks_factory: ReadinessChecksFactory | None = None,
    release_gate_resolver: ReleaseGateResolver | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)
    checks_factory = readiness_checks_factory or default_readiness_checks

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        timeout = settings.health_check_timeout_seconds
        if settings.master_key is not None:
            crypto.set_master_key(crypto.decode_master_key(settings.master_key.get_secret_value()))
        engine = create_app_engine(settings)
        resources = Resources(
            engine=engine,
            session_factory=create_session_factory(engine),
            redis=Redis.from_url(
                settings.redis_url.get_secret_value(),
                socket_timeout=timeout,
                socket_connect_timeout=timeout,
            ),
            s3=create_s3_client(settings) if settings.s3_configured else None,
        )
        app.state.resources = resources
        app.state.readiness_checks = checks_factory(settings, resources)
        if release_gate_resolver is None:
            app.state.release_gate_resolver = DbReleaseGateResolver(resources.session_factory)
        try:
            yield
        finally:
            await resources.redis.aclose()
            await resources.engine.dispose()

    app = FastAPI(
        title="MH Verwaltungsplattform API",
        version=settings.app_version,
        description=(
            "Offene REST-API der MH Verwaltungsplattform. Fachbegriffe deutsch, Feldnamen "
            "englisch. Fehler als RFC 9457 Problem Details (application/problem+json)."
        ),
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.release_gate_resolver = release_gate_resolver or ClosedReleaseGateResolver()
    install_problem_handlers(app)
    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(auth_router, prefix=API_PREFIX)
    app.include_router(oidc.router, prefix=API_PREFIX)
    app.include_router(oidc.well_known)
    app.include_router(platform_router, prefix=API_PREFIX)
    app.include_router(tenant_router, prefix=API_PREFIX)
    app.include_router(tenant_setup_router, prefix=API_PREFIX)
    app.include_router(contacts_router, prefix=API_PREFIX)
    app.include_router(contacts_p16_router, prefix=API_PREFIX)
    app.include_router(contacts_merge_router, prefix=API_PREFIX)
    app.include_router(properties_router, prefix=API_PREFIX)
    app.include_router(catalogs_router, prefix=API_PREFIX)
    app.include_router(properties_patch_router, prefix=API_PREFIX)
    app.include_router(properties_p16_router, prefix=API_PREFIX)
    app.include_router(properties_takeover_router, prefix=API_PREFIX)
    app.include_router(properties_masterdata_router, prefix=API_PREFIX)
    app.include_router(properties_termination_router, prefix=API_PREFIX)
    app.include_router(properties_creditors_router, prefix=API_PREFIX)
    app.include_router(notice_crm_router, prefix=API_PREFIX)
    app.include_router(notice_portal_router, prefix=API_PREFIX)
    app.include_router(contracts_router, prefix=API_PREFIX)
    app.include_router(contracts_p16_router, prefix=API_PREFIX)
    app.include_router(service_contracts_router, prefix=API_PREFIX)
    app.include_router(deposit_settlements_router, prefix=API_PREFIX)
    # Static intake paths must be registered before /documents/{document_id} (A42).
    app.include_router(documents_intake_router, prefix=API_PREFIX)
    app.include_router(privacy_router, prefix=API_PREFIX)
    app.include_router(documents_router, prefix=API_PREFIX)
    app.include_router(paperless_webhook_router, prefix=API_PREFIX)
    app.include_router(handover_router, prefix=API_PREFIX)
    app.include_router(handover_imports_router, prefix=API_PREFIX)
    app.include_router(handover_portal_router, prefix=API_PREFIX)
    app.include_router(handover_staff_portal_router, prefix=API_PREFIX)
    app.include_router(imports_router, prefix=API_PREFIX)
    app.include_router(list_imports_router, prefix=API_PREFIX)
    app.include_router(reconciliation_router, prefix=API_PREFIX)
    app.include_router(vollimport_router, prefix=API_PREFIX)
    app.include_router(import_history_router, prefix=API_PREFIX)
    app.include_router(migration_router, prefix=API_PREFIX)
    app.include_router(ai_router, prefix=API_PREFIX)
    app.include_router(ai_onboarding_router, prefix=API_PREFIX)
    app.include_router(workspace_router, prefix=API_PREFIX)
    app.include_router(deadline_router, prefix=API_PREFIX)
    app.include_router(data_quality_router, prefix=API_PREFIX)
    app.include_router(ops_router, prefix=API_PREFIX)
    app.include_router(accounting_router, prefix=API_PREFIX)
    app.include_router(g1_opening_router, prefix=API_PREFIX)
    app.include_router(accounting_intake_router, prefix=API_PREFIX)
    app.include_router(accounting_xrechnung_router, prefix=API_PREFIX)
    app.include_router(accounting_admin_fee_router, prefix=API_PREFIX)
    app.include_router(accounting_audit_export_router, prefix=API_PREFIX)
    app.include_router(accounting_report_router, prefix=API_PREFIX)
    app.include_router(accounting_tax_router, prefix=API_PREFIX)
    app.include_router(rent_invoice_router, prefix=API_PREFIX)
    app.include_router(datev_mapping_router, prefix=API_PREFIX)
    app.include_router(datev_check_router, prefix=API_PREFIX)
    app.include_router(chart_release_router, prefix=API_PREFIX)
    app.include_router(banking_router, prefix=API_PREFIX)
    app.include_router(direct_debit_router, prefix=API_PREFIX)
    app.include_router(payment_run_router, prefix=API_PREFIX)
    app.include_router(finapi_router, prefix=API_PREFIX)
    app.include_router(lexoffice_router, prefix=API_PREFIX)
    app.include_router(lexoffice_ext_router, prefix=API_PREFIX)
    app.include_router(schadenstool_router, prefix=API_PREFIX)
    app.include_router(fints_router, prefix=API_PREFIX)
    app.include_router(billing_router, prefix=API_PREFIX)
    app.include_router(heating_router, prefix=API_PREFIX)
    app.include_router(consumption_info_router, prefix=API_PREFIX)
    app.include_router(statement_letters_router, prefix=API_PREFIX)
    app.include_router(owner_statement_router, prefix=API_PREFIX)
    app.include_router(statement_ai_check_router, prefix=API_PREFIX)
    app.include_router(operating_cost_type_router, prefix=API_PREFIX)
    app.include_router(allocability_router, prefix=API_PREFIX)
    app.include_router(advance_rule_router, prefix=API_PREFIX)
    app.include_router(advance_proposal_router, prefix=API_PREFIX)
    app.include_router(hoa_router, prefix=API_PREFIX)
    app.include_router(hoa_meetings_router, prefix=API_PREFIX)
    app.include_router(hoa_meeting_rules_router, prefix=API_PREFIX)
    app.include_router(hoa_levies_router, prefix=API_PREFIX)
    app.include_router(hoa_board_router, prefix=API_PREFIX)
    app.include_router(hoa_majority_router, prefix=API_PREFIX)
    app.include_router(hoa_package_router, prefix=API_PREFIX)
    app.include_router(hoa_finance_router, prefix=API_PREFIX)
    app.include_router(hoa_inspection_router, prefix=API_PREFIX)
    app.include_router(hoa_assets_router, prefix=API_PREFIX)
    app.include_router(rentindex_router, prefix=API_PREFIX)
    app.include_router(letting_router, prefix=API_PREFIX)
    app.include_router(rentlaw_router, prefix=API_PREFIX)
    app.include_router(rentlaw_platform_router, prefix=API_PREFIX)
    app.include_router(licensing_router, prefix=API_PREFIX)
    app.include_router(market_readiness_router, prefix=API_PREFIX)
    app.include_router(platform_overview_router, prefix=API_PREFIX)
    app.include_router(assignment_review_router, prefix=API_PREFIX)
    app.include_router(rule_proposal_router, prefix=API_PREFIX)
    app.include_router(tickets_router, prefix=API_PREFIX)
    app.include_router(work_order_proposal_router, prefix=API_PREFIX)
    app.include_router(sla_router, prefix=API_PREFIX)
    app.include_router(metering_router, prefix=API_PREFIX)
    app.include_router(automation_router, prefix=API_PREFIX)
    app.include_router(whatsapp_webhook_router, prefix=API_PREFIX)
    app.include_router(gmail_push_router, prefix=API_PREFIX)
    app.include_router(schadenstool_webhook_router, prefix=API_PREFIX)
    app.include_router(immoware_router, prefix=API_PREFIX)
    app.include_router(objektakte_router, prefix=API_PREFIX)
    app.include_router(objektakte_sync_router, prefix=API_PREFIX)
    app.include_router(objektakte_review_router, prefix=API_PREFIX)
    app.include_router(objektakte_completeness_router, prefix=API_PREFIX)
    app.include_router(objektakte_export_router, prefix=API_PREFIX)
    app.include_router(objektakte_rules_router, prefix=API_PREFIX)
    app.include_router(receipts_router, prefix=API_PREFIX)
    app.include_router(objektakte_ai_call_router, prefix=API_PREFIX)
    app.include_router(objektakte_lists_router, prefix=API_PREFIX)
    app.include_router(objektakte_dms_router, prefix=API_PREFIX)
    app.include_router(objektakte_previews_router, prefix=API_PREFIX)
    app.include_router(objektakte_local_model_router, prefix=API_PREFIX)
    app.include_router(objektakte_reconciliation_router, prefix=API_PREFIX)
    app.include_router(objektakte_webhook_router, prefix=API_PREFIX)
    app.include_router(mail_router, prefix=API_PREFIX)
    app.include_router(mail_signature_router, prefix=API_PREFIX)
    app.include_router(mail_draft_attachments_router, prefix=API_PREFIX)
    app.include_router(dispatch_router, prefix=API_PREFIX)
    app.include_router(calendar_feed_router, prefix=API_PREFIX)
    app.include_router(postal_router, prefix=API_PREFIX)
    app.include_router(telephony_router, prefix=API_PREFIX)
    app.include_router(portal_router, prefix=API_PREFIX)
    app.include_router(portal_admin_router, prefix=API_PREFIX)
    app.include_router(portal_board_router, prefix=API_PREFIX)
    app.include_router(portal_board_context_router, prefix=API_PREFIX)
    app.include_router(portal_board_submissions_router, prefix=API_PREFIX)
    app.include_router(portal_owner_router, prefix=API_PREFIX)
    app.include_router(portal_consumption_info_router, prefix=API_PREFIX)
    app.include_router(portal_owner_meetings_router, prefix=API_PREFIX)
    app.include_router(portal_form_router, prefix=API_PREFIX)
    app.include_router(portal_form_admin_router, prefix=API_PREFIX)
    app.include_router(portal_chat_router, prefix=API_PREFIX)
    app.include_router(portal_chat_admin_router, prefix=API_PREFIX)
    app.include_router(portal_management_router, prefix=API_PREFIX)
    app.include_router(portal_management_admin_router, prefix=API_PREFIX)
    app.include_router(portal_owner_extra_router, prefix=API_PREFIX)
    app.include_router(portal_owner_overview_router, prefix=API_PREFIX)
    app.include_router(portal_owner_statements_router, prefix=API_PREFIX)
    app.include_router(portal_provider_einvoice_router, prefix=API_PREFIX)
    app.include_router(portal_mandate_router, prefix=API_PREFIX)
    app.include_router(portal_mandate_admin_router, prefix=API_PREFIX)
    # Deprecation marks into the OpenAPI document after all routers (ADR 0009, A50).
    mark_deprecated_routes(app)
    # Order (inner to outer): idempotency, rate limit, correlation id (outermost, A48/A49).
    # API-Version and deprecation headers (ADR 0009, A50), inside the correlation id.
    app.add_middleware(ApiVersionMiddleware, version=settings.app_version)
    app.add_middleware(IdempotencyMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    return app


def __getattr__(name: str) -> FastAPI:
    if name == "app":
        return create_app()
    raise AttributeError(name)
