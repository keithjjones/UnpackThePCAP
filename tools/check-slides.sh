#!/usr/bin/env bash
#
# Export a Slidev deck to PDF and check it for content running off the slide.
# One command for the edit -> export -> check loop.
#
#   tools/check-slides.sh episodes/260623-ClickFix.../slides.md
#   tools/check-slides.sh episodes/260623-ClickFix...           # a dir works too
#   tools/check-slides.sh <deck> --annotate /tmp/ov             # PNGs of the bad pages
#   tools/check-slides.sh <deck> --json                         # machine-readable
#
# --keep-pdf FILE keeps the export instead of using a temp file. Every other
# flag is forwarded to check_slides.py (--pages, --margin, --fail-on, ...).
#
# Note: slidev's own --range is ignored for PDF export (v52), so there is no
# single-slide fast path; a warm full-deck export takes a few seconds.

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ $# -eq 0 ]]; then
  sed -n '3,15p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit 2
fi

deck="$1"
shift
[[ -d "$deck" ]] && deck="$deck/slides.md"
if [[ ! -f "$deck" ]]; then
  echo "check-slides: no such deck: $deck" >&2
  exit 2
fi
deck="$(cd "$(dirname "$deck")" && pwd)/$(basename "$deck")"

pdf=""
checker_args=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --keep-pdf) pdf="$2"; shift 2 ;;
    --keep-pdf=*) pdf="${1#*=}"; shift ;;
    *) checker_args+=("$1"); shift ;;
  esac
done

if [[ -z "$pdf" ]]; then
  pdf="$(mktemp -t slidecheck)"
  rm -f "$pdf"
  pdf="$pdf.pdf"
  trap 'rm -f "$pdf"' EXIT
fi

log=/tmp/check-slides-export.log
echo "exporting $(basename "$(dirname "$deck")")..." >&2
if ! (cd "$(dirname "$deck")" &&
      npx --no-install slidev export "$deck" \
        --format pdf --output "$pdf" --timeout 60000) >"$log" 2>&1; then
  echo "check-slides: slidev export failed; see $log" >&2
  tail -20 "$log" >&2
  exit 2
fi

# ${a[@]+"${a[@]}"} because macOS ships bash 3.2, where expanding an empty
# array trips set -u.
exec python3 "$here/check_slides.py" "$pdf" --slides "$deck" \
  ${checker_args[@]+"${checker_args[@]}"}
