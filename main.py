"""
TradeBook License Server — Flask application.
No Rust/compilation required, works on any Python version.

Environment variables to set in Render:
    SUPABASE_URL      — your Supabase project URL
    SUPABASE_KEY      — your Supabase service_role key (NOT anon key)
    ADMIN_KEY         — a strong secret you choose, used by admin_tool.py
    HMAC_SECRET       — a strong secret used to sign tokens (never share)
"""

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timezone

import requests as req
from flask import Flask, jsonify, request

app = Flask(__name__)

SUPABASE_URL  = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY  = os.environ.get("SUPABASE_KEY", "")
ADMIN_KEY     = os.environ.get("ADMIN_KEY", "change-this")
HMAC_SECRET   = os.environ.get("HMAC_SECRET", "change-this-too")

_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

# ── Supabase helpers ───────────────────────────────────────────────────────────

def _headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

def _get_license(key: str):
    r = req.get(
        f"{SUPABASE_URL}/rest/v1/licenses",
        headers=_headers(),
        params={"key": f"eq.{key}", "select": "*"},
        timeout=10,
    )
    data = r.json()
    return data[0] if data else None

def _update_license(key: str, fields: dict):
    req.patch(
        f"{SUPABASE_URL}/rest/v1/licenses",
        headers=_headers(),
        params={"key": f"eq.{key}"},
        json=fields,
        timeout=10,
    )

def _insert_license(fields: dict):
    req.post(
        f"{SUPABASE_URL}/rest/v1/licenses",
        headers=_headers(),
        json=fields,
        timeout=10,
    )

def _list_licenses():
    r = req.get(
        f"{SUPABASE_URL}/rest/v1/licenses",
        headers=_headers(),
        params={"select": "*", "order": "created_at.desc"},
        timeout=10,
    )
    return r.json()

# ── Helpers ────────────────────────────────────────────────────────────────────

def _generate_key():
    groups = ["".join(secrets.choice(_CHARS) for _ in range(4)) for _ in range(3)]
    return "TB-" + "-".join(groups)

def _make_token(key: str, machine_id: str) -> str:
    msg = f"{key}:{machine_id}".encode()
    return hmac.new(HMAC_SECRET.encode(), msg, hashlib.sha256).hexdigest()

def _require_admin():
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {ADMIN_KEY}":
        return jsonify({"detail": "Invalid admin key"}), 403
    return None

# ── Public endpoints ───────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/activate")
def activate():
    data       = request.get_json()
    key        = (data.get("key") or "").strip().upper()
    machine_id = (data.get("machine_id") or "").strip().lower()
    machine_name = data.get("machine_name", "")

    if not key or not machine_id:
        return jsonify({"detail": "key and machine_id are required"}), 400

    lic = _get_license(key)
    if not lic:
        return jsonify({"detail": "License key not found. Contact your vendor."}), 404

    if not lic.get("is_active"):
        return jsonify({"detail": "This license key has been revoked."}), 403

    existing = (lic.get("machine_id") or "").strip().lower()
    if existing and existing != machine_id:
        return jsonify({
            "detail": (
                "This key is already activated on another computer. "
                "Contact your vendor to transfer the license."
            )
        }), 409

    token = _make_token(key, machine_id)
    now   = datetime.now(timezone.utc).isoformat()

    _update_license(key, {
        "machine_id":   machine_id,
        "machine_name": machine_name,
        "activated_at": now,
    })

    return jsonify({
        "token":         token,
        "customer_name": lic.get("customer_name", ""),
        "activated_at":  now,
    })


# ── Admin endpoints ────────────────────────────────────────────────────────────

@app.post("/admin/keys")
def create_key():
    err = _require_admin()
    if err: return err

    data = request.get_json()
    key  = _generate_key()
    _insert_license({
        "key":            key,
        "customer_name":  data.get("customer_name", ""),
        "customer_phone": data.get("customer_phone", ""),
        "notes":          data.get("notes", ""),
        "is_active":      True,
    })
    return jsonify({"key": key, "customer_name": data.get("customer_name", "")})


@app.get("/admin/keys")
def list_keys():
    err = _require_admin()
    if err: return err
    return jsonify({"keys": _list_licenses()})


@app.post("/admin/keys/<key>/reset")
def reset_key(key):
    err = _require_admin()
    if err: return err
    key = key.strip().upper()
    _update_license(key, {"machine_id": "", "machine_name": "", "activated_at": None})
    return jsonify({"message": f"Key {key} reset"})


@app.post("/admin/keys/<key>/revoke")
def revoke_key(key):
    err = _require_admin()
    if err: return err
    key = key.strip().upper()
    _update_license(key, {"is_active": False})
    return jsonify({"message": f"Key {key} revoked"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
