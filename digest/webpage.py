"""Dựng trang web tĩnh (GitHub Pages) cho các bản digest."""
import datetime as dt
import html
import json
import re
from pathlib import Path

from youtube import parse_time

WEEKDAYS = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]

CSS = """
:root{--bg:#f6f4ef;--card:#fffdf8;--ink:#1d1b17;--muted:#6b665c;--line:#e4dfd3;
--accent:#c2410c;--accent-soft:#fdeee4;--good:#15803d;--good-soft:#e5f4ea;--chip:#efebe1}
@media (prefers-color-scheme:dark){:root{--bg:#14130f;--card:#1d1c17;--ink:#ece8de;--muted:#a19b8e;
--line:#2f2d26;--accent:#fb923c;--accent-soft:#3a2416;--good:#4ade80;--good-soft:#16301f;--chip:#2a2822}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.65 "Be Vietnam Pro",system-ui,sans-serif}
a{color:inherit}
.wrap{max-width:760px;margin:0 auto;padding:28px 16px 64px}
.brand{font-size:13px;letter-spacing:.12em;text-transform:uppercase;color:var(--accent);font-weight:700}
h1{font-size:30px;line-height:1.2;margin:6px 0 4px}
.stats{color:var(--muted);font-size:14px}
.nav{display:flex;justify-content:space-between;margin:14px 0 22px;font-size:14px}
.nav a{color:var(--muted);text-decoration:none}.nav a:hover{color:var(--accent)}
h2{font-size:13px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin:34px 0 12px}
.theme{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin-bottom:12px}
.theme h3{margin:0 0 6px;font-size:18px}
.tpoints{margin:0 0 10px;padding-left:20px}.tpoints li{margin:5px 0}
.src{margin:8px 0 2px;font-size:13px;color:var(--muted)}
.refs{font-size:14px;color:var(--muted);margin:0;padding-left:18px}
.refs a{text-decoration:none}.refs a:hover{color:var(--accent)}
.video{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin-bottom:14px;scroll-margin-top:16px}
.vhead{display:flex;gap:14px;align-items:flex-start}
.vhead img{width:120px;aspect-ratio:16/9;object-fit:cover;border-radius:8px;flex:none;background:var(--chip)}
.meta{font-size:13px;color:var(--muted)}
.video h3{margin:2px 0 6px;font-size:17px;line-height:1.35}
.video h3 a{text-decoration:none}.video h3 a:hover{color:var(--accent)}
.highlights{background:var(--accent-soft);border-left:4px solid var(--accent);border-radius:8px;padding:12px 16px 12px 34px;margin:0;font-weight:500}
.highlights li{margin:6px 0}
.core{margin:14px 0 6px;font-weight:600}
.video h4{margin:16px 0 4px;font-size:15px}
.points{margin:0 0 8px;padding-left:20px}.points li{margin:4px 0}
.ts{font-size:12px;font-variant-numeric:tabular-nums;color:var(--accent);text-decoration:none;margin-left:6px;font-weight:600}
.chips{margin-top:2px}.chips span{display:inline-block;font-size:12px;background:var(--chip);border-radius:6px;padding:2px 8px;margin:2px 4px 0 0}
.failed li{font-size:14px;color:var(--muted)}
.archive{columns:2;font-size:14px;padding-left:18px}.archive a{text-decoration:none}
@media (max-width:520px){.vhead img{width:88px}h1{font-size:25px}.archive{columns:1}}
"""


def _e(s) -> str:
    return html.escape(str(s or ""))


def _ts_seconds(ts: str):
    if not ts or not re.fullmatch(r"\d{1,2}(:\d{1,2}){1,2}", ts.strip()):
        return None
    sec = 0
    for part in ts.strip().split(":"):
        sec = sec * 60 + int(part)
    return sec


def vn_date(iso_date: str) -> str:
    d = dt.date.fromisoformat(iso_date)
    return f"{WEEKDAYS[d.weekday()]}, {d.day:02d}/{d.month:02d}/{d.year}"


def _video_card(r: dict, tz) -> str:
    pub = parse_time(r["published"]).astimezone(tz).strftime("%H:%M %d/%m") if r.get("published") else ""
    secs = []
    for sec in r.get("sections", []):
        t = _ts_seconds(sec.get("timestamp", ""))
        ts = f' <a class="ts" href="{_e(r["url"])}&t={t}s" target="_blank">{_e(sec["timestamp"])}</a>' if t is not None else ""
        pts = "".join(f"<li>{_e(p)}</li>" for p in sec.get("points", []))
        secs.append(f"<h4>{_e(sec['heading'])}{ts}</h4><ul class='points'>{pts}</ul>")
    chips = "".join(f"<span>{_e(t)}</span>" for t in r.get("topics", []))
    return f"""
<article class="video" id="v-{_e(r['video_id'])}">
  <div class="vhead">
    <a href="{_e(r['url'])}" target="_blank"><img loading="lazy" src="{_e(r['thumbnail'])}" alt=""></a>
    <div>
      <div class="meta">{_e(r['channel'])} · {pub}</div>
      <h3><a href="{_e(r['url'])}" target="_blank">{_e(r['title'])}</a></h3>
      <div class="chips">{chips}</div>
    </div>
  </div>
  <p class="core">{_e(r.get('core'))}</p>
  {''.join(secs)}
</article>"""


def render_day(date: str, digest: dict, records: list[dict], failed: list[dict],
               all_dates: list[str], tz) -> str:
    records = sorted(records, key=lambda r: (r["channel"], r.get("published", "")))
    by_id = {r["video_id"]: r for r in records}
    channels = len({r["channel"] for r in records})
    idx = all_dates.index(date)
    newer = all_dates[idx - 1] if idx > 0 else None
    older = all_dates[idx + 1] if idx + 1 < len(all_dates) else None
    nav = (f'<a href="{older}.html">← {vn_date(older)}</a>' if older else "<span></span>") + \
          (f'<a href="{newer}.html">{vn_date(newer)} →</a>' if newer else "<span></span>")

    hl = digest.get("highlights") or []
    hl_html = ""
    if hl:
        hl_html = "<h2>Kiến thức nổi bật hôm nay</h2><ul class='highlights'>" + "".join(
            f"<li>{_e(h)}</li>" for h in hl) + "</ul>"

    themes_html = ""
    if digest.get("themes"):
        parts = []
        for t in digest["themes"]:
            refs = "".join(
                f'<li><a href="#v-{_e(v)}">{_e(by_id[v]["title"])}</a> · {_e(by_id[v]["channel"])}</li>'
                for v in t.get("video_ids", []) if v in by_id)
            parts.append(f'<section class="theme"><h3>{_e(t["title"])}</h3><ul class="tpoints">{"".join(f"<li>{_e(p)}</li>" for p in t.get("points", []))}</ul>'
                         f'<p class="src">Nguồn:</p><ul class="refs">{refs}</ul></section>')
        themes_html = "<h2>Tổng hợp theo chủ đề</h2>" + "".join(parts)

    failed_html = ""
    if failed:
        failed_html = "<h2>Không tóm tắt được</h2><ul class='failed'>" + "".join(
            f'<li><a href="{_e(f["url"])}" target="_blank">{_e(f["title"])}</a> · {_e(f["channel"])}</li>'
            for f in failed) + "</ul>"

    archive = "".join(f'<li><a href="{d}.html">{vn_date(d)}</a></li>' for d in all_dates[:60])

    return f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>YT Digest · {vn_date(date)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>{CSS}</style></head>
<body><main class="wrap">
<div class="brand">YT Digest</div>
<h1>{vn_date(date)}</h1>
<div class="stats">{len(records)} video mới · {channels} kênh</div>
<nav class="nav">{nav}</nav>
{hl_html}
{themes_html}
<h2>Ghi chú chi tiết từng video</h2>
{''.join(_video_card(r, tz) for r in records)}
{failed_html}
<h2>Các ngày trước</h2><ul class="archive">{archive}</ul>
</main></body></html>"""


def load_day(day_dir: Path):
    records = [json.loads(p.read_text("utf-8")) for p in sorted(day_dir.glob("*.json"))
               if p.name not in ("_digest.json", "_failed.json")]  # ID video cũng có thể bắt đầu bằng "_"
    digest_p, failed_p = day_dir / "_digest.json", day_dir / "_failed.json"
    digest = json.loads(digest_p.read_text("utf-8")) if digest_p.exists() else {"highlights": [], "themes": []}
    failed = json.loads(failed_p.read_text("utf-8")) if failed_p.exists() else []
    return records, digest, failed


def build_site(summaries_dir: Path, site_dir: Path, tz) -> None:
    site_dir.mkdir(parents=True, exist_ok=True)
    dates = sorted((p.name for p in summaries_dir.iterdir()
                    if p.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.name)), reverse=True)
    dates = [d for d in dates if load_day(summaries_dir / d)[0]]
    for d in dates:
        records, digest, failed = load_day(summaries_dir / d)
        (site_dir / f"{d}.html").write_text(render_day(d, digest, records, failed, dates, tz), "utf-8")
    if dates:
        latest = (site_dir / f"{dates[0]}.html").read_text("utf-8")
        (site_dir / "index.html").write_text(latest, "utf-8")
    else:
        (site_dir / "index.html").write_text(
            "<!doctype html><meta charset='utf-8'><title>YT Digest</title>"
            "<p style='font-family:system-ui;padding:24px'>Chưa có bản digest nào.</p>", "utf-8")
    (site_dir / ".nojekyll").write_text("", "utf-8")
