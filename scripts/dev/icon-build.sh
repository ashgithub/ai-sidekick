#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
asset_dir="$repo_root/src/ai_tools/web_panel/static/assets"
source_png="$asset_dir/codex-sidekick-icon.png"
output_icns="$asset_dir/codex-sidekick-icon.icns"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "macOS icon generation requires Darwin because it uses sips and iconutil." >&2
  exit 1
fi

for tool in sips iconutil; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "Missing required tool: $tool" >&2
    exit 1
  fi
done

if [[ ! -f "$source_png" ]]; then
  echo "Missing source icon: $source_png" >&2
  exit 1
fi

tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/codex-sidekick-icon.XXXXXX")"
trap 'rm -rf "$tmp_dir"' EXIT

iconset="$tmp_dir/CodexSidekick.iconset"
mkdir -p "$iconset"

sips -z 16 16 "$source_png" --out "$iconset/icon_16x16.png" >/dev/null
sips -z 32 32 "$source_png" --out "$iconset/icon_16x16@2x.png" >/dev/null
sips -z 32 32 "$source_png" --out "$iconset/icon_32x32.png" >/dev/null
sips -z 64 64 "$source_png" --out "$iconset/icon_32x32@2x.png" >/dev/null
sips -z 128 128 "$source_png" --out "$iconset/icon_128x128.png" >/dev/null
sips -z 256 256 "$source_png" --out "$iconset/icon_128x128@2x.png" >/dev/null
sips -z 256 256 "$source_png" --out "$iconset/icon_256x256.png" >/dev/null
sips -z 512 512 "$source_png" --out "$iconset/icon_256x256@2x.png" >/dev/null
sips -z 512 512 "$source_png" --out "$iconset/icon_512x512.png" >/dev/null
sips -z 1024 1024 "$source_png" --out "$iconset/icon_512x512@2x.png" >/dev/null

if ! iconutil -c icns "$iconset" -o "$output_icns"; then
  echo "iconutil rejected the iconset; writing PNG-backed ICNS fallback." >&2
  python3 - "$output_icns" \
    icp4 "$iconset/icon_16x16.png" \
    icp5 "$iconset/icon_32x32.png" \
    icp6 "$iconset/icon_32x32@2x.png" \
    ic07 "$iconset/icon_128x128.png" \
    ic08 "$iconset/icon_256x256.png" \
    ic09 "$iconset/icon_512x512.png" \
    ic10 "$iconset/icon_512x512@2x.png" <<'PY'
from pathlib import Path
import sys

output = Path(sys.argv[1])
entries = []
args = sys.argv[2:]
for chunk_type, source in zip(args[0::2], args[1::2]):
    data = Path(source).read_bytes()
    payload_length = len(data) + 8
    entries.append(chunk_type.encode("ascii") + payload_length.to_bytes(4, "big") + data)

body = b"".join(entries)
output.write_bytes(b"icns" + (len(body) + 8).to_bytes(4, "big") + body)
PY
fi
sips -g format -g pixelWidth -g pixelHeight "$output_icns"
