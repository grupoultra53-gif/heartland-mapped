"""
Heartland Mapped — Public Domain & Open-License Archival Ingestion Engine
Fetches verified historical archive items and modern 'Today' photos from:
  - Wikimedia Commons MediaWiki API (strict Public Domain / CC0 / CC BY / CC BY-SA gate)
  - Library of Congress (loc.gov) direct IIIF/image URLs ("No known restrictions")

Outputs inside `<longform_dir>`:
  - `archive/<id>.jpg` or `today/<id>.jpg`
  - `archive_index.json` (metadata, width, height, local path, URL, license, credit)
  - `fontes_imagens.txt` (human-readable full audit & attribution log)

Refuses any image without an explicit acceptable license!
"""
import argparse
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image

USER_AGENT = "HeartlandMappedWebdoc/1.0 (Educational Historical Documentary; https://github.com/grupoultra53-gif/heartland-mapped)"

ALLOWED_LICENSE_PATTERNS = [
    r"public domain",
    r"^pd[- ]?",
    r"^pd$",
    r"cc0",
    r"cc[- ]?zero",
    r"cc[- ]?by[- ]?(sa[- ]?)?[1-4]\.[0-9]",
    r"no known (copyright )?restrictions",
    r"us government",
    r"us-gov",
]

FORBIDDEN_LICENSE_PATTERNS = [
    r"noncommercial",
    r"\bnc\b",
    r"all rights reserved",
    r"fair use",
    r"copyrighted",
    r"getty",
    r"associated press",
    r"\bupi\b",
]


def strip_html(text: str) -> str:
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = html.unescape(clean)
    return re.sub(r"\s+", " ", clean).strip()


def is_license_allowed(lic_name: str, lic_url: str = "") -> bool:
    combined = f"{lic_name} {lic_url}".lower().strip()
    if not combined:
        return False
    for pat in FORBIDDEN_LICENSE_PATTERNS:
        if re.search(pat, combined):
            return False
    for pat in ALLOWED_LICENSE_PATTERNS:
        if re.search(pat, combined):
            return True
    return False


def http_get_json(url: str, timeout: int = 25) -> dict:
    for attempt in range(4):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 3:
                time.sleep(2.5 * (attempt + 1))
                continue
            raise
    raise RuntimeError(f"Failed GET {url}")


def download_binary(url: str, dest: Path, timeout: int = 45) -> bool:
    data = None
    for attempt in range(4):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
                break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 3:
                time.sleep(3.0 * (attempt + 1))
                continue
            raise
    tmp = dest.with_suffix(".tmp")
    tmp.write_bytes(data)
    # Convert/normalize cleanly to RGB JPEG (handles PNG, TIFF, WebP, grayscale, CMYK)
    with Image.open(tmp) as im:
        im = im.convert("RGB")
        # Cap giant scans cleanly to max 2600px on long edge so disk & RAM stay fast while preserving 1080p+ headroom
        w, h = im.size
        max_dim = 2600
        if max(w, h) > max_dim:
            scale = max_dim / float(max(w, h))
            im = im.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
        im.save(dest, "JPEG", quality=92, optimize=True)
    tmp.unlink(missing_ok=True)
    return True


def query_commons_file(file_title: str) -> dict | None:
    if not file_title.startswith("File:"):
        file_title = "File:" + file_title
    params = urllib.parse.urlencode({
        "action": "query",
        "titles": file_title,
        "prop": "imageinfo",
        "iiprop": "url|size|mime|extmetadata",
        "iiurlwidth": 2000,
        "format": "json",
    })
    data = http_get_json(f"https://commons.wikimedia.org/w/api.php?{params}")
    pages = data.get("query", {}).get("pages", {})
    for pid, page in pages.items():
        if int(pid) < 0 or "imageinfo" not in page:
            continue
        ii = page["imageinfo"][0]
        mime = ii.get("mime", "")
        if not any(m in mime for m in ("image/jpeg", "image/png", "image/tiff", "image/webp")):
            continue
        meta = ii.get("extmetadata", {})
        lic_short = strip_html(meta.get("LicenseShortName", {}).get("value", ""))
        lic_url = strip_html(meta.get("LicenseUrl", {}).get("value", ""))
        artist = strip_html(meta.get("Artist", {}).get("value", "")) or "Unknown / Archival"
        desc = strip_html(meta.get("ImageDescription", {}).get("value", ""))[:180]
        # Prefer thumburl (~2000px) for huge TIFFs or >6MB files, otherwise original url
        dl_url = ii.get("thumburl") or ii.get("url")
        return {
            "title": page.get("title", file_title),
            "page_url": ii.get("descriptionurl", f"https://commons.wikimedia.org/wiki/{urllib.parse.quote(file_title)}"),
            "download_url": dl_url,
            "orig_width": ii.get("width", 0),
            "orig_height": ii.get("height", 0),
            "license": lic_short,
            "license_url": lic_url,
            "artist": artist[:120],
            "description": desc,
            "source": "Wikimedia Commons",
        }
    return None


def search_commons(query: str, min_width: int = 700, prefer_landscape: bool = False, limit: int = 12) -> dict | None:
    params = urllib.parse.urlencode({
        "action": "query",
        "generator": "search",
        "gsrnamespace": 6,
        "gsrsearch": query,
        "gsrlimit": limit,
        "prop": "imageinfo",
        "iiprop": "url|size|mime|extmetadata",
        "iiurlwidth": 2000,
        "format": "json",
    })
    data = http_get_json(f"https://commons.wikimedia.org/w/api.php?{params}")
    pages = data.get("query", {}).get("pages", {})
    candidates = []
    for pid, page in pages.items():
        if int(pid) < 0 or "imageinfo" not in page:
            continue
        ii = page["imageinfo"][0]
        mime = ii.get("mime", "")
        if not any(m in mime for m in ("image/jpeg", "image/png", "image/tiff", "image/webp")):
            continue
        w, h = ii.get("width", 0), ii.get("height", 0)
        if w < min_width or h < 400:
            continue
        title = page.get("title", "")
        if any(bad in title.lower() for bad in (".svg", ".pdf", ".djvu", ".ogv", ".webm", "flag_of_", "seal_of_", "locator_map", "blank_map", "stub")):
            continue
        meta = ii.get("extmetadata", {})
        lic_short = strip_html(meta.get("LicenseShortName", {}).get("value", ""))
        lic_url = strip_html(meta.get("LicenseUrl", {}).get("value", ""))
        if not is_license_allowed(lic_short, lic_url):
            continue
        artist = strip_html(meta.get("Artist", {}).get("value", "")) or "Unknown / Archival"
        desc = strip_html(meta.get("ImageDescription", {}).get("value", ""))[:180]
        score = min(w, 2400) / 100.0
        if "public domain" in lic_short.lower() or lic_short.lower().startswith("pd"):
            score += 8.0
        if prefer_landscape and w >= h * 1.15:
            score += 10.0
        if not prefer_landscape and w >= 900:
            score += 3.0
        candidates.append((score, {
            "title": title,
            "page_url": ii.get("descriptionurl", ""),
            "download_url": ii.get("thumburl") or ii.get("url"),
            "orig_width": w,
            "orig_height": h,
            "license": lic_short,
            "license_url": lic_url,
            "artist": artist[:120],
            "description": desc,
            "source": "Wikimedia Commons",
        }))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def ingest_manifest(ep_dir: Path, manifest_path: Path):
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    items = manifest.get("items", [])
    results = []
    errors = []

    for item in items:
        item_id = item["id"]
        category = item.get("category", "archive")
        sub_dir = ep_dir / ("today" if category == "today" else "archive")
        sub_dir.mkdir(parents=True, exist_ok=True)
        dest = sub_dir / f"{item_id}.jpg"
        min_w = item.get("min_width", 650)

        info = None
        if "commons_file" in item:
            info = query_commons_file(item["commons_file"])
            if info and not is_license_allowed(info["license"], info["license_url"]):
                print(f"[BLOCKED LICENSE] {item_id}: {info['license']}")
                info = None
        if info is None and "fallback_queries" in item:
            for q in item["fallback_queries"]:
                info = search_commons(q, min_width=min_w, prefer_landscape=item.get("prefer_landscape", False))
                if info:
                    break
                time.sleep(0.25)
        elif info is None and "query" in item:
            info = search_commons(item["query"], min_width=min_w, prefer_landscape=item.get("prefer_landscape", False))

        if info is None:
            msg = f"[MISSING] {item_id}: no verified PD/CC image found"
            print(msg)
            errors.append(msg)
            continue

        if not is_license_allowed(info["license"], info["license_url"]):
            msg = f"[BLOCKED] {item_id}: disallowed license '{info['license']}'"
            print(msg)
            errors.append(msg)
            continue

        try:
            if not dest.exists() or item.get("force", False):
                download_binary(info["download_url"], dest)
                time.sleep(0.85)
            with Image.open(dest) as im:
                dw, dh = im.size
            low_res_flag = dw < 1280
            rec = {
                "id": item_id,
                "category": category,
                "local_path": str(dest.relative_to(ep_dir)).replace("\\", "/"),
                "width": dw,
                "height": dh,
                "low_res_frame_required": low_res_flag,
                "license": info["license"],
                "license_url": info["license_url"],
                "artist": info["artist"],
                "source": info["source"],
                "page_url": info["page_url"],
                "caption": item.get("caption", info["title"]),
                "credit_line": item.get("credit_line") or f"{info['source']} ({info['license']})",
            }
            results.append(rec)
            flag = " [FRAME-ON-PARCHMENT]" if low_res_flag else " [FULL-HD-OK]"
            print(f"[OK] {item_id:<28} {dw}x{dh:<5} | {info['license']:<16} | {info['title'][:50]}{flag}")
        except Exception as exc:
            msg = f"[ERROR] {item_id}: {exc}"
            print(msg)
            errors.append(msg)

    index_path = ep_dir / "archive_index.json"
    index_path.write_text(json.dumps({"items": results, "errors": errors}, indent=2, ensure_ascii=False), encoding="utf-8")

    # Write fontes_imagens.txt required by audit_longform.py & YouTube description credits
    lines = [
        "================================================================================",
        f"HEARTLAND MAPPED — FONTES E LICENCAS DE IMAGENS ({ep_dir.name})",
        "Todos os arquivos abaixo foram verificados quanto a Dominio Publico ou CC BY / CC BY-SA.",
        "================================================================================",
        "",
    ]
    for r in results:
        lines.append(f"[{r['id']}] ({r['category'].upper()}) — {r['local_path']} ({r['width']}x{r['height']})")
        lines.append(f"  Descricao : {r['caption']}")
        lines.append(f"  Autor     : {r['artist']}")
        lines.append(f"  Licenca   : {r['license']}" + (f" ({r['license_url']})" if r["license_url"] else ""))
        lines.append(f"  URL       : {r['page_url']}")
        lines.append("")
    (ep_dir / "fontes_imagens.txt").write_text("\n".join(lines), encoding="utf-8")

    print(f"\nIngested {len(results)}/{len(items)} items. Errors: {len(errors)}")
    print(f"Saved: {index_path} and {ep_dir / 'fontes_imagens.txt'}")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("episode_dir", help="Path to longform episode directory")
    parser.add_argument("--manifest", default="archive_manifest.json", help="Manifest JSON filename inside episode_dir")
    args = parser.parse_args()
    ep = Path(args.episode_dir).resolve()
    ingest_manifest(ep, ep / args.manifest)
