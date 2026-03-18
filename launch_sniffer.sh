#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  Media URL Sniffer — Full Launch Script
#  Starts mitmproxy sniffer + opens Firefox (mitmproxy profile)
#  Terminal prompt returns IMMEDIATELY — Firefox gets full keyboard focus.
#
#  Usage: bash launch_sniffer.sh          ← start
#         bash launch_sniffer.sh stop     ← stop sniffer
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PORT=8080
LINKS_FILE="$SCRIPT_DIR/links.txt"
LOG_FILE="$SCRIPT_DIR/sniffer.log"
PID_FILE="$SCRIPT_DIR/sniffer.pid"
FIREFOX_PROFILE="mitmproxy"

# ── Stop command ──────────────────────────────────────────────────────────────
if [[ "$1" == "stop" ]]; then
    if [[ -f "$PID_FILE" ]]; then
        kill $(cat "$PID_FILE") 2>/dev/null
        rm -f "$PID_FILE"
        echo "  [+] Sniffer stopped."
    else
        pkill -f "mitmdump.*url_sniffer" 2>/dev/null && echo "  [+] Stopped." || echo "  [!] Not running."
    fi
    # Log file clear karo
    > "$LOG_FILE"
    echo "  [🗑] sniffer.log cleared."
    exit 0
fi

# ── Banner ────────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║         Media URL Sniffer — Launching                ║"
echo "╠══════════════════════════════════════════════════════╣"
echo "║  Proxy   : 127.0.0.1:$PORT                            ║"
echo "║  Browser : Firefox (profile: $FIREFOX_PROFILE)        ║"
echo "║  Output  : $LINKS_FILE"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── Start sniffer in background (logs to file only) ───────────────────────────
nohup mitmdump \
    -s "$SCRIPT_DIR/url_sniffer.py" \
    --listen-port $PORT \
    --ssl-insecure \
    --set block_global=false \
    > "$LOG_FILE" 2>&1 &

MITM_PID=$!
echo "$MITM_PID" > "$PID_FILE"
echo "  [+] Sniffer started (PID: $MITM_PID)"
echo "  [i] Raw logs → sniffer.log"
sleep 1

# ── Launch Firefox in X11 mode (fixes Wayland keyboard input issue) ───────────
# MOZ_ENABLE_WAYLAND=0  → force X11 backend so typing works normally
# GDK_BACKEND=x11       → GTK also uses X11
# nohup + setsid        → fully detached, terminal prompt returns immediately
echo "  [+] Opening Firefox (X11 mode, profile: $FIREFOX_PROFILE)..."
nohup env MOZ_ENABLE_WAYLAND=0 GDK_BACKEND=x11 \
    setsid firefox -P "$FIREFOX_PROFILE" --no-remote \
    > /dev/null 2>&1 &

echo "$!" >> "$PID_FILE"
disown
echo "  [+] Firefox started ✓"
echo ""
echo "  ✅ Keyboard will now work normally in Firefox."
echo "  📄 Captured URLs → links.txt"
echo ""
echo "  👇 Watch captured URLs live (open new terminal):"
echo "     tail -f $LINKS_FILE"
echo ""
echo "  🛑 Stop sniffer: bash launch_sniffer.sh stop"
echo ""
