"""TEST DOUBLE for Clerk's JWKS endpoint, used by the local end-to-end run only.

It serves the public half of a locally generated RSA key and mints session tokens signed with
it. The API verifies these exactly as it verifies Clerk tokens, so nothing in the API is
bypassed; point CLERK_JWKS_URL at this server only on a machine you control.

    python scripts/dev_stubs/test_identity.py serve --port 8788 --key /tmp/evalai-test-key.pem
    python scripts/dev_stubs/test_identity.py mint --key /tmp/evalai-test-key.pem --sub user_1 --email a@b.c
"""
from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ISSUER = "https://evalai-test-identity.local"
KID = "evalai-test"


def load_key(path: str):
    p = Path(path)
    if not p.exists():
        k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        p.write_bytes(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    return serialization.load_pem_private_key(p.read_bytes(), password=None)


def mint(key, sub: str, email: str, ttl: int = 8 * 3600) -> str:
    now = int(time.time())
    return jwt.encode({"sub": sub, "iss": ISSUER, "iat": now, "nbf": now - 5, "exp": now + ttl, "email": email, "email_verified": True},
                      key, algorithm="RS256", headers={"kid": KID})


def serve(key, port: int) -> None:
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key())) | {"kid": KID, "use": "sig", "alg": "RS256"}
    body = json.dumps({"keys": [jwk]}).encode()

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.send_header("content-type", "application/json"); self.end_headers(); self.wfile.write(body)

        def log_message(self, *a):
            pass

    HTTPServer(("127.0.0.1", port), H).serve_forever()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["serve", "mint"])
    ap.add_argument("--key", required=True)
    ap.add_argument("--port", type=int, default=8788)
    ap.add_argument("--sub")
    ap.add_argument("--email")
    a = ap.parse_args()
    k = load_key(a.key)
    if a.cmd == "serve":
        serve(k, a.port)
    else:
        print(mint(k, a.sub, a.email))
