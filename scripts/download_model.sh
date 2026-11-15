#!/bin/sh
set -eu
. "$(dirname "$0")/env.sh"
MODEL="$PROJECT_ROOT/models/LFM3-1.7B-Q4_K_M.gguf"
EXPECTED_SHA='3793e1e6e2266919d6e015287221b41100175a98eddaba92e111aed3b05c93c4'
if [ -L "$MODEL" ] || [ -L "$MODEL.part" ]; then echo 'Model path is a symlink' >&2; exit 1; fi
URL='https://huggingface.co/LiquidAI/LFM3-1.7B-GGUF/resolve/cd0c74c/LFM3-1.7B-Q4_K_M.gguf'
verify_model() {
  ACTUAL_SHA=$(shasum -a 256 "$1" | awk '{print $1}')
  if [ "$ACTUAL_SHA" != "$EXPECTED_SHA" ]; then echo 'Model SHA-256 does not match the publisher checksum' >&2; exit 1; fi
}
if [ -s "$MODEL" ]; then verify_model "$MODEL"; echo 'Existing model matches publisher SHA-256; no duplicate download.'; exit 0; fi
FREE_KIB=$(df -Pk "$PROJECT_ROOT" | awk 'NR==2 {print $4}')
if [ "$FREE_KIB" -lt 1800000 ]; then echo 'At least 1.8 GB free disk space required' >&2; exit 1; fi
curl --fail --location --retry 3 --continue-at - --output "$MODEL.part" "$URL"
SIZE=$(wc -c < "$MODEL.part" | tr -d ' ')
if [ "$SIZE" -lt 1000000000 ]; then echo 'Downloaded model is unexpectedly small; retained .part for inspection' >&2; exit 1; fi
MAGIC=$(head -c 4 "$MODEL.part")
if [ "$MAGIC" != 'GGUF' ]; then echo 'Downloaded file has invalid GGUF header; retained .part' >&2; exit 1; fi
verify_model "$MODEL.part"
mv "$MODEL.part" "$MODEL"
echo "$EXPECTED_SHA  LFM3-1.7B-Q4_K_M.gguf" > "$MODEL.sha256"
echo 'Model downloaded and matched publisher SHA-256.'
