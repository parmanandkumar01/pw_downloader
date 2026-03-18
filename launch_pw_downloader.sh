#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  PW Video Downloader — Batch from links.txt
#  links.txt se master playlist URLs fetch karke download karta hai.
#
#  Usage:
#    bash launch_pw_downloader.sh
#    (Script khud prefix aur resolution poochh lega)
#
#  Ya directly args deke:
#    bash launch_pw_downloader.sh "Lecture" 720
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LINKS_FILE="$SCRIPT_DIR/links.txt"
PY_SCRIPT="$SCRIPT_DIR/pw_download.py"

# ── Colors ────────────────────────────────────────────────────────────────────
GREEN="\033[92m"
YELLOW="\033[93m"
CYAN="\033[96m"
RED="\033[91m"
BOLD="\033[1m"
RESET="\033[0m"

echo ""
echo -e "╔══════════════════════════════════════════════════════╗"
echo -e "║       ${BOLD}PW Video Downloader — Batch Mode${RESET}              ║"
echo -e "╚══════════════════════════════════════════════════════╝"
echo ""

# ── Sanity checks ─────────────────────────────────────────────────────────────
if [[ ! -f "$LINKS_FILE" ]]; then
    echo -e "${RED}[✗] links.txt not found: $LINKS_FILE${RESET}"
    exit 1
fi

if [[ ! -f "$PY_SCRIPT" ]]; then
    echo -e "${RED}[✗] pw_download.py not found: $PY_SCRIPT${RESET}"
    exit 1
fi

# ── Extract URLs from links.txt ───────────────────────────────────────────────
# Full line lena hai (URL + optional ||HEADERS|| suffix for auth)
mapfile -t ALL_URLS < <(grep -E '^https?://' "$LINKS_FILE")

if [[ ${#ALL_URLS[@]} -eq 0 ]]; then
    echo -e "${YELLOW}[!] links.txt mein koi URL nahi mila.${RESET}"
    echo -e "    Pehle sniffer chalao aur video play karo."
    exit 1
fi

echo -e "${CYAN}[i] links.txt mein ${#ALL_URLS[@]} URL(s) mili:${RESET}"
echo ""
for i in "${!ALL_URLS[@]}"; do
    num=$((i + 1))
    url="${ALL_URLS[$i]}"
    # Display mein sirf URL part dikhao (||HEADERS|| suffix chupa do)
    url_display="${url%% ||HEADERS||*}"
    short="${url_display:0:80}"
    [[ ${#url_display} -gt 80 ]] && short="${short}..."
    has_headers=""
    [[ "$url" == *" ||HEADERS||"* ]] && has_headers=" ${CYAN}[🔑auth]${RESET}"
    echo -e "  ${BOLD}[$num]${RESET} $short${has_headers}"
done
echo ""

# ── Select URLs to download ───────────────────────────────────────────────────
if [[ ${#ALL_URLS[@]} -eq 1 ]]; then
    SELECTED_INDICES=(0)
    echo -e "${GREEN}[+] Sirf ek URL hai — automatically select ho gayi.${RESET}"
else
    echo -e "${CYAN}Konsi URLs download karni hain?${RESET}"
    echo -e "  Enter: numbers (e.g. ${BOLD}1 3 5${RESET}), ranges (e.g. ${BOLD}3-5${RESET} ya ${BOLD}3-${RESET}), direct link, ${BOLD}all${RESET} for sab, ya ${BOLD}q${RESET} to quit"
    read -r selection

    if [[ "$selection" == "q" ]]; then
        echo "Cancelled."
        exit 0
    fi

    SELECTED_INDICES=()
    if [[ "$selection" == "all" ]]; then
        for i in "${!ALL_URLS[@]}"; do SELECTED_INDICES+=($i); done
    elif [[ "$selection" =~ ^http ]]; then
        # Handle direct pasted link by appending to ALL_URLS
        ALL_URLS+=("$selection")
        SELECTED_INDICES+=($((${#ALL_URLS[@]} - 1)))
        echo -e "${GREEN}[+] Custom link added to list.${RESET}"
    else
        for num in $selection; do
            if [[ "$num" =~ ^([0-9]+)-([0-9]+)$ ]]; then
                start=${BASH_REMATCH[1]}
                end=${BASH_REMATCH[2]}
                for (( i = start - 1; i < end; i++ )); do
                    if (( i >= 0 && i < ${#ALL_URLS[@]} )); then
                        SELECTED_INDICES+=($i)
                    fi
                done
            elif [[ "$num" =~ ^([0-9]+)-$ ]]; then
                start=${BASH_REMATCH[1]}
                for (( i = start - 1; i < ${#ALL_URLS[@]}; i++ )); do
                    SELECTED_INDICES+=($i)
                done
            elif [[ "$num" =~ ^[0-9]+$ ]] && (( num >= 1 && num <= ${#ALL_URLS[@]} )); then
                SELECTED_INDICES+=($((num - 1)))
            else
                echo -e "${YELLOW}[!] Invalid selection: $num — skip kar raha hoon${RESET}"
            fi
        done
    fi
fi

if [[ ${#SELECTED_INDICES[@]} -eq 0 ]]; then
    echo -e "${RED}[✗] Koi valid URL select nahi hui.${RESET}"
    exit 1
fi

# ── Resolution input ──────────────────────────────────────────────────────────
if [[ -n "$2" ]]; then
    RESOLUTION="$2"
else
    echo ""
    echo -e "${CYAN}Video resolution (e.g. 1080, 720, 480, 360) [default: 720]:${RESET}"
    read -r RESOLUTION
    RESOLUTION="${RESOLUTION:-720}"
fi

if ! [[ "$RESOLUTION" =~ ^[0-9]+$ ]]; then
    echo -e "${YELLOW}[!] Invalid resolution '$RESOLUTION' — 720 use karunga.${RESET}"
    RESOLUTION=720
fi

# ── Output filename prefix input ──────────────────────────────────────────────
if [[ -n "$1" ]]; then
    PREFIX="$1"
else
    echo ""
    echo -e "${CYAN}Output file name prefix (e.g. 'Lecture', 'Class'):${RESET}"
    read -r PREFIX
    PREFIX="${PREFIX:-video}"
fi

echo ""
echo -e "${GREEN}[✓] Settings:${RESET}"
echo -e "    Prefix     : ${BOLD}$PREFIX${RESET}"
echo -e "    Resolution : ${BOLD}${RESOLUTION}p${RESET}"
echo -e "    URL(s)     : ${BOLD}${#SELECTED_INDICES[@]} selected${RESET}"
echo ""

# ── Auto-numbering helper ─────────────────────────────────────────────────────
# Existing files check karke next available number deta hai
next_number() {
    local prefix="$1"
    local dir="$SCRIPT_DIR/Download"
    local n=1
    # Clean prefix (spaces to underscores, remove special chars, squeeze underscores, drop trailing underscore)
    local safe_prefix
    safe_prefix=$(echo "$prefix" | sed 's/[^a-zA-Z0-9 _-]//g' | tr ' ' '_' | tr -s '_' | sed 's/_$//')

    while [[ -f "$dir/${safe_prefix}_${n}.mp4" ]]; do
        n=$((n + 1))
    done
    echo "$n"
}

# ── Internet Wait Helper ──────────────────────────────────────────────────────
wait_for_internet() {
    while ! ping -c 1 -W 2 8.8.8.8 >/dev/null 2>&1; do
        echo -e "\n${RED}[!] Internet diconnected. Waiting for connection...${RESET}"
        sleep 5
    done
}

# ── Download loop ─────────────────────────────────────────────────────────────
SUCCESS=0
FAILED=0

for idx in "${SELECTED_INDICES[@]}"; do
    url="${ALL_URLS[$idx]}"
    num=$((idx + 1))

    # Auto number generate karo
    file_num=$(next_number "$PREFIX")
    safe_prefix=$(echo "$PREFIX" | sed 's/[^a-zA-Z0-9 _-]//g' | tr ' ' '_' | tr -s '_' | sed 's/_$//')
    output_name="${safe_prefix}_${file_num}"

    echo -e "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo -e "${BOLD}[URL $num / ${#ALL_URLS[@]}]${RESET} Downloading..."
    echo -e "  Output : ${CYAN}${output_name}.mp4${RESET}"
    echo -e "  Res    : ${CYAN}${RESOLUTION}p${RESET}"
    echo ""

    wait_for_internet

    python3 "$PY_SCRIPT" "$url" "$output_name" "$RESOLUTION"
    exit_code=$?

    if [[ $exit_code -eq 0 ]]; then
        echo -e "\n${GREEN}✅ Saved: ${output_name}.mp4${RESET}"
        SUCCESS=$((SUCCESS + 1))
    else
        echo -e "\n${RED}❌ Failed (exit code $exit_code): URL $num${RESET}"
        FAILED=$((FAILED + 1))
    fi

    # Thoda pause multiple downloads ke beech
    if [[ ${#SELECTED_INDICES[@]} -gt 1 && "$idx" != "${SELECTED_INDICES[-1]}" ]]; then
        echo -e "\n${YELLOW}[i] Next download 3s mein shuru hoga...${RESET}"
        sleep 3
    fi
done

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${BOLD}Download Summary:${RESET}"
echo -e "  ${GREEN}✅ Success : $SUCCESS${RESET}"
[[ $FAILED -gt 0 ]] && echo -e "  ${RED}❌ Failed  : $FAILED${RESET}"
echo -e "  📁 Files saved in: $SCRIPT_DIR/Download"
echo ""
