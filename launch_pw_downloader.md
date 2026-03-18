
# PW Downloader — Complete Workflow Guide

Sniffer se video link capture karo aur directly terminal se download karo.\
Koi browser extension, website, ya manual copy-paste ki zaroorat nahi.

---

## Files Overview

| File | Kaam |
|------|------|
| `launch_sniffer.sh` | mitmproxy sniffer + Firefox launch karta hai |
| `url_sniffer.py` | Sirf master playlist URLs capture karta hai |
| `launch_pw_downloader.sh` | `links.txt` se URLs padh ke download karta hai |
| `pw_download.py` | Actual downloader (HLS + DASH dono handle karta hai) |
| `links.txt` | Captured master playlist URLs (auto-generated) |

---

## Step-by-Step Workflow

### Step 1 — Sniffer Chalao

```bash
bash launch_sniffer.sh
```

- Mitmproxy background mein start hoga (port 8080)
- Firefox automatically `mitmproxy` profile ke saath open hoga
- `links.txt` ready rahega URLs capture karne ke liye

### Step 2 — Video Play Karo

Firefox mein PW website open karo aur video play karo.\
Sniffer automatically **master playlist URL** (`master.m3u8` / `master.mpd`) pakad lega.

> **Sirf master playlist save hogi** — `.ts` segments, chunks, DRM keys sab ignore hote hain.

### Step 3 — Sniffer Band Karo

```bash
bash launch_sniffer.sh stop
```

Sniffer band hoga aur `sniffer.log` automatically clear ho jayega.

### Step 4 — Download Karo

```bash
bash launch_pw_downloader.sh
```

Script poochega:

```
Konsi URLs download karni hain?  → 1  /  1 3  /  all  /  q
Video resolution (720)?          → 1080
Output file name prefix?         → Lecture
```

Output files:
```
Lecture_1.mp4
Lecture_2.mp4   ← conflict nahi aayega, auto-numbered
```

---

## Direct Args (Interactive Prompt Skip)

```bash
bash launch_pw_downloader.sh "Lecture" 720
```

---

## URL Selection Options

| Input | Matlab |
|-------|--------|
| `1` | Sirf pehli URL |
| `1 3 5` | URL 1, 3, 5 |
| `all` | Saari URLs |
| `q` | Quit |

---

## Auto-Numbering Logic

Script existing files check karta hai aur next available number use karta hai:

```
Lecture_1.mp4  ← already exists
Lecture_2.mp4  ← already exists
Lecture_3.mp4  ← naya file yahan save hoga ✅
```

Koi file overwrite nahi hoti.

---

## Supported Resolutions

`1080` → `720` → `480` → `360` → `240`

Agar forced resolution available nahi hai to script automatically next best resolution use karti hai.

---

## Requirements

```bash
which yt-dlp    # HLS downloads ke liye
which ffmpeg    # DASH decrypt + mux ke liye
which mitmdump  # Sniffer ke liye (mitmproxy package)
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `links.txt mein koi URL nahi mila` | Sniffer chalao, video play karo, phir download karo |
| `HTTP 403` | URL expire ho gayi — fresh URL ki zaroorat hai |
| `All resolutions ✗` | Signature ke end mein `~` hai — hata do |
| `yt-dlp exited code 1` | Network issue — dobara chalao |
