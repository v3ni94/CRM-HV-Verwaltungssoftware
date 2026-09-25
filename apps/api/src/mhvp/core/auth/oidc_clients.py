"""``python -m mhvp.core.auth.oidc_clients``: register relying parties of the OIDC provider.

Relying parties (for example oauth2-proxy in front of the status page) are registered by the
operator, never through the API. The client secret is printed exactly once and stored as a
SHA-256 hash (``OidcClient.client_secret_hash``). Public clients (``--public``) get no secret
and rely on PKCE alone.

    python -m mhvp.core.auth.oidc_clients create --client-id status --name "Statusseite" \\
        --redirect-uri https://status.example.org/oauth2/callback
    python -m mhvp.core.auth.oidc_clients list
    python -m mhvp.core.auth.oidc_clients rotate-secret --client-id status
    python -m mhvp.core.auth.oidc_clients deactivate --client-id status
"""

import argparse
import asyncio
import re
import sys
from collections.abc import Sequence
from typing import TextIO
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.auth import tokens
from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.db.tenancy import platform_transaction
from mhvp.core.logging import configure_logging
from mhvp.platform.models import OidcClient

CLIENT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{1,99}$")
LOCAL_HOSTS = ("localhost", "127.0.0.1", "[::1]")


class OidcClientError(Exception):
    """Operator facing error; the message is printed and the command exits with 1."""


def validate_client_id(client_id: str) -> str:
    if not CLIENT_ID_PATTERN.match(client_id):
        raise OidcClientError(
            "client id must be 2 to 100 characters of lower case letters, digits, '.', '_' or '-'"
        )
    return client_id


def validate_redirect_uri(uri: str) -> str:
    """Absolute https URI without fragment; plain http only for local development hosts."""
    parts = urlsplit(uri)
    if parts.fragment or not parts.netloc:
        raise OidcClientError(f"redirect uri must be absolute and without fragment: {uri}")
    if parts.scheme == "https":
        return uri
    if parts.scheme == "http" and parts.hostname in LOCAL_HOSTS:
        return uri
    raise OidcClientError(f"redirect uri must use https (http only for localhost): {uri}")


async def _get(session: AsyncSession, client_id: str) -> OidcClient | None:
    client: OidcClient | None = await session.scalar(
        select(OidcClient).where(OidcClient.client_id == client_id)
    )
    return client


async def create_client(
    session: AsyncSession,
    *,
    client_id: str,
    name: str,
    redirect_uris: Sequence[str],
    public: bool = False,
) -> str | None:
    """Insert a client and return its plain secret (``None`` for public clients)."""
    validate_client_id(client_id)
    uris = [validate_redirect_uri(uri) for uri in redirect_uris]
    if not uris:
        raise OidcClientError("at least one redirect uri is required")
    if not name.strip():
        raise OidcClientError("name must not be empty")
    if await _get(session, client_id) is not None:
        raise OidcClientError(f"client '{client_id}' already exists")
    secret = None if public else tokens.new_opaque_secret()
    session.add(
        OidcClient(
            client_id=client_id,
            name=name.strip(),
            redirect_uris=list(dict.fromkeys(uris)),
            client_secret_hash=None if secret is None else tokens.sha256_hex(secret),
            active=True,
        )
    )
    return secret


async def list_clients(session: AsyncSession) -> list[OidcClient]:
    return list(await session.scalars(select(OidcClient).order_by(OidcClient.client_id)))


async def rotate_secret(session: AsyncSession, client_id: str) -> str:
    """Replace the secret of a confidential client; the old secret stops working at once."""
    client = await _get(session, client_id)
    if client is None:
        raise OidcClientError(f"client '{client_id}' not found")
    if client.client_secret_hash is None:
        raise OidcClientError(f"client '{client_id}' is public and has no secret")
    secret = tokens.new_opaque_secret()
    client.client_secret_hash = tokens.sha256_hex(secret)
    return secret


async def set_active(session: AsyncSession, client_id: str, active: bool) -> None:
    client = await _get(session, client_id)
    if client is None:
        raise OidcClientError(f"client '{client_id}' not found")
    client.active = active


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m mhvp.core.auth.oidc_clients",
        description="Register relying parties of the platform OIDC provider.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create", help="register a client and print its secret once")
    create.add_argument("--client-id", required=True)
    create.add_argument("--name", required=True, help="display name shown in the client list")
    create.add_argument(
        "--redirect-uri",
        action="append",
        required=True,
        dest="redirect_uris",
        help="allowed callback (repeatable), https only",
    )
    create.add_argument(
        "--public", action="store_true", help="no client secret, PKCE only (browser apps)"
    )

    commands.add_parser("list", help="list clients")

    rotate = commands.add_parser("rotate-secret", help="issue a new secret for a client")
    rotate.add_argument("--client-id", required=True)

    for command, help_text in (
        ("deactivate", "deactivate a client (logins with it fail immediately)"),
        ("activate", "activate a client again"),
    ):
        sub = commands.add_parser(command, help=help_text)
        sub.add_argument("--client-id", required=True)
    return parser


async def _execute(args: argparse.Namespace, settings: Settings, out: TextIO) -> None:
    engine = create_app_engine(settings)
    try:
        factory = create_session_factory(engine)
        async with platform_transaction(factory) as session:
            if args.command == "create":
                secret = await create_client(
                    session,
                    client_id=args.client_id,
                    name=args.name,
                    redirect_uris=args.redirect_uris,
                    public=args.public,
                )
                print(f"client_id: {args.client_id}", file=out)
                if secret is None:
                    print("client_secret: (public client, PKCE only)", file=out)
                else:
                    print(f"client_secret: {secret}", file=out)
                    print("The secret is shown once; store it in the relying party now.", file=out)
            elif args.command == "list":
                for client in await list_clients(session):
                    kind = "public" if client.client_secret_hash is None else "confidential"
                    state = "active" if client.active else "inactive"
                    uris = " ".join(client.redirect_uris)
                    print(f"{client.client_id}\t{state}\t{kind}\t{client.name}\t{uris}", file=out)
            elif args.command == "rotate-secret":
                secret = await rotate_secret(session, args.client_id)
                print(f"client_id: {args.client_id}", file=out)
                print(f"client_secret: {secret}", file=out)
            elif args.command in ("deactivate", "activate"):
                await set_active(session, args.client_id, args.command == "activate")
                print(f"client_id: {args.client_id}\tstate: {args.command}d", file=out)
    finally:
        await engine.dispose()


async def run(
    argv: Sequence[str] | None = None,
    settings: Settings | None = None,
    out: TextIO = sys.stdout,
    err: TextIO = sys.stderr,
) -> int:
    args = build_parser().parse_args(argv)
    resolved = settings or get_settings()
    if settings is None:
        configure_logging(resolved)
    try:
        await _execute(args, resolved, out)
    except OidcClientError as error:
        print(f"error: {error}", file=err)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(asyncio.run(run()))
