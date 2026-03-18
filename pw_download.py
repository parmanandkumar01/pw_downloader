#!/usr/bin/env python3
"""
PW (Physics Wallah) Video Downloader
======================================
Auto-detects whether the PW video uses:
  - HLS + AES-128 → downloads via local proxy + yt-dlp
  - DASH + ClearKey CENC → downloads all segments directly + ffmpeg decryption

Usage:
    python3 pw_download.py "<PW_URL>" "Output Video Name"
    python3 pw_download.py "<PW_URL>" "Output Video Name" 480   # force resolution

Examples:
    python3 pw_download.py "https://sec-prod-mediacdn.pw.live/.../master.mpd?..." "Lecture 01"
    python3 pw_download.py "https://sec-prod-mediacdn.pw.live/.../dash/240/init.mp4?..." "Lecture 02"
"""

import sys, re, os, ssl, json, threading, subprocess, urllib.request, urllib.error, time, tempfile, shutil
import concurrent.futures
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode, quote
import urllib.parse

# ── Config ────────────────────────────────────────────────────────────────────
PROXY_PORT      = 18888
PREFERRED_RES   = [1080, 720, 480, 360, 240]

# ↤ Downloaded videos yahan save honge ────────────────────────────
# Change this path to save videos in a different folder.
OUTPUT_DIR = "/home/parmanand/Desktop/pw_down/Download"
PW_HEADERS = {
    "User-Agent":  "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "Referer":     "https://www.pw.live/",
    "Origin":      "https://www.pw.live",
    "Accept":      "*/*",
}

# ── SSL context ───────────────────────────────────────────────────────────────
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode    = ssl.CERT_NONE


# ── PyInstaller resource path ─────────────────────────────────────────────────
def get_resource_path(name: str) -> str:
    """Return absolute path to an external tool (yt-dlp, ffmpeg, etc.).

    Search order:
      1. System PATH  — always preferred (works both frozen and not-frozen)
      2. Folder next to the executable / script  (for portable bundles)
      3. PyInstaller _MEIPASS temp dir  (fallback, should not normally be needed)
    """
    # 1. Try system PATH first
    found = shutil.which(name)
    if found:
        return found

    # 2. Try folder alongside the frozen exe or the source script
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
    else:
        exe_dir = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.join(exe_dir, name)
    if os.path.isfile(candidate):
        return candidate

    # 3. PyInstaller _MEIPASS temp dir (last resort)
    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        candidate = os.path.join(meipass, name)
        if os.path.isfile(candidate):
            return candidate

    # Nothing found — return the name itself so the OS error is clear
    return name


# ── Subprocess helpers (suppress console window on Windows) ───────────────────
def _popen_kwargs() -> dict:
    """Extra kwargs for Popen/run to suppress console windows on Windows."""
    if sys.platform == 'win32':
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return {'startupinfo': si, 'creationflags': subprocess.CREATE_NO_WINDOW}
    return {}


def fetch_pw(url: str, extra_headers: dict = None) -> bytes:
    """Fetch a URL from PW CDN with correct browser headers.
    extra_headers: additional headers (e.g. Cookie, Authorization) captured by sniffer.
    """
    merged = {**PW_HEADERS, **(extra_headers or {})}
    req = urllib.request.Request(url, headers=merged)
    try:
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=30) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} fetching {url[:90]}") from e


def parse_url_and_headers(raw_line: str):
    """
    Parse a line from links.txt that may contain a ||HEADERS|| suffix.
    Returns (clean_url, headers_dict).
    Format saved by sniffer:  <url> ||HEADERS|| {"Cookie":"...", ...}
    """
    DELIM = " ||HEADERS|| "
    if DELIM in raw_line:
        url_part, hdr_part = raw_line.split(DELIM, 1)
        try:
            headers = json.loads(hdr_part.strip())
        except json.JSONDecodeError:
            headers = {}
        return url_part.strip(), headers
    return raw_line.strip(), {}

def extract_params(url: str) -> dict:
    qs = parse_qs(urlparse(url).query)
    return {k: v[0] for k, v in qs.items()}


def get_unique_filepath(output_dir: str, safe_name: str, ext: str = ".mp4") -> str:
    """Return a unique file path by appending a counter if the file already exists."""
    base_path = os.path.join(output_dir, f"{safe_name}{ext}")
    if not os.path.exists(base_path):
        return base_path
    counter = 1
    while True:
        new_path = os.path.join(output_dir, f"{safe_name}_{counter}{ext}")
        if not os.path.exists(new_path):
            return new_path
        counter += 1


# ═══════════════════════════════════════════════════════════════════════════════
# CloudFront URL helpers
# ═══════════════════════════════════════════════════════════════════════════════

def is_cloudfront_url(url: str) -> bool:
    """Return True if the *hostname* is a CloudFront CDN (not sec-prod).
    Checks urlparse netloc so cloudfront.net in a query param doesn't match.
    """
    return 'cloudfront.net' in urlparse(url).netloc


def is_penpencil_api_url(url: str) -> bool:
    """Return True if URL is a PW API endpoint (api.penpencil.co)."""
    return 'penpencil.co' in urlparse(url).netloc


def resolve_penpencil_video_url(api_url: str, sniff_headers: dict) -> str:
    """
    Call the PW API with auth headers and extract the signed CDN URL
    from the JSON response.
    The API returns JSON like: { "data": { "url": "https://sec-prod-..." } }
    We recursively search for any string value that looks like a signed CDN URL.
    """
    print(f"  [+] Calling PW API to resolve signed CDN URL...")
    if not sniff_headers:
        raise RuntimeError(
            "No auth headers found.\n"
            "  Re-sniff with the sniffer — it now captures Authorization/Cookie automatically."
        )

    raw = fetch_pw(api_url, extra_headers=sniff_headers)
    try:
        data = json.loads(raw.decode())
    except json.JSONDecodeError:
        raise RuntimeError(f"API did not return JSON. Raw: {raw[:200]}")

    def find_cdn_url(obj, depth=0):
        """Recursively find a signed CDN URL in any JSON value."""
        if depth > 8:
            return None
        if isinstance(obj, str):
            # Accept sec-prod or direct cloudfront URLs that have MPD/M3U8
            if (('sec-prod-mediacdn.pw.live' in obj or
                 ('cloudfront.net' in obj and 'cloudfront.net' in urlparse(obj).netloc))
                    and ('.mpd' in obj or '.m3u8' in obj or 'URLPrefix=' in obj)):
                return obj
        elif isinstance(obj, dict):
            for v in obj.values():
                r = find_cdn_url(v, depth + 1)
                if r:
                    return r
        elif isinstance(obj, list):
            for item in obj:
                r = find_cdn_url(item, depth + 1)
                if r:
                    return r
        return None

    signed_url = find_cdn_url(data)
    if not signed_url:
        # Print truncated response to help debug
        print(f"  [!] API response (first 400 chars):\n{json.dumps(data)[:400]}")
        raise RuntimeError(
            "Could not find a signed CDN URL in the API response.\n"
            "  The API may need a different auth token or the URL format changed."
        )

    print(f"  [+] Resolved: {signed_url[:90]}...")
    return signed_url


def normalize_mpd_url(url: str) -> str:
    """
    Some sniffers capture URLs with '&' instead of '?' as the first
    query-string delimiter (e.g. master.mpd&secondaryParentId=...).
    Fix that so urllib can parse params correctly.
    """
    if '?' not in url and '&' in url:
        url = url.replace('&', '?', 1)
    return url


def extract_cloudfront_video_id(url: str) -> str:
    """Extract the UUID from a CloudFront CDN URL."""
    m = re.search(r'cloudfront\.net/([0-9a-f-]{36})/', url)
    if not m:
        raise ValueError("No video UUID found in CloudFront URL")
    return m.group(1)


def cloudfront_base(url: str) -> str:
    """Return the base CDN root for a CloudFront video (up to UUID)."""
    m = re.match(r'(https://[^/]+/[0-9a-f-]{36})/', url)
    if not m:
        raise ValueError("Cannot determine CloudFront base URL")
    return m.group(1)


def extract_video_id(url: str) -> str:
    m = re.search(r'sec-prod-mediacdn\.pw\.live/([0-9a-f-]{36})', url)
    if not m:
        raise ValueError("No video UUID found in URL")
    return m.group(1)


def signed_qs(params: dict) -> str:
    # quote_via=quote so ~ is NOT encoded as %7E (would break signatures)
    return urlencode(
        {k: params[k] for k in ("URLPrefix", "Expires", "KeyName", "Signature")},
        quote_via=quote
    )


def pw_hls_url(vid: str, res: int, params: dict) -> str:
    return f"https://sec-prod-mediacdn.pw.live/{vid}/hls/{res}/main.m3u8?{signed_qs(params)}"


def check_hls(vid: str, res: int, params: dict) -> bool:
    try:
        fetch_pw(pw_hls_url(vid, res, params))
        return True
    except Exception:
        return False


def check_dash(vid: str, res: int, params: dict) -> bool:
    try:
        fetch_pw(f"https://sec-prod-mediacdn.pw.live/{vid}/dash/{res}/init.mp4?{signed_qs(params)}")
        return True
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# HLS mode (AES-128) — proxy + yt-dlp
# ═══════════════════════════════════════════════════════════════════════════════

class State:
    video_id   = ""
    params     = {}
    resolution = 720


class ProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): pass

    def _send(self, data: bytes, ctype="application/octet-stream", status=200):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?")[0]

        if path == "/m3u8":
            try:
                url  = pw_hls_url(State.video_id, State.resolution, State.params)
                raw  = fetch_pw(url).decode()
                self._send(self._rewrite_m3u8(raw).encode(), ctype="application/vnd.apple.mpegurl")
                print(f"    [proxy] Served m3u8")
            except Exception as e:
                print(f"    [proxy] m3u8 error: {e}")
                self._send(b"error", status=500)

        elif path.startswith("/key/"):
            real_url = urllib.parse.unquote(path[5:])
            try:
                data = fetch_pw(real_url)
                self._send(data)
                print(f"    [proxy] Served enc.key ({len(data)} bytes)")
            except Exception as e:
                print(f"    [proxy] key error: {e}")
                self._send(b"", status=500)

        elif path.startswith("/seg/"):
            real_url = urllib.parse.unquote(path[5:])
            try:
                data = fetch_pw(real_url)
                self._send(data, ctype="video/MP2T")
                print(f"    [proxy] Segment {len(data)//1024}KB")
            except Exception as e:
                print(f"    [proxy] segment error: {e}")
                self._send(b"", status=500)
        else:
            self._send(b"not found", status=404)

    def _rewrite_m3u8(self, content: str) -> str:
        lines = content.splitlines()
        out   = []
        qs    = signed_qs(State.params)
        cdn_key_url = f"https://sec-prod-mediacdn.pw.live/{State.video_id}/hls/enc.key?{qs}"

        for line in lines:
            if line.startswith("#EXT-X-KEY"):
                def replace_key_uri(m):
                    raw_uri = m.group(1)
                    if "api.penpencil.co" in raw_uri or "get-hls-key" in raw_uri:
                        raw_uri = cdn_key_url
                    elif "?" not in raw_uri:
                        raw_uri += "?" + qs
                    encoded = urllib.parse.quote(raw_uri, safe="")
                    return f'URI="http://127.0.0.1:{PROXY_PORT}/key/{encoded}"'
                line = re.sub(r'URI="([^"]+)"', replace_key_uri, line)
                out.append(line)
            elif line.startswith("https://") and ".ts" in line:
                seg_url = line.strip()
                if "URLPrefix=" not in seg_url:
                    sep = "&" if "?" in seg_url else "?"
                    seg_url += sep + qs
                encoded = urllib.parse.quote(seg_url, safe="")
                out.append(f"http://127.0.0.1:{PROXY_PORT}/seg/{encoded}")
            elif line.endswith(".ts") and not line.startswith("#"):
                base = f"https://sec-prod-mediacdn.pw.live/{State.video_id}/hls/{State.resolution}/"
                seg_url = base + line.strip() + "?" + qs
                encoded = urllib.parse.quote(seg_url, safe="")
                out.append(f"http://127.0.0.1:{PROXY_PORT}/seg/{encoded}")
            else:
                out.append(line)
        return "\n".join(out)


def start_proxy():
    server = HTTPServer(("127.0.0.1", PROXY_PORT), ProxyHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"  [+] Local proxy started on http://127.0.0.1:{PROXY_PORT}")
    return server


def download_hls(output_name: str, output_dir: str, stop_event=None, pause_event=None, progress_callback=None, log_callback=None):
    safe = re.sub(r'[^\w\s-]', '', output_name).strip().replace(' ', '_')
    out  = get_unique_filepath(output_dir, safe, ".mp4")

    print(f"\n  [+] Downloading (HLS mode) → {out}")
    print(f"  [+] Resolution : {State.resolution}p\n")

    cmd = [
        get_resource_path("yt-dlp"),
        f"http://127.0.0.1:{PROXY_PORT}/m3u8",
        "-o", out,
        "--hls-use-mpegts",
        "--merge-output-format", "mp4",
        "--no-check-certificate",
        "--newline", "--progress",
        "--concurrent-fragments", "4",
        "--retries", "infinite",
        "--fragment-retries", "infinite",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1, **_popen_kwargs())
    for line in iter(proc.stdout.readline, ''):
        ls = line.rstrip()
        if ls: print(ls)
        if stop_event and stop_event.is_set():
            proc.terminate(); raise RuntimeError("Stopped by user.")
        if progress_callback:
            m = re.search(r'\[download\]\s+([\d.]+)%.*?at\s+(\S+)\s+ETA\s+(\S+)', ls)
            if m:
                progress_callback({'percent': float(m.group(1)), 'speed': m.group(2), 'eta': m.group(3), 'status': 'downloading'})
    proc.wait()
    if proc.returncode == 0:
        print(f"\n✅ Download complete: {out}")
    else:
        raise RuntimeError(f"yt-dlp failed with exit code {proc.returncode}")


# ═══════════════════════════════════════════════════════════════════════════════
# DASH mode (ClearKey CENC) — direct segment download + ffmpeg decryption
# ═══════════════════════════════════════════════════════════════════════════════

def get_enc_key(vid: str, params: dict) -> str:
    """Fetch the AES decryption key from PW CDN enc.key endpoint."""
    key_bytes = fetch_pw(f"https://sec-prod-mediacdn.pw.live/{vid}/hls/enc.key?{signed_qs(params)}")
    return key_bytes.hex()


def _count_segments_in_timeline(adaptation_el) -> int:
    """Count total segments in a SegmentTimeline, accounting for r (repeat) attributes.
    Each <S d="..." r="N"/> means N+1 segments (r=0 or absent means 1 segment).
    """
    total = 0
    for seg_tl in adaptation_el.iter('SegmentTimeline'):
        for s in seg_tl.iter('S'):
            r = int(s.get('r', 0))
            total += r + 1
    return total


def count_dash_segments(vid: str, params: dict) -> tuple:
    """Parse the MPD to count segments per track. Returns (n_video, n_audio).
    Falls back to simple <S> tag counting / 2 if parsing fails.
    """
    import xml.etree.ElementTree as ET
    mpd_url = f"https://sec-prod-mediacdn.pw.live/{vid}/master.mpd?{signed_qs(params)}"
    content = fetch_pw(mpd_url).decode()
    # Strip namespaces for easier parsing
    content_ns = re.sub(r'\s+xmlns(?::\w+)?="[^"]*"', '', content)
    content_ns = re.sub(r'\s+\w+:\w+="[^"]*"', '', content_ns)
    content_ns = re.sub(r'<(/?)(\w+):(\w+)', r'<\1\3', content_ns)
    try:
        root = ET.fromstring(content_ns)
    except ET.ParseError:
        # Fallback: simple count
        s_tags = re.findall(r'<S\s', content)
        n = len(s_tags) // 2
        return (n, n)

    n_video = 0
    n_audio = 0
    for adapt in root.iter('AdaptationSet'):
        mime = adapt.get('mimeType', '') or adapt.get('contentType', '')
        reps = list(adapt.iter('Representation'))
        first_mime = mime or (reps[0].get('mimeType', '') if reps else '')
        count = _count_segments_in_timeline(adapt)
        # Also check SegmentTimeline inside Representation
        if count == 0 and reps:
            count = _count_segments_in_timeline(reps[0])
        if 'video' in first_mime:
            n_video = max(n_video, count)
        elif 'audio' in first_mime:
            n_audio = max(n_audio, count)
    # If we couldn't determine one, fall back to the other
    if n_video == 0 and n_audio == 0:
        s_tags = re.findall(r'<S\s', content)
        n = len(s_tags) // 2
        return (n, n)
    if n_video == 0:
        n_video = n_audio
    if n_audio == 0:
        n_audio = n_video
    return (n_video, n_audio)


def download_dash(vid: str, params: dict, resolution: int, output_name: str, output_dir: str,
                  stop_event=None, pause_event=None, progress_callback=None, log_callback=None):
    safe = re.sub(r'[^\w\s-]', '', output_name).strip().replace(' ', '_')
    out  = get_unique_filepath(output_dir, safe, ".mp4")
    qs   = signed_qs(params)

    if log_callback: log_callback(f"\n  [+] Fetching encryption key...", "info")
    else: print(f"\n  [+] Fetching encryption key...")
    try:
        key_hex = get_enc_key(vid, params)
        if log_callback: log_callback(f"  [+] Key: {key_hex}", "info")
        else: print(f"  [+] Key: {key_hex}")
    except Exception as e:
        raise RuntimeError(f"Could not get encryption key: {e}")

    print(f"  [+] Counting segments from MPD...")
    try:
        n_v_segs, n_a_segs = count_dash_segments(vid, params)
        print(f"  [+] Segments: {n_v_segs} video, {n_a_segs} audio")
    except Exception:
        n_v_segs = n_a_segs = None
        print("  [!] Could not count segments from MPD — will stop on first 404")

    tmpdir = tempfile.mkdtemp(prefix="pw_dash_", dir=output_dir)
    print(f"  [+] Temp dir: {tmpdir}")

    # ── Segment downloader (with retry + internet-wait) ────────────────────────
    session = requests.Session()
    session.headers.update(PW_HEADERS)

    def dl_segment(url: str, path: str, is_video=True):
        """Download one segment with retry. Raises HTTPError on 403/404/410."""
        import socket as _socket
        while True:
            # Early break if the other thread already hit the end of stream
            if (is_video and _v_stop[0]) or (not is_video and _a_stop[0]):
                raise urllib.error.HTTPError(url, 404, "Stream ended", {}, None)

            while True:  # wait for internet
                try:
                    _socket.setdefaulttimeout(3)
                    _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM).connect(("8.8.8.8", 53))
                    break
                except OSError:
                    if stop_event and stop_event.is_set(): raise
                    time.sleep(2)

            try:
                r = session.get(url, stream=True, timeout=10)
                r.raise_for_status()

                with open(path, "wb") as f:
                    for chunk in r.iter_content(65536):
                        if chunk:
                            f.write(chunk)
                return  # success
            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code if e.response is not None else 500
                if status_code in [403, 404, 410]:
                    raise urllib.error.HTTPError(url, status_code, "HTTP Error", {}, None)
                if stop_event and stop_event.is_set():
                    raise
                time.sleep(1)
            except urllib.error.HTTPError as e:
                if e.code in [403, 404, 410]:
                    raise
                if stop_event and stop_event.is_set():
                    raise
                time.sleep(1)
            except Exception:
                if stop_event and stop_event.is_set(): raise
                time.sleep(1)

    try:
        # ── Phase 0: download init segments concurrently ──────────────────────
        print(f"\n  [+] Downloading init segments (video {resolution}p + audio)...")
        init_vid_path = os.path.join(tmpdir, "v_init.mp4")
        init_aud_path = os.path.join(tmpdir, "a_init.mp4")

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as _ie:
            _fv = _ie.submit(dl_segment,
                             f"https://sec-prod-mediacdn.pw.live/{vid}/dash/{resolution}/init.mp4?{qs}",
                             init_vid_path, is_video=True)
            _fa = _ie.submit(dl_segment,
                             f"https://sec-prod-mediacdn.pw.live/{vid}/dash/audio/init.mp4?{qs}",
                             init_aud_path, is_video=False)
            _fv.result()  # propagate exceptions
            _fa.result()

        # ── Phase 1: parallel interleaved segment downloads ────────────────────
        # Determine how many segments exist. If unknown, probe until 404.
        # We submit video segments as tasks V_1..V_N and audio as A_1..A_N.
        # Workers download them all concurrently so the CDN URL doesn't expire.

        MAX_WORKERS = min(48, (os.cpu_count() or 4) * 4)
        print(f"  [+] Downloading segments in parallel ({MAX_WORKERS} workers)...")

        # Shared progress tracking
        _lock          = threading.Lock()
        _v_done        = [0]      # mutable counter (video segs completed)
        _a_done        = [0]      # mutable counter (audio segs completed)
        _total_bytes   = [os.path.getsize(init_vid_path) + os.path.getsize(init_aud_path)]
        _start         = time.time()
        _v_stop        = [False]   # set when video hits 404/403 (end-of-video-stream)
        _a_stop        = [False]   # set when audio hits 404/403 (end-of-audio-stream)

        def _progress_report():
            """Print and call progress_callback based on current state."""
            with _lock:
                v = _v_done[0];  a = _a_done[0]
                tb = _total_bytes[0]
            elapsed = time.time() - _start
            if elapsed > 0:
                spd = tb / elapsed
                speed_str = (f"{spd/(1024*1024):.2f}MiB/s" if spd > 1024*1024
                             else f"{spd/1024:.2f}KiB/s")
            else:
                speed_str = "—"
            # Separate video and audio percentages
            v_pct_f = min(v / n_v_segs * 100, 99.9) if n_v_segs else 0.0
            a_pct_f = min(a / n_a_segs * 100, 100.0) if n_a_segs else 0.0
            if n_v_segs and n_a_segs:
                done_segs  = v + a
                total_segs = n_v_segs + n_a_segs
                pct_f      = min(done_segs / total_segs * 100, 99.9)
                remaining  = max(total_segs - done_segs, 0)
                rate       = done_segs / elapsed if elapsed > 0 else 0
                eta_sec    = int(remaining / rate) if rate > 0 else 0
                eta_str    = (f"{eta_sec//3600:02d}:{(eta_sec%3600)//60:02d}:{eta_sec%60:02d}"
                              if eta_sec >= 3600 else f"{eta_sec//60:02d}:{eta_sec%60:02d}")
                pct_label  = f"{pct_f:.1f}%"
            else:
                pct_f, pct_label, eta_str = 0.0, f"V:{v} A:{a}", "—"
            print(f"    [parallel] {pct_label}  V:{v}/{n_v_segs or '?'}  A:{a}/{n_a_segs or '?'}"
                  f"  at {speed_str}  ETA {eta_str}", end='\r', flush=True)
            if progress_callback:
                progress_callback({'percent': pct_f, 'v_pct': v_pct_f, 'a_pct': a_pct_f,
                                   'speed': speed_str, 'eta': eta_str, 'status': 'downloading'})

        def _dl_video_seg(n: int) -> str | None:
            """Download video segment n; returns path on success, None on end-of-stream."""
            if stop_event and stop_event.is_set():
                return None
            if _v_stop[0]:
                return None
            
            # User observation workaround: if audio is 100% complete based on exact counts,
            # it means the video stream has also ended even if n_v_segs was overestimated.
            with _lock:
                a_finished = (n_a_segs and _a_done[0] >= n_a_segs)
            if a_finished:
                _v_stop[0] = True
                return None
                
            while pause_event and pause_event.is_set():
                time.sleep(0.1) # Busy-wait for pause to end
            url  = f"https://sec-prod-mediacdn.pw.live/{vid}/dash/{resolution}/{n}.mp4?{qs}"
            path = os.path.join(tmpdir, f"v_{n:05d}.mp4")
            try:
                dl_segment(url, path, is_video=True)
                with _lock:
                    _v_done[0] += 1
                    if os.path.exists(path):
                        _total_bytes[0] += os.path.getsize(path)
                _progress_report()
                return path
            except urllib.error.HTTPError as e:
                if e.code in (403, 404, 410):  # true end-of-stream
                    _v_stop[0] = True
                # transient — return None but don't kill whole stream
                return None
            except Exception:
                return None  # network hiccup — don't kill stream

        def _dl_audio_seg(n: int) -> str | None:
            """Download audio segment n; returns path on success, None on end-of-stream."""
            if stop_event and stop_event.is_set():
                return None
            if _a_stop[0]:
                return None
            while pause_event and pause_event.is_set():
                time.sleep(0.1) # Busy-wait for pause to end
            url  = f"https://sec-prod-mediacdn.pw.live/{vid}/dash/audio/{n}.mp4?{qs}"
            path = os.path.join(tmpdir, f"a_{n:05d}.mp4")
            try:
                dl_segment(url, path, is_video=False)
                with _lock:
                    _a_done[0] += 1
                    if os.path.exists(path):
                        _total_bytes[0] += os.path.getsize(path)
                _progress_report()
                # User observation workaround: if audio hits its final expected count, 
                # kill the video loop too as it's likely overestimating.
                if n_a_segs and _a_done[0] >= n_a_segs:
                    _v_stop[0] = True
                    
                return path
            except urllib.error.HTTPError as e:
                if e.code in (404, 410):  # true end-of-stream
                    _a_stop[0] = True
                return None
            except Exception:
                return None  # network hiccup — don't kill stream


        # Submit tasks: V1, A1, V2, A2, ...
        # Video and audio may have DIFFERENT segment counts (audio is typically more).
        max_probe_v = n_v_segs if n_v_segs else 9999
        max_probe_a = n_a_segs if n_a_segs else 9999
        max_probe   = max(max_probe_v, max_probe_a)

        vid_results = {}   # seg_num → path or None
        aud_results = {}   # seg_num → path or None

        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futures_v = {}
            futures_a = {}
            for n in range(1, max_probe + 1):
                if n <= max_probe_v:
                    futures_v[ex.submit(_dl_video_seg, n)] = n
                if n <= max_probe_a:
                    futures_a[ex.submit(_dl_audio_seg, n)] = n

            all_futs = {**futures_v, **futures_a}
            while all_futs:
                if stop_event and stop_event.is_set():
                    ex.shutdown(wait=False, cancel_futures=True)
                    raise RuntimeError("Stopped by user.")
                
                # Check if we should definitively break the loop due to both streams stopping
                a_done_status = _a_stop[0] or (n_a_segs and _a_done[0] >= n_a_segs)
                v_done_status = _v_stop[0] or (n_v_segs and _v_done[0] >= n_v_segs)
                if a_done_status and v_done_status:
                    # Cancel any eternally hung connections instantly
                    ex.shutdown(wait=False, cancel_futures=True)
                    break

                done, not_done = concurrent.futures.wait(
                    all_futs, timeout=1.0, return_when=concurrent.futures.FIRST_COMPLETED
                )
                for fut in done:
                    all_futs.pop(fut, None)

            # Collect results in order, safely handling forcefully cancelled futures
            for fut, n in futures_v.items():
                try:
                    vid_results[n] = fut.result(timeout=0)
                except Exception:
                    vid_results[n] = None
            for fut, n in futures_a.items():
                try:
                    aud_results[n] = fut.result(timeout=0)
                except Exception:
                    aud_results[n] = None


        # Final 100% progress
        print()  # newline after \r progress
        if progress_callback:
            progress_callback({'percent': 100, 'v_pct': 100, 'a_pct': 100,
                               'speed': '—', 'eta': '0:00', 'status': 'done'})

        # Collect ordered file lists (stop at first None / missing)
        vid_files = [init_vid_path]
        missing_v = []
        for n in range(1, max_probe_v + 1):
            p = vid_results.get(n)
            if not p:
                if not _v_stop[0]:  # not a clean EOF — warn about gap
                    missing_v.append(n)
                break
            vid_files.append(p)

        aud_files = [init_aud_path]
        missing_a = []
        for n in range(1, max_probe_a + 1):
            p = aud_results.get(n)
            if not p:
                if not _a_stop[0]:
                    missing_a.append(n)
                break
            aud_files.append(p)

        actual_v = len(vid_files) - 1
        actual_a = len(aud_files) - 1
        est_v = n_v_segs or '?'
        est_a = n_a_segs or '?'
        print(f"  [+] Downloaded {actual_v}/{est_v} video + {actual_a}/{est_a} audio segments")
        if missing_v:
            print(f"  [!] WARNING: Video gaps at segments {missing_v[:5]} (possible failed fetch)")
        if missing_a:
            print(f"  [!] WARNING: Audio gaps at segments {missing_a[:5]} (possible failed fetch)")

        # ── Concatenate ───────────────────────────────────────────
        print(f"  [+] Concatenating segments...")
        enc_vid = os.path.join(tmpdir, "enc_video.mp4")
        with open(enc_vid, 'wb') as out_f:
            for fp in vid_files:
                with open(fp, 'rb') as f: out_f.write(f.read())

        enc_aud = os.path.join(tmpdir, "enc_audio.mp4")
        with open(enc_aud, 'wb') as out_f:
            for fp in aud_files:
                with open(fp, 'rb') as f: out_f.write(f.read())

        # ── Decrypt video and audio ───────────────────────────────
        print(f"  [+] Decrypting with ffmpeg (key={key_hex})...")
        dec_vid = os.path.join(tmpdir, "dec_video.mp4")
        dec_aud = os.path.join(tmpdir, "dec_audio.mp4")

        ffmpeg_bin = get_resource_path("ffmpeg")
        for enc, dec, label in [(enc_vid, dec_vid, "video"), (enc_aud, dec_aud, "audio")]:
            r = subprocess.run(
                [ffmpeg_bin, "-y", "-decryption_key", key_hex, "-i", enc, "-c", "copy", dec],
                capture_output=True, **_popen_kwargs()
            )
            if r.returncode != 0:
                raise RuntimeError(
                    f"ffmpeg decryption failed for {label}:\n{r.stderr.decode()[-500:]}"
                )
            print(f"  [+] {label} decrypted ✓")

        # ── Mux video + audio → final mp4 ────────────────────────
        print(f"  [+] Muxing video + audio → {out}")
        r = subprocess.run([
            ffmpeg_bin, "-y",
            "-i", dec_vid,
            "-i", dec_aud,
            "-c", "copy",
            "-movflags", "+faststart",
            out
        ], capture_output=True, **_popen_kwargs())
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg mux failed:\n{r.stderr.decode()[-500:]}")

        print(f"\n✅ Download complete: {out}")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════════
# CloudFront DASH download  (yt-dlp primary → manual segment fallback)
# ═══════════════════════════════════════════════════════════════════════════════

def _cloudfront_manual_dash(url: str, output_name: str, output_dir: str, resolution: int,
                             sniff_headers: dict = None, stop_event=None, pause_event=None, progress_callback=None,
                             log_callback=None):
    """
    Manual CloudFront DASH segment downloader.
    Fetches the MPD, parses video/audio AdaptationSets, picks the closest
    resolution, downloads init + numbered segments, decrypts with ffmpeg,
    then muxes to mp4.  Mirrors the sec-prod DASH flow.
    """
    import xml.etree.ElementTree as ET

    safe = re.sub(r'[^\w\s-]', '', output_name).strip().replace(' ', '_')
    out  = get_unique_filepath(output_dir, safe, ".mp4")
    base = cloudfront_base(url)          # e.g. https://xxx.cloudfront.net/<uuid>
    # Extract signed query params from the master.mpd URL so we can append
    # them to all segment/key URLs (CloudFront requires them on every request)
    signed_qs_str = urlparse(url).query  # Signature=...&Key-Pair-Id=...&Policy=...

    # ── Fetch MPD ────────────────────────────────────────────────
    print(f"  [+] Fetching MPD manifest...")
    mpd_raw = fetch_pw(normalize_mpd_url(url), extra_headers=sniff_headers).decode(errors='replace')

    # Strip ALL XML namespaces so ElementTree works without prefixes.
    # Step 1: remove xmlns declarations (default and prefixed), e.g. xmlns="..." xmlns:xsi="..."
    mpd_raw_ns = re.sub(r'\s+xmlns(?::\w+)?="[^"]*"', '', mpd_raw)
    # Step 2: remove namespace-prefixed attributes, e.g. xsi:schemaLocation="..."
    mpd_raw_ns = re.sub(r'\s+\w+:\w+="[^"]*"', '', mpd_raw_ns)
    # Step 3: remove namespace prefix from element tags, e.g. <mpd:MPD ...> → <MPD ...>
    mpd_raw_ns = re.sub(r'<(/?)(\w+):(\w+)', r'<\1\3', mpd_raw_ns)
    try:
        root = ET.fromstring(mpd_raw_ns)
    except ET.ParseError as e:
        print(f"❌ Could not parse MPD: {e}")
        print(f"  [!] MPD content (first 500 chars):\n{mpd_raw_ns[:500]}")
        sys.exit(1)

    # ── Collect AdaptationSets ────────────────────────────────────
    # Find video reps sorted by height, pick closest to desired resolution
    video_rep = None
    audio_rep = None
    video_base_url = None
    audio_base_url = None

    for adapt in root.iter('AdaptationSet'):
        mime = adapt.get('mimeType', '') or adapt.get('contentType', '')
        # Some MPDs put mimeType on Representation instead
        reps = list(adapt.iter('Representation'))
        if not reps:
            continue
        first_mime = mime or reps[0].get('mimeType', '')

        if 'video' in first_mime:
            # Pick rep whose height is <= desired, or smallest available
            best = None
            best_h = 0
            for r in reps:
                h = int(r.get('height', 0) or 0)
                if h <= resolution and h >= best_h:
                    best_h = h
                    best   = r
            if best is None:          # all reps taller than desired → pick smallest
                best = min(reps, key=lambda r: int(r.get('height', 9999) or 9999))
            video_rep = best
            # BaseURL for this rep (relative or absolute)
            burl_el = best.find('BaseURL') or adapt.find('BaseURL') or root.find('BaseURL')
            video_base_url = (burl_el.text.strip() if burl_el is not None else None)

        elif 'audio' in first_mime:
            audio_rep = reps[0]
            burl_el = reps[0].find('BaseURL') or adapt.find('BaseURL')
            audio_base_url = (burl_el.text.strip() if burl_el is not None else None)

    if video_rep is None:
        print("❌ Could not find a video stream in the MPD.")
        sys.exit(1)

    chosen_h = video_rep.get('height', '?')
    print(f"  [+] Video stream chosen: {chosen_h}p")

    # ── Build segment URL factories ───────────────────────────────
    def _append_qs(u: str) -> str:
        """Append CloudFront signed query params to a segment URL."""
        if not signed_qs_str:
            return u
        sep = '&' if '?' in u else '?'
        return u + sep + signed_qs_str

    # Try SegmentTemplate approach first (most common in PW CloudFront MPDs)
    def seg_url(rep, adapt, kind, seg_num=None, init=False):
        """Return URL for init or a numbered segment."""
        # Try SegmentTemplate on rep, then on adapt (use 'is not None' to avoid DeprecationWarning)
        tmpl = rep.find('SegmentTemplate')
        if tmpl is None:
            tmpl = adapt.find('SegmentTemplate')
        if tmpl is not None:
            rid = rep.get('id', '')
            bw  = rep.get('bandwidth', '')
            if init:
                tpl = tmpl.get('initialization', '')
            else:
                tpl = tmpl.get('media', '')
            if tpl:
                tpl = tpl.replace('$RepresentationID$', rid)
                tpl = tpl.replace('$Bandwidth$', bw)
                if not init:
                    tpl = tpl.replace('$Number$', str(seg_num))
                # Resolve against base, then append signed QS
                raw = tpl if tpl.startswith('http') else f"{base}/{tpl.lstrip('/')}"
                return _append_qs(raw)
        # Fall back: path-style (sec-prod style)
        if kind == 'video':
            h = rep.get('height', resolution)
            raw = (f"{base}/dash/{h}/init.mp4" if init
                   else f"{base}/dash/{h}/{seg_num}.mp4")
        else:
            raw = (f"{base}/dash/audio/init.mp4" if init
                   else f"{base}/dash/audio/{seg_num}.mp4")
        return _append_qs(raw)

    # Adapt parent node for SegmentTemplate lookup
    def get_adapt(rep, root):
        for a in root.iter('AdaptationSet'):
            if rep in list(a.iter('Representation')):
                return a
        return root

    v_adapt = get_adapt(video_rep, root)
    a_adapt = get_adapt(audio_rep, root) if audio_rep is not None else root

    # ── Count segments per track from MPD ────────────────────────────
    n_v_segs = _count_segments_in_timeline(v_adapt)
    n_a_segs = _count_segments_in_timeline(a_adapt) if audio_rep is not None else 0
    # Fallback if per-adapt counting failed
    if n_v_segs == 0:
        s_tags = root.findall('.//{*}S')
        n_v_segs = len(s_tags) // 2 if len(s_tags) > 1 else 0
    if n_a_segs == 0 and audio_rep is not None:
        n_a_segs = n_v_segs
    if n_v_segs:
        print(f"  [+] Estimated segments: {n_v_segs} video, {n_a_segs} audio")
    else:
        print("  [!] Segment count unknown — will stop on first 404")
        n_v_segs = None
        n_a_segs = None

    # ── Fetch encryption key ──────────────────────────────────────
    print(f"  [+] Fetching encryption key...")
    key_hex = None
    try:
        # Append signed QS to enc.key URL too — CloudFront requires it
        key_url = _append_qs(f"{base}/hls/enc.key")
        key_bytes = fetch_pw(key_url, extra_headers=sniff_headers)
        key_hex = key_bytes.hex()
        print(f"  [+] Key: {key_hex}")
    except Exception as e:
        print(f"  [!] Could not fetch enc.key — will try unencrypted: {e}")

    tmpdir = tempfile.mkdtemp(prefix="pw_cf_dash_", dir=output_dir)
    print(f"  [+] Temp dir: {tmpdir}")

    session = requests.Session()

    def dl_segment(url_: str, path: str):
        """Download one segment with retry. Raises HTTPError on 403/404/410."""
        import socket as _socket
        merged = {**PW_HEADERS, **(sniff_headers or {})}
        while True:
            while True:  # wait for internet
                try:
                    _socket.setdefaulttimeout(3)
                    _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM).connect(("8.8.8.8", 53))
                    break
                except OSError:
                    print(f"    [!] network issue, waiting...", end='\r')
                    time.sleep(5)
            try:
                r = session.get(url_, headers=merged, stream=True, timeout=60)
                r.raise_for_status()

                with open(path, "wb") as f:
                    for chunk in r.iter_content(65536):
                        if chunk:
                            f.write(chunk)
                return  # success
            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code if e.response is not None else 500
                if status_code in [403, 404, 410]:
                    raise urllib.error.HTTPError(url_, status_code, "HTTP Error", {}, None)
                print(f"    [!] HTTP {status_code}, retrying...", end='\r')
                time.sleep(3)
            except urllib.error.HTTPError as e:
                if e.code in [403, 404, 410]:
                    raise
                print(f"    [!] HTTP {e.code}, retrying...", end='\r')
                time.sleep(3)
            except Exception:
                print(f"    [!] connection error, retrying...", end='\r')
                time.sleep(3)

    try:
        # ── Phase 0: download init segments concurrently ─────────────────────
        print(f"\n  [+] Downloading init segments (video {chosen_h}p + audio)...")
        init_vid_path = os.path.join(tmpdir, 'v_init.mp4')
        init_aud_path = os.path.join(tmpdir, 'a_init.mp4') if audio_rep is not None else None

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as _ie:
            _fv = _ie.submit(dl_segment,
                             seg_url(video_rep, v_adapt, 'video', init=True),
                             init_vid_path)
            if audio_rep is not None:
                _fa = _ie.submit(dl_segment,
                                 seg_url(audio_rep, a_adapt, 'audio', init=True),
                                 init_aud_path)
            _fv.result()
            if audio_rep is not None:
                _fa.result()

        # ── Phase 1: parallel interleaved segment downloads ──────────────────
        MAX_WORKERS = min(48, (os.cpu_count() or 4) * 4)
        print(f"  [+] Downloading segments in parallel ({MAX_WORKERS} workers)...")

        _lock        = threading.Lock()
        _v_done      = [0]
        _a_done      = [0]
        init_bytes   = os.path.getsize(init_vid_path)
        if init_aud_path and os.path.exists(init_aud_path):
            init_bytes += os.path.getsize(init_aud_path)
        _total_bytes = [init_bytes]
        _start       = time.time()
        _v_stop      = [False]   # set when video hits 404 (end-of-video-stream)
        _a_stop      = [False]   # set when audio hits 404 (end-of-audio-stream)

        def _progress_report():
            with _lock:
                v = _v_done[0]; a = _a_done[0]; tb = _total_bytes[0]
            elapsed = time.time() - _start
            if elapsed > 0:
                spd = tb / elapsed
                speed_str = (f"{spd/(1024*1024):.2f}MiB/s" if spd > 1024*1024
                             else f"{spd/1024:.2f}KiB/s")
            else:
                speed_str = "—"
            # Separate video and audio percentages
            v_pct_f = min(v / n_v_segs * 100, 99.9) if n_v_segs else 0.0
            a_pct_f = min(a / n_a_segs * 100, 100.0) if n_a_segs else 0.0
            if n_v_segs and n_a_segs:
                done_segs  = v + a
                total_segs = n_v_segs + n_a_segs
                pct_f      = min(done_segs / total_segs * 100, 99.9)
                remaining  = max(total_segs - done_segs, 0)
                rate       = done_segs / elapsed if elapsed > 0 else 0
                eta_sec    = int(remaining / rate) if rate > 0 else 0
                eta_str    = (f"{eta_sec//3600:02d}:{(eta_sec%3600)//60:02d}:{eta_sec%60:02d}"
                              if eta_sec >= 3600 else f"{eta_sec//60:02d}:{eta_sec%60:02d}")
                pct_label  = f"{pct_f:.1f}%"
            elif n_v_segs:
                done_segs  = v
                pct_f      = min(done_segs / n_v_segs * 100, 99.9)
                remaining  = max(n_v_segs - done_segs, 0)
                rate       = done_segs / elapsed if elapsed > 0 else 0
                eta_sec    = int(remaining / rate) if rate > 0 else 0
                eta_str    = (f"{eta_sec//3600:02d}:{(eta_sec%3600)//60:02d}:{eta_sec%60:02d}"
                              if eta_sec >= 3600 else f"{eta_sec//60:02d}:{eta_sec%60:02d}")
                pct_label  = f"{pct_f:.1f}%"
            else:
                pct_f, pct_label, eta_str = 0.0, f"V:{v} A:{a}", "—"
            print(f"    [parallel] {pct_label}  V:{v}/{n_v_segs or '?'}  A:{a}/{n_a_segs or '?'}"
                  f"  at {speed_str}  ETA {eta_str}", end='\r', flush=True)
            if progress_callback:
                progress_callback({'percent': pct_f, 'v_pct': v_pct_f, 'a_pct': a_pct_f,
                                   'speed': speed_str, 'eta': eta_str, 'status': 'downloading'})

        def _dl_video_seg(n: int):
            if stop_event and stop_event.is_set(): return None
            if _v_stop[0]: return None
            while pause_event and pause_event.is_set():
                time.sleep(0.1) # Busy-wait for pause to end
            sp = os.path.join(tmpdir, f'v_{n:05d}.mp4')
            try:
                dl_segment(seg_url(video_rep, v_adapt, 'video', seg_num=n), sp)
                with _lock:
                    _v_done[0] += 1
                    if os.path.exists(sp): _total_bytes[0] += os.path.getsize(sp)
                _progress_report()
                return sp
            except urllib.error.HTTPError as e:
                if e.code in (404, 410):  # true end-of-stream
                    _v_stop[0] = True
                return None  # transient 403/5xx → don't kill stream
            except Exception:
                return None  # network hiccup → don't kill stream

        def _dl_audio_seg(n: int):
            if stop_event and stop_event.is_set(): return None
            if _a_stop[0]: return None
            while pause_event and pause_event.is_set():
                time.sleep(0.1) # Busy-wait for pause to end
            sp = os.path.join(tmpdir, f'a_{n:05d}.mp4')
            try:
                dl_segment(seg_url(audio_rep, a_adapt, 'audio', seg_num=n), sp)
                with _lock:
                    _a_done[0] += 1
                    if os.path.exists(sp): _total_bytes[0] += os.path.getsize(sp)
                _progress_report()
                return sp
            except urllib.error.HTTPError as e:
                if e.code in (404, 410):  # true end-of-stream
                    _a_stop[0] = True
                return None
            except Exception:
                return None


        # Submit tasks interleaved: V1, A1, V2, A2, ...
        # Video and audio may have DIFFERENT segment counts.
        max_probe_v = n_v_segs if n_v_segs else 9999
        max_probe_a = n_a_segs if n_a_segs else 9999
        max_probe   = max(max_probe_v, max_probe_a if audio_rep is not None else 0)
        vid_results = {}
        aud_results = {}

        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futures_v = {}
            futures_a = {}
            for n in range(1, max_probe + 1):
                if n <= max_probe_v:
                    futures_v[ex.submit(_dl_video_seg, n)] = n
                if audio_rep is not None and n <= max_probe_a:
                    futures_a[ex.submit(_dl_audio_seg, n)] = n

            all_futures = {**futures_v, **futures_a}
            for fut in concurrent.futures.as_completed(all_futures):
                if stop_event and stop_event.is_set():
                    ex.shutdown(wait=False, cancel_futures=True)
                    raise RuntimeError("Stopped by user.")
            for fut, n in futures_v.items():
                vid_results[n] = fut.result()
            for fut, n in futures_a.items():
                aud_results[n] = fut.result()


        # Final 100% progress
        print()  # newline after \r progress
        if progress_callback:
            progress_callback({'percent': 100, 'v_pct': 100, 'a_pct': 100,
                               'speed': '—', 'eta': '0:00', 'status': 'done'})

        vid_files = [init_vid_path]
        missing_v = []
        for n in range(1, max_probe_v + 1):
            p = vid_results.get(n)
            if not p:
                if not _v_stop[0]:  # not clean EOF — warn about gap
                    missing_v.append(n)
                break
            vid_files.append(p)

        if init_aud_path:
            aud_files = [init_aud_path]
            missing_a = []
            for n in range(1, max_probe_a + 1):
                p = aud_results.get(n)
                if not p:
                    if not _a_stop[0]:
                        missing_a.append(n)
                    break
                aud_files.append(p)
        else:
            aud_files = []
            missing_a = []

        actual_v = len(vid_files) - 1
        actual_a = len(aud_files) - 1
        est_v = n_v_segs or '?'
        est_a = n_a_segs or '?'
        print(f"  [+] Downloaded {actual_v}/{est_v} video + {actual_a}/{est_a} audio segments")
        if missing_v:
            print(f"  [!] WARNING: Video gaps at segments {missing_v[:5]} (possible failed fetch)")
        if missing_a:
            print(f"  [!] WARNING: Audio gaps at segments {missing_a[:5]} (possible failed fetch)")

        # ── Concatenate ───────────────────────────────────────────
        if log_callback: log_callback(f"\n  [+] Concatenating segments...", "info")
        else: print(f"\n  [+] Concatenating segments...")
        enc_vid = os.path.join(tmpdir, 'enc_video.mp4')
        with open(enc_vid, 'wb') as wf:
            for fp in vid_files:
                with open(fp, 'rb') as rf: wf.write(rf.read())

        if aud_files:
            enc_aud = os.path.join(tmpdir, 'enc_audio.mp4')
            with open(enc_aud, 'wb') as wf:
                for fp in aud_files:
                    with open(fp, 'rb') as rf: wf.write(rf.read())
        else:
            enc_aud = None

        # ── Decrypt (if key available) ────────────────────────────
        ffmpeg_bin = get_resource_path("ffmpeg")
        if key_hex:
            if log_callback: log_callback(f"  [+] Decrypting with ffmpeg (key={key_hex})...", "info")
            else: print(f"  [+] Decrypting with ffmpeg (key={key_hex})...")
            dec_vid = os.path.join(tmpdir, 'dec_video.mp4')
            r = subprocess.run(
                [ffmpeg_bin, '-y', '-decryption_key', key_hex, '-i', enc_vid, '-c', 'copy', dec_vid],
                capture_output=True, **_popen_kwargs()
            )
            if r.returncode != 0:
                raise RuntimeError(
                    f"ffmpeg video decryption failed:\n{r.stderr.decode()[-500:]}"
                )
            print("  [+] video decrypted ✓")

            if enc_aud:
                dec_aud = os.path.join(tmpdir, 'dec_audio.mp4')
                r = subprocess.run(
                    [ffmpeg_bin, '-y', '-decryption_key', key_hex, '-i', enc_aud, '-c', 'copy', dec_aud],
                    capture_output=True, **_popen_kwargs()
                )
                if r.returncode != 0:
                    raise RuntimeError(
                        f"ffmpeg audio decryption failed:\n{r.stderr.decode()[-500:]}"
                    )
                print("  [+] audio decrypted ✓")
            else:
                dec_aud = None
        else:
            # No encryption — use raw files
            dec_vid = enc_vid
            dec_aud = enc_aud

        # ── Mux ───────────────────────────────────────────────────
        if log_callback: log_callback(f"  [+] Muxing → {out}", "info")
        else: print(f"  [+] Muxing → {out}")
        if dec_aud:
            r = subprocess.run(
                [ffmpeg_bin, '-y', '-i', dec_vid, '-i', dec_aud,
                 '-c', 'copy', '-movflags', '+faststart', out],
                capture_output=True, **_popen_kwargs()
            )
        else:
            r = subprocess.run(
                [ffmpeg_bin, '-y', '-i', dec_vid, '-c', 'copy', '-movflags', '+faststart', out],
                capture_output=True, **_popen_kwargs()
            )
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg mux failed:\n{r.stderr.decode()[-500:]}")

        if log_callback: log_callback(f"✅ Download complete: {out}", "success")
        else: print(f"\n✅ Download complete: {out}")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

def download_cloudfront(url: str, output_name: str, output_dir: str, resolution: int,
                         sniff_headers: dict = None, stop_event=None, pause_event=None, progress_callback=None,
                         log_callback=None):
    """
    Download a CloudFront MPD link.
    sniff_headers: Cookie/Authorization captured by the sniffer (fixes 403).
    Strategy:
      1. Try yt-dlp directly (handles many DASH streams natively).
      2. If yt-dlp fails → fall back to manual MPD parse + segment download.
    """
    url = normalize_mpd_url(url)
    safe = re.sub(r'[^\w\s-]', '', output_name).strip().replace(' ', '_')
    out  = get_unique_filepath(output_dir, safe, ".mp4")

    print(f"\n  [+] CloudFront DASH URL detected")
    print(f"  [+] Output      : {out}")
    print(f"  [+] Resolution  : {resolution}p")
    if sniff_headers:
        print(f"  [+] Auth headers: {list(sniff_headers.keys())}")
    print(f"\n  [→] Trying yt-dlp first...\n")

    fmt = f"bestvideo[height<={resolution}]+bestaudio/bestvideo[height<={resolution}]/best[height<={resolution}]/best"

    yt_cmd = [
        get_resource_path('yt-dlp'), url,
        '-o', out,
        '--format', fmt,
        '--merge-output-format', 'mp4',
        '--no-check-certificate',
        '--progress',
        '--concurrent-fragments', '4',
        '--add-header', f'Referer:https://www.pw.live/',
        '--add-header', f'Origin:https://www.pw.live',
        '--add-header', f"User-Agent:{PW_HEADERS['User-Agent']}",
        '--retries', 'infinite',
        '--fragment-retries', 'infinite',
    ]
    # Inject sniffed headers into yt-dlp
    for hname, hval in (sniff_headers or {}).items():
        yt_cmd += ['--add-header', f'{hname}:{hval}']

    # Use Popen to stream output and parse progress
    proc = subprocess.Popen(yt_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1, **_popen_kwargs())
    for line in iter(proc.stdout.readline, ''):
        ls = line.rstrip()
        if ls: print(ls)
        if stop_event and stop_event.is_set():
            proc.terminate(); raise RuntimeError("Stopped by user.")
        if pause_event and pause_event.is_set():
            while pause_event.is_set():
                time.sleep(0.1) # Busy-wait for pause to end
        if progress_callback:
            m = re.search(r'\[download\]\s+([\d.]+)%.*?at\s+(\S+)\s+ETA\s+(\S+)', ls)
            if m:
                progress_callback({'percent': float(m.group(1)), 'speed': m.group(2), 'eta': m.group(3), 'status': 'downloading'})
    proc.wait()


    if proc.returncode == 0:
        print(f"\n✅ Download complete: {out}")
        return

    if log_callback: log_callback(f"  [!] yt-dlp failed (exit {proc.returncode}) — falling back to manual DASH...", "warning")
    else: print(f"\n  [!] yt-dlp failed (exit {proc.returncode}) — falling back to manual DASH downloader...")

    _cloudfront_manual_dash(url, output_name, output_dir, resolution, sniff_headers=sniff_headers,
                             stop_event=stop_event, pause_event=pause_event, progress_callback=progress_callback,
                             log_callback=log_callback)


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════════
# Public API  —  called by the GUI
# ═══════════════════════════════════════════════════════════════════════════════

def download_video(url: str, output_name: str, resolution: str, output_dir: str,
                   stop_event=None, pause_event=None, progress_callback=None, log_callback=None) -> bool:
    """
    Public entry point used by the GUI.

    Parameters
    ----------
    url          : raw line from links.txt (may contain ||HEADERS|| suffix)
    output_name  : desired filename without extension (e.g. 'lecture_01')
    resolution   : '1080p','720p','480p','360p','240p', or 'Auto'
    output_dir   : absolute path to the output directory
    stop_event   : optional threading.Event; if set the download should abort
                   (passed through where supported)

    Returns True on success, raises RuntimeError on failure.
    """
    os.makedirs(output_dir, exist_ok=True)

    # ── Parse URL + optional sniffed headers ─────────────────────
    pw_url, sniff_headers = parse_url_and_headers(url)

    # ── Resolve forced resolution ─────────────────────────────────
    if resolution and resolution.lower() != "auto":
        try:
            force_res = int(resolution.replace("p", ""))
        except ValueError:
            force_res = None
    else:
        force_res = None

    # ── Step 1: Resolve PW API URLs ───────────────────────────────
    if is_penpencil_api_url(pw_url):
        print(f"  [+] PW API URL detected — resolving signed CDN URL...")
        pw_url = resolve_penpencil_video_url(pw_url, sniff_headers)

    # ── Step 2: Route by CDN type ─────────────────────────────────
    if is_cloudfront_url(pw_url):
        print(f"  [+] CloudFront CDN URL — using CloudFront downloader")
        download_cloudfront(pw_url, output_name, output_dir,
                            force_res or 720, sniff_headers=sniff_headers,
                            stop_event=stop_event, pause_event=pause_event, progress_callback=progress_callback,
                            log_callback=log_callback)
        return True

    # ── sec-prod CDN: extract video ID and params ─────────────────
    try:
        video_id = extract_video_id(pw_url)
        params   = extract_params(pw_url)
    except ValueError as e:
        raise RuntimeError(str(e))

    required = {"URLPrefix", "Expires", "KeyName", "Signature"}
    missing  = required - params.keys()
    if missing:
        raise RuntimeError(f"Missing URL params: {missing}")

    if log_callback: log_callback(f"  [+] Video ID : {video_id}", "info")
    else: print(f"  [+] Video ID : {video_id}")

    # Show expiry
    import datetime
    exp_ts = int(params['Expires'])
    now_ts = int(time.time())
    diff   = exp_ts - now_ts
    if diff <= 0:
        raise RuntimeError(
            f"Signed URL has expired {abs(diff)//3600}h {(abs(diff)%3600)//60}m ago."
        )

    # ── Detect video type and resolution ─────────────────────────
    if log_callback: log_callback(f"  [+] Detecting video type & resolution...", "info")
    else: print(f"  [+] Detecting video type & resolution...")
    candidates = ([force_res] + [r for r in PREFERRED_RES if r != force_res]) if force_res else PREFERRED_RES

    video_type  = None
    chosen_res  = None

    for res in candidates:
        if stop_event and stop_event.is_set():
            raise RuntimeError("Download stopped by user.")
        if check_hls(video_id, res, params):
            if log_callback: log_callback(f"  [+] Found HLS {res}p", "info")
            video_type = "hls"
            chosen_res = res
            break
        else:
            print("✗", end="  ")
            print(f"DASH {res}p...", end=" ", flush=True)
            if check_dash(video_id, res, params):
                if log_callback: log_callback(f"  [+] Found DASH {res}p", "info")
                video_type = "dash"
                chosen_res = res
                break

    if not video_type:
        raise RuntimeError("No resolutions found. Link may be expired or all 403.")

    if log_callback: log_callback(f"  [+] Mode: {video_type.upper()} | Resolution: {chosen_res}p", "info")
    else: print(f"  [+] Mode: {video_type.upper()} | Resolution: {chosen_res}p")

    # ── Execute download ──────────────────────────────────────────
    if stop_event and stop_event.is_set():
        raise RuntimeError("Download stopped by user.")

    if video_type == "hls":
        State.video_id   = video_id
        State.params     = params
        State.resolution = chosen_res
        start_proxy()
        time.sleep(0.5)
        download_hls(output_name, output_dir, stop_event=stop_event, pause_event=pause_event, progress_callback=progress_callback, log_callback=log_callback)
    elif video_type == "dash":
        download_dash(video_id, params, chosen_res, output_name, output_dir,
                      stop_event=stop_event, pause_event=pause_event, progress_callback=progress_callback,
                      log_callback=log_callback)

    return True


def main():
    print("=" * 60)
    print("  PW Video Downloader")
    print("=" * 60)

    # ── Parse URL + headers from command line ────────────────────
    if len(sys.argv) >= 2:
        raw_arg = sys.argv[1].strip()
    else:
        print("\nPaste the PW CDN signed URL (or CloudFront URL from links.txt):")
        raw_arg = input("URL: ").strip()

    pw_url, sniff_headers = parse_url_and_headers(raw_arg)

    if len(sys.argv) >= 3:
        output_name = sys.argv[2].strip()
    else:
        output_name = input("Output file name (without extension): ").strip() or "pw_video"

    force_res = None
    if len(sys.argv) >= 4:
        try:
            force_res = int(sys.argv[3])
        except ValueError:
            pass

        output_dir = OUTPUT_DIR
        os.makedirs(output_dir, exist_ok=True)

    # ── Route by URL type ─────────────────────────────────────────

    # Step 1 — Resolve PW API URLs to actual signed CDN URL first
    if is_penpencil_api_url(pw_url):
        print(f"\n  [+] PW API URL detected (api.penpencil.co) — resolving signed CDN URL...")
        try:
            pw_url = resolve_penpencil_video_url(pw_url, sniff_headers)
        except RuntimeError as e:
            print(f"\n❌ {e}")
            sys.exit(1)

    # Step 2 — Route to appropriate downloader
    if is_cloudfront_url(pw_url):
        print(f"\n  [+] CloudFront CDN URL — using CloudFront downloader")
        download_cloudfront(pw_url, output_name, output_dir, force_res or 720,
                            sniff_headers=sniff_headers)
        return

    # ── Parse URL (sec-prod CDN) ───────────────────────────────────
    print(f"\n  [+] Parsing URL...")
    try:
        video_id = extract_video_id(pw_url)
        params   = extract_params(pw_url)
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(1)

    required = {"URLPrefix", "Expires", "KeyName", "Signature"}
    missing  = required - params.keys()
    if missing:
        print(f"❌ Missing URL params: {missing}")
        sys.exit(1)

    print(f"  [+] Video ID : {video_id}")

    # Show human-readable expiry info
    import datetime
    exp_ts  = int(params['Expires'])
    exp_dt  = datetime.datetime.fromtimestamp(exp_ts)
    now_ts  = int(time.time())
    diff    = exp_ts - now_ts
    if diff <= 0:
        exp_str = f"❌ EXPIRED {abs(diff)//3600}h {(abs(diff)%3600)//60}m ago"
    elif diff < 3600:
        exp_str = f"⚠️  Expires in {diff//60}m {diff%60}s  ← Download NOW!"
    elif diff < 86400:
        exp_str = f"⚠️  Expires in {diff//3600}h {(diff%3600)//60}m"
    else:
        exp_str = f"✅ Expires in {diff//86400} days  ({exp_dt.strftime('%d %b %Y %I:%M %p')})"
    print(f"  [+] URL Expiry: {exp_str}")

    if diff <= 0:
        print("❌ This signed URL has expired. Get a fresh URL from the browser.")
        sys.exit(1)

    # ── Detect video type & find resolution ───────────────────────
    print(f"\n  [+] Detecting video type and available resolutions...")

    candidates = ([force_res] + [r for r in PREFERRED_RES if r != force_res]) if force_res else PREFERRED_RES

    video_type = None
    chosen_res = None

    for res in candidates:
        label = f"{res}p (forced)" if force_res and res == force_res else f"{res}p"
        print(f"    [?] HLS {label}...", end=" ", flush=True)
        if check_hls(video_id, res, params):
            print("✓  [HLS mode]")
            video_type = "hls"
            chosen_res = res
            if force_res and res != force_res:
                print(f"  [!] Forced {force_res}p not available — using {res}p")
            break
        else:
            print("✗", end="  ")
            print(f"DASH {label}...", end=" ", flush=True)
            if check_dash(video_id, res, params):
                print("✓  [DASH mode]")
                video_type = "dash"
                chosen_res = res
                if force_res and res != force_res:
                    print(f"  [!] Forced {force_res}p not available — using {res}p")
                break
            else:
                print("✗")

    if not video_type:
        print("\n❌ No resolutions found. Link may be expired or all 403.")
        sys.exit(1)

    print(f"\n  [+] Mode       : {video_type.upper()}")
    print(f"  [+] Resolution : {chosen_res}p")

    # ── Execute download ──────────────────────────────────────────
    if video_type == "hls":
        State.video_id   = video_id
        State.params     = params
        State.resolution = chosen_res
        start_proxy()
        time.sleep(0.5)
        download_hls(output_name, output_dir)

    elif video_type == "dash":
        download_dash(video_id, params, chosen_res, output_name, output_dir)


if __name__ == "__main__":
    main()
