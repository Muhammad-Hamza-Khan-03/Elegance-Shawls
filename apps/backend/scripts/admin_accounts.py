"""Operator CLI for admin accounts. Run from apps/backend against the target DATABASE_URL.

  python scripts/admin_accounts.py bootstrap-owner --email you@example.com
  python scripts/admin_accounts.py reset-password --email you@example.com      # recovery; revokes all their sessions

The password is read from ADMIN_ACCOUNT_PASSWORD (unset it afterwards) or prompted twice on a terminal; it is never an
argument, never printed and never audited. bootstrap-owner is idempotent: when an active owner already exists it changes
nothing, so it is safe in runbooks and repeated deploys. There is no default credential.
"""
import argparse
import asyncio
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: E402

from database.pg import make_engine  # noqa: E402
from models.relational_model import AdminAccount  # noqa: E402
from repositories import admin as repo  # noqa: E402
from security.passwords import hash_password_async, password_problem  # noqa: E402

LOCK_KEY = 727001   # serialises concurrent bootstraps


class CliError(Exception):
    pass


async def bootstrap_owner(sessions, email: str, password: str) -> str:
    """'created' or 'exists'. Raises CliError for an unusable email/password."""
    email = repo.normalize_email(email)
    if problem := password_problem(password, email):
        raise CliError(problem)
    password_hash = await hash_password_async(password)
    async with sessions() as session, session.begin():
        await session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": LOCK_KEY})
        owners = (await session.execute(select(AdminAccount.id).where(AdminAccount.role == "owner", AdminAccount.status == "active").limit(1))).first()
        if owners:
            return "exists"
        if await repo.get_account_by_email(session, email):
            raise CliError("That email already belongs to a non-owner or disabled account; use reset-password and have an owner fix its role")
        account = await repo.create_account(session, email=email, role="owner", password_hash=password_hash)
        await repo.add_audit(session, actor_type="system", actor_id="cli", action="admin.bootstrap_owner",
                             target=f"admin_account:{account.id}", outcome="success")
        return "created"


async def reset_password(sessions, email: str, password: str) -> None:
    email = repo.normalize_email(email)
    if problem := password_problem(password, email):
        raise CliError(problem)
    password_hash = await hash_password_async(password)
    async with sessions() as session, session.begin():
        account = await repo.get_account_by_email(session, email)
        if account is None:
            raise CliError("No such account")
        await repo.set_password(session, account.id, password_hash)
        await repo.add_audit(session, actor_type="system", actor_id="cli", action="admin.reset_password",
                             target=f"admin_account:{account.id}", outcome="success", detail={"sessions_revoked": True})


def _read_password() -> str:
    if password := os.environ.get("ADMIN_ACCOUNT_PASSWORD"):
        return password
    if not sys.stdin.isatty():
        raise CliError("Set ADMIN_ACCOUNT_PASSWORD or run on a terminal")
    first = getpass.getpass("Password: ")
    if first != getpass.getpass("Repeat password: "):
        raise CliError("Passwords differ")
    return first


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["bootstrap-owner", "reset-password"])
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    engine = None
    try:
        password = _read_password()
        engine = make_engine()
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        if args.command == "bootstrap-owner":
            result = await bootstrap_owner(sessions, args.email, password)
            print("Owner created." if result == "created" else "An active owner already exists; nothing changed.")
        else:
            await reset_password(sessions, args.email, password)
            print("Password reset; all sessions for the account were revoked.")
        return 0
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        if engine:
            await engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
