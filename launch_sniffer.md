# Media URL Sniffer — `url_sniffer.py`

A mitmproxy-based network interceptor that automatically captures streaming and DRM-related media URLs while you browse **any** video website — PW, YouTube, Hotstar, Udemy, Vimeo, Twitch, JioCinema, Zee5, SonyLIV, and more.

---

## How It Works

```
Browser  →  HTTP/HTTPS Request
              │
              ▼
         mitmproxy (port 8080)
              │
         url_sniffer.py addon
              │  ← Matches URL against streaming patterns
              │
         Match found?
           │         │
          YES        NO → Pass through silently
           │
     Print to terminal (color-coded)
     Append to links.txt (no duplicates)
```

---

## What Gets Captured

### URL Extension Patterns

| Pattern | Type |
|---------|------|
| `.m3u8` | HLS playlists |
| `.mpd` | MPEG-DASH manifests |
| `.ts` | MPEG-TS segments |
| `.m4s` | fMP4 DASH segments |
| `.mp4` | Direct MP4 streams |
| `.vtt` | WebVTT subtitles |

### Keyword Patterns

| Category | Keywords |
|----------|---------|
| **Manifests** | `manifest`, `master.mpd`, `master.m3u8`, `playlist.m3u8`, `chunklist` |
| **Stream paths** | `/hls/`, `/dash/`, `/cmaf/`, `/stream/`, `/segment`, `/chunk`, `/frag` |
| **DRM** | `widevine`, `playready`, `fairplay`, `/license`, `/drm`, `/enc.key`, `pssh`, `cenc` |
| **CDN** | `akamaized.net`, `cloudfront.net`, `fastly.net`, `akamaihd.net` |
| **PW** | `URLPrefix=`, `sec-prod-mediacdn`, `penpencil.co` |
| **YouTube** | `googlevideo.com` |
| **Hotstar** | `hotstar.com/playlist`, `akamaihd.net` |
| **Udemy** | `udemycdn.com` |
| **Vimeo** | `vimeocdn.com` |
| **Twitch** | `twitchsvc.net`, `live-video.net` |
| **Others** | JioCinema, Zee5, SonyLIV, MX Player, Coursera |

### Terminal Output Tags

Each captured URL shows **two tags**: Platform + Stream Type

```
[PW]      [DASH]     → PW CDN DASH stream
[YouTube] [HLS]      → YouTube HLS stream
[Hotstar] [DRM-KEY]  → Hotstar Widevine license
[Udemy]   [DASH]     → Udemy DASH stream
[OTHER]   [MEDIA]    → Unknown platform stream
```

| Platform Tag | Stream Type Tag |
|-------------|-----------------|
| `[PW]` 🟡 | `[HLS]` 🟢 |
| `[YouTube]` 🔵 | `[DASH]` 🟢 |
| `[Hotstar]` 🔵 | `[DRM-KEY]` 🟡 |
| `[Udemy]` 🔵 | `[SEG]` |
| `[Vimeo]` 🔵 | `[MEDIA]` |
| `[Twitch]` 🔵 | |
| `[OTHER]` 🔵 | |

---

## Requirements

```bash
which mitmdump     # check if installed
mitmdump --version

# Install if missing
pip install mitmproxy
# or
sudo apt install mitmproxy
```

---

## One-Time Setup — Install mitmproxy Certificate

Required to intercept **HTTPS** traffic.

### Step 1 — Generate the certificate
```bash
bash run_sniffer.sh
# Press Ctrl+C after a few seconds
```
Certificate location: `~/.mitmproxy/mitmproxy-ca-cert.pem`

### Step 2 — Install in browser

**Chrome / Chromium / Brave:**
```
Settings → Privacy and Security → Security
→ Manage Certificates → Authorities → Import
→ select: ~/.mitmproxy/mitmproxy-ca-cert.pem
→ ✅ Trust this certificate for identifying websites → OK
```

**Firefox:**
```
Settings → Privacy & Security → Certificates → View Certificates
→ Authorities → Import
→ select: ~/.mitmproxy/mitmproxy-ca-cert.pem
→ ✅ Trust this CA to identify websites → OK
```

**System-wide:**
```bash
sudo cp ~/.mitmproxy/mitmproxy-ca-cert.pem /usr/local/share/ca-certificates/mitmproxy.crt
sudo update-ca-certificates
```

### Step 3 — Set browser proxy

**Manual proxy settings:**
```
Host: 127.0.0.1    Port: 8080    (HTTP + HTTPS)
```

**Chrome via command line (easiest):**
```bash
google-chrome --proxy-server="127.0.0.1:8080"
chromium --proxy-server="127.0.0.1:8080"
```

**Firefox:** Settings → Network Settings → Manual proxy → `127.0.0.1 : 8080`

---

## Usage

### Option A — All-in-one (Recommended)
Starts sniffer + Firefox together. Terminal prompt returns immediately.
```bash
bash launch_sniffer.sh
```
- Opens Firefox with `mitmproxy` profile automatically
- `MOZ_ENABLE_WAYLAND=0` applied — keyboard works normally in Firefox
- Sniffer runs in background, terminal is free
- URLs saved to `links.txt` silently

**Watch captured URLs live (new terminal):**
```bash
tail -f links.txt
```

**Stop the sniffer:**
```bash
bash launch_sniffer.sh stop
```

---

### Option B — Sniffer only (browser separately)
```bash
bash run_sniffer.sh
```
Then open Firefox manually with `mitmproxy` profile (proxy already set in profile).

---

### Option C — Direct mitmdump
```bash
mitmdump -s url_sniffer.py --listen-port 8080 --ssl-insecure
```

---

## Browse any video site
Open Firefox (`mitmproxy` profile), go to any video site, start playing.  
Captured URLs appear in `links.txt` automatically.

### Sample captured URLs (`links.txt`)
```
────────────────────────────────────────────────────────────
  [PW] [DASH]  09:23:14 [GET]
  https://sec-prod-mediacdn.pw.live/.../master.mpd?URLPrefix=...&Signature=...

────────────────────────────────────────────────────────────
  [YouTube] [MEDIA]  09:24:01 [POST]
  https://rr1---sn-abc.googlevideo.com/videoplayback?expire=...

────────────────────────────────────────────────────────────
  [OTHER] [DRM-KEY]  09:25:10 [GET]
  https://license.example.com/widevine?token=...
```

---

## Keyboard Not Working in Firefox? (Wayland Fix)

`launch_sniffer.sh` already applies the fix automatically. If you launch Firefox manually and keyboard doesn't work:

```bash
# Launch Firefox with X11 mode (fixes keyboard on Wayland systems)
MOZ_ENABLE_WAYLAND=0 GDK_BACKEND=x11 firefox -P mitmproxy --no-remote &
```

| Problem | Cause | Fix |
|---------|-------|-----|
| Cursor appears but can't type | Firefox running in Wayland mode | Use `MOZ_ENABLE_WAYLAND=0` |
| No keyboard at all | Terminal has focus | Click Firefox window first |

---


## Chrome Launch Errors (Now Fixed Automatically)

Previous Chrome-based approach had these issues — now using Firefox with fixes built-in:

| Error | Cause | Harmless? |
|-------|-------|----------|
| `wayland not compatible with Vulkan` | GPU rendering conflict | ✅ Yes — use `--ozone-platform=x11` |
| `Failed to connect to MCS endpoint` | Google push notifications | ✅ Yes |
| `Fontconfig error` | Missing font config | ✅ Yes |

`launch_sniffer.sh` already handles these automatically.

---

## Output File — `links.txt`

```
# Media URL Sniffer — Captured Links

[2026-03-01 09:23:14] [GET]
https://sec-prod-mediacdn.pw.live/.../master.mpd?URLPrefix=...

[2026-03-01 09:24:01] [GET]
https://rr1---sn.googlevideo.com/.../index.m3u8?...
```

- No duplicates across runs (existing URLs loaded on startup)
- Appended in real-time

---

## Use Captured URLs with pw_download.py

```bash
# Pick the latest PW MPD link and download it
python3 pw_download.py "$(grep -A1 'PW.*DASH' links.txt | grep 'master.mpd' | tail -1)" "Lecture_Name"
```

---

## Customize Patterns

Edit `url_sniffer.py` to add your own:

```python
# Add a new platform keyword
KEYWORD_PATTERNS = [
    ...
    r'your-cdn\.example\.com',   # My custom platform
]

# Ignore a noisy domain
IGNORE_PATTERNS = re.compile(
    r'(... | your-noise-domain\.com)',
    re.IGNORECASE
)
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| HTTPS sites show cert error | Install mitmproxy cert (Step 2) |
| No URLs appear | Check browser proxy → 127.0.0.1:8080 |
| "Proxy refused connection" | Start `run_sniffer.sh` first |
| Too many unrelated URLs | Add domain to `IGNORE_PATTERNS` |
| Missing a platform's URLs | Add its CDN domain to `KEYWORD_PATTERNS` |

---

## File Structure

```
pw_down/
├── url_sniffer.py      ← mitmproxy addon (core sniffer logic)
├── run_sniffer.sh      ← sniffer-only launcher
├── launch_sniffer.sh   ← sniffer + Chrome all-in-one launcher ⭐
├── links.txt           ← captured URLs (auto-created)
├── pw_download.py      ← PW video downloader
├── README.md           ← pw_download.py docs
└── README_SNIFFER.md   ← this file
```
