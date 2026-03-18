#!/usr/bin/env python3
"""
PW Video Downloader — Production-Ready GUI v2
==============================================
A professional CustomTkinter GUI for the PW Video Downloader backend.

Architecture (all in this file, clearly sectioned):
  A. ConfigManager      — config.json (last-used paths/settings)
  B. DownloadHistory    — download_history.json (skip already-done videos)
  C. QueueState         — queue.json (auto-resume after crash)
  D. LinkParser         — parse "all/N/N-M/N,M/N-/-N" selection strings
  E. URLUtils           — validate, expiry-check, internet, temp cleanup
  F. ProgressInterceptor— intercept backend stdout → log + parse progress
  G. DownloadManager    — queue, threading, retry×3, stop, skip, history
  H. VideoProgressCard  — CTkFrame: current video %, speed, ETA
  I. LinkPreviewWindow  — CTkToplevel table: Index / URL / Status
  J. PWDownloaderApp    — main CTk application window (12 sections)

Build commands (included here for reference):
  Windows EXE :  pyinstaller --onefile --noconsole app.py
  Linux binary:  pyinstaller --onefile app.py
"""

# ── Standard Library ──────────────────────────────────────────────────────────
import os, sys, re, json, time, glob, shutil, socket, queue, threading, hashlib
from datetime import datetime
from urllib.parse import urlparse, parse_qs

# ── Third-Party ───────────────────────────────────────────────────────────────
try:
    import customtkinter as ctk
    from tkinter import filedialog, messagebox
    import tkinter as tk
except ImportError:
    sys.exit("[ERROR] customtkinter not installed.  Run: pip install customtkinter")
try:
    from PIL import Image, ImageTk
    _PIL_OK = True
except ImportError:
    _PIL_OK = False  # icon is optional; won't crash

# ── Backend ───────────────────────────────────────────────────────────────────
try:
    import pw_download
except ImportError:
    pw_download = None  # UI still launches; error shown at download start

# ── App directory (same folder as this script) ────────────────────────────────
APP_DIR      = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE  = os.path.join(APP_DIR, "config.json")
HISTORY_FILE = os.path.join(APP_DIR, "download_history.json")
QUEUE_FILE   = os.path.join(APP_DIR, "queue.json")


# ══════════════════════════════════════════════════════════════════════════════
# A — Config Manager
# ══════════════════════════════════════════════════════════════════════════════
class ConfigManager:
    """Persist user settings between sessions via config.json."""
    DEFAULTS = {
        "last_links_file"  : "",
        "last_output_folder": os.path.join(os.path.expanduser("~"), "Downloads", "PW_Videos"),
        "resolution"       : "Auto",
        "prefix"           : "lecture",
        "selection"        : "all",
    }
    def __init__(self):
        self._d = dict(self.DEFAULTS)
        self.load()

    def load(self):
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                self._d.update(json.load(f))
        except Exception:
            pass

    def save(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self._d, f, indent=2)
        except Exception:
            pass

    def get(self, k):  return self._d.get(k, self.DEFAULTS.get(k, ""))
    def set(self, k, v): self._d[k] = v; self.save()


# ══════════════════════════════════════════════════════════════════════════════
# B — Download History
# ══════════════════════════════════════════════════════════════════════════════
class DownloadHistory:
    """Track downloaded URLs (by path hash) to auto-skip re-downloads."""
    def __init__(self):
        self._h: dict = {}
        self.load()

    def load(self):
        try:
            with open(HISTORY_FILE, encoding="utf-8") as f:
                self._h = json.load(f)
        except Exception:
            self._h = {}

    def save(self):
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self._h, f, indent=2)
        except Exception:
            pass

    def _key(self, url: str) -> str:
        base = urlparse(url.split(" ||HEADERS|| ")[0].strip())
        return hashlib.sha1(f"{base.netloc}{base.path}".encode()).hexdigest()[:16]

    def is_downloaded(self, url: str) -> bool:
        return self._key(url) in self._h

    def mark(self, url: str, name: str):
        self._h[self._key(url)] = {"name": name, "time": datetime.now().isoformat(timespec="seconds")}
        self.save()


# ══════════════════════════════════════════════════════════════════════════════
# C — Queue State (Auto-Resume)
# ══════════════════════════════════════════════════════════════════════════════
class QueueState:
    """Save/load queue.json so downloads resume after a crash."""
    def save(self, jobs: list):
        try:
            with open(QUEUE_FILE, "w", encoding="utf-8") as f:
                json.dump(jobs, f, indent=2)
        except Exception:
            pass

    def remove(self, url: str, jobs: list):
        remaining = [j for j in jobs if j.get("url") != url]
        if remaining:
            self.save(remaining)
        else:
            self.clear()
        return remaining

    def load(self) -> list:
        try:
            with open(QUEUE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def clear(self):
        if os.path.exists(QUEUE_FILE):
            try: os.remove(QUEUE_FILE)
            except Exception: pass


# ══════════════════════════════════════════════════════════════════════════════
# D — Link Parser
# ══════════════════════════════════════════════════════════════════════════════
def parse_link_selection(sel: str, total: int) -> list[int]:
    """
    Parse user selection string → sorted list of 1-based indices.
    Formats: all | N | N,M,K | N-M | N- | -N
    """
    s = sel.strip().lower()
    if s in ("all", ""):
        return list(range(1, total + 1))
    if m := re.fullmatch(r"(\d+)-(\d+)", s):
        a, b = int(m.group(1)), int(m.group(2))
        if a < 1 or b > total or a > b: raise ValueError(f"Range {a}-{b} out of bounds (1-{total}).")
        return list(range(a, b + 1))
    if m := re.fullmatch(r"(\d+)-", s):
        a = int(m.group(1))
        if not (1 <= a <= total): raise ValueError(f"Index {a} out of bounds (1-{total}).")
        return list(range(a, total + 1))
    if m := re.fullmatch(r"-(\d+)", s):
        b = int(m.group(1))
        if not (1 <= b <= total): raise ValueError(f"Index {b} out of bounds (1-{total}).")
        return list(range(1, b + 1))
    if "," in s:
        out = []
        for p in s.split(","):
            p = p.strip()
            if not p.isdigit(): raise ValueError(f"'{p}' is not a valid number.")
            n = int(p)
            if not (1 <= n <= total): raise ValueError(f"Index {n} out of bounds (1-{total}).")
            out.append(n)
        return sorted(set(out))
    if s.isdigit():
        n = int(s)
        if not (1 <= n <= total): raise ValueError(f"Index {n} out of bounds (1-{total}).")
        return [n]
    raise ValueError(f"Cannot parse '{sel}'.\nValid: all | N | N,M,K | N-M | N- | -N")


# ══════════════════════════════════════════════════════════════════════════════
# E — URL Utilities
# ══════════════════════════════════════════════════════════════════════════════
def is_valid_url(line: str) -> bool:
    return line.split(" ||HEADERS|| ")[0].strip().startswith(("http://", "https://"))

def get_expiry_info(url: str) -> str | None:
    """Return human-readable expiry string for signed URLs, or None."""
    qs = parse_qs(urlparse(url.split(" ||HEADERS|| ")[0].strip()).query)
    exp = qs.get("Expires", [None])[0]
    if not exp: return None
    try:
        diff = int(exp) - int(time.time())
        if diff < 0:      return f"EXPIRED {abs(diff)//3600}h {(abs(diff)%3600)//60}m ago"
        if diff < 3600:   return f"Expires in {diff//60}m {diff%60}s — download NOW!"
        if diff < 86400:  return f"Expires in {diff//3600}h {(diff%3600)//60}m"
        return f"Expires in {diff//86400} days"
    except ValueError:
        return None

def check_internet() -> bool:
    try:
        socket.setdefaulttimeout(3)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect(("8.8.8.8", 53))
        return True
    except OSError:
        return False

def cleanup_temp_folders(odir: str = None) -> int:
    """Remove leftover pw_dash_* / pw_cf_dash_* temp dirs. Returns count."""
    n = 0
    patterns = ["/tmp/pw_dash_*", "/tmp/pw_cf_dash_*"]
    if odir:
        patterns.extend([os.path.join(odir, "pw_dash_*"), os.path.join(odir, "pw_cf_dash_*")])
    for pat in patterns:
        for d in glob.glob(pat):
            shutil.rmtree(d, ignore_errors=True); n += 1
    return n


# ══════════════════════════════════════════════════════════════════════════════
# F — REMOVED (No longer used, pw_download handles callbacks directly)
# ══════════════════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════════════════
# G — Download Manager
# ══════════════════════════════════════════════════════════════════════════════
class DownloadManager:
    """
    Manages the download queue in background threads.
    Features: configurable parallel downloads, stop signal, 3× auto-retry,
              history skip, duplicate removal, file-exists skip,
              network wait, links.txt auto-remove on success.
    """
    MAX_RETRIES = 3

    def __init__(self, log_cb, progress_cb, counter_cb, overall_cb, vidprog_cb, add_card_cb, remove_card_cb):
        self._log      = log_cb
        self._overall  = overall_cb
        self._counter  = counter_cb
        self._vidprog  = vidprog_cb  # changed to receive (url, info)
        self._add_card = add_card_cb # (url, name, signals_dict)
        self._kill_card= remove_card_cb # (url)
        self._stop     = threading.Event()
        self._thread   = None
        self._jobs     = []
        self._queue    = queue.Queue()
        self._qs       = QueueState()
        self._hist     = DownloadHistory()
        self._total = self._done = self._failed = 0
        self._max_workers = 1  # set by start()
        self._signals = {}  # url -> {"stop": Event(), "pause": Event()}

    # ── Public ─────────────────────────────────────────────────────────────
    def start(self, jobs: list, links_file: str = "", max_workers: int = 1):
        if self.is_running(): return
        self._stop.clear()
        self._jobs       = list(jobs)
        self._total      = len(jobs)
        self._done       = self._failed = 0
        self._overall(0, self._total)
        self._links_file = links_file
        self._max_workers = max(1, min(max_workers, 4))  # clamp 1-4
        self._qs.save(jobs)
        for j in jobs: self._queue.put(j)
        self._update()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._log("⏹  Stop signal sent — waiting for current download to finish…", "warning")

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def load_resume(self) -> list:
        return self._qs.load()

    # ── Internal ───────────────────────────────────────────────────────────
    def _worker(self):
        n = self._max_workers
        self._log(f"⚙️  Parallel downloads: {n}", "info")
        _stopped = False

        if n == 1:
            # ── Sequential mode (original behaviour) ──────────────────────
            while True:
                if self._stop.is_set():
                    self._log("🛑  Queue cancelled by user.", "error")
                    _stopped = True
                    while True:
                        try:
                            self._queue.get_nowait()
                            self._failed += 1
                        except queue.Empty:
                            break
                    break
                try:
                    job = self._queue.get_nowait()
                except queue.Empty:
                    break
                self._run_job(job)
        else:
            # ── Parallel mode — N workers run simultaneously ───────────────
            import concurrent.futures as _cf
            _lock = threading.Lock()

            def _run_one(job):
                if self._stop.is_set():
                    with _lock:
                        self._failed += 1
                    return
                self._run_job(job)

            jobs = []
            while True:
                try:
                    jobs.append(self._queue.get_nowait())
                except queue.Empty:
                    break

            with _cf.ThreadPoolExecutor(max_workers=n) as ex:
                # Assign each job a modulo slot (0 to n-1)
                futs = {ex.submit(_run_one, j): j for i, j in enumerate(jobs)}
                for fut in _cf.as_completed(futs):
                    if self._stop.is_set():
                        self._log("🛑  Queue cancelled by user.", "error")
                        _stopped = True
                        ex.shutdown(wait=False, cancel_futures=True)
                        break
                    try:
                        fut.result()
                    except Exception as exc:
                        self._log(f"❌  Worker error: {exc}", "error")

        # clear cards inside _run_job on success/fail
        pass
        self._update()
        self._log("━" * 44, "info")
        if not _stopped:
            self._log("✅  All queued downloads finished.", "success")
        self._qs.clear()

    def _run_job(self, job: dict):
        idx   = job["index"]; total = job["total"]
        url   = job["url"];   name  = job["output_name"]
        res   = job["resolution"]; odir = job["output_dir"]

        self._log(f"━" * 44, "info")
        self._log(f"📥  [{idx}/{total}]  {name}", "info")
        
        # Add tracking signals
        sigs = {"stop": threading.Event(), "pause": threading.Event()}
        self._signals[url] = sigs

        # Register UI Card
        self._add_card(url, name, sigs)

        # A lambda to bind this job's URL for progress updates
        _slot_prog = lambda info: self._vidprog(url, info)
        
        _slot_prog({"name": name})
        self._overall(self._done + self._failed, self._total)

        # ── Skip: history ────────────────────────────────────────
        if self._hist.is_downloaded(url):
            self._log(f"⏭  {name} already in history — skipping.", "warning")
            self._done += 1; self._update(); return

        # ── Skip: file exists ─────────────────────────────────────
        expected = os.path.join(odir, f"{re.sub(r'[^\\w\\s-]','',name).strip().replace(' ','_')}.mp4")
        if os.path.exists(expected):
            self._log(f"⏭  {name} file already exists — skipping.", "warning")
            self._hist.mark(url, name)
            self._done += 1; self._update(); return

        # ── Expiry check ─────────────────────────────────────────
        exp = get_expiry_info(url)
        if exp:
            tag = "error" if "EXPIRED" in exp else "warning"
            self._log(f"⏰  {exp}", tag)
            if "EXPIRED" in exp:
                self._failed += 1; self._update(); return

        # ── Network wait ─────────────────────────────────────────
        if not check_internet():
            self._log("🌐  No internet — waiting for connection…", "warning")
            while not check_internet():
                if self._stop.is_set(): return
                time.sleep(5)
            self._log("🌐  Connection restored.", "success")

        # ── Retry loop (with exponential backoff) ────────────────
        _BACKOFF = [0, 2, 5]   # seconds to wait before attempts 1, 2, 3
        success = False
        for attempt in range(1, self.MAX_RETRIES + 1):
            if self._stop.is_set() or sigs["stop"].is_set(): break
            if attempt > 1:
                wait_s = _BACKOFF[min(attempt - 1, len(_BACKOFF) - 1)]
                self._log(f"🔄  Retry {attempt-1}/{self.MAX_RETRIES-1}… (waiting {wait_s}s)", "warning")
                time.sleep(wait_s)

            # We no longer override sys.stdout here because it breaks parallel downloads
            # instead, pw_download uses progress_callback directly and stdout prints naturally
            try:
                if pw_download is None:
                    raise ImportError("pw_download.py not found.")
                pw_download.download_video(
                    url=url, output_name=name, resolution=res,
                    output_dir=odir, stop_event=sigs["stop"], pause_event=sigs["pause"],
                    progress_callback=_slot_prog, log_callback=self._log
                )
                success = True
            except Exception as e:
                self._log(f"❌  {e}", "error")
                if attempt == self.MAX_RETRIES:
                    self._log(f"💀  All {self.MAX_RETRIES} attempts failed: {name}", "error")

            if success: break

        if success:
            _slot_prog({'percent': 100, 'v_pct': 100, 'a_pct': 100, 'speed': '—', 'eta': '0:00', 'status': 'done', 'name': name})
            self._done += 1
            self._log(f"✅  Completed: {name}", "success")
            self._hist.mark(url, name)
            self._remove_from_links_file(url)
        else:
            _slot_prog({'percent': 0, 'v_pct': 0, 'a_pct': 0, 'speed': '—', 'eta': 'FAILED', 'status': 'failed', 'name': name})
            self._failed += 1

        done = self._done + self._failed
        self._overall(done, self._total)
        self._jobs = self._qs.remove(url, self._jobs)
        # Destroy card cleanly on finish
        self._kill_card(url)
        self._signals.pop(url, None)
        self._update()

    def _remove_from_links_file(self, url: str):
        """Remove this URL from the original links.txt file."""
        if not self._links_file or not os.path.exists(self._links_file):
            return
        try:
            with open(self._links_file, encoding="utf-8") as f:
                lines = f.readlines()
            # Keep lines whose URL part doesn't match
            base = url.split(" ||HEADERS|| ")[0].strip()
            kept = [l for l in lines if l.strip().split(" ||HEADERS|| ")[0].strip() != base]
            with open(self._links_file, "w", encoding="utf-8") as f:
                f.writelines(kept)
        except Exception:
            pass

    def _update(self):
        remaining = max(self._total - self._done - self._failed, 0)
        self._counter(self._total, self._done, self._failed, remaining)


# ══════════════════════════════════════════════════════════════════════════════
# H — Video Progress Card Widget
# ══════════════════════════════════════════════════════════════════════════════
class VideoProgressCard(ctk.CTkFrame):
    """Shows current video name, separate video+audio progress bars, speed, and ETA."""
    def __init__(self, master, **kw):
        super().__init__(master, fg_color="#0f1e35", corner_radius=8, **kw)

        self.columnconfigure(0, weight=0, minsize=28)
        self.columnconfigure(1, weight=1)
        self.columnconfigure(2, weight=0, minsize=45)

        self._name_var  = tk.StringVar(value="No active download")
        self._v_pct_var = tk.StringVar(value="")
        self._a_pct_var = tk.StringVar(value="")
        self._speed_var = tk.StringVar(value="")
        self._eta_var   = tk.StringVar(value="")

        # Header
        ctk.CTkLabel(self, text="⚙  Current Download",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#60a5fa").grid(row=0, column=0, columnspan=3,
                     padx=10, pady=(8, 2), sticky="w")
        ctk.CTkLabel(self, textvariable=self._name_var,
                     font=ctk.CTkFont(size=11), text_color="#cbd5e1",
                     anchor="w").grid(row=1, column=0, columnspan=3, padx=10, pady=(0, 6), sticky="ew")

        # ── Video bar row ─────────────────────────────────────────────────────
        ctk.CTkLabel(self, text="🎬", font=ctk.CTkFont(size=10), text_color="#64748b",
                     width=20, anchor="w").grid(row=2, column=0, padx=(10, 2), pady=(0, 4), sticky="w")
        self._v_bar = ctk.CTkProgressBar(self, height=9, corner_radius=4,
                                          fg_color="#1e293b", progress_color="#3b82f6")
        self._v_bar.set(0)
        self._v_bar.grid(row=2, column=1, padx=(0, 6), pady=(0, 4), sticky="ew")
        ctk.CTkLabel(self, textvariable=self._v_pct_var, font=ctk.CTkFont(family="monospace", size=10),
                     text_color="#3b82f6", width=42, anchor="e").grid(
                     row=2, column=2, padx=(0, 10), pady=(0, 4), sticky="e")

        # ── Audio bar row ─────────────────────────────────────────────────────
        ctk.CTkLabel(self, text="🔊", font=ctk.CTkFont(size=10), text_color="#64748b",
                     width=20, anchor="w").grid(row=3, column=0, padx=(10, 2), pady=(0, 6), sticky="w")
        self._a_bar = ctk.CTkProgressBar(self, height=9, corner_radius=4,
                                          fg_color="#1e293b", progress_color="#22c55e")
        self._a_bar.set(0)
        self._a_bar.grid(row=3, column=1, padx=(0, 6), pady=(0, 6), sticky="ew")
        ctk.CTkLabel(self, textvariable=self._a_pct_var, font=ctk.CTkFont(family="monospace", size=10),
                     text_color="#22c55e", width=42, anchor="e").grid(
                     row=3, column=2, padx=(0, 10), pady=(0, 6), sticky="e")

        # ── Speed / ETA row ───────────────────────────────────────────────────
        info_frame = ctk.CTkFrame(self, fg_color="transparent")
        info_frame.grid(row=4, column=0, columnspan=3, sticky="ew", padx=10, pady=(0, 8))
        info_frame.columnconfigure(0, weight=1)
        info_frame.columnconfigure(1, weight=1)
        
        ctk.CTkLabel(info_frame, textvariable=self._speed_var,
                     font=ctk.CTkFont(family="monospace", size=10),
                     text_color="#64748b", anchor="w").grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(info_frame, textvariable=self._eta_var,
                     font=ctk.CTkFont(family="monospace", size=10),
                     text_color="#64748b", anchor="w").grid(row=0, column=1, padx=(10,0), sticky="w")
                     
        # ── Controls row ──────────────────────────────────────────────────────
        self._ctrl_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._ctrl_frame.grid(row=5, column=0, columnspan=3, sticky="ew", padx=10, pady=(0, 6))
        self._btn_pause = ctk.CTkButton(self._ctrl_frame, text="⏸ Pause", width=50, height=20,
                                        font=ctk.CTkFont(size=9), command=self._toggle_pause,
                                        fg_color="#334155", hover_color="#475569")
        self._btn_pause.pack(side="left", padx=(0, 4))
        self._btn_stop = ctk.CTkButton(self._ctrl_frame, text="⏹ Stop", width=50, height=20,
                                       font=ctk.CTkFont(size=9), command=self._trigger_stop,
                                       fg_color="#7f1d1d", hover_color="#991b1b")
        self._btn_stop.pack(side="left")

        self.signals = None
        self._paused = False
        
    def bind_signals(self, sigs, stop_ui_cb=None):
        self.signals = sigs
        self._stop_ui_cb = stop_ui_cb

    def _toggle_pause(self):
        if not self.signals: return
        self._paused = not self._paused
        if self._paused:
            self.signals["pause"].set()
            self._btn_pause.configure(text="▶ Resume", fg_color="#16a34a", hover_color="#15803d")
        else:
            self.signals["pause"].clear()
            self._btn_pause.configure(text="⏸ Pause", fg_color="#334155", hover_color="#475569")

    def _trigger_stop(self):
        if not self.signals: return
        self.signals["stop"].set()
        self._btn_stop.configure(state="disabled")
        if hasattr(self, '_stop_ui_cb') and self._stop_ui_cb:
            self._stop_ui_cb()

    def update_progress(self, info: dict | None):
        """Called from DownloadManager (via after() on main thread)."""
        if info is None:
            self._name_var.set("No active download")
            self._v_pct_var.set(""); self._a_pct_var.set("")
            self._speed_var.set(""); self._eta_var.set("")
            self._v_bar.set(0); self._a_bar.set(0)
            return

        if "name" in info:
            self.set_name(info["name"])
            if len(info) == 1:
                return

        # If backend sends separate v_pct/a_pct use them; fall back to combined
        v_pct = info.get("v_pct", info.get("percent", 0))
        a_pct = info.get("a_pct", info.get("percent", 0))

        self._v_bar.set(v_pct / 100)
        self._a_bar.set(a_pct / 100)
        self._v_pct_var.set(f"{v_pct:.1f}%")
        self._a_pct_var.set(f"{a_pct:.1f}%")
        self._speed_var.set(f"⚡ {info.get('speed', '—')}")
        self._eta_var.set(f"⏱ ETA {info.get('eta', '—')}")

    def set_name(self, name: str):
        self._name_var.set(f"📹  {name}")
        self._v_bar.set(0); self._a_bar.set(0)
        self._v_pct_var.set("0%"); self._a_pct_var.set("0%")
        self._speed_var.set(""); self._eta_var.set("")


# ══════════════════════════════════════════════════════════════════════════════
# I — Link Preview Window
# ══════════════════════════════════════════════════════════════════════════════
class LinkPreviewWindow(ctk.CTkToplevel):
    """Popup window showing links as indexed table with Status column."""
    STATUS_COLORS = {"Pending": "#94a3b8", "Done": "#22c55e",
                     "Failed": "#f87171", "Skipped": "#fbbf24"}

    def __init__(self, master, links: list[str], history: DownloadHistory):
        super().__init__(master)
        self.title("Link Preview")
        self.geometry("740x440")
        self.resizable(True, True)

        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=14, pady=(12, 4))
        ctk.CTkLabel(hdr, text=f"📋  {len(links)} link(s) loaded",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#60a5fa").pack(side="left")

        # Column header row
        cols = ctk.CTkFrame(self, fg_color="#0f172a")
        cols.pack(fill="x", padx=14)
        for txt, w in [("#", 40), ("URL", 0), ("Expiry / Status", 200)]:
            ctk.CTkLabel(cols, text=txt, font=ctk.CTkFont(size=10, weight="bold"),
                         text_color="#475569", width=w, anchor="w").pack(
                         side="left", padx=(4, 0), pady=4)

        scr = ctk.CTkScrollableFrame(self, fg_color="#070d18")
        scr.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        scr.columnconfigure(1, weight=1)

        for i, url in enumerate(links, 1):
            clean = url.split(" ||HEADERS|| ")[0].strip()
            exp   = get_expiry_info(clean) or ""
            done  = history.is_downloaded(url)
            color = "#22c55e" if done else ("#f87171" if "EXPIRED" in exp else
                    "#fbbf24" if "NOW" in exp else "#94a3b8")

            row = ctk.CTkFrame(scr, fg_color="transparent")
            row.grid(row=i-1, column=0, columnspan=3, sticky="ew", pady=1)
            row.columnconfigure(1, weight=1)

            ctk.CTkLabel(row, text=str(i), width=36,
                         font=ctk.CTkFont(size=10), text_color="#475569",
                         anchor="e").grid(row=0, column=0, padx=(0, 6))
            url_txt = clean[:70] + "…" if len(clean) > 70 else clean
            ctk.CTkLabel(row, text=url_txt,
                         font=ctk.CTkFont(family="monospace", size=9),
                         text_color="#cbd5e1", anchor="w").grid(row=0, column=1, sticky="ew")
            status = "✅ Done" if done else (f"⚠ {exp}" if exp else "⏳ Pending")
            ctk.CTkLabel(row, text=status, width=190,
                         font=ctk.CTkFont(size=9), text_color=color,
                         anchor="w").grid(row=0, column=2, padx=(6, 0))


# ══════════════════════════════════════════════════════════════════════════════
# J — Main Application Window
# ══════════════════════════════════════════════════════════════════════════════
class PWDownloaderApp(ctk.CTk):
    """Main application window — 12 UI sections across sidebar + log panel."""
    RESOLUTIONS = ["Auto", "1080p", "720p", "480p", "360p", "240p"]
    TAGS = {"success": "#22c55e", "error": "#f87171",
            "warning": "#fbbf24", "info": "#94a3b8"}

    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.title("PW Video Downloader")
        self.geometry("950x640")
        self.minsize(860, 580)

        # ── Set window icon (app_icon.jpeg from updated folder) ────────────────
        if _PIL_OK:
            try:
                _icon_candidates = [
                    os.path.join(APP_DIR, 'updated ', 'app_icon.jpeg'),
                    os.path.join(APP_DIR, 'updated ', 'app_icon.jpg'),
                    os.path.join(APP_DIR, 'updated', 'app_icon.jpeg'),
                    os.path.join(APP_DIR, 'updated', 'app_icon.jpg'),
                    os.path.join(APP_DIR, 'app_icon.jpeg'),
                    os.path.join(APP_DIR, 'app_icon.jpg'),
                ]
                for _p in _icon_candidates:
                    if os.path.exists(_p):
                        _img = Image.open(_p)
                        _img = _img.resize((64, 64), Image.LANCZOS)
                        self._icon_photo = ImageTk.PhotoImage(_img)  # keep ref!
                        self.iconphoto(True, self._icon_photo)
                        break
            except Exception:
                pass  # icon failure is non-fatal

        self._cfg   = ConfigManager()
        self._hist  = DownloadHistory()
        self._links : list[str] = []
        self._preview_win = None

        self._mgr = DownloadManager(
            log_cb     = self._log,
            progress_cb= self._on_progress,
            counter_cb = self._on_counter,
            overall_cb = self._on_overall,
            vidprog_cb = self._on_vidprog,
            add_card_cb= self._add_video_card,
            remove_card_cb= self._remove_video_card,
        )

        self._build_ui()
        self._load_config()
        self._startup()

    # ── Startup ──────────────────────────────────────────────────────────────
    def _startup(self):
        odir = self._cfg.get("last_output_folder")
        n = cleanup_temp_folders(odir)
        if n:
            self._log(f"🧹  Cleaned up {n} leftover temp folder(s).", "warning")

        # Auto-resume check
        pending = self._mgr.load_resume()
        if pending:
            self._log(f"♻️  Found {len(pending)} pending job(s) from last session.", "warning")
            if messagebox.askyesno("Auto Resume",
                    f"Resume {len(pending)} pending download(s) from last session?"):
                self._start_jobs(pending)

    # ── Build UI ─────────────────────────────────────────────────────────────
    def _build_ui(self):
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()
        self._build_log_panel()
        # Fix two-finger / mousewheel scroll on Linux for the sidebar
        self.after(100, lambda: self._enable_scroll(self._sidebar))

    # ── SIDEBAR ───────────────────────────────────────────────────────────────
    def _build_sidebar(self):
        sb = ctk.CTkScrollableFrame(self, width=370, corner_radius=0,
                                    fg_color=("#1e293b","#0f172a"))
        sb.grid(row=0, column=0, sticky="nsew")
        sb.grid_columnconfigure(0, weight=1)
        self._sidebar = sb  # kept for scroll binding

        # Header
        ctk.CTkLabel(sb, text="⚡ PW Video Downloader",
                     font=ctk.CTkFont(size=18, weight="bold"),
                     text_color="#60a5fa").grid(row=0, column=0, padx=16, pady=(20,2), sticky="w")
        ctk.CTkLabel(sb, text="Physics Wallah · Batch Downloader",
                     font=ctk.CTkFont(size=11), text_color="#475569").grid(
                     row=1, column=0, padx=16, pady=(0,14), sticky="w")
        self._div(sb, 2)

        r = 3
        # Section 1 — Links File
        r = self._slabel(sb, r, "📁  Links File (.txt)")
        f1 = ctk.CTkFrame(sb, fg_color="transparent")
        f1.grid(row=r, column=0, padx=12, pady=(0,4), sticky="ew"); f1.columnconfigure(0, weight=1)
        r += 1
        self._links_var = tk.StringVar(value="No file selected…")
        ctk.CTkEntry(f1, textvariable=self._links_var, height=32, state="readonly",
                     font=ctk.CTkFont(size=10)).grid(row=0, column=0, sticky="ew", padx=(0,6))
        ctk.CTkButton(f1, text="Browse", width=76, height=32, command=self._browse_links,
                      fg_color="#2563eb", hover_color="#1d4ed8").grid(row=0, column=1)
        ctk.CTkButton(sb, text="👁  Preview Links", height=30, command=self._preview,
                      fg_color="transparent", border_color="#334155", border_width=1,
                      text_color="#94a3b8", hover_color="#1e293b").grid(
                      row=r, column=0, padx=12, pady=(0,6), sticky="ew"); r += 1

        self._div(sb, r); r += 1

        # Section 2 — Output Folder
        r = self._slabel(sb, r, "💾  Download Folder")
        f2 = ctk.CTkFrame(sb, fg_color="transparent")
        f2.grid(row=r, column=0, padx=12, pady=(0,6), sticky="ew"); f2.columnconfigure(0, weight=1)
        r += 1
        self._dir_var = tk.StringVar()
        ctk.CTkEntry(f2, textvariable=self._dir_var, height=32,
                     font=ctk.CTkFont(size=10)).grid(row=0, column=0, sticky="ew", padx=(0,6))
        ctk.CTkButton(f2, text="Browse", width=76, height=32, command=self._browse_dir,
                      fg_color="#2563eb", hover_color="#1d4ed8").grid(row=0, column=1)

        self._div(sb, r); r += 1

        # Section 3 — Link Selection
        r = self._slabel(sb, r, "🔢  Select Links To Download")
        self._sel_var = tk.StringVar(value="all")
        ctk.CTkEntry(sb, textvariable=self._sel_var, height=32,
                     placeholder_text="all  |  3  |  3,4,5  |  5-8  |  5-  |  -3",
                     font=ctk.CTkFont(size=12)).grid(row=r, column=0, padx=12, pady=(0,2), sticky="ew"); r += 1
        ctk.CTkLabel(sb, text="   all | N | N,M | N-M | N- | -N",
                     font=ctk.CTkFont(size=10), text_color="#475569").grid(
                     row=r, column=0, padx=12, pady=(0,4), sticky="w"); r += 1

        self._div(sb, r); r += 1

        # Section 4 — Resolution
        r = self._slabel(sb, r, "🎞  Resolution")
        self._res_var = tk.StringVar(value="Auto")
        ctk.CTkOptionMenu(sb, values=self.RESOLUTIONS, variable=self._res_var, height=32,
                          fg_color="#1e293b", button_color="#2563eb",
                          button_hover_color="#1d4ed8", dropdown_fg_color="#0f172a",
                          font=ctk.CTkFont(size=12)).grid(
                          row=r, column=0, padx=12, pady=(0,6), sticky="ew"); r += 1

        self._div(sb, r); r += 1

        r = self._slabel(sb, r, "✏️  Filename Prefix")
        self._pfx_var = tk.StringVar(value="lecture")
        ctk.CTkEntry(sb, textvariable=self._pfx_var, height=32,
                     placeholder_text="lecture  →  lecture_01.mp4",
                     font=ctk.CTkFont(size=12)).grid(row=r, column=0, padx=12, pady=(0,2), sticky="ew"); r += 1
        ctk.CTkLabel(sb, text="   Empty → video_01.mp4",
                     font=ctk.CTkFont(size=10), text_color="#475569").grid(
                     row=r, column=0, padx=12, pady=(0,6), sticky="w"); r += 1

        self._div(sb, r); r += 1

        # Section 6 — Parallel Downloads
        r = self._slabel(sb, r, "⚡  Parallel Downloads")
        par_frame = ctk.CTkFrame(sb, fg_color="transparent")
        par_frame.grid(row=r, column=0, padx=12, pady=(0,6), sticky="ew")
        par_frame.columnconfigure(1, weight=1)
        r += 1
        self._par_var = tk.IntVar(value=1)
        ctk.CTkLabel(par_frame, text="Videos at once:",
                     font=ctk.CTkFont(size=11), text_color="#94a3b8").grid(
                     row=0, column=0, padx=(0,8), sticky="w")
        ctk.CTkSegmentedButton(
            par_frame,
            values=["1", "2", "3", "4"],
            variable=tk.StringVar(value="1"),
            command=lambda v: self._par_var.set(int(v)),
            font=ctk.CTkFont(size=12),
            selected_color="#2563eb",
            selected_hover_color="#1d4ed8",
            unselected_color="#1e293b",
            unselected_hover_color="#334155",
            text_color="#e2e8f0",
            height=30,
        ).grid(row=0, column=1, sticky="ew")
        ctk.CTkLabel(sb, text="   ⚠ Use 2-4 only on fast connections",
                     font=ctk.CTkFont(size=10), text_color="#475569").grid(
                     row=r, column=0, padx=12, pady=(0,4), sticky="w"); r += 1

        self._div(sb, r); r += 1

        # Sections 6-12 (buttons + counters)
        self._start_btn = ctk.CTkButton(sb, text="▶  START DOWNLOAD", height=42,
                                         font=ctk.CTkFont(size=14, weight="bold"),
                                         fg_color="#16a34a", hover_color="#15803d",
                                         command=self._on_start)
        self._start_btn.grid(row=r, column=0, padx=12, pady=(6,3), sticky="ew"); r += 1
        self._stop_btn = ctk.CTkButton(sb, text="⏹  STOP DOWNLOAD", height=36,
                                        font=ctk.CTkFont(size=13),
                                        fg_color="#991b1b", hover_color="#7f1d1d",
                                        command=self._on_stop, state="disabled")
        self._stop_btn.grid(row=r, column=0, padx=12, pady=(0,3), sticky="ew"); r += 1
        ctk.CTkButton(sb, text="🗑  Clear Logs", height=30, command=self._clear_logs,
                      fg_color="transparent", border_color="#334155", border_width=1,
                      text_color="#64748b", hover_color="#1e293b").grid(
                      row=r, column=0, padx=12, pady=(0,10), sticky="ew"); r += 1

        self._div(sb, r); r += 1

        # Counters (Section 11)
        cbox = ctk.CTkFrame(sb, fg_color="#0a1628", corner_radius=8)
        cbox.grid(row=r, column=0, padx=12, pady=8, sticky="ew"); r += 1
        cbox.columnconfigure((0,1,2,3), weight=1)
        self._cvars = [tk.StringVar(value="0") for _ in range(4)]
        for col, (lbl, clr) in enumerate(zip(
                ["Total","Done","Failed","Left"],
                ["#60a5fa","#22c55e","#f87171","#fbbf24"])):
            ctk.CTkLabel(cbox, text=lbl, font=ctk.CTkFont(size=10),
                         text_color="#475569").grid(row=0, column=col, padx=8, pady=(8,0))
            ctk.CTkLabel(cbox, textvariable=self._cvars[col],
                         font=ctk.CTkFont(size=20, weight="bold"),
                         text_color=clr).grid(row=1, column=col, padx=8, pady=(0,8))

    # ── LOG PANEL ─────────────────────────────────────────────────────────────
    def _build_log_panel(self):
        p = ctk.CTkFrame(self, fg_color=("#0f172a","#070d18"), corner_radius=0)
        p.grid(row=0, column=1, sticky="nsew")
        p.grid_columnconfigure(0, weight=1)
        p.grid_rowconfigure(1, weight=1)

        # Header
        hdr = ctk.CTkFrame(p, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=12, pady=(12,4))
        ctk.CTkLabel(hdr, text="📋  Download Log",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#60a5fa").pack(side="left")

        # Log textbox (Section 8)
        self._log_box = ctk.CTkTextbox(p, font=ctk.CTkFont(family="monospace", size=11),
                                        fg_color="#070d18", text_color="#94a3b8",
                                        corner_radius=6, wrap="word", state="disabled")
        self._log_box.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0,6))
        for tag, clr in self.TAGS.items():
            self._log_box._textbox.tag_configure(tag, foreground=clr)

        # Video Progress Cards (Section 9) — dynamic grid
        self._prog_container = ctk.CTkFrame(p, fg_color="transparent")
        self._prog_container.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0,6))
        self._prog_container.columnconfigure((0,1), weight=1, uniform="col")
        self._prog_container.rowconfigure((0,1), weight=0)
        
        self._prog_cards = {} # url -> VideoProgressCard

        # Overall progress bar (Section 10)
        pf = ctk.CTkFrame(p, fg_color="transparent")
        pf.grid(row=3, column=0, sticky="ew", padx=12, pady=(0,4)); pf.columnconfigure(1, weight=1)
        self._ovr_lbl = ctk.CTkLabel(pf, text="0 / 0  downloads",
                                      font=ctk.CTkFont(size=11), text_color="#475569",
                                      width=120, anchor="w")
        self._ovr_lbl.grid(row=0, column=0, sticky="w", padx=(0,8))
        self._ovr_bar = ctk.CTkProgressBar(pf, height=12, corner_radius=6,
                                            fg_color="#1e293b", progress_color="#2563eb")
        self._ovr_bar.set(0)
        self._ovr_bar.grid(row=0, column=1, sticky="ew")

        # Status bar
        self._status = tk.StringVar(value="Ready")
        ctk.CTkLabel(p, textvariable=self._status, font=ctk.CTkFont(size=10),
                     text_color="#334155", anchor="w").grid(
                     row=4, column=0, sticky="ew", padx=14, pady=(0,8))

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _enable_scroll(self, scrollable_frame: ctk.CTkScrollableFrame):
        """
        Fix two-finger trackpad / mousewheel scrolling for CTkScrollableFrame.
        Recursively binds scroll events on all child widgets so they forward
        to the scrollable frame's internal canvas (Linux: Button-4/5, Win/Mac: MouseWheel).
        """
        canvas = scrollable_frame._parent_canvas

        def _scroll(event):
            if event.num == 4 or getattr(event, 'delta', 0) > 0:
                canvas.yview_scroll(-1, "units")
            elif event.num == 5 or getattr(event, 'delta', 0) < 0:
                canvas.yview_scroll(1, "units")

        def _bind(widget):
            try:
                widget.bind("<Button-4>",   _scroll, add="+")
                widget.bind("<Button-5>",   _scroll, add="+")
                widget.bind("<MouseWheel>", _scroll, add="+")
            except NotImplementedError:
                pass  # some CTk widgets (e.g. CTkSegmentedButton) don't support bind
            for child in widget.winfo_children():
                _bind(child)

        _bind(scrollable_frame)

    def _div(self, parent, row):
        ctk.CTkFrame(parent, height=1, fg_color="#1e3a5f",
                     corner_radius=0).grid(row=row, column=0, padx=12, pady=4, sticky="ew")

    def _slabel(self, parent, row, text):
        ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#cbd5e1").grid(row=row, column=0, padx=16, pady=(12,2), sticky="w")
        return row + 1

    # ── Config load ───────────────────────────────────────────────────────────
    def _load_config(self):
        lf = self._cfg.get("last_links_file")
        if lf and os.path.exists(lf):
            self._links_var.set(lf)
            self._load_links(lf)
        self._dir_var.set(self._cfg.get("last_output_folder"))
        self._res_var.set(self._cfg.get("resolution"))
        self._pfx_var.set(self._cfg.get("prefix"))
        self._sel_var.set(self._cfg.get("selection"))

    # ── Browse / file loading ─────────────────────────────────────────────────
    def _browse_links(self):
        p = filedialog.askopenfilename(title="Select links.txt",
                                        filetypes=[("Text files","*.txt"),("All","*.*")])
        if p:
            self._links_var.set(p)
            self._cfg.set("last_links_file", p)
            self._load_links(p)

    def _load_links(self, path: str):
        try:
            with open(path, encoding="utf-8") as f:
                raw = [l.strip() for l in f if l.strip()]
            # Deduplicate (preserve order) + validate
            seen, valid = set(), []
            for line in raw:
                if not is_valid_url(line):
                    continue
                key = line.split(" ||HEADERS|| ")[0].strip()
                if key not in seen:
                    seen.add(key); valid.append(line)
            removed_dup  = len(raw) - len(valid) - (len(raw) - sum(1 for l in raw if is_valid_url(l)))
            removed_inv  = len(raw) - len(valid) - removed_dup
            self._links  = valid
            self._log(f"📂  Loaded {len(valid)} valid link(s) from {os.path.basename(path)}", "success")
            if removed_inv:  self._log(f"⚠️   Removed {removed_inv} invalid line(s).", "warning")
            if removed_dup:  self._log(f"⚠️   Removed {removed_dup} duplicate(s).", "warning")
            self._status.set(f"Loaded {len(valid)} links from {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("File Error", str(e))

    def _browse_dir(self):
        d = filedialog.askdirectory(title="Select output folder")
        if d:
            self._dir_var.set(d); self._cfg.set("last_output_folder", d)

    # ── Preview (Section 1 button) ────────────────────────────────────────────
    def _preview(self):
        if not self._links:
            messagebox.showwarning("No Links", "Load a links.txt file first."); return
        if self._preview_win and self._preview_win.winfo_exists():
            self._preview_win.lift(); return
        self._preview_win = LinkPreviewWindow(self, self._links, self._hist)

    # ── Start / Stop ──────────────────────────────────────────────────────────
    def _on_start(self):
        if pw_download is None:
            messagebox.showerror("Backend Missing", "pw_download.py not found."); return
        lf = self._links_var.get()
        if not self._links or lf == "No file selected…":
            messagebox.showerror("No Links", "Browse and select a links.txt file first."); return
        if self._mgr.is_running():
            messagebox.showinfo("Running", "A download is already in progress."); return
        self._load_links(lf)  # reload fresh
        if not self._links: return

        try:
            indices = parse_link_selection(self._sel_var.get(), len(self._links))
        except ValueError as e:
            messagebox.showerror("Invalid Selection", str(e)); return

        odir = self._dir_var.get().strip()
        if not odir:
            messagebox.showerror("No Folder", "Choose an output folder."); return
        try: os.makedirs(odir, exist_ok=True)
        except Exception as e:
            messagebox.showerror("Folder Error", str(e)); return

        pfx = self._pfx_var.get().strip() or "video"
        res = self._res_var.get()
        self._cfg.set("prefix", pfx); self._cfg.set("resolution", res)
        self._cfg.set("selection", self._sel_var.get())

        jobs = [{"url": self._links[i-1], "output_name": f"{pfx}_{n:02d}",
                 "resolution": res, "output_dir": odir, "index": n, "total": len(indices)}
                for n, i in enumerate(indices, 1)]

        par = self._par_var.get()
        self._log(f"\n🚀  Starting {len(jobs)} download(s)  [res={res}  prefix={pfx}  parallel={par}]", "success")
        
        self._start_btn.configure(state="disabled")
        self._start_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        self._mgr.start(jobs, links_file=lf, max_workers=par)
        self._poll()

    def _start_jobs(self, jobs: list):
        """Start a resumed job list directly (uses current par_var setting)."""
        if not jobs: return
        self._start_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        par = getattr(self, '_par_var', None)
        par_val = par.get() if par else 1
        
        self._start_btn.configure(state="disabled")
        self._mgr.start(jobs, max_workers=par_val)
        self._poll()

    def _on_stop(self):
        self._mgr.stop(); self._stop_btn.configure(state="disabled")

    def _poll(self):
        if self._mgr.is_running():
            self.after(400, self._poll)
        else:
            self._start_btn.configure(state="normal")
            self._stop_btn.configure(state="disabled")
            self._status.set("Ready")

    # ── Log callbacks (Section 8) ─────────────────────────────────────────────
    def _log(self, msg: str, tag: str = "info"):
        # ── Write to GUI log box ──────────────────────────────────────────────
        def _w():
            self._log_box.configure(state="normal")
            self._log_box._textbox.insert("end", msg + "\n", tag)
            self._log_box._textbox.see("end")
            self._log_box.configure(state="disabled")
        self.after(0, _w)
        # ── Write to log file (with timestamp) ───────────────────────────────
        try:
            log_path = os.path.join(
                self._cfg.get("last_output_folder") or APP_DIR, "log.txt"
            )
            ts = datetime.now().strftime("%H:%M:%S")
            with open(log_path, "a", encoding="utf-8") as lf:
                lf.write(f"[{ts}] {msg}\n")
        except Exception:
            pass  # log file write failure is non-fatal

    def _clear_logs(self):
        self._log_box.configure(state="normal")
        self._log_box.delete("0.0", "end")
        self._log_box.configure(state="disabled")

    # ── Progress callbacks ────────────────────────────────────────────────────
    def _on_progress(self, info: dict | None):  # for ProgressInterceptor compatibility
        pass  # individual progress comes via _on_vidprog

    def _add_video_card(self, url: str, name: str, sigs: dict):
        def _add():
            if url in self._prog_cards: return
            c = VideoProgressCard(self._prog_container)
            index = len(self._prog_cards)
            c.grid(row=index//2, column=index%2, sticky="nsew", padx=4, pady=4)
            c.set_name(name)
            c.bind_signals(sigs, stop_ui_cb=lambda: self._remove_video_card(url))
            self._prog_cards[url] = c
            self._regrid_cards()
        self.after(0, _add)

    def _remove_video_card(self, url: str):
        def _rem():
            c = self._prog_cards.pop(url, None)
            if c:
                c.grid_remove()
                c.destroy()
                self._regrid_cards()
        self.after(0, _rem)

    def _regrid_cards(self):
        # Reposition all current cards to fill up slots sequentially
        for i, (u, c) in enumerate(list(self._prog_cards.items())):
            c.grid(row=i//2, column=i%2, sticky="nsew", padx=4, pady=4)

    def _on_vidprog(self, url: str, info: dict | None):
        if url not in self._prog_cards:
            return
            
        card = self._prog_cards[url]
        if info is None:
            # Flash 100% / done state for 2 seconds, then reset
            def _flash():
                if url in self._prog_cards:
                    card.update_progress({'percent': 100, 'speed': '✅ Done', 'eta': '—', 'status': 'done'})
            self.after(0, _flash)
        else:
            self.after(0, lambda i=info: card.update_progress(i))

    def _on_overall(self, done: int, total: int):
        def _u():
            frac = done / total if total else 0
            self._ovr_bar.set(frac)
            self._ovr_lbl.configure(text=f"{done} / {total}  downloads")
            self._status.set(f"Downloading… {done}/{total}  ({int(frac*100)}%)")
        self.after(0, _u)

    def _on_counter(self, total, done, failed, remaining):
        def _u():
            for var, val in zip(self._cvars, [total, done, failed, remaining]):
                var.set(str(val))
        self.after(0, _u)


# ══════════════════════════════════════════════════════════════════════════════


    def _on_mousewheel(self, event, direction=None):
        if str(self.focus_get()) == ".": return
        
        # In Linux, Button-4 is up (negative direction in Tkinter terms)
        if event.num == 4:
            direction = -1
        elif event.num == 5:
            direction = 1
            
        widget = self.winfo_containing(event.x_root, event.y_root)
        if not widget: return
        
        # Traverse up to find a scrollable widget
        w = widget
        while w:
            if hasattr(w, 'yview_scroll'):
                w.yview_scroll(direction, "units")
                return
            if w == self: break
            w = w.master


# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════
def main():
    app = PWDownloaderApp()
    app.mainloop()

if __name__ == "__main__":
    main()
