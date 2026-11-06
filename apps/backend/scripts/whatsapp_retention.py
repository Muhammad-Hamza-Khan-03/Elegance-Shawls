"""WhatsApp message retention (plan: 12 months unless the customer asks for deletion). Run from apps/backend (needs DATABASE_URL).

  python scripts/whatsapp_retention.py purge [--months 12] [--apply]     # delete messages older than N months, then chats left empty
  python scripts/whatsapp_retention.py delete-chat +923001234567 [--apply]  # a customer's deletion request: all their messages and the chat record
Dry run by default: prints what would go. Enquiries are not deleted; deleting a chat only unlinks them (customer_details is cleared).
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from database.pg import close_postgres, connect_to_postgres, session_factory  # noqa: E402

PURGE = [
    "DELETE FROM whatsapp_messages WHERE sent_at < now() - make_interval(months => :months)",
    # A chat with no messages left and no enquiry attached holds nothing worth keeping.
    "DELETE FROM whatsapp_contacts c WHERE NOT EXISTS (SELECT 1 FROM whatsapp_messages m WHERE m.contact_id = c.id)"
    " AND NOT EXISTS (SELECT 1 FROM enquiries e WHERE e.whatsapp_contact_id = c.id)",
]


async def run(args) -> int:
    await connect_to_postgres()
    try:
        async with session_factory()() as session, session.begin():
            if args.command == "purge":
                params = {"months": args.months}
                n = (await session.execute(text("SELECT count(*) FROM whatsapp_messages WHERE sent_at < now() - make_interval(months => :months)"), params)).scalar_one()
                print(f"{n} messages older than {args.months} months")
                if args.apply:
                    for statement in PURGE:
                        await session.execute(text(statement), params)
            else:
                phone = "+" + "".join(ch for ch in args.phone if ch.isdigit())
                contact = (await session.execute(text("SELECT id FROM whatsapp_contacts WHERE phone_e164 = :p"), {"p": phone})).scalar_one_or_none()
                if contact is None:
                    print(f"no chat for {phone}")
                    return 1
                n = (await session.execute(text("SELECT count(*) FROM whatsapp_messages WHERE contact_id = :c"), {"c": contact})).scalar_one()
                print(f"{n} messages in the chat for {phone}")
                if args.apply:
                    await session.execute(text("UPDATE enquiries SET customer_details = NULL WHERE whatsapp_contact_id = :c"), {"c": contact})
                    await session.execute(text("DELETE FROM whatsapp_contacts WHERE id = :c"), {"c": contact})   # messages cascade; enquiries are unlinked (SET NULL)
            if not args.apply:
                print("dry run: nothing deleted (add --apply)")
                session.sync_session.rollback()
    finally:
        await close_postgres()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    purge = sub.add_parser("purge")
    purge.add_argument("--months", type=int, default=12)
    delete = sub.add_parser("delete-chat")
    delete.add_argument("phone")
    for p in (purge, delete):
        p.add_argument("--apply", action="store_true")
    sys.exit(asyncio.run(run(parser.parse_args())))
