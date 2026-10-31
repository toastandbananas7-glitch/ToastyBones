"""Toasty's Drops full catalog: every English Pokemon TCG card and product with
today's TCGplayer prices, for the price check's all-eras search.

Source: tcgcsv.com (Pokemon is category 3), the same daily TCGplayer mirror as
market.py, but every group (about 220 sets, ~31,000 priced products).
Stdlib only. The workflow publishes the file on its own `catalog` branch,
replaced each run, so the 3 MB daily file never piles up in main's history.

Usage: python catalog.py OUT_PATH
Writes {"updated", "sets": [[name, year], ...], "items": [[id, name, set index,
number, rarity, [[finish, market, low], ...]], ...]}.
"""
import json
import os
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date

BASE = "https://tcgcsv.com/tcgplayer/3"
UA = {"User-Agent": "ToastysDrops/1.0 (toastybones.com/drops)"}
# "SWSH05: Battle Styles" -> "Battle Styles"; "SV: Scarlet & Violet 151" -> "Scarlet & Violet 151"
SET_PREFIX = re.compile(r"^[A-Z0-9.]{1,8}:\s*")
CASE = re.compile(r"\bCase\b")


def get(path):
    req = urllib.request.Request(BASE + path, headers=UA)
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)["results"]


def group(g):
    return g, get("/%d/products" % g["groupId"]), get("/%d/prices" % g["groupId"])


def main():
    out_path = sys.argv[1]
    groups = sorted(get("/groups"), key=lambda g: g["publishedOn"], reverse=True)
    sets, items = [], []
    # Six at a time: quick (about 20 s for everything) without hammering a free mirror.
    with ThreadPoolExecutor(6) as ex:
        for g, products, prices in ex.map(group, groups):
            variants = {}
            for pr in prices:
                mp, lp = pr.get("marketPrice"), pr.get("lowPrice")
                if mp or lp:
                    variants.setdefault(pr["productId"], []).append(
                        [pr["subTypeName"], mp and round(mp, 2), lp and round(lp, 2)])
            si = len(sets)
            sets.append([SET_PREFIX.sub("", g["name"]), g["publishedOn"][:4]])
            for p in products:
                v = variants.get(p["productId"])
                # Wholesale cases ("Elite Trainer Box Case") would top every search; market.py skips them too.
                if not v or p["name"].startswith("Code Card") or CASE.search(p["name"]):
                    continue
                ext = {e["name"]: e["value"] for e in p.get("extendedData", [])}
                num, rar = ext.get("Number"), ext.get("Rarity")
                if rar == "Code Card":
                    continue
                name = re.sub(r"\s+-\s+\S+$", "", p["name"]) if num else p["name"]
                items.append([p["productId"], name, si, num, rar, v])
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"updated": date.today().isoformat(), "source": "TCGplayer prices via tcgcsv.com",
                   "sets": sets, "items": items}, f, ensure_ascii=False, separators=(",", ":"))
    print("sets=%d items=%d bytes=%d" % (len(sets), len(items), os.path.getsize(out_path)))


if __name__ == "__main__":
    sys.exit(main())
