"""Package Markdown revision artifacts without executing benchmark targets."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

PAPER = Path(__file__).resolve().parents[1]
REVIEW = PAPER / "revision-v4"


def main() -> None:
    current = (PAPER / "manuscript.md").read_text()
    portable = PAPER / "portable"
    if portable.exists():
        shutil.rmtree(portable)
    portable.mkdir()
    images = set()
    for name in ("manuscript.md", "supplement.md"):
        text = (PAPER / name).read_text()
        for image in re.findall(r"!\[[^]]*\]\(([^)]+)\)", text):
            source = Path(image)
            target = portable / "figures" / source.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            text = text.replace(image, "figures/" + source.name)
            images.add(source.name)
        (portable / name).write_text(text)
    for name in ("references.bib", "revision-checklist.md", "sources.md"):
        shutil.copy2(PAPER / name, portable / name)
    shutil.copytree(PAPER / "evidence", portable / "evidence")
    (portable / "revision-v4").mkdir(exist_ok=True)
    for name in ("gap-assessment.md", "change-summary.md", "material-chain.md"):
        shutil.copy2(REVIEW / name, portable / "revision-v4" / name)
    for image in images:
        for ext in ("svg", "pdf"):
            source = PAPER / "figures" / (Path(image).stem + "." + ext)
            shutil.copy2(source, portable / "figures" / source.name)
    (portable / "README.md").write_text(
        "# MemVulBench 可移植阅读包\n\n"
        "正文 manuscript.md 与补充材料 supplement.md 使用包内图片相对路径，"
        "figures 同时提供 PNG/SVG/PDF。证据 JSON 和 CSV 包含原历史路径，供来源定位，"
        "不意味着镜像或 PoC 已随包公开。\n"
    )
    manifest = {
        "revised_sha256": hashlib.sha256(current.encode()).hexdigest(),
        "portable_images": sorted(images),
    }
    (REVIEW / "revision-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Packaged revision, {len(images)} figures.")


if __name__ == "__main__":
    main()
