"""Create the three requested Supabase Auth demo accounts after migration 008.

Passwords come only from ignored environment variables. They are sent directly
to Supabase Auth and are never written to CarePilot business tables or logs.
"""

import os
import sys

import httpx

from app.database import SessionLocal
from app.domain import ensure_demo_order_entitlements
from app.models import Profile


ACCOUNTS = (
    ("demo.user@carepilot.local", "演示用户", "user", "CARE_PILOT_DEMO_USER_PASSWORD"),
    ("demo.admin@carepilot.local", "演示客服", "admin", "CARE_PILOT_DEMO_ADMIN_PASSWORD"),
    ("demo.superadmin@carepilot.local", "演示超级管理员", "superadmin", "CARE_PILOT_DEMO_SUPERADMIN_PASSWORD"),
)


def required_env(name: str) -> str:
    value = os.getenv(name) or ""
    if len(value) < 12:
        raise RuntimeError(f"{name} must be at least 12 characters")
    return value


def main() -> None:
    supabase_url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    secret_key = os.getenv("SUPABASE_SECRET_KEY") or ""
    if not supabase_url or not secret_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SECRET_KEY are required")
    passwords = {email: required_env(password_env) for email, _, _, password_env in ACCOUNTS}
    headers = {"apikey": secret_key, "Authorization": f"Bearer {secret_key}"}
    with httpx.Client(timeout=20) as client:
        existing_response = client.get(f"{supabase_url}/auth/v1/admin/users", headers=headers, params={"page": 1, "per_page": 1000})
        existing_response.raise_for_status()
        existing = {item["email"].lower(): item for item in existing_response.json().get("users", [])}
        account_ids: dict[str, str] = {}
        for email, display_name, _, _ in ACCOUNTS:
            record = existing.get(email)
            if not record:
                response = client.post(
                    f"{supabase_url}/auth/v1/admin/users",
                    headers=headers,
                    json={"email": email, "password": passwords[email], "email_confirm": True, "user_metadata": {"display_name": display_name}},
                )
                response.raise_for_status()
                record = response.json()
            else:
                response = client.put(
                    f"{supabase_url}/auth/v1/admin/users/{record['id']}",
                    headers=headers,
                    json={"password": passwords[email], "email_confirm": True, "user_metadata": {"display_name": display_name}},
                )
                response.raise_for_status()
                record = response.json()
            account_ids[email] = str(record["id"])
    with SessionLocal() as db:
        for email, display_name, role, _ in ACCOUNTS:
            profile = db.get(Profile, account_ids[email])
            if not profile:
                raise RuntimeError(f"Profile trigger did not create a record for {email}; confirm migration 008 completed")
            profile.display_name = display_name
            profile.role = role
            if role == "user":
                ensure_demo_order_entitlements(db, profile.id)
        db.commit()
    print("Created or updated 3 Supabase Auth demo accounts: user, admin, superadmin.")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, httpx.HTTPError) as error:
        print(f"Demo Auth provisioning failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
