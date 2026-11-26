#!/usr/bin/env python3
"""
YouTube niche tracker — GitHub Actions par din mein kuch baar apne aap chalta hai.

Har run mein:
  1. niche-queries.txt ki queries se pichhle DAYS din ke videos dhoondta hai.
  2. channels.txt ke competitor channels ke naye uploads leta hai.
  3. Pehle se jama videos ke views dobara padhta hai (sasta, 1 unit / 50 videos),
     taaki pata chale ki ABHI kaun tezi se badh raha hai.
  4. DAYS din se purane videos hata deta hai.
  5. data/youtube-trends.md (Claude ke padhne ke liye), data/youtube-trends.json
     aur data/history.json likhta hai.

Key: environment variable YOUTUBE_API_KEY (GitHub Secret). Key kabhi print nahi hoti.
Sirf Python standard library.
"""
import json
import os
import re
import statistics
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
API = "https://www.googleapis.com/youtube/v3/"

DAYS = int(os.environ.get("TRACK_DAYS", "10"))          # kitne din ka data rakhna hai
PER_QUERY = int(os.environ.get("PER_QUERY", "15"))      # har query se kitne videos
REGION = os.environ.get("REGION", "IN")
LANG = os.environ.get("LANG_HINT", "hi")
TOP = int(os.environ.get("TOP", "30"))
IST = timezone(timedelta(hours=5, minutes=30))


class ApiError(Exception):
    pass


def api_get(endpoint, params, key):
    url = API + endpoint + "?" + urllib.parse.urlencode(dict(params, key=key))
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode("utf-8"))["error"]["message"]
        except Exception:
            msg = str(e)
        raise ApiError(f"YouTube API error {e.code}: {msg.replace(key, '***')}") from None
    except urllib.error.URLError as e:
        raise ApiError(f"network: {e.reason}") from None


def read_lines(path):
    p = Path(path)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.append(line)
    return out


def iso_secs(d):
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", d or "")
    if not m:
        return 0
    a, b, c, s = (int(x or 0) for x in m.groups())
    return a * 86400 + b * 3600 + c * 60 + s


def chunks(seq, n):
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def parse_time(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def fmt(n):
    if n is None:
        return "-"
    n = int(n)
    if n >= 10_000_000:
        return f"{n/10_000_000:.1f} Cr"
    if n >= 100_000:
        return f"{n/100_000:.1f} L"
    if n >= 1000:
        return f"{n/1000:.1f}K"
    return str(n)


# ---------------- collect ----------------

def search_ids(q, after, key):
    ids = []
    for dur, n in (("medium", PER_QUERY), ("long", max(5, PER_QUERY // 2))):
        d = api_get("search", {
            "part": "snippet", "q": q, "type": "video", "order": "viewCount",
            "publishedAfter": after, "maxResults": min(n, 50), "regionCode": REGION,
            "relevanceLanguage": LANG, "videoDuration": dur,
        }, key)
        ids += [it["id"]["videoId"] for it in d.get("items", [])]
    return ids


def resolve_channel(link, key):
    m = re.search(r"(UC[\w-]{22})", link)
    if m:
        return m.group(1)
    m = re.search(r"@([\w.\-]+)", link)
    if m:
        d = api_get("channels", {"part": "id", "forHandle": "@" + m.group(1)}, key)
        items = d.get("items", [])
        return items[0]["id"] if items else None
    return None


def uploads(cid, key, n=15):
    d = api_get("playlistItems", {"part": "contentDetails", "playlistId": "UU" + cid[2:], "maxResults": n}, key)
    return [it["contentDetails"]["videoId"] for it in d.get("items", [])]


def videos(ids, key):
    out = {}
    for g in chunks(dict.fromkeys(ids), 50):
        d = api_get("videos", {"part": "snippet,statistics,contentDetails", "id": ",".join(g)}, key)
        for it in d.get("items", []):
            out[it["id"]] = it
    return out


def channels(cids, key):
    out = {}
    for g in chunks(dict.fromkeys(cids), 50):
        d = api_get("channels", {"part": "snippet,statistics", "id": ",".join(g)}, key)
        for it in d.get("items", []):
            out[it["id"]] = int(it.get("statistics", {}).get("subscriberCount", 0) or 0)
    return out


# ---------------- metrics ----------------

def views_last_24h(snaps, now):
    """snaps: [[iso, views], ...] purane se naye. ~24 ghante pehle ke snapshot se farq, per-day."""
    if len(snaps) < 2:
        return None
    latest_t, latest_v = parse_time(snaps[-1][0]), snaps[-1][1]
    best = None
    for t, v in snaps[:-1]:
        hrs = (latest_t - parse_time(t)).total_seconds() / 3600
        if hrs >= 6:
            if best is None or abs(hrs - 24) < abs(best[0] - 24):
                best = (hrs, v)
    if not best:
        return None
    hrs, v = best
    return int(max(latest_v - v, 0) * 24 / hrs)


def enrich(vid, h, now):
    pub = parse_time(h["published"])
    age = max((now - pub).total_seconds() / 86400, 0.25)
    views = h["snaps"][-1][1]
    vpd = int(views / age)
    subs = h.get("subs") or 0
    outlier = round(views / subs, 2) if subs else None
    med = h.get("channel_median")
    xmed = round(views / med, 1) if med else None
    v24 = views_last_24h(h["snaps"], now)
    if v24 is None and age <= 1.5:
        v24 = vpd                     # naya video: abhi tak ki speed hi aaj ki speed
    boost = 1.0
    if outlier:
        boost += min(outlier, 20) / 4
    if xmed:
        boost += min(xmed, 20) / 4
    return {
        "id": vid, "title": h["title"], "channel": h["channel"], "subs": subs,
        "url": f"https://www.youtube.com/watch?v={vid}",
        "published": pub.astimezone(IST).strftime("%Y-%m-%d"),
        "age_days": round(age, 1), "minutes": h.get("minutes"),
        "views": views, "views_per_day": vpd, "views_last_24h": v24,
        "outlier_x_subs": outlier, "x_channel_normal": xmed,
        "found_by": h.get("found_by", []),
        "viral_score": int(vpd * boost),
        "rising_score": int((v24 or 0) * boost),
    }


def table(rows, cols):
    head = "| # | Title | Channel (subs) | Views | " + " | ".join(c[0] for c in cols) + " | Outlier | Age | Link |"
    sep = "|" + "---|" * (8 + len(cols) - 1)
    lines = [head, sep]
    for i, r in enumerate(rows, 1):
        o = []
        if r["outlier_x_subs"] is not None:
            o.append(f"{r['outlier_x_subs']}x subs")
        if r["x_channel_normal"] is not None:
            o.append(f"{r['x_channel_normal']}x normal")
        extra = " | ".join(fmt(r[c[1]]) for c in cols)
        lines.append(f"| {i} | {r['title'].replace('|', '/')} | {r['channel']} ({fmt(r['subs'])}) | "
                     f"{fmt(r['views'])} | {extra} | {', '.join(o) or '-'} | {r['age_days']}d | {r['url']} |")
    return "\n".join(lines)


def write_report(rows, now, queries, chans, errors):
    viral = sorted(rows, key=lambda r: r["viral_score"], reverse=True)[:TOP]
    rising = sorted([r for r in rows if r["views_last_24h"]], key=lambda r: r["rising_score"], reverse=True)[:TOP]
    fresh = sorted([r for r in rows if r["age_days"] <= 2], key=lambda r: r["views_per_day"], reverse=True)[:15]
    md = [
        "# YouTube trends — business economics (Hindi niche)",
        "",
        f"**Updated:** {now.astimezone(IST).strftime('%Y-%m-%d %H:%M')} IST  ",
        f"**Window:** pichhle {DAYS} din ke videos · Shorts hata diye · kul {len(rows)} videos",
        "",
        "Kaise padhein: *Views/day* = publish se ab tak roz ki average. *Last 24h* = pichhle ~24 ghante mein kitne naye views (ABHI ki speed).",
        "*Outlier* = video ne channel ke subscribers se kitne guna views liye (1x+ = topic khud kheench raha hai), "
        "aur tracked channels ke liye unke normal video se kitne guna.",
        "",
        f"## A. Pichhle {DAYS} din ke sabse viral (viral score se rank)",
        "",
        table(viral, [("Views/day", "views_per_day"), ("Last 24h", "views_last_24h")]),
        "",
        "## B. Abhi tezi se badh rahe (pichhle ~24 ghante ki speed se rank)",
        "",
        table(rising, [("Last 24h", "views_last_24h"), ("Views/day", "views_per_day")]) if rising
        else "_Abhi data kam hai — tracker ke 2-3 run ke baad ye list bharegi._",
        "",
        "## C. Bilkul naye (48 ghante ke andar publish)",
        "",
        table(fresh, [("Views/day", "views_per_day")]) if fresh else "_Koi nahi._",
        "",
        "---",
        f"Queries: {', '.join(queries)}  ",
        f"Tracked channels: {len(chans)}",
    ]
    if errors:
        md += ["", "Dikkatein is run mein:"] + [f"- {e}" for e in errors]
    (DATA / "youtube-trends.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (DATA / "youtube-trends.json").write_text(json.dumps({
        "updated": now.isoformat(), "days": DAYS, "viral": viral, "rising": rising, "fresh": fresh,
    }, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------- main ----------------

def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not key:
        print("NO_KEY: GitHub repo ke Settings > Secrets > Actions mein YOUTUBE_API_KEY daalo.")
        sys.exit(2)

    DATA.mkdir(exist_ok=True)
    hist_path = DATA / "history.json"
    hist = json.loads(hist_path.read_text(encoding="utf-8")) if hist_path.exists() else {}

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=DAYS)
    after = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
    queries = read_lines(ROOT / "niche-queries.txt")
    chan_links = read_lines(ROOT / "channels.txt")
    errors, found, tracked = [], {}, {}

    try:
        for q in queries:
            try:
                for v in search_ids(q, after, key):
                    found.setdefault(v, set()).add("search: " + q)
            except ApiError as e:
                if "quota" in str(e).lower() or "network" in str(e):
                    raise
                errors.append(f"{q}: {e}")
        for link in chan_links:
            try:
                cid = resolve_channel(link, key)
                if not cid:
                    errors.append(f"channel samajh nahi aaya: {link}")
                    continue
                tracked[cid] = uploads(cid, key)
                for v in tracked[cid]:
                    found.setdefault(v, set()).add("tracked channel")
            except ApiError as e:
                if "quota" in str(e).lower() or "network" in str(e):
                    raise
                errors.append(f"{link}: {e}")

        all_ids = set(found) | set(hist)
        det = videos(all_ids, key)
        subs = channels({d["snippet"]["channelId"] for d in det.values()}, key)
    except ApiError as e:
        print("ERROR:", e)
        sys.exit(3)

    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    for vid, it in det.items():
        sn, st, cd = it["snippet"], it.get("statistics", {}), it.get("contentDetails", {})
        secs = iso_secs(cd.get("duration"))
        if (secs and secs < 61) or parse_time(sn["publishedAt"]) < cutoff:
            continue
        h = hist.get(vid, {"snaps": [], "found_by": []})
        h.update({
            "title": sn["title"], "channel": sn["channelTitle"], "channel_id": sn["channelId"],
            "published": sn["publishedAt"], "minutes": round(secs / 60, 1),
            "subs": subs.get(sn["channelId"], h.get("subs", 0)),
        })
        h["found_by"] = sorted(set(h.get("found_by", [])) | found.get(vid, set()))
        h["snaps"].append([stamp, int(st.get("viewCount", 0) or 0)])
        h["snaps"] = [s for s in h["snaps"] if parse_time(s[0]) >= now - timedelta(days=3)]
        hist[vid] = h

    # purane videos hatao
    hist = {v: h for v, h in hist.items() if parse_time(h["published"]) >= cutoff and v in det}

    # tracked channels ka normal (median) views
    for cid, ids in tracked.items():
        vals = [int(det[v].get("statistics", {}).get("viewCount", 0) or 0) for v in ids
                if v in det and iso_secs(det[v].get("contentDetails", {}).get("duration")) > 60]
        if len(vals) >= 3:
            med = statistics.median(vals)
            for v, h in hist.items():
                if h["channel_id"] == cid:
                    h["channel_median"] = med or None

    rows = [enrich(v, h, now) for v, h in hist.items()]
    hist_path.write_text(json.dumps(hist, ensure_ascii=False), encoding="utf-8")
    write_report(rows, now, queries, chan_links, errors)
    print(f"OK: {len(rows)} videos track ho rahe. Report: data/youtube-trends.md")
    if errors:
        print("Dikkatein:", *errors, sep="\n - ")


if __name__ == "__main__":
    main()
