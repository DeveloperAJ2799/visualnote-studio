import json
import sys
from pathlib import Path

from config import CONFIG

manifest_path = CONFIG.output_dir / "scene_manifest.json"
if not manifest_path.exists():
    print(f"Manifest not found: {manifest_path}", file=sys.stderr)
    sys.exit(1)

with open(manifest_path, "r", encoding="utf-8") as f:
    m = json.load(f)
scenes = m.get("scenes", [])
print(f"Number of items in scenes: {len(scenes)}")
for i, s in enumerate(scenes):
    print(f"  [{i}] type={type(s).__name__}", end="")
    if isinstance(s, dict):
        print(f' scene_id={s.get("scene_id")} title={s.get("title","")[:50]!r}')
    else:
        print(f" value={repr(s)[:200]}")
