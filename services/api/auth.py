"""Signed-token auth stub (architecture decision 12).

A token carries who the caller is: `sub` (user id), `role` and, for patients, `patient_id`. The API
puts these into graph state, so no tool ever trusts an id typed into a message (pack p36). OIDC
with OTP replaces the issuer later; the checks on the receiving side stay the same.

Format: base64url(JSON claims) + "." + base64url(HMAC-SHA256(claims, AUTH_SIGNING_KEY)).

    python -m services.api.auth --sub P-PRIYA --role patient --patient-id P-PRIYA   # dev token, 1 hour
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Literal

Role = Literal["patient", "front_desk", "compliance"]
ROLES = ("patient", "front_desk", "compliance")


class AuthError(Exception):
    pass


@dataclass(frozen=True)
class Caller:
    sub: str
    role: Role
    patient_id: str | None


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _key(key: str | None) -> bytes:
    k = key or os.environ.get("AUTH_SIGNING_KEY", "")
    if len(k) < 32:
        raise AuthError("AUTH_SIGNING_KEY must be at least 32 characters")
    return k.encode()


def mint(sub: str, role: Role, patient_id: str | None = None, ttl_s: int = 3600, key: str | None = None,
         now: float | None = None) -> str:
    if role not in ROLES:
        raise AuthError(f"unknown role {role}")
    if role == "patient" and not patient_id:
        raise AuthError("a patient token needs patient_id")
    claims = {"sub": sub, "role": role, "patient_id": patient_id, "exp": int((now or time.time()) + ttl_s)}
    body = _b64(json.dumps(claims, separators=(",", ":"), sort_keys=True).encode())
    sig = _b64(hmac.new(_key(key), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify(token: str, key: str | None = None, now: float | None = None) -> Caller:
    try:
        body, sig = token.split(".")
    except ValueError:
        raise AuthError("malformed token") from None
    expected = _b64(hmac.new(_key(key), body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        raise AuthError("bad signature")
    try:
        claims = json.loads(_unb64(body))
    except Exception:
        raise AuthError("malformed claims") from None
    if claims.get("exp", 0) < (now or time.time()):
        raise AuthError("token expired")
    if claims.get("role") not in ROLES:
        raise AuthError("unknown role")
    if claims["role"] == "patient" and not claims.get("patient_id"):
        raise AuthError("patient token without patient_id")
    return Caller(sub=claims["sub"], role=claims["role"], patient_id=claims.get("patient_id"))


def main() -> None:
    from dotenv import load_dotenv
    load_dotenv()
    ap = argparse.ArgumentParser(description="Mint a development token")
    ap.add_argument("--sub", required=True)
    ap.add_argument("--role", choices=ROLES, default="patient")
    ap.add_argument("--patient-id")
    ap.add_argument("--ttl", type=int, default=3600)
    a = ap.parse_args()
    print(mint(a.sub, a.role, a.patient_id or (a.sub if a.role == "patient" else None), a.ttl))


if __name__ == "__main__":
    main()
