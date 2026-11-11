#!/usr/bin/env bash
# carve.sh — carve the exfiltrated SCREEN: screenshots out of a PCAP, using Zeek.
#
# Usage: ./scripts/carve.sh <capture.pcapng> <output-dir>
#
#   <capture.pcapng>  the PCAP to read (any path — relative or absolute)
#   <output-dir>      where screen1..N.jpg land (created if missing)
#
# No paths are hardwired: the audience runs this against their own copy of the
# capture, wherever it lives. All pipeline logic lives here so slides.md stays
# a one-liner.
#
# How it works:
#   1. Zeek reads the PCAP with scripts/extract_http_post.zeek, which attaches
#      Files::ANALYZER_EXTRACT to every HTTP request body (client -> server).
#      Each body lands in extract_files/extract-<ts>-HTTP-<fuid> as text.
#   2. Bodies whose first 7 bytes are the SCREEN: marker are base64: strip the
#      prefix, decode -> a JPEG named by its epoch timestamp.
#   3. Sort chronologically, rename to screen1..N, print the listing.
#
# The outputs are DATA carved from a PCAP — display them, never execute
# anything out of the output directory.

set -euo pipefail

if [ $# -ne 2 ]; then
    echo "usage: $0 <capture.pcapng> <output-dir>" >&2
    exit 1
fi
PCAP="$1"
OUT="$2"

EP="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"     # episode directory
EXTRACT_SCRIPT="$EP/scripts/extract_http_post.zeek"

[ -f "$PCAP" ]            || { echo "carve.sh: no such PCAP: $PCAP" >&2; exit 1; }
[ -f "$EXTRACT_SCRIPT" ]  || { echo "carve.sh: missing $EXTRACT_SCRIPT" >&2; exit 1; }

# Zeek resolution: $ZEEK override, then plain zeek (the audience's path),
# then zenv (this machine's layout: venv-style envs for Zeek + zkg).
if [ -n "${ZEEK:-}" ]; then
    ZEEK_CMD=("$ZEEK")
elif command -v zeek >/dev/null 2>&1; then
    ZEEK_CMD=(zeek)
elif command -v zenv >/dev/null 2>&1; then
    ZEEK_CMD=(zenv exec "${ZENV_ENV:-261015}" -- zeek)
else
    echo "carve.sh: zeek not found — install Zeek, or set ZEEK=/path/to/zeek" >&2
    exit 1
fi

# Absolute paths before we change directory anywhere; keep $OUT as given for
# the final listing so the output shows the caller's own path, not ours.
PCAP_ABS="$(cd "$(dirname "$PCAP")" && pwd)/$(basename "$PCAP")"
mkdir -p "$OUT"
OUT_ABS="$(cd "$OUT" && pwd)"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/carve.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

# Run Zeek in the scratch dir so its logs never land in the caller's folder.
( cd "$WORK" && "${ZEEK_CMD[@]}" -C -r "$PCAP_ABS" "$EXTRACT_SCRIPT" >/dev/null 2>&1 ) \
    || { echo "carve.sh: zeek run failed" >&2; exit 1; }

# Clear stale outputs so the rename maps exactly this run.
rm -f "$OUT_ABS"/screen_*.jpg "$OUT_ABS"/screen[0-9]*.jpg

# Order the SCREEN: bodies chronologically (epoch timestamps sort numerically).
ORDER="$WORK/order.txt"
: > "$ORDER"
for f in "$WORK"/extract_files/extract-*; do
    [ -e "$f" ] || continue
    if head -c 7 "$f" | grep -q '^SCREEN:$'; then
        ts=$(basename "$f" | sed -e 's/^extract-//' -e 's/-HTTP.*//')
        printf '%s %s\n' "$ts" "$f" >> "$ORDER"
    fi
done
[ -s "$ORDER" ] || { echo "carve.sh: no SCREEN: bodies found in this PCAP" >&2; exit 1; }

sort -n "$ORDER" | while read -r ts f; do
    tail -c +8 "$f" | tr -d '\r\n' | base64 -d > "$OUT_ABS/screen_${ts}.jpg"
done

i=1
for f in "$OUT_ABS"/screen_*.jpg; do
    [ -e "$f" ] || { echo "carve.sh: decode produced no files" >&2; exit 1; }
    mv -f "$f" "$OUT_ABS/screen$i.jpg"
    i=$((i+1))
done

ls -l "$OUT"/screen*.jpg
