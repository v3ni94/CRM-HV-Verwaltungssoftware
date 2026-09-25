"""Platform administration (/api/v1/platform) and tenant administration (/api/v1/tenant)."""

import secrets
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from mhvp.core.auth import passwords, tokens
from mhvp.core.auth import service as auth_service
from mhvp.core.auth.permissions import ALL_PERMISSIONS, validate_permission
from mhvp.core.auth.principal import (
    Principal,
    TenantPrincipal,
    format_api_key,
    require_permission,
    require_platform_admin,
    resolve_host_tenant,
    sessions,
    tenant_tx,
)
from mhvp.core.config import Settings
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.core.events import AuditLog, DomainEvent, diff, emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.release_gates import GATE_LABELS, ReleaseGate
from mhvp.core.webhooks import (
    UnsafeWebhookTargetError,
    WebhookDelivery,
    WebhookSubscription,
    check_target,
    redeliver,
)
from mhvp.platform import gates
from mhvp.platform.models import (
    ApiKey,
    GateRequestStatus,
    Membership,
    MembershipRole,
    MembershipStatus,
    RefreshToken,
    ReleaseGateRequest,
    Role,
    RolePermission,
    Tenant,
    TenantSettings,
    User,
)
from mhvp.platform.schemas import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyOut,
    AuditOut,
    Branding,
    BrandingOut,
    CompanyData,
    DeliveryOut,
    EventOut,
    GateDecision,
    GateRequestCreate,
    GateRequestOut,
    GateStateOut,
    MemberCompetences,
    MemberCreate,
    MemberInvite,
    MemberMobilePhone,
    MemberOut,
    MemberRoles,
    MemberStatusIn,
    PasswordResetIn,
    RoleCreate,
    RoleOut,
    RolePermissions,
    TenantCreate,
    TenantOut,
    TenantSettingsOut,
    TenantSettingsPatch,
    UserCreate,
    UserOut,
    WebhookCreate,
    WebhookCreated,
    WebhookOut,
    WebhookPatch,
)
from mhvp.platform.services import add_member, create_user, provision_tenant, set_member_roles

platform_router = APIRouter(prefix="/platform", tags=["Plattform"])
tenant_router = APIRouter(prefix="/tenant", tags=["Mandant"])

Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=200)]


def _not_found() -> ProblemError:
    return ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)


# Platform ------------------------------------------------------------------------------


@platform_router.get("/tenants", summary="Mandanten auflisten")
async def list_tenants(
    request: Request, _: Principal = Depends(require_platform_admin)
) -> list[TenantOut]:
    async with platform_transaction(sessions(request)) as session:
        rows = (await session.scalars(select(Tenant).order_by(Tenant.name))).all()
        return [TenantOut(id=t.id, slug=t.slug, name=t.name, status=t.status.value) for t in rows]


@platform_router.post("/tenants", status_code=201, summary="Mandanten anlegen")
async def create_tenant(
    body: TenantCreate, request: Request, principal: Principal = Depends(require_platform_admin)
) -> TenantOut:
    tenant_id, created = await provision_tenant(
        sessions(request), slug=body.slug, name=body.name, actor_user_id=principal.user_id
    )
    if not created:
        raise ProblemError(ErrorCodes.CONFLICT)
    return TenantOut(id=tenant_id, slug=body.slug, name=body.name, status="active")


@platform_router.post("/users", status_code=201, summary="Benutzer anlegen")
async def create_platform_user(
    body: UserCreate, request: Request, _: Principal = Depends(require_platform_admin)
) -> UserOut:
    user_id = await create_user(
        sessions(request),
        email=body.email,
        display_name=body.display_name,
        password=body.password,
        is_platform_admin=body.is_platform_admin,
    )
    return UserOut(
        id=user_id,
        email=body.email.lower(),
        display_name=body.display_name,
        is_platform_admin=body.is_platform_admin,
        totp_enabled=False,
    )


@platform_router.post(
    "/tenants/{tenant_id}/members", status_code=201, summary="Mitglied hinzufügen"
)
async def platform_add_member(
    tenant_id: uuid.UUID,
    body: MemberCreate,
    request: Request,
    principal: Principal = Depends(require_platform_admin),
) -> dict[str, uuid.UUID]:
    membership_id = await add_member(
        sessions(request),
        tenant_id=tenant_id,
        user_id=body.user_id,
        role_codes=body.role_codes,
        actor_user_id=principal.user_id,
    )
    return {"membership_id": membership_id}


async def _decide(
    request: Request,
    principal: Principal,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    approve: bool,
    comment: str | None,
) -> GateRequestOut:
    async with tenant_transaction(sessions(request), tenant_id) as session:
        item = await session.get(ReleaseGateRequest, request_id)
        if item is None or item.tenant_id != tenant_id:
            raise _not_found()
        if item.status is not GateRequestStatus.REQUESTED:
            raise ProblemError(ErrorCodes.GATE_STATE)
        if item.requested_by == principal.user_id:
            raise ProblemError(ErrorCodes.GATE_FOUR_EYES)
        item.status = GateRequestStatus.APPROVED if approve else GateRequestStatus.REJECTED
        item.decided_by = principal.user_id
        item.decided_at = gates.now()
        item.decision_comment = comment
        await emit(
            session,
            tenant_id=tenant_id,
            type="release_gate.opened" if approve else "release_gate.rejected",
            entity_type="release_gate_request",
            entity_id=item.id,
            actor_user_id=principal.user_id,
            payload={"gate": item.gate, "scope": item.scope},
            changes={"status": {"old": "requested", "new": item.status.value}},
        )
        return _gate_out(item)


@platform_router.post(
    "/tenants/{tenant_id}/release-gates/requests/{request_id}/approve",
    summary="Freigabestufe genehmigen (zweite Person)",
)
async def approve_gate(
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    body: GateDecision,
    request: Request,
    principal: Principal = Depends(require_platform_admin),
) -> GateRequestOut:
    return await _decide(request, principal, tenant_id, request_id, True, body.comment)


@platform_router.post(
    "/tenants/{tenant_id}/release-gates/requests/{request_id}/reject",
    summary="Freigabeantrag ablehnen",
)
async def reject_gate(
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    body: GateDecision,
    request: Request,
    principal: Principal = Depends(require_platform_admin),
) -> GateRequestOut:
    return await _decide(request, principal, tenant_id, request_id, False, body.comment)


# Tenant settings and branding ----------------------------------------------------------


def _settings_out(row: TenantSettings) -> TenantSettingsOut:
    return TenantSettingsOut(
        tenant_id=row.tenant_id,
        company=CompanyData.model_validate(row.company),
        branding=Branding.model_validate(row.branding),
        sources=row.sources,
        auto_posting_enabled=row.auto_posting_enabled,
        version=row.version,
    )


@tenant_router.get("/settings", summary="Mandanteneinstellungen")
async def get_settings(
    request: Request,
    response: Response,
    principal: TenantPrincipal = Depends(require_permission("tenant_settings:read")),
) -> TenantSettingsOut:
    async with tenant_tx(request, principal) as session:
        row = await session.scalar(select(TenantSettings))
        if row is None:
            raise _not_found()
        response.headers["ETag"] = f'"{row.version}"'
        return _settings_out(row)


@tenant_router.patch("/settings", summary="Mandanteneinstellungen ändern")
async def patch_settings(
    body: TenantSettingsPatch,
    request: Request,
    response: Response,
    if_match: Annotated[str | None, Header()] = None,
    principal: TenantPrincipal = Depends(require_permission("tenant_settings:update")),
) -> TenantSettingsOut:
    async with tenant_tx(request, principal) as session:
        row = await session.scalar(select(TenantSettings).with_for_update())
        if row is None:
            raise _not_found()
        if if_match is not None and if_match.strip('"') != str(row.version):
            raise ProblemError(ErrorCodes.VERSION_CONFLICT)
        before = {"company": row.company, "branding": row.branding}
        if body.company is not None:
            row.company = body.company.model_dump(mode="json")
        if body.branding is not None:
            row.branding = body.branding.model_dump(mode="json", by_alias=True)
        after = {"company": row.company, "branding": row.branding}
        changes = diff(before, after)
        if changes:
            row.version += 1
            row.updated_by = principal.user_id
            await emit(
                session,
                tenant_id=row.tenant_id,
                type="tenant_settings.updated",
                entity_type="tenant_settings",
                entity_id=row.id,
                actor_user_id=principal.user_id,
                payload={"fields": sorted(changes)},
                changes=changes,
            )
        response.headers["ETag"] = f'"{row.version}"'
        return _settings_out(row)


@tenant_router.get("/branding", summary="Branding des Mandanten (White-Label)")
async def branding(request: Request) -> BrandingOut:
    """Public for portals: resolved from the Host header (3.3); with a token from its tenant."""
    tenant_id = await resolve_host_tenant(request)
    if tenant_id is None and request.headers.get("authorization"):
        from mhvp.core.auth.principal import get_principal

        tenant_id = (await get_principal(request)).tenant_id
    if tenant_id is None:
        raise _not_found()
    async with platform_transaction(sessions(request)) as session:
        tenant = await session.get(Tenant, tenant_id)
    async with tenant_transaction(sessions(request), tenant_id) as session:
        row = await session.scalar(select(TenantSettings))
    if tenant is None or row is None:
        raise _not_found()
    return BrandingOut(
        tenant_id=tenant_id, name=tenant.name, branding=Branding.model_validate(row.branding)
    )


# Roles and members ---------------------------------------------------------------------


async def _role_out(session, role: Role) -> RoleOut:  # type: ignore[no-untyped-def]
    perms = await session.execute(
        select(RolePermission.resource, RolePermission.action).where(
            RolePermission.role_id == role.id
        )
    )
    return RoleOut(
        id=role.id,
        code=role.code,
        name=role.name,
        is_system=role.is_system,
        parent_role_id=role.parent_role_id,
        permissions=sorted(f"{p.resource}:{p.action}" for p in perms),
    )


def _check_permissions(values: list[str]) -> None:
    try:
        for value in values:
            validate_permission(value)
    except ValueError as exc:
        raise ProblemError(ErrorCodes.VALIDATION, detail=str(exc)) from None


@tenant_router.get("/roles", summary="Rollen")
async def list_roles(
    request: Request, principal: TenantPrincipal = Depends(require_permission("roles:read"))
) -> list[RoleOut]:
    async with tenant_tx(request, principal) as session:
        roles = (await session.scalars(select(Role).order_by(Role.code))).all()
        return [await _role_out(session, role) for role in roles]


@tenant_router.post("/roles", status_code=201, summary="Rolle anlegen")
async def create_role(
    body: RoleCreate,
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("roles:create")),
) -> RoleOut:
    _check_permissions(body.permissions)
    async with tenant_tx(request, principal) as session:
        if await session.scalar(select(Role.id).where(Role.code == body.code)) is not None:
            raise ProblemError(ErrorCodes.CONFLICT)
        if body.parent_role_id and await session.get(Role, body.parent_role_id) is None:
            raise _not_found()
        role = Role(
            tenant_id=principal.tenant_id,
            code=body.code,
            name=body.name,
            parent_role_id=body.parent_role_id,
            created_by=principal.user_id,
        )
        session.add(role)
        await session.flush()
        for permission in sorted(set(body.permissions)):
            resource, action = permission.split(":")
            session.add(
                RolePermission(
                    tenant_id=principal.tenant_id, role_id=role.id, resource=resource, action=action
                )
            )
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="role.created",
            entity_type="role",
            entity_id=role.id,
            actor_user_id=principal.user_id,
            payload={"code": role.code, "permissions": sorted(set(body.permissions))},
        )
        return await _role_out(session, role)


@tenant_router.put("/roles/{role_id}/permissions", summary="Rechte einer Rolle setzen")
async def set_role_permissions(
    role_id: uuid.UUID,
    body: RolePermissions,
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("roles:update")),
) -> RoleOut:
    _check_permissions(body.permissions)
    async with tenant_tx(request, principal) as session:
        role = await session.get(Role, role_id)
        if role is None:
            raise _not_found()
        if role.is_system:
            raise ProblemError(
                ErrorCodes.FORBIDDEN, developer_message="System roles are managed by the platform."
            )
        before = (await _role_out(session, role)).permissions
        for existing in (
            await session.scalars(select(RolePermission).where(RolePermission.role_id == role.id))
        ).all():
            await session.delete(existing)
        await session.flush()
        for permission in sorted(set(body.permissions)):
            resource, action = permission.split(":")
            session.add(
                RolePermission(
                    tenant_id=principal.tenant_id, role_id=role.id, resource=resource, action=action
                )
            )
        await session.flush()
        out = await _role_out(session, role)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="role.updated",
            entity_type="role",
            entity_id=role.id,
            actor_user_id=principal.user_id,
            changes={"permissions": {"old": before, "new": out.permissions}},
        )
        return out


@tenant_router.get("/members", summary="Mitglieder des Mandanten")
async def list_members(
    request: Request, principal: TenantPrincipal = Depends(require_permission("members:read"))
) -> list[MemberOut]:
    async with platform_transaction(sessions(request)) as session:
        rows = (
            await session.execute(
                select(
                    Membership.id,
                    Membership.user_id,
                    Membership.status,
                    Membership.contact_id,
                    Membership.competences,
                    Membership.mobile_phone,
                    User.email,
                    User.display_name,
                    User.last_login_at,
                )
                .join(User, User.id == Membership.user_id)
                .where(Membership.tenant_id == principal.tenant_id)
                .order_by(User.display_name)
            )
        ).all()
    async with tenant_tx(request, principal) as session:
        role_rows = (
            await session.execute(
                select(MembershipRole.membership_id, Role.code).join(
                    Role, Role.id == MembershipRole.role_id
                )
            )
        ).all()
    roles: dict[uuid.UUID, list[str]] = {}
    for row in role_rows:
        roles.setdefault(row.membership_id, []).append(row.code)
    return [
        MemberOut(
            membership_id=r.id,
            user_id=r.user_id,
            email=r.email,
            display_name=r.display_name,
            status=r.status.value,
            roles=sorted(roles.get(r.id, [])),
            competences=list(r.competences or []),
            contact_id=r.contact_id,
            last_login_at=r.last_login_at,
            mobile_phone=r.mobile_phone,
        )
        for r in rows
    ]


@tenant_router.post("/members", status_code=201, summary="Benutzer hinzufügen")
async def invite_member(
    body: MemberInvite,
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("members:create")),
) -> MemberOut:
    """Creates the account when the e-mail is new (start password required), otherwise adds
    the existing account to the tenant. Every user is also kept as a contact of the tenant."""
    from mhvp.contacts.models import Contact, ContactEmail, ContactKind

    email = body.email.strip().lower()
    async with platform_transaction(sessions(request)) as session:
        user_id = await session.scalar(select(User.id).where(User.email == email))
    if user_id is None:
        if not body.password:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Für ein neues Konto ist ein Startpasswort nötig."
            )
        user_id = await create_user(
            sessions(request), email=email, display_name=body.display_name, password=body.password
        )
    membership_id = await add_member(
        sessions(request),
        tenant_id=principal.tenant_id,
        user_id=user_id,
        role_codes=body.role_codes,
        actor_user_id=principal.user_id,
    )
    async with platform_transaction(sessions(request)) as session:
        membership = await session.get(Membership, membership_id)
        assert membership is not None  # noqa: S101 - just created
        contact_id = membership.contact_id
    if contact_id is None:
        first, _, last = body.display_name.strip().rpartition(" ")
        async with tenant_tx(request, principal) as session:
            contact = Contact(
                tenant_id=principal.tenant_id,
                created_by=principal.user_id,
                kind=ContactKind.PERSON,
                first_name=first or None,
                last_name=last or body.display_name.strip(),
                display_name=body.display_name.strip(),
                search_text=f"{body.display_name} {email}".lower(),
            )
            session.add(contact)
            await session.flush()
            session.add(
                ContactEmail(
                    tenant_id=principal.tenant_id,
                    contact_id=contact.id,
                    label="work",
                    email=email,
                    is_primary=True,
                )
            )
            contact_id = contact.id
        async with platform_transaction(sessions(request)) as session:
            membership = await session.get(Membership, membership_id)
            assert membership is not None  # noqa: S101
            membership.contact_id = contact_id
    members = await list_members(request, principal)
    return next(m for m in members if m.membership_id == membership_id)


async def _tenant_membership(
    request: Request, principal: TenantPrincipal, membership_id: uuid.UUID
) -> Membership:
    async with platform_transaction(sessions(request)) as session:
        membership = await session.get(Membership, membership_id)
        if membership is None or membership.tenant_id != principal.tenant_id:
            raise _not_found()
        return membership


@tenant_router.patch("/members/{membership_id}", summary="Mitglied aktivieren oder sperren")
async def patch_member_status(
    membership_id: uuid.UUID,
    body: MemberStatusIn,
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("members:update")),
) -> MemberOut:
    """Members are never deleted (audit trail); a disabled membership cannot log in to this
    tenant and its sessions are revoked. Nobody disables their own membership."""
    membership = await _tenant_membership(request, principal, membership_id)
    if membership.user_id == principal.user_id and body.status == "disabled":
        raise ProblemError(ErrorCodes.VALIDATION, detail="Eigene Mitgliedschaft nicht sperrbar.")
    async with platform_transaction(sessions(request)) as session:
        row = await session.get(Membership, membership_id)
        assert row is not None  # noqa: S101
        before = row.status.value
        row.status = MembershipStatus(body.status)
        if body.status == "disabled":
            await session.execute(
                update(RefreshToken)
                .where(
                    RefreshToken.user_id == row.user_id,
                    RefreshToken.tenant_id == principal.tenant_id,
                    RefreshToken.revoked_at.is_(None),
                )
                .values(revoked_at=datetime.now(UTC))
            )
    async with tenant_tx(request, principal) as session:
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="membership.status_changed",
            entity_type="membership",
            entity_id=membership_id,
            actor_user_id=principal.user_id,
            payload={"before": before, "after": body.status},
        )
    members = await list_members(request, principal)
    return next(m for m in members if m.membership_id == membership_id)


@tenant_router.post(
    "/members/{membership_id}/reset-password", status_code=204, summary="Passwort zurücksetzen"
)
async def reset_member_password(
    membership_id: uuid.UUID,
    body: PasswordResetIn,
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("members:update")),
) -> Response:
    """Sets a new start password, clears the lockout and ends all sessions of the user. The
    administrator hands the password over personally; the user changes it under Meine Daten."""
    membership = await _tenant_membership(request, principal, membership_id)
    violation = passwords.policy_violation(body.password)
    if violation:
        raise ProblemError(ErrorCodes.PASSWORD_POLICY, detail=violation)
    async with platform_transaction(sessions(request)) as session:
        user = await session.get(User, membership.user_id)
        assert user is not None  # noqa: S101
        user.password_hash = passwords.hash_password(body.password)
        user.failed_logins = 0
        user.locked_until = None
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
    # A password reset by an admin revokes every trusted device of that user too (operator
    # 25.09.2026, ADR 0006 addendum): the device would otherwise still skip TOTP.
    await auth_service.revoke_all_trusted_devices(sessions(request), membership.user_id)
    async with tenant_tx(request, principal) as session:
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="membership.password_reset",
            entity_type="membership",
            entity_id=membership_id,
            actor_user_id=principal.user_id,
            payload={},
        )
    return Response(status_code=204)


@tenant_router.put(
    "/members/{membership_id}/roles", status_code=204, summary="Rollen eines Mitglieds setzen"
)
async def put_member_roles(
    membership_id: uuid.UUID,
    body: MemberRoles,
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("members:update")),
) -> Response:
    async with platform_transaction(sessions(request)) as session:
        membership = await session.get(Membership, membership_id)
        if membership is None or membership.tenant_id != principal.tenant_id:
            raise _not_found()
    await set_member_roles(
        sessions(request),
        tenant_id=principal.tenant_id,
        membership_id=membership_id,
        role_codes=body.role_codes,
        actor_user_id=principal.user_id,
    )
    return Response(status_code=204)


@tenant_router.get("/competence-catalogue", summary="Kompetenzkatalog (Basis und Mandant)")
async def get_competence_catalogue(
    request: Request, principal: TenantPrincipal = Depends(require_permission("members:read"))
) -> list[dict[str, str]]:
    from mhvp.platform.models import TenantSettings
    from mhvp.tickets.competences import full_catalogue

    async with tenant_tx(request, principal) as session:
        extra = await session.scalar(
            select(TenantSettings.competence_catalogue_extra).where(
                TenantSettings.tenant_id == principal.tenant_id
            )
        )
    return [{"code": c["code"], "label": c["label"]} for c in full_catalogue(list(extra or []))]


@tenant_router.put(
    "/members/{membership_id}/competences",
    status_code=204,
    summary="Kompetenzen eines Mitglieds setzen",
)
async def put_member_competences(
    membership_id: uuid.UUID,
    body: MemberCompetences,
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("members:update")),
) -> Response:
    from mhvp.platform.models import TenantSettings
    from mhvp.tickets.competences import is_known_code

    async with tenant_tx(request, principal) as session:
        extra = await session.scalar(
            select(TenantSettings.competence_catalogue_extra).where(
                TenantSettings.tenant_id == principal.tenant_id
            )
        )
    unknown = [c for c in body.competence_codes if not is_known_code(c, list(extra or []))]
    if unknown:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail=f"Unbekannte Kompetenzen: {', '.join(unknown)}."
        )
    async with platform_transaction(sessions(request)) as session:
        membership = await session.get(Membership, membership_id)
        if membership is None or membership.tenant_id != principal.tenant_id:
            raise _not_found()
        before = sorted(membership.competences)
        membership.competences = sorted(dict.fromkeys(body.competence_codes))
        membership.updated_by = principal.user_id
    async with tenant_tx(request, principal) as session:
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="membership.competences_changed",
            entity_type="membership",
            entity_id=membership_id,
            actor_user_id=principal.user_id,
            changes={"competences": {"old": before, "new": sorted(membership.competences)}},
        )
    return Response(status_code=204)


@tenant_router.put(
    "/members/{membership_id}/mobile-phone",
    status_code=204,
    summary="Mobilnummer eines Mitglieds setzen (SMS-Eskalation, M35)",
)
async def put_member_mobile_phone(
    membership_id: uuid.UUID,
    body: MemberMobilePhone,
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("members:update")),
) -> Response:
    async with platform_transaction(sessions(request)) as session:
        membership = await session.get(Membership, membership_id)
        if membership is None or membership.tenant_id != principal.tenant_id:
            raise _not_found()
        changed = membership.mobile_phone != body.mobile_phone
        membership.mobile_phone = body.mobile_phone
        membership.updated_by = principal.user_id
    if changed:
        async with tenant_tx(request, principal) as session:
            # Die Nummer selbst wird nicht ins Ereignisprotokoll geschrieben (Datensparsamkeit).
            await emit(
                session,
                tenant_id=principal.tenant_id,
                type="membership.mobile_phone_changed",
                entity_type="membership",
                entity_id=membership_id,
                actor_user_id=principal.user_id,
                changes={"mobile_phone": {"set": body.mobile_phone is not None}},
            )
    return Response(status_code=204)


# API keys ------------------------------------------------------------------------------


def _key_out(key: ApiKey) -> ApiKeyOut:
    return ApiKeyOut(
        id=key.id,
        name=key.name,
        prefix=key.prefix,
        scopes=key.scopes,
        expires_at=key.expires_at,
        last_used_at=key.last_used_at,
        revoked_at=key.revoked_at,
    )


@tenant_router.get("/api-keys", summary="API-Schlüssel")
async def list_api_keys(
    request: Request, principal: TenantPrincipal = Depends(require_permission("api_keys:read"))
) -> list[ApiKeyOut]:
    async with tenant_tx(request, principal) as session:
        return [
            _key_out(k)
            for k in (await session.scalars(select(ApiKey).order_by(ApiKey.created_at))).all()
        ]


@tenant_router.post("/api-keys", status_code=201, summary="API-Schlüssel erzeugen")
async def create_api_key(
    body: ApiKeyCreate,
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("api_keys:create")),
) -> ApiKeyCreated:
    _check_permissions(body.scopes)
    if not set(body.scopes) <= principal.permissions:
        raise ProblemError(
            ErrorCodes.FORBIDDEN, developer_message="Scopes exceed your own permissions."
        )
    prefix, secret = secrets.token_hex(6), tokens.new_opaque_secret()
    async with tenant_tx(request, principal) as session:
        key = ApiKey(
            tenant_id=principal.tenant_id,
            name=body.name,
            prefix=prefix,
            secret_hash=tokens.sha256_hex(secret),
            scopes=sorted(set(body.scopes)),
            expires_at=body.expires_at,
            created_by=principal.user_id,
        )
        session.add(key)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="api_key.created",
            entity_type="api_key",
            entity_id=key.id,
            actor_user_id=principal.user_id,
            payload={"name": key.name, "scopes": key.scopes},
        )
        return ApiKeyCreated(
            **_key_out(key).model_dump(), key=format_api_key(principal.tenant_id, prefix, secret)
        )


@tenant_router.delete("/api-keys/{key_id}", status_code=204, summary="API-Schlüssel widerrufen")
async def revoke_api_key(
    key_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("api_keys:delete")),
) -> Response:
    async with tenant_tx(request, principal) as session:
        key = await session.get(ApiKey, key_id)
        if key is None or key.revoked_at is not None:
            raise _not_found()
        key.revoked_at = gates.now()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="api_key.revoked",
            entity_type="api_key",
            entity_id=key.id,
            actor_user_id=principal.user_id,
        )
    return Response(status_code=204)


# Webhooks ------------------------------------------------------------------------------


def _hook_out(hook: WebhookSubscription) -> WebhookOut:
    return WebhookOut(
        id=hook.id,
        url=hook.url,
        event_types=hook.event_types,
        active=hook.active,
        description=hook.description,
    )


def _check_url(request: Request, url: str) -> None:
    settings: Settings = request.app.state.settings
    try:
        check_target(url, allow_private=settings.webhook_allow_private_targets)
    except UnsafeWebhookTargetError as exc:
        raise ProblemError(ErrorCodes.WEBHOOK_TARGET, detail=str(exc)) from None


@tenant_router.get("/webhooks", summary="Webhook-Abonnements")
async def list_webhooks(
    request: Request, principal: TenantPrincipal = Depends(require_permission("webhooks:read"))
) -> list[WebhookOut]:
    async with tenant_tx(request, principal) as session:
        return [
            _hook_out(h)
            for h in (
                await session.scalars(
                    select(WebhookSubscription).order_by(WebhookSubscription.created_at)
                )
            ).all()
        ]


@tenant_router.post("/webhooks", status_code=201, summary="Webhook abonnieren")
async def create_webhook(
    body: WebhookCreate,
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("webhooks:create")),
) -> WebhookCreated:
    _check_url(request, body.url)
    secret = tokens.new_opaque_secret()
    async with tenant_tx(request, principal) as session:
        hook = WebhookSubscription(
            tenant_id=principal.tenant_id,
            url=body.url,
            event_types=sorted(set(body.event_types)),
            secret=secret,
            description=body.description,
            created_by=principal.user_id,
        )
        session.add(hook)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="webhook_subscription.created",
            entity_type="webhook_subscription",
            entity_id=hook.id,
            actor_user_id=principal.user_id,
            payload={"url": hook.url, "event_types": hook.event_types},
        )
        return WebhookCreated(**_hook_out(hook).model_dump(), secret=secret)


@tenant_router.patch("/webhooks/{hook_id}", summary="Webhook ändern")
async def patch_webhook(
    hook_id: uuid.UUID,
    body: WebhookPatch,
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("webhooks:update")),
) -> WebhookOut:
    async with tenant_tx(request, principal) as session:
        hook = await session.get(WebhookSubscription, hook_id)
        if hook is None:
            raise _not_found()
        before = {"active": hook.active, "event_types": hook.event_types}
        if body.active is not None:
            hook.active = body.active
        if body.event_types is not None:
            hook.event_types = sorted(set(body.event_types))
        changes = diff(before, {"active": hook.active, "event_types": hook.event_types})
        if changes:
            await emit(
                session,
                tenant_id=principal.tenant_id,
                type="webhook_subscription.updated",
                entity_type="webhook_subscription",
                entity_id=hook.id,
                actor_user_id=principal.user_id,
                changes=changes,
            )
        return _hook_out(hook)


@tenant_router.get("/webhooks/{hook_id}/deliveries", summary="Zustellprotokoll")
async def list_deliveries(
    hook_id: uuid.UUID,
    request: Request,
    page: Page = 1,
    page_size: PageSize = 50,
    principal: TenantPrincipal = Depends(require_permission("webhooks:read")),
) -> list[DeliveryOut]:
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.scalars(
                select(WebhookDelivery)
                .where(WebhookDelivery.subscription_id == hook_id)
                .order_by(WebhookDelivery.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return [
            DeliveryOut(
                id=d.id,
                event_id=d.event_id,
                status=d.status.value,
                attempts=d.attempts,
                next_attempt_at=d.next_attempt_at,
                last_status_code=d.last_status_code,
                last_error=d.last_error,
                delivered_at=d.delivered_at,
            )
            for d in rows
        ]


@tenant_router.post(
    "/webhook-deliveries/{delivery_id}/redeliver", status_code=202, summary="Erneut zustellen"
)
async def redeliver_endpoint(
    delivery_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("webhooks:update")),
) -> Response:
    async with tenant_tx(request, principal) as session:
        delivery = await session.get(WebhookDelivery, delivery_id)
        if delivery is None:
            raise _not_found()
        redeliver(delivery)
    return Response(status_code=202)


# Events and audit ----------------------------------------------------------------------


@tenant_router.get("/events", summary="Domänenereignisse")
async def list_events(
    request: Request,
    page: Page = 1,
    page_size: PageSize = 50,
    type: str | None = None,
    principal: TenantPrincipal = Depends(require_permission("audit:read")),
) -> list[EventOut]:
    async with tenant_tx(request, principal) as session:
        query = select(DomainEvent).order_by(DomainEvent.occurred_at.desc(), DomainEvent.id.desc())
        if type:
            query = query.where(DomainEvent.type == type)
        rows = (await session.scalars(query.offset((page - 1) * page_size).limit(page_size))).all()
        return [
            EventOut(
                id=e.id,
                type=e.type,
                entity_type=e.entity_type,
                entity_id=e.entity_id,
                payload=e.payload,
                actor_user_id=e.actor_user_id,
                occurred_at=e.occurred_at,
                correlation_id=e.correlation_id,
            )
            for e in rows
        ]


@tenant_router.get("/audit-log", summary="Änderungsprotokoll")
async def list_audit(
    request: Request,
    page: Page = 1,
    page_size: PageSize = 50,
    entity_id: uuid.UUID | None = None,
    principal: TenantPrincipal = Depends(require_permission("audit:read")),
) -> list[AuditOut]:
    async with tenant_tx(request, principal) as session:
        query = select(AuditLog).order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
        if entity_id:
            query = query.where(AuditLog.entity_id == entity_id)
        rows = (await session.scalars(query.offset((page - 1) * page_size).limit(page_size))).all()
        return [
            AuditOut(
                id=a.id,
                event_id=a.event_id,
                entity_type=a.entity_type,
                entity_id=a.entity_id,
                changes=a.changes,
                actor_user_id=a.actor_user_id,
                occurred_at=a.occurred_at,
            )
            for a in rows
        ]


# Release gates -------------------------------------------------------------------------


def _gate_out(item: ReleaseGateRequest) -> GateRequestOut:
    return GateRequestOut(
        id=item.id,
        gate=item.gate,
        scope=item.scope,
        evidence=item.evidence,
        status=item.status.value,
        requested_by=item.requested_by,
        decided_by=item.decided_by,
        decided_at=item.decided_at,
        decision_comment=item.decision_comment,
    )


@tenant_router.get("/release-gates", summary="Stand der Freigabestufen G1 bis G5")
async def gate_state(
    request: Request, principal: TenantPrincipal = Depends(require_permission("release_gates:read"))
) -> list[GateStateOut]:
    async with tenant_tx(request, principal) as session:
        result = []
        for gate in ReleaseGate:
            scopes = await gates.approved_scopes(session, principal.tenant_id, gate)
            result.append(
                GateStateOut(
                    gate=gate.value, label=GATE_LABELS[gate], open=bool(scopes), scopes=scopes
                )
            )
        return result


@tenant_router.get("/release-gates/requests", summary="Freigabeanträge")
async def list_gate_requests(
    request: Request, principal: TenantPrincipal = Depends(require_permission("release_gates:read"))
) -> list[GateRequestOut]:
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.scalars(
                select(ReleaseGateRequest).order_by(ReleaseGateRequest.created_at.desc())
            )
        ).all()
        return [_gate_out(r) for r in rows]


@tenant_router.post(
    "/release-gates/requests", status_code=201, summary="Freigabe einer Stufe beantragen"
)
async def request_gate(
    body: GateRequestCreate,
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("release_gates:create")),
) -> GateRequestOut:
    if principal.user_id is None:
        raise ProblemError(
            ErrorCodes.FORBIDDEN, developer_message="Gate requests need a person, not an API key."
        )
    async with tenant_tx(request, principal) as session:
        item = ReleaseGateRequest(
            tenant_id=principal.tenant_id,
            gate=body.gate,
            scope=body.scope,
            evidence=body.evidence,
            requested_by=principal.user_id,
            created_by=principal.user_id,
        )
        session.add(item)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="release_gate.requested",
            entity_type="release_gate_request",
            entity_id=item.id,
            actor_user_id=principal.user_id,
            payload={"gate": item.gate, "scope": item.scope},
        )
        return _gate_out(item)


@tenant_router.post("/release-gates/requests/{request_id}/revoke", summary="Freigabe widerrufen")
async def revoke_gate(
    request_id: uuid.UUID,
    body: GateDecision,
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("release_gates:update")),
) -> GateRequestOut:
    async with tenant_tx(request, principal) as session:
        item = await session.get(ReleaseGateRequest, request_id)
        if item is None:
            raise _not_found()
        if item.status not in (GateRequestStatus.APPROVED, GateRequestStatus.REQUESTED):
            raise ProblemError(ErrorCodes.GATE_STATE)
        old = item.status.value
        item.status = GateRequestStatus.REVOKED
        item.decided_by = principal.user_id
        item.decided_at = gates.now()
        item.decision_comment = body.comment
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="release_gate.revoked",
            entity_type="release_gate_request",
            entity_id=item.id,
            actor_user_id=principal.user_id,
            payload={"gate": item.gate},
            changes={"status": {"old": old, "new": "revoked"}},
        )
        return _gate_out(item)


__all__ = ["ALL_PERMISSIONS", "IntegrityError", "platform_router", "tenant_router"]
