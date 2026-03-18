#!/usr/bin/env python3
"""
test_penpencil.py
=================
Test script to:
  1. Read the api.penpencil.co URL from links.txt
  2. Ask for your auth token interactively
  3. Call the API and show the JSON response
  4. Try to download the video if the response contains a signed CDN URL

Run:
    python3 test_penpencil.py
"""

import sys, re, json, ssl, urllib.request, urllib.error
from urllib.parse import urlparse

LINKS_FILE = "links.txt"

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode    = ssl.CERT_NONE

GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RED    = "\033[91m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def read_penpencil_url():
    """Extract the first api.penpencil.co URL from links.txt."""
    with open(LINKS_FILE, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('https://api.penpencil.co'):
                return line.split(' ||HEADERS||')[0]  # strip headers suffix if any
    return None

def call_api(url, token, header_name):
    """Call the PW API with the given auth header. Return (status_code, json_data)."""
    headers = {
        "User-Agent":  "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36",
        "Referer":     "https://www.pw.live/",
        "Origin":      "https://www.pw.live",
        "Accept":      "application/json",
        header_name:   token,
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=30) as r:
            raw = r.read().decode()
            return r.status, json.loads(raw)
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"raw": body[:500]}

def find_cdn_url(obj, depth=0):
    """Recursively find a signed CDN URL in JSON."""
    if depth > 8:
        return None
    if isinstance(obj, str):
        if ('sec-prod-mediacdn.pw.live' in obj or
                ('cloudfront.net' in obj and 'cloudfront.net' in urlparse(obj).netloc)):
            if '.mpd' in obj or '.m3u8' in obj or 'URLPrefix=' in obj:
                return obj
    elif isinstance(obj, dict):
        for v in obj.values():
            r = find_cdn_url(v, depth+1)
            if r: return r
    elif isinstance(obj, list):
        for item in obj:
            r = find_cdn_url(item, depth+1)
            if r: return r
    return None

def main():
    print(f"\n{BOLD}{'='*60}")
    print("  PW API URL Tester")
    print(f"{'='*60}{RESET}\n")

    # ── Read URL ──────────────────────────────────────────────────
    pw_url = read_penpencil_url()
    if not pw_url:
        print(f"{RED}[✗] Koi api.penpencil.co URL links.txt mein nahi mili.{RESET}")
        print("     Sniffer chalao aur video play karo pehle.")
        sys.exit(1)
    print(f"{CYAN}[i] URL mili:{RESET}")
    print(f"    {pw_url[:100]}...")

    # ── Ask for auth token ────────────────────────────────────────
    print(f"\n{YELLOW}Apna PW auth token paste karo.{RESET}")
    print("  (Browser → F12 → Network → koi penpencil.co request → Request Headers)")
    print("  Common headers: 'Authorization' (Bearer token) ya 'token' ya 'x-access-token'")
    print()
    print("  Header name [default: token]: ", end="")
    hname = input().strip() or "token"
    print(f"  Token value: ", end="")
    token = input().strip()

    if not token:
        print(f"\n{RED}[✗] Token blank hai. Exiting.{RESET}")
        sys.exit(1)

    # Strip 'Bearer ' prefix if user pasted the full header value
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
        # Reconstruct with proper format for Authorization header
        if hname.lower() in ("authorization", "auth"):
            token = "Bearer " + token

    print(f"\n{CYAN}[→] API call kar raha hoon...{RESET}")
    print(f"    Header: {hname}")
    status, data = call_api(pw_url, token, hname)

    print(f"\n{BOLD}[API Response] Status: {status}{RESET}")

    if status == 401:
        print(f"{RED}[✗] 401 Unauthorized — token galat hai ya expire ho gaya.{RESET}")
        print(f"    Response: {json.dumps(data)[:200]}")
        sys.exit(1)

    if status == 200:
        print(f"{GREEN}[✓] 200 OK — token sahi hai!{RESET}")
        print(f"\n{CYAN}[JSON response (first 600 chars)]:{RESET}")
        print(json.dumps(data, indent=2)[:600])

        signed_url = find_cdn_url(data)
        if signed_url:
            print(f"\n{GREEN}[✓] Signed CDN URL mili:{RESET}")
            print(f"    {signed_url[:100]}...")
            print(f"\n{BOLD}✅ Sab sahi hai! Token aur API kaam kar raha hai.{RESET}")
            print(f"\n{YELLOW}[→] Ab main script mein yeh header add kar dega:{RESET}")
            print(f'    Header name : {hname}')
            print(f'    Token prefix: {token[:20]}...')

            # Save the working token to a temp file for integration
            with open(".pw_auth_token", "w") as f:
                json.dump({"header": hname, "token": token}, f)
            print(f"\n{CYAN}[✓] Token .pw_auth_token file mein save kar diya (launch_pw_downloader.sh padhega).{RESET}")
        else:
            print(f"\n{YELLOW}[!] Signed CDN URL nahi mili response mein.{RESET}")
            print(f"    Full JSON response:")
            print(json.dumps(data, indent=2)[:1000])
    else:
        print(f"{YELLOW}[!] Unexpected status {status}{RESET}")
        print(json.dumps(data, indent=2)[:400])

if __name__ == "__main__":
    main()
