"""Fix existing project data: restore polluted opening_hook."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

proj_dir = Path("data/projects")
for d in proj_dir.iterdir():
    plots_file = d / "plots.json"
    if not plots_file.exists():
        continue
    data = json.loads(plots_file.read_text("utf-8"))
    changed = False
    for k, v in data.get("plots", {}).items():
        oh = v.get("opening_hook", "")
        if oh and oh.startswith("## 第"):
            # Polluted - restore from summary or clear
            v["opening_hook"] = ""
            changed = True
            print(f"  Fixed plot {k} opening_hook ({len(oh)} chars -> empty)")
    if changed:
        plots_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
        print(f"Saved {plots_file}")
    else:
        print(f"  No fix needed for {d.name}")
