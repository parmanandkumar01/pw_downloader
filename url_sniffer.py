#!/usr/bin/env python3
"""
PW CDN Master MPD Sniffer — mitmproxy addon
=============================================
Sirf yahi 2 types ki links capture karta hai:

  1. CloudFront CDN   : https://d1d34p8vz63oiq.cloudfront.net/<uuid>/master.mpd?Signature=...&Key-Pair-Id=...&Policy=...
  2. sec-prod CDN     : https://sec-prod-mediacdn.pw.live/<uuid>/master.mpd?URLPrefix=...&Expires=...&KeyName=...&Signature=...

Koi aur URL save NAHI hogi — na www.pw.live/watch, na api.penpencil.co, na segments.
Duplicate detection video UUID se hoti hai (same video ka alag signed URL = duplicate, skip).

Run with:
    mitmdump -s url_sniffer.py --listen-port 8080 --ssl-insecure

URLs terminal pe print hoti hain aur links.txt me save hoti hain (no duplicates).
"""

import re
import os
import json
from datetime import datetime
from mitmproxy import http

# ── Output file ───────────────────────────────────────────────────────────────
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "links.txt")

# ── Strict CDN master.mpd URL patterns ───────────────────────────────────────
# Only these two CDN hosts + must be master.mpd + must have signed QS

CLOUDFRONT_MPD = re.compile(
    r'^https://[^/]*cloudfront\.net/[0-9a-f-]{36}/master\.mpd'
    r'.*[?&]Signature=.*[?&]Key-Pair-Id=.*[?&]Policy=',
    re.IGNORECASE
)

SECPROD_MPD = re.compile(
    r'^https://sec-prod-mediacdn\.pw\.live/[0-9a-f-]{36}/master\.mpd'
    r'.*[?&]URLPrefix=.*[?&]Expires=.*[?&]Signature=',
    re.IGNORECASE
)

# UUID extractor (for deduplication by video ID, ignoring different signatures)
UUID_RE = re.compile(r'/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/', re.IGNORECASE)


def _is_target_url(url: str) -> bool:
    """Return True only for the exact 2 CDN master.mpd URL types we want."""
    return bool(CLOUDFRONT_MPD.search(url) or SECPROD_MPD.search(url))


def _extract_uuid(url: str) -> str | None:
    """Extract video UUID from URL path for dedup."""
    m = UUID_RE.search(url)
    return m.group(1).lower() if m else None


# ── In-memory dedup sets ───────────────────────────────────────────────────────
seen_uuids: set = set()   # dedup by video UUID (same video = skip)
seen_urls:  set = set()   # also track full URLs loaded from file


def _load_existing():
    """Restart ke baad already-captured UUIDs load karo (no re-capture)."""
    if not os.path.exists(OUTPUT_FILE):
        return
    with open(OUTPUT_FILE, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or line.startswith('['):
                continue
            # Strip ||HEADERS|| suffix if present to get clean URL
            clean = line.split(' ||HEADERS|| ')[0].strip()
            seen_urls.add(clean)
            uid = _extract_uuid(clean)
            if uid:
                seen_uuids.add(uid)


def _save_url(url: str, label: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(OUTPUT_FILE, 'a') as f:
        f.write(f"{url}\n")


def _detect_label(url: str) -> str:
    YELLOW = "\033[93m"
    CYAN   = "\033[96m"
    GREEN  = "\033[92m"
    BOLD   = "\033[1m"
    RESET  = "\033[0m"

    if 'sec-prod-mediacdn' in url:
        platform = f"{YELLOW}{BOLD}[PW-SECPROD]{RESET}"
    elif 'cloudfront.net' in url:
        platform = f"{CYAN}[PW-CloudFront]{RESET}"
    else:
        platform = f"{CYAN}[CDN]{RESET}"

    return f"{platform} {GREEN}[DASH-MANIFEST]{RESET}"


class MasterPlaylistSniffer:
    def __init__(self):
        _load_existing()
        print(f"\n{'='*60}")
        print("  🎯 PW CDN MPD Sniffer — ACTIVE")
        print(f"  📁 Saving to: {OUTPUT_FILE}")
        print(f"  🔁 Loaded {len(seen_uuids)} existing video UUIDs (deduped)")
        print("  ✅ Captures: CloudFront master.mpd + sec-prod master.mpd ONLY")
        print("  ❌ Skip: www.pw.live/watch, api.penpencil.co, segments, everything else")
        print(f"{'='*60}")
        print("  Video play karo — master.mpd URL neeche dikhegi.\n")

        # Init file if not exists
        if not os.path.exists(OUTPUT_FILE):
            open(OUTPUT_FILE, 'w').close()

    def request(self, flow: http.HTTPFlow) -> None:
        self._check(flow.request.pretty_url)

    def response(self, flow: http.HTTPFlow) -> None:
        url = flow.request.pretty_url
        ct  = flow.response.headers.get("content-type", "")
        # Also catch MPD responses identified by Content-Type
        if "application/dash+xml" in ct:
            self._check(url)

    def _check(self, url: str):
        # ── Step 1: strict pattern match ──────────────────────────
        if not _is_target_url(url):
            return

        # ── Step 2: UUID-based deduplication ──────────────────────
        uid = _extract_uuid(url)
        if uid and uid in seen_uuids:
            print(f"  [skip-dup] UUID already captured: {uid}")
            return
        if url in seen_urls:
            return

        # ── Step 3: record & save ─────────────────────────────────
        if uid:
            seen_uuids.add(uid)
        seen_urls.add(url)

        label    = _detect_label(url)
        timestamp = datetime.now().strftime("%H:%M:%S")

        print(f"\n{'─'*60}")
        print(f"  {label}  {timestamp}")
        print(f"  {url}")
        print(f"{'─'*60}", flush=True)

        _save_url(url, label)


addons = [MasterPlaylistSniffer()]
