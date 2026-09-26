"""Process local cache of effective roles and permissions per (tenant_id, user_id).

Performance review 26.09.2026, open item 2: resolving the tenant context cost eight statements
per request, five of them for roles, role inheritance and permissions. This cache keeps the
result of :func:`mhvp.core.auth.permissions.effective_permissions` for a short time so that a
request only verifies the user (active), the membership (active, scope) and the host tenant.

Security behaviour (documented in ``core/README.md``, addendum to ADR 0002):

* Only roles and permissions are cached. Locks are never cached: ``User.active`` and
  ``Membership.status`` are read on every request, so disabling a user or a membership takes
  effect immediately. Portal grants (``mhvp.portal.access``) never pass through this cache.
* A role change through ``set_member_roles`` (PUT /tenant/members/{id}/roles, membership
  creation, re-sync) and a change of a role's permissions invalidate the tenant. Without an
  explicit invalidation (for example a change written by another process) a role withdrawal
  takes effect after at most :data:`MAX_TTL_SECONDS`.
* The cache is per process. In a multi process deployment the invalidation reaches only the
  process that handled the change; the other processes fall back to the TTL.
* An entry is bound to the membership id: a membership replaced by a new one (new id) never
  reuses the old entry.
"""

import os
import time
import uuid
from dataclasses import dataclass

MAX_TTL_SECONDS = 30.0
_ENV_TTL = "MHVP_PERMISSION_CACHE_TTL_SECONDS"
MAX_ENTRIES = 10_000


@dataclass(frozen=True)
class CachedPermissions:
    membership_id: uuid.UUID
    permissions: frozenset[str]
    roles: tuple[str, ...]
    expires_at: float


def _ttl_from_env() -> float:
    raw = os.environ.get(_ENV_TTL)
    if raw is None:
        return MAX_TTL_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return MAX_TTL_SECONDS
    return max(0.0, min(value, MAX_TTL_SECONDS))


class PermissionCache:
    """TTL cache keyed by ``(tenant_id, user_id)``; ``ttl_seconds`` 0 disables it."""

    def __init__(self, ttl_seconds: float = MAX_TTL_SECONDS) -> None:
        self._entries: dict[tuple[uuid.UUID, uuid.UUID], CachedPermissions] = {}
        self.ttl_seconds = min(max(ttl_seconds, 0.0), MAX_TTL_SECONDS)

    def get(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID, membership_id: uuid.UUID
    ) -> CachedPermissions | None:
        entry = self._entries.get((tenant_id, user_id))
        if entry is None:
            return None
        if entry.expires_at <= time.monotonic() or entry.membership_id != membership_id:
            self._entries.pop((tenant_id, user_id), None)
            return None
        return entry

    def put(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        membership_id: uuid.UUID,
        permissions: frozenset[str],
        roles: tuple[str, ...],
    ) -> None:
        if self.ttl_seconds <= 0:
            return
        if len(self._entries) >= MAX_ENTRIES:
            self._evict_expired()
            if len(self._entries) >= MAX_ENTRIES:
                self._entries.clear()
        self._entries[(tenant_id, user_id)] = CachedPermissions(
            membership_id=membership_id,
            permissions=permissions,
            roles=roles,
            expires_at=time.monotonic() + self.ttl_seconds,
        )

    def invalidate(self, tenant_id: uuid.UUID, user_id: uuid.UUID | None = None) -> int:
        """Drops the entries of one user or, without ``user_id``, of the whole tenant."""
        if user_id is not None:
            return 1 if self._entries.pop((tenant_id, user_id), None) is not None else 0
        keys = [key for key in self._entries if key[0] == tenant_id]
        for key in keys:
            del self._entries[key]
        return len(keys)

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)

    def _evict_expired(self) -> None:
        now = time.monotonic()
        for key in [k for k, v in self._entries.items() if v.expires_at <= now]:
            del self._entries[key]


# Process wide instance used by ``mhvp.core.auth.principal``.
permission_cache = PermissionCache(_ttl_from_env())


def invalidate_permissions(tenant_id: uuid.UUID, user_id: uuid.UUID | None = None) -> int:
    """Invalidation hook for role and permission changes (platform services and routers)."""
    return permission_cache.invalidate(tenant_id, user_id)
