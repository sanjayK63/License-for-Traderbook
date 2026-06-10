"""
TradeBook License Server — FastAPI application.

Deploy to Render.com (free tier). Set these environment variables in Render:
    SUPABASE_URL      — your Supabase project URL
    SUPABASE_KEY      — your Supabase service_role key (NOT anon key)
    ADMIN_KEY         — a strong secret you choose, used by admin_tool.py
    HMAC_SECRET       — a strong secret used to sign tokens (never share)
"""

import hashlib
import hmac
import os
import secrets
import string
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from supabase import create_client, Client

# ── Config ─────────────────────────────────────────────────────────────────────
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
ADMIN_KEY = os.environ.get("ADMIN_KEY", "change-this-in-render")
HMAC_SECRET = os.environ.get("HMAC_SECRET", "change-this-in-render")

app = FastAPI(title="TradeBook License Server", version="1.0.0")
_sb: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── Key generation ─────────────────────────────────────────────────────────────
_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no I/O/0/1 to avoid confusion


def _generate_key() -> str:
    groups = ["".join(secrets.choice(_CHARS) for _ in range(4)) for _ in range(3)]
    return "TB-" + "-".join(groups)


def _make_token(key: str, machine_id: str) -> str:
    msg = f"{key}:{machine_id}".encode()
    return hmac.new(HMAC_SECRET.encode(), msg, hashlib.sha256).hexdigest()


def _require_admin(authorization: str | None):
    if not authorization or authorization != f"Bearer {ADMIN_KEY}":
        raise HTTPException(status_code=403, detail="Invalid admin key")


# ── Schemas ────────────────────────────────────────────────────────────────────
class ActivateRequest(BaseModel):
    key: str
    machine_id: str
    machine_name: str = ""


class CreateKeyRequest(BaseModel):
    customer_name: str
    customer_phone: str = ""
    notes: str = ""


# ── Public endpoints ───────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/activate")
def activate(req: ActivateRequest):
    key = req.key.strip().upper()
    machine_id = req.machine_id.strip().lower()

    row = _sb.table("licenses").select("*").eq("key", key).single().execute()
    if not row.data:
        raise HTTPException(status_code=404, detail="License key not found. Contact your vendor.")

    lic = row.data

    if not lic["is_active"]:
        raise HTTPException(status_code=403, detail="This license key has been revoked.")

    existing_machine = (lic.get("machine_id") or "").strip().lower()

    if existing_machine and existing_machine != machine_id:
        raise HTTPException(
            status_code=409,
            detail=(
                "This key is already activated on another computer. "
                "Contact your vendor to transfer the license."
            ),
        )

    token = _make_token(key, machine_id)
    now = datetime.now(timezone.utc).isoformat()

    _sb.table("licenses").update({
        "machine_id": machine_id,
        "machine_name": req.machine_name,
        "activated_at": now,
    }).eq("key", key).execute()

    return {
        "token": token,
        "customer_name": lic.get("customer_name", ""),
        "activated_at": now,
    }


# ── Admin endpoints ────────────────────────────────────────────────────────────
@app.post("/admin/keys")
def create_key(
    req: CreateKeyRequest,
    authorization: str | None = Header(default=None),
):
    _require_admin(authorization)
    key = _generate_key()
    _sb.table("licenses").insert({
        "key": key,
        "customer_name": req.customer_name,
        "customer_phone": req.customer_phone,
        "notes": req.notes,
        "is_active": True,
    }).execute()
    return {"key": key, "customer_name": req.customer_name, "customer_phone": req.customer_phone}


@app.get("/admin/keys")
def list_keys(authorization: str | None = Header(default=None)):
    _require_admin(authorization)
    result = _sb.table("licenses").select("*").order("created_at", desc=True).execute()
    return {"keys": result.data}


@app.post("/admin/keys/{key}/reset")
def reset_key(key: str, authorization: str | None = Header(default=None)):
    _require_admin(authorization)
    key = key.strip().upper()
    result = _sb.table("licenses").update({
        "machine_id": "",
        "machine_name": "",
        "activated_at": None,
    }).eq("key", key).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Key not found")
    return {"message": f"Key {key} reset — machine binding cleared"}


@app.post("/admin/keys/{key}/revoke")
def revoke_key(key: str, authorization: str | None = Header(default=None)):
    _require_admin(authorization)
    key = key.strip().upper()
    result = _sb.table("licenses").update({"is_active": False}).eq("key", key).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Key not found")
    return {"message": f"Key {key} revoked"}
