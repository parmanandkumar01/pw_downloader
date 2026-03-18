# PW Video Downloader — `pw_download.py`

Download DRM-protected videos from **pw.live** (Physics Wallah) using signed CDN URLs directly from your terminal — no third-party website required.

---

## How It Works

PW uses two types of encrypted video delivery:

| Type | Encryption | Detection |
|------|-----------|-----------|
| **HLS** | AES-128 | `/hls/{res}/main.m3u8` |
| **DASH** | ClearKey CENC | `/dash/{res}/init.mp4` |

```
PW Signed URL
     │
     ▼
Auto-detect (HLS or DASH?)
     │
   ┌─┴──────────────────────────┐
   │ HLS                        │ DASH
   ▼                            ▼
Local Proxy (port 18888)   Download all segments directly
+ yt-dlp downloads         + ffmpeg -decryption_key
     │                          │
     └──────────┬───────────────┘
                ▼
           output.mp4 ✅
```

**Why a local proxy for HLS?**
PW CDN requires specific browser headers (`Referer`, `Origin`) on every `.ts` segment request. The local proxy adds these headers transparently so `yt-dlp` can download all fragments without 403 errors.

---

## Requirements

```bash
# Check if installed
which yt-dlp    # required
which ffmpeg    # required (for DASH videos)

# Install if missing
sudo apt install yt-dlp ffmpeg
# or
pip install yt-dlp
```

No extra Python packages needed — uses Python stdlib only.

---

## Getting the PW Signed URL

Open the video on `pw.live` → Press **F12** → **Network tab** → Play the video  
Filter by: `mpd` or `m3u8` or `init.mp4`

Copy the full URL — it looks like:
```
https://sec-prod-mediacdn.pw.live/<uuid>/master.mpd?URLPrefix=...&Expires=...&KeyName=pw-prod-key&Signature=...
```

> ⚠️ **Do NOT include a trailing `~`** at the end of the Signature — that is a browser copy artifact.

---

## Usage

### Basic (auto-selects best resolution)
```bash
python3 pw_download.py "<PW_URL>" "Lecture Name"
```

### Force a specific resolution
```bash
python3 pw_download.py "<PW_URL>" "Lecture Name" 720
```

### Interactive (no arguments)
```bash
python3 pw_download.py
# Prompts for URL and output name
```

---

## Arguments

| Position | Argument | Description |
|----------|----------|-------------|
| 1 | `<PW_URL>` | PW CDN signed URL (`master.mpd` or `dash/init.mp4`) |
| 2 | Output Name | Output filename without extension |
| 3 *(optional)* | Resolution | `1080`, `720`, `480`, `360`, or `240` |

---

## Supported URL Formats

```
# DASH-style (from init.mp4 request)
https://sec-prod-mediacdn.pw.live/<uuid>/dash/240/init.mp4?URLPrefix=...&Expires=...&Signature=...

# MPD manifest
https://sec-prod-mediacdn.pw.live/<uuid>/master.mpd?URLPrefix=...&Expires=...&Signature=...
```

---

## Resolution Auto-Detection

If no resolution is forced, the script checks in order:

```
1080p → 720p → 480p → 360p → 240p
```

It checks **both HLS and DASH** for each resolution before moving to the next.

---

## URL Expiry

The script automatically shows expiry status:

```
✅ Expires in 364 days  (28 Feb 2027 09:46 AM)   ← Safe to use
⚠️  Expires in 23m 45s  ← Download NOW!
❌ EXPIRED 2h 15m ago   ← Get a fresh URL
```

PW URLs are typically valid for **~1 year**.

---

## Output

Files are saved as `.mp4` in the **same directory as the script**:
```
/home/parmanand/Desktop/pw_down/Lecture_Name.mp4
```

---

## Examples

```bash
# Download at best available quality
python3 pw_download.py \
  "https://sec-prod-mediacdn.pw.live/9ff66.../master.mpd?URLPrefix=...&Signature=..." \
  "Physics_Chapter_01"

# Force 480p
python3 pw_download.py \
  "https://sec-prod-mediacdn.pw.live/9ff66.../master.mpd?URLPrefix=...&Signature=..." \
  "Physics_Chapter_01" 480
```

---

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `All resolutions ✗` | Signature has `~` at end or URL expired | Remove `~` from end of URL or get fresh URL |
| `HTTP 403` | Wrong headers / IP blocked | Try again, check Signature is complete |
| `yt-dlp exited code 1` | Network issue mid-download | Re-run, yt-dlp will retry from start |
| `ffmpeg decryption failed` | DASH key mismatch | Usually means wrong video UUID |

---

## Notes

- The local proxy runs on port **18888** — ensure it is free
- DASH downloads are sequential (slower); HLS uses 4 parallel fragments
- Temp files for DASH are cleaned up automatically after muxing
