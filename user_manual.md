# PW Video Downloader — User Manual

**Version:** 2.0  
**Platform:** Linux / Windows  
**Framework:** Python 3 + CustomTkinter

---

## Table of Contents

1. [Overview](#overview)
2. [First Launch](#first-launch)
3. [Interface Layout](#interface-layout)
4. [Step-by-Step Usage](#step-by-step-usage)
   - [Step 1 — Load Links File](#step-1--load-links-file)
   - [Step 2 — Choose Output Folder](#step-2--choose-output-folder)
   - [Step 3 — Select Which Links to Download](#step-3--select-which-links-to-download)
   - [Step 4 — Choose Resolution](#step-4--choose-resolution)
   - [Step 5 — Set Filename Prefix](#step-5--set-filename-prefix)
   - [Step 6 — Start Download](#step-6--start-download)
   - [Step 7 — Monitor Progress](#step-7--monitor-progress)
   - [Step 8 — Stop Download](#step-8--stop-download)
5. [Link Preview Window](#link-preview-window)
6. [Log Colors Explained](#log-colors-explained)
7. [Smart Features](#smart-features)
   - [Auto-Resume After Crash](#auto-resume-after-crash)
   - [Skip Already Downloaded](#skip-already-downloaded)
   - [Auto-Remove Completed Links](#auto-remove-completed-links)
   - [URL Expiry Warning](#url-expiry-warning)
   - [Network Wait](#network-wait)
   - [Temp File Cleanup](#temp-file-cleanup)
8. [links.txt File Format](#linkstxt-file-format)
9. [Link Selection Syntax](#link-selection-syntax)
10. [Download Counter](#download-counter)
11. [Saved Files](#saved-files)
12. [Tips & Best Practices](#tips--best-practices)
13. [Troubleshooting](#troubleshooting)

---

## Overview

PW Video Downloader is a desktop application that downloads PW (Physics Wallah)
lecture videos in bulk from a text file of links. It handles:

- HLS (AES-128 encrypted) streams
- DASH (ClearKey CENC encrypted) streams
- CloudFront CDN links
- PW API (`api.penpencil.co`) links (auto-resolves to CDN URL)

---

## First Launch

```bash
python app.py
# or on Windows: double-click PW_Downloader.exe
```

On first launch the app:
1. Cleans up any leftover temp folders from previous sessions.
2. Checks `queue.json` — if a previous download was interrupted, it offers to **resume**.
3. Loads your last-used settings from `config.json` (paths, resolution, prefix).

---

## Interface Layout

```
┌────────────────────────┬──────────────────────────────────────┐
│  SIDEBAR (left)        │  LOG PANEL (right)                   │
│                        │                                      │
│  ⚡ PW Video Downloader│  📋 Download Log                     │
│                        │  (scrollable coloured log)           │
│  📁 Links File         │                                      │
│  💾 Download Folder    │  ⚙ Current Download                  │
│  🔢 Select Links       │  [video name]                        │
│  🎞 Resolution         │  ████████░░ 45%  ⚡3.2MB/s  ⏱ETA 02:15│
│  ✏️ Prefix              │                                      │
│                        │  ████████████░░░  8 / 10 downloads   │
│  [▶ START DOWNLOAD]    │                                      │
│  [⏹ STOP DOWNLOAD]     │  Total | Done | Failed | Left        │
│  [🗑 Clear Logs]       │    10     8      1       1           │
│                        │                                      │
└────────────────────────┴──────────────────────────────────────┘
```

---

## Step-by-Step Usage

### Step 1 — Load Links File

1. Click **Browse** next to **Links File**.
2. Select your `.txt` file containing PW video URLs (one per line).
3. The app will:
   - Remove blank / non-URL lines automatically.
   - Remove duplicate URLs automatically.
   - Show how many valid links were loaded in the log.

> **Your `links.txt` file path is remembered** for the next session.

---

### Step 2 — Choose Output Folder

1. Click **Browse** next to **Download Folder**.
2. Select (or create) the folder where videos should be saved.
3. If the folder doesn't exist, it will be created automatically.

---

### Step 3 — Select Which Links to Download

Type a selection in the **Select Links To Download** box.

| Input | Meaning |
|-------|---------|
| `all` | Download every link in the file |
| `3` | Download only link number 3 |
| `3,4,5` | Download links 3, 4, and 5 |
| `5-8` | Download links 5 through 8 |
| `5-` | Download from link 5 to the last link |
| `-3` | Download from the first link up to link 3 |

> Leave blank or type `all` to download everything.

---

### Step 4 — Choose Resolution

Click the **Resolution** dropdown and select:

| Option | Behaviour |
|--------|-----------|
| `Auto` | Backend detects the best available resolution (default) |
| `1080p` | Force 1080p (falls back to lower if not available) |
| `720p` | Force 720p |
| `480p` | Force 480p |
| `360p` | Force 360p |
| `240p` | Force 240p |

---

### Step 5 — Set Filename Prefix

Type a prefix in the **Filename Prefix** box.

| Prefix | Output files |
|--------|-------------|
| `lecture` | `lecture_01.mp4`, `lecture_02.mp4`, … |
| `class` | `class_01.mp4`, `class_02.mp4`, … |
| *(empty)* | `video_01.mp4`, `video_02.mp4`, … |

Files are numbered based on their **position in your selection**, not their position in the original file.

---

### Step 6 — Start Download

Click **▶ START DOWNLOAD**.

The app will:
1. Reload the links file (picks up any edits).
2. Remove duplicates and invalid lines.
3. Parse your link selection.
4. Check each link's history and skip already-downloaded ones.
5. Download sequentially, one video at a time.
6. Retry up to **3 times** on failure.
7. Mark each video in `download_history.json` on success.
8. Remove the downloaded URL from `links.txt` automatically.

> The UI stays **fully responsive** — you can scroll logs and check counters while downloading.

---

### Step 7 — Monitor Progress

**Current Download Card** (bottom-right area):
- Shows the active video name.
- Live progress bar with percentage.
- Download speed (e.g. `3.2MiB/s`).
- Estimated time remaining (ETA).

**Overall Progress Bar**:
- Shows how many videos out of the total are done.

**Download Counters**:

| Counter | Meaning |
|---------|---------|
| Total | Total videos queued for this session |
| Done | Successfully downloaded |
| Failed | All 3 retries exhausted |
| Left | Still in queue |

---

### Step 8 — Stop Download

Click **⏹ STOP DOWNLOAD** at any time.

- The current download finishes its current segment, then stops.
- Remaining queued videos are cancelled.
- The queue state is **saved** — you can resume next time.

---

## Link Preview Window

Click the **👁 Preview Links** button to open the preview popup.

Shows a table with:

| Column | Content |
|--------|---------|
| # | Link index number (1-based) |
| URL | Shortened URL |
| Expiry / Status | Expiry countdown, or ✅ Done if already in history |

**Status colours:**
- 🟢 Green = already downloaded
- 🔴 Red = URL has expired
- 🟡 Yellow = URL expires soon (< 1 hour)
- ⚫ Grey = normal pending link

---

## Log Colors Explained

| Color | Meaning |
|-------|---------|
| 🟢 Green | Success — download completed |
| 🔴 Red | Error — download failed or stopped |
| 🟡 Yellow | Warning — retry, skipped, expiry notice |
| ⚫ Grey | Info — backend output, segment progress |

Click **🗑 Clear Logs** to wipe the log panel.

---

## Smart Features

### Auto-Resume After Crash

If the app crashes or is closed mid-download:
- The remaining queue is saved in `queue.json`.
- On next launch, you will be asked: **"Resume N pending downloads from last session?"**
- Click **Yes** to continue exactly where it left off.

---

### Skip Already Downloaded

Before each download:
1. The app checks `download_history.json` — if the URL was previously downloaded, it is **skipped** automatically.
2. The app checks if the output `.mp4` file already exists on disk — if so, it is **skipped** automatically.

Log message:
```
⏭  lecture_03 already exists — skipping.
⏭  lecture_04 already in history — skipping.
```

---

### Auto-Remove Completed Links

After each **successful** download, the downloaded URL is automatically **removed from `links.txt`**.

This means `links.txt` always contains only the **remaining, not-yet-downloaded** links. Safe to re-run without re-downloading anything.

---

### URL Expiry Warning

PW signed URLs expire. The app checks the `Expires` parameter in each URL:

| Condition | Action |
|-----------|--------|
| Already expired | ❌ Skip with error log |
| Expires in < 1 hour | ⚠️ Warning logged, download starts |
| Expires in > 1 hour | ✅ Proceed normally |

Check the **Preview Window** to see expiry times before starting.

---

### Network Wait

If the internet goes down during a download:
- The app **pauses** and waits silently.
- It checks for reconnection every 5 seconds.
- Once reconnected, it **resumes automatically**.

Log message:
```
🌐  No internet — waiting for connection…
🌐  Connection restored.
```

---

### Retry System

If a download fails:
- It retries up to **3 times** automatically.
- Each retry is logged:
```
🔄  Retry 1/2…
🔄  Retry 2/2…
💀  All 3 attempts failed: lecture_05
```

---

### Temp File Cleanup

On every startup, the app removes leftover temporary folders created by previous downloads:
```
/tmp/pw_dash_*
/tmp/pw_cf_dash_*
```

This keeps your disk clean automatically.

---

## links.txt File Format

Each line should be one video URL. The sniffer tool can also append auth headers in this format:

```
https://sec-prod-mediacdn.pw.live/.../master.mpd?Signature=...
https://d1d34p8vz63oiq.cloudfront.net/.../master.mpd?Signature=...
https://api.penpencil.co/v1/... ||HEADERS|| {"Authorization":"Bearer ...","Cookie":"..."}
```

- **Blank lines** → ignored automatically.
- **Lines without `http://` or `https://`** → treated as invalid, ignored.
- **Duplicate URLs** → removed automatically on load.

---

## Link Selection Syntax

| Syntax | Example | Result |
|--------|---------|--------|
| `all` | `all` | Every link |
| Single | `5` | Link 5 only |
| List | `1,3,7` | Links 1, 3, 7 |
| Range | `3-7` | Links 3, 4, 5, 6, 7 |
| From N | `4-` | Links 4 to end |
| Up to N | `-5` | Links 1 to 5 |
| Empty | *(blank)* | Same as `all` |

Invalid input shows an error popup before any download starts.

---

## Download Counter

| Counter | When it updates |
|---------|----------------|
| **Total** | Set at start — total videos queued |
| **Done** | +1 after each successful download |
| **Failed** | +1 after all 3 retries are exhausted |
| **Left** | Total − Done − Failed (live) |

---

## Saved Files

The app saves these files in the **same folder as `app.py`** (or the EXE):

| File | Purpose |
|------|---------|
| `config.json` | Remembers last-used paths, resolution, prefix |
| `download_history.json` | Tracks which URLs have been downloaded |
| `queue.json` | Saves the current queue for auto-resume |

These files are created automatically — you don't need to create them.  
You can **delete** `download_history.json` if you want to re-download everything.

---

## Tips & Best Practices

1. **Get fresh URLs** before starting. PW signed URLs expire (usually within a few hours or days). Always use the URL sniffer tool to capture fresh links before downloading.

2. **Use `links.txt` as a master list.** Since successful downloads are auto-removed from the file, you can safely re-run the app anytime — it will only download whatever is left.

3. **Use the Preview window first.** Before clicking Start, open Preview to see expiry status of each URL and skip expired ones.

4. **For large batches**, run overnight. The retry and network-wait system will handle temporary failures automatically.

5. **Don't rename `links.txt` mid-download.** The auto-remove feature writes back to whatever file path was loaded at start time.

6. **For a clean re-download**, delete `download_history.json` and re-add URLs to `links.txt`.

---

## Troubleshooting

| Problem | Solution |
|---------|---------|
| App doesn't start | Run `pip install customtkinter` |
| Download fails immediately | URL may be expired — check Preview window |
| `yt-dlp not found` error | Install: `pip install yt-dlp` or download `yt-dlp` binary |
| `ffmpeg not found` error | Install ffmpeg and add to PATH |
| Slow downloads | Try a lower resolution (e.g. 480p) |
| Video file is 0 bytes | URL expired mid-download — get fresh URL |
| Links not loading | Make sure file is `.txt` with one URL per line |
| History not clearing | Delete `download_history.json` manually |
| Resume prompt at startup | Click Yes to continue, or No to start fresh |

---

*PW Video Downloader v2.0 — Built with Python 3 + CustomTkinter*
