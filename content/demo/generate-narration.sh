#!/usr/bin/env bash
# Generate every line of narration-lines.json one at a time (serial; the host is shared).
# Usage: REF_TEXT="<exact words spoken in ref-james-6s.wav>" ./generate-narration.sh [line-id ...]
# With no ids it generates all lines; pass ids such as 2-2 4-2 to retry or test only some.
set -euo pipefail
cd "$(dirname "$0")"
: "${REF_TEXT:?set REF_TEXT to the exact transcript of voice/ref-james-6s.wav}"
HOST="${TTS_HOST:-http://192.168.8.12:7860}"
OUT="${OUT_DIR:-out}"; mkdir -p "$OUT"
want=("$@")
python3 - "$@" <<'PY' | while IFS=$'\t' read -r id file text; do
import json, sys
want = set(sys.argv[1:])
for l in json.load(open("narration-lines.json"))["lines"]:
    if not want or l["id"] in want:
        print(f'{l["id"]}\t{l["file"]}\t{l["text"]}')
PY
  take=1; f="$OUT/${file}"
  while [ -e "$f" ]; do take=$((take+1)); f="$OUT/${file/take1/take$take}"; done
  echo "== $id -> $f"
  start=$(date +%s)
  # A failed request (timeout, 500, host down) must not stop the batch.
  code=$(curl -s -m 600 -o "$f" -w '%{http_code}' -X POST "$HOST/api/tts" \
    -F "text=$text" -F mode=zero_shot -F speed=1.0 -F stream=0 \
    -F "prompt_wav=@voice/ref-james-6s.wav" -F "prompt_text=$REF_TEXT" || true)
  code=${code:-000}
  dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$f" 2>/dev/null || echo "?")
  echo "   HTTP $code in $(( $(date +%s) - start )) s, audio ${dur}s"
  [ "$code" = "200" ] || { echo "   failed, removing $f"; rm -f "$f"; }
done
