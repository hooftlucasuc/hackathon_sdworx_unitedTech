"""Leestoegang tot het dashboard beheren: de custom claim agent=true in Firebase Auth (zie infra/firestore.rules).

De e-mailadressen gaan alleen als argument mee en komen nooit in de repo. De persoon moet eerst één keer
met Google ingelogd zijn op het dashboard (dan bestaat het account) en na het toekennen opnieuw inloggen.

  python scripts/grant_access.py grant naam@example.com [...]
  python scripts/grant_access.py revoke naam@example.com
  python scripts/grant_access.py list

Vereist: pip install firebase-admin, en lokale ADC (gcloud auth application-default login) met de rol
Firebase Authentication Admin op het project. GCP_PROJECT uit de omgeving of .env.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLAIM = "agent"

log = logging.getLogger("grant_access")


def project_id() -> str:
    project = os.environ.get("GCP_PROJECT", "")
    env_file = REPO_ROOT / ".env"
    if not project and env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("GCP_PROJECT="):
                project = line.split("=", 1)[1].strip().strip('"')
    if not project:
        raise SystemExit("GCP_PROJECT ontbreekt (omgeving of .env)")
    return project


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=("grant", "revoke", "list"))
    parser.add_argument("emails", nargs="*")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if args.action != "list" and not args.emails:
        parser.error("geef minstens één e-mailadres")

    try:
        import firebase_admin
        from firebase_admin import auth
    except ImportError:
        raise SystemExit("pip install firebase-admin") from None
    firebase_admin.initialize_app(options={"projectId": project_id()})

    try:
        if args.action == "list":
            for user in auth.list_users().iterate_all():
                if (user.custom_claims or {}).get(CLAIM):
                    log.info("toegang: %s", user.email)
            return 0
        for email in args.emails:
            try:
                user = auth.get_user_by_email(email)
            except auth.UserNotFoundError:
                log.warning("%s: nog geen account; laat de persoon eerst één keer inloggen op het dashboard", email)
                continue
            claims = dict(user.custom_claims or {})
            if args.action == "grant":
                claims[CLAIM] = True
            else:
                claims.pop(CLAIM, None)
            auth.set_custom_user_claims(user.uid, claims or None)
            log.info("%s: %s", email, "toegang gegeven" if args.action == "grant" else "toegang ingetrokken")
    except Exception as exc:  # meestal credentials of een ontbrekend quota project
        if "quota project" in str(exc).lower():
            hint = f"zet eerst het quota-project: gcloud auth application-default set-quota-project {project_id()}"
            raise SystemExit(hint) from exc
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
