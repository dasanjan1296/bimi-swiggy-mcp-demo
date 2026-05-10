"""Quick outbound smoke test — proves the POC server can talk to Evolution.

Usage:
    python test-send.py "+910000000000" "Hello from Bimi POC"

Or with a JID directly:
    python test-send.py "910000000000@s.whatsapp.net" "..."

For groups:
    python test-send.py "120363xxxxxxxxx@g.us" "Hello group"
"""
import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()

EVOLUTION_URL = os.getenv("EVOLUTION_PUBLIC_URL", "http://localhost:8080")
EVOLUTION_KEY = os.getenv("EVOLUTION_API_KEY", "")
INSTANCE = os.getenv("EVOLUTION_INSTANCE", "bimi-poc")


def send(to: str, text: str) -> None:
    # Strip leading + and spaces — Evolution accepts E.164 without the +.
    target = to.lstrip("+").replace(" ", "") if "@" not in to else to
    url = f"{EVOLUTION_URL}/message/sendText/{INSTANCE}"
    payload = {"number": target, "text": text}
    resp = httpx.post(url, json=payload, headers={"apikey": EVOLUTION_KEY}, timeout=15.0)
    print(f"HTTP {resp.status_code}")
    print(resp.text[:500])


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python test-send.py <to> <text>")
        sys.exit(1)
    send(sys.argv[1], sys.argv[2])
