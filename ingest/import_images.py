"""FlowGenie가 만든 이미지를 번들의 images/ 로 가져온다 (로컬 파일 복사만, AI 없음).

FlowGenie(크롬 확장)는 이미지를 `~/Downloads/FlowGenie/` 에 저장한다.
- 한 번 생성에서 여러 후보가 나오면:  name_1.png, name_2.png, ...  (밑줄+번호)
- 같은 이름으로 재생성하면 Chrome이:    name (1).png, name (2).png   (uniquify)
- 후보가 하나면:                         name.png

씬을 여러 번 다시 뽑으면 한 씬(chNN_XX)에 여러 파일이 쌓인다. 기본은
**가장 최근(mtime 최신) 한 장만** 골라 images/ 로 복사한다 → mp4maker가 옛
변형을 집는 문제를 없앤다. prefer="earliest" 로 뒤집을 수 있다.

CLI:
    python ingest/import_images.py <bundle_dir> [--downloads DIR]
                                   [--prefer latest|earliest] [--move]
"""
from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
# 파일명 끝의 변형 토큰:  _3   또는   (2)
_VARIANT_RE = re.compile(r"(?:_(\d+)|\s*\((\d+)\))$")


def _default_download_dirs() -> list[Path]:
    dl = Path.home() / "Downloads"
    return [dl / "FlowGenie", dl]


def chapter_num(bundle_dir: Path) -> str | None:
    """번들 폴더 이름에서 2자리 챕터 번호를 뽑는다 (ch90_bundle → '90')."""
    m = re.search(r"(\d{1,3})", bundle_dir.name.replace("_bundle", ""))
    return f"{int(m.group(1)):02d}" if m else None


def _scene_of(filename: str, chap: str) -> int | None:
    """파일명이 이 챕터의 씬에 속하면 씬 번호(int)를, 아니면 None."""
    m = re.match(rf"(?:ch)?0*{int(chap)}_(\d{{2}})", filename, re.IGNORECASE)
    return int(m.group(1)) if m else None


def _variant_index(name: str) -> int:
    """파일명 끝 변형 번호 (_3 / (2)) → int. 없으면 0(원본/첫 장)."""
    m = _VARIANT_RE.search(Path(name).stem)
    if not m:
        return 0
    return int(m.group(1) or m.group(2))


def _strip_variant(name: str) -> str:
    """변형 토큰을 떼어 정규 파일명으로. 'ch90_01_opening_3.png' → 'ch90_01_opening.png'."""
    p = Path(name)
    return _VARIANT_RE.sub("", p.stem) + p.suffix.lower()


def import_from_downloads(
    bundle_dir: str | Path,
    *,
    downloads: str | Path | None = None,
    prefer: str = "latest",
    move: bool = False,
) -> list[dict]:
    """Downloads(및 Downloads/FlowGenie)에서 이 번들 챕터의 이미지를 씬당 1장 복사.

    Returns: [{"scene": 1, "src": <원본경로>, "dst": <복사된 파일명>, "variants": N}, ...]
    """
    bundle = Path(bundle_dir).resolve()
    chap = chapter_num(bundle)
    if chap is None:
        raise ValueError(f"번들 이름에서 챕터 번호를 찾지 못함: {bundle.name} (예: ch90_bundle)")

    dst_dir = bundle / "images"
    dst_dir.mkdir(parents=True, exist_ok=True)

    search_dirs = [Path(downloads)] if downloads else _default_download_dirs()

    groups: dict[int, list[Path]] = {}
    for d in search_dirs:
        if not d.is_dir():
            continue
        for f in d.iterdir():
            if not f.is_file() or f.suffix.lower() not in IMG_EXTS:
                continue
            sc = _scene_of(f.name, chap)
            if sc is None:
                continue
            groups.setdefault(sc, []).append(f)

    newest_first = prefer != "earliest"
    imported: list[dict] = []
    for scene in sorted(groups):
        files = groups[scene]
        # 1차: mtime, 2차: 변형 번호 — 둘 다 "최근일수록 큼"
        files.sort(key=lambda p: (p.stat().st_mtime, _variant_index(p.name)), reverse=newest_first)
        chosen = files[0]
        target = dst_dir / _strip_variant(chosen.name)
        (shutil.move if move else shutil.copy2)(str(chosen), str(target))
        imported.append(
            {"scene": scene, "src": str(chosen), "dst": target.name, "variants": len(files)}
        )
    return imported


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="FlowGenie 다운로드 이미지를 번들 images/ 로 가져오기")
    ap.add_argument("bundle", help="번들 폴더 경로 (예: _assets/ch90_bundle)")
    ap.add_argument("--downloads", default=None, help="검색할 다운로드 폴더 (기본: ~/Downloads[/FlowGenie])")
    ap.add_argument("--prefer", choices=["latest", "earliest"], default="latest",
                    help="씬당 여러 장일 때 고를 기준 (기본 latest=최신)")
    ap.add_argument("--move", action="store_true", help="복사 대신 이동")
    args = ap.parse_args(argv)

    rows = import_from_downloads(
        args.bundle, downloads=args.downloads, prefer=args.prefer, move=args.move
    )
    if not rows:
        print("가져온 이미지 없음. 파일명이 chNN_XX_* 규칙인지, Downloads/FlowGenie 위치인지 확인.")
        return 0
    for r in rows:
        extra = f"  ({r['variants']}장 중 최신)" if r["variants"] > 1 else ""
        print(f"씬{r['scene']:02d}  ←  {r['dst']}{extra}")
    print(f"\n총 {len(rows)}개 씬 이미지 가져옴 → {Path(args.bundle).resolve() / 'images'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
