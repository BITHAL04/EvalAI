"""Create the private Supabase Storage bucket EvalAI uses. Safe to run more than once.

    SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... SUPABASE_STORAGE_BUCKET=evalai-private python scripts/setup_supabase.py
"""
import os
import sys

import httpx

url, key = os.environ.get("SUPABASE_URL", "").rstrip("/"), os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
bucket = os.environ.get("SUPABASE_STORAGE_BUCKET", "evalai-private")
max_mb = int(os.environ.get("MAX_UPLOAD_SIZE_MB", "50"))
if not url or not key:
    sys.exit("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")
h = {"Authorization": f"Bearer {key}", "apikey": key}
body = {"id": bucket, "name": bucket, "public": False, "file_size_limit": max_mb * 1024 * 1024,
        "allowed_mime_types": ["application/pdf", "text/plain", "image/jpeg", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/octet-stream"]}
r = httpx.post(f"{url}/storage/v1/bucket", headers=h, json=body, timeout=30)
if r.status_code in (200, 201):
    print(f"Created private bucket {bucket}")
elif "already exists" in r.text.lower() or r.status_code == 409:
    r = httpx.put(f"{url}/storage/v1/bucket/{bucket}", headers=h, json={k: v for k, v in body.items() if k not in ("id", "name")}, timeout=30)
    r.raise_for_status()
    print(f"Bucket {bucket} exists; settings updated (private)")
else:
    sys.exit(f"Failed: HTTP {r.status_code} {r.text[:300]}")
info = httpx.get(f"{url}/storage/v1/bucket/{bucket}", headers=h, timeout=30).json()
assert info.get("public") is False, "Bucket must be private"
print("Verified: bucket is private. No storage policies are needed: only the API (service role) reads or writes, via signed URLs.")
