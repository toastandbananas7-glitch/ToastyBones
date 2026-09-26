"""Drop Watch market data: daily TCGplayer prices for the current Pokemon TCG era.

Source: tcgcsv.com, a free daily mirror of TCGplayer's catalog and prices
(Pokemon is category 3; it refreshes around 20:00 UTC). Stdlib only, so the
GitHub Action needs no installs.

Writes:
  drops/market.json          what the page shows (per set: chase cards + sealed)
  drops/market-history.json  daily market price per tracked product, last 35 days,
                             used for the 7/30-day change and the "heating up" list
"""
import json
import os
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "drops", "market.json")
HIST = os.path.join(ROOT, "drops", "market-history.json")
MSRP = os.path.join(ROOT, "drops", "msrp.json")
BASE = "https://tcgcsv.com/tcgplayer/3"
UA = {"User-Agent": "DropWatch/1.0 (toastybones.com/drops)"}

# Current era = Mega Evolution sets ("ME01: ...", "ME: 30th Celebration").
SET_RE = re.compile(r"^ME(\d+)?:")
SKIP_SET = re.compile(r"Promo|Energies", re.I)
# Sealed items nobody lines up at Target for: wholesale cases/displays, bundles
# of several SKUs, and online-only Pokemon Center exclusives.
SKIP_SEALED = re.compile(r"\bCase\b|Display|Set of \d|Code Card|Pokemon Center|International Version", re.I)
TOP_CARDS = 40
MOVER_MIN = 5.0      # ignore bulk: a $0.40 card going to $0.80 isn't news
KEEP_DAYS = 35


def get(path):
    req = urllib.request.Request(BASE + path, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)["results"]


def ext(product, name):
    for e in product.get("extendedData", []):
        if e["name"] == name:
            return e["value"]
    return None


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def change(series, dates, days):
    """% change from the newest price back to the price closest to `days` ago
    (never less than days-1 ago). None until the history is that deep."""
    if not series or series[-1] is None:
        return None
    target = datetime.strptime(dates[-1], "%Y-%m-%d").date() - timedelta(days=days - 1)
    old = None
    for d, p in zip(dates, series):
        if datetime.strptime(d, "%Y-%m-%d").date() > target:
            break
        if p:
            old = p
    if not old:
        return None
    return round((series[-1] - old) / old * 100, 1)


def main():
    today = date.today().isoformat()
    msrp_rules = load(MSRP, {"rules": []})["rules"]
    hist = load(HIST, {"dates": [], "p": {}})

    groups = [g for g in get("/groups") if SET_RE.match(g["name"]) and not SKIP_SET.search(g["name"])]
    groups.sort(key=lambda g: g["publishedOn"], reverse=True)

    sets, prices_today, card_meta = [], {}, {}
    for g in groups:
        products = {p["productId"]: p for p in get("/%d/products" % g["groupId"])}
        best = {}
        for pr in get("/%d/prices" % g["groupId"]):
            mp = pr.get("marketPrice")
            if mp and mp > best.get(pr["productId"], (0,))[0]:
                best[pr["productId"]] = (mp, pr["subTypeName"])

        cards, sealed = [], []
        for pid, (mp, sub) in best.items():
            p = products.get(pid)
            if not p:
                continue
            item = {"id": pid, "name": p["name"], "price": round(mp, 2),
                    "img": p["imageUrl"], "url": p["url"]}
            if ext(p, "Rarity"):
                # "Mew ex - 152/128" -> "Mew ex"; the number has its own field.
                item.update(name=re.sub(r"\s+-\s+\S+$", "", p["name"]),
                            number=ext(p, "Number"), rarity=ext(p, "Rarity"),
                            finish=sub if sub != "Normal" else None)
                cards.append(item)
            elif not SKIP_SEALED.search(p["name"]):
                item["released"] = ((p.get("presaleInfo") or {}).get("releasedOn") or g["publishedOn"])[:10]
                for rule in msrp_rules:
                    if re.search(rule["match"], p["name"], re.I):
                        item.update(msrp=rule["msrp"], msrp_source=rule["source"])
                        break
                sealed.append(item)

        cards.sort(key=lambda c: c["price"], reverse=True)
        sealed.sort(key=lambda s: s["price"], reverse=True)
        for c in cards:
            if c["price"] >= MOVER_MIN:
                prices_today[str(c["id"])] = c["price"]
                card_meta[str(c["id"])] = dict(c, set=g["name"])
        for s in sealed:
            prices_today[str(s["id"])] = s["price"]
        sets.append({"name": re.sub(r"^ME\d*:\s*", "", g["name"]), "code": g["name"].split(":")[0],
                     "release": g["publishedOn"][:10], "cards": cards[:TOP_CARDS], "sealed": sealed})

    # History: one column per day, re-running on the same day overwrites it.
    dates = hist["dates"]
    if dates and dates[-1] == today:
        for s in hist["p"].values():
            s.pop()
        dates.pop()
    dates.append(today)
    n = len(dates)
    for k, s in hist["p"].items():
        s.append(prices_today.get(k))
    for k, v in prices_today.items():
        if k not in hist["p"]:
            hist["p"][k] = [None] * (n - 1) + [v]
    if n > KEEP_DAYS:
        cut = n - KEEP_DAYS
        del dates[:cut]
        for s in hist["p"].values():
            del s[:cut]
    hist["p"] = {k: s for k, s in hist["p"].items() if any(s)}

    def with_change(item):
        s = hist["p"].get(str(item["id"]))
        item["ch7"] = change(s, dates, 7)
        item["ch30"] = change(s, dates, 30)
        return item

    for st in sets:
        st["cards"] = [with_change(c) for c in st["cards"]]
        st["sealed"] = [with_change(s) for s in st["sealed"]]

    movers = []
    for k, meta in card_meta.items():
        ch = change(hist["p"].get(k), dates, 7)
        if ch is not None and ch > 0:
            movers.append(dict(meta, ch7=ch))
    movers.sort(key=lambda m: m["ch7"], reverse=True)

    out = {"updated": today, "history_days": n if n <= KEEP_DAYS else KEEP_DAYS,
           "source": "TCGplayer market prices via tcgcsv.com",
           "sets": sets, "movers": movers[:12]}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    with open(HIST, "w", encoding="utf-8") as f:
        json.dump(hist, f, separators=(",", ":"))
    print("sets=%d tracked=%d movers=%d" % (len(sets), len(hist["p"]), len(movers)))


if __name__ == "__main__":
    sys.exit(main())
