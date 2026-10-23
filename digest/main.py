#!/usr/bin/env python3
"""YT Digest: tự tìm video mới từ các kênh bạn theo dõi, tóm tắt, gom thành digest,
dựng trang web và gửi về Telegram.

Chạy:  python digest/main.py           (cần GEMINI_API_KEY)
       python digest/main.py --fake    (chạy thử với tóm tắt giả lập, không cần key)
"""
import argparse
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8")  # console Windows mặc định cp1252, không in được emoji/tiếng Việt

import notify  # noqa: E402
import webpage  # noqa: E402
import youtube  # noqa: E402
from summarize import FakeSummarizer, GeminiSummarizer, QuotaExhausted  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "state"
SUMMARIES_DIR = ROOT / "summaries"
SITE_DIR = ROOT / "docs"


def log(msg: str) -> None:
    print(msg, flush=True)


def load_json(path: Path, default):
    return json.loads(path.read_text("utf-8")) if path.exists() else default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")


def read_channels() -> list[str]:
    lines = (ROOT / "channels.txt").read_text("utf-8").splitlines()
    return [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]


def site_url(cfg: dict) -> str:
    if cfg.get("site_url"):
        return cfg["site_url"].rstrip("/") + "/"
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" in repo:
        owner, name = repo.split("/", 1)
        if name.lower() == f"{owner.lower()}.github.io":
            return f"https://{name}/"
        return f"https://{owner}.github.io/{name}/"
    return ""


def collect_candidates(cfg, processed, cache, now) -> list[dict]:
    lookback = dt.timedelta(days=cfg.get("lookback_days", 2))
    max_attempts = cfg.get("max_attempts", 3)
    seen, out = set(), []
    for link in read_channels():
        try:
            cid = youtube.resolve_channel_id(link, cache)
            videos = youtube.fetch_feed(cid)
        except Exception as e:  # một kênh lỗi không làm hỏng cả lượt chạy
            log(f"⚠️  Bỏ qua kênh {link}: {e}")
            continue
        for v in videos:
            vid = v["video_id"]
            if vid in seen or not v["published"]:
                continue
            if now - youtube.parse_time(v["published"]) > lookback:
                continue
            rec = processed.get(vid)
            if rec and (rec["status"] in ("done", "skipped") or rec.get("attempts", 0) >= max_attempts):
                continue
            seen.add(vid)
            out.append(v)
    out.sort(key=lambda v: v["published"])
    return out[: cfg.get("max_videos_per_run", 25)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fake", action="store_true", help="tóm tắt giả lập, không gọi Gemini")
    ap.add_argument("--no-telegram", action="store_true")
    args = ap.parse_args()

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text("utf-8"))
    tz = ZoneInfo(cfg.get("timezone", "Asia/Ho_Chi_Minh"))
    now = dt.datetime.now(dt.timezone.utc)
    today = now.astimezone(tz).date().isoformat()

    processed = load_json(STATE_DIR / "processed.json", {})
    cache = load_json(STATE_DIR / "channels.json", {})

    if args.fake:
        summarizer = FakeSummarizer(cfg)
    else:
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            log("❌ Thiếu GEMINI_API_KEY (thêm vào GitHub Secrets).")
            return 1
        summarizer = GeminiSummarizer(key, cfg)

    candidates = collect_candidates(cfg, processed, cache, now)
    save_json(STATE_DIR / "channels.json", cache)
    log(f"🔎 {len(read_channels())} kênh, {len(candidates)} video mới cần xử lý")

    day_dir = SUMMARIES_DIR / today
    failed_path = day_dir / "_failed.json"
    failed_final = load_json(failed_path, [])
    new_count = 0

    for v in candidates:
        vid = v["video_id"]
        if cfg.get("skip_shorts", True) and not args.fake and youtube.is_short(vid):
            processed[vid] = {"status": "skipped", "reason": "short", "date": today}
            log(f"⏭️  Shorts: {v['title']}")
            continue
        log(f"📝 {v['channel']} | {v['title']}")
        try:
            summary = summarizer.summarize_video(v)
        except QuotaExhausted:
            log("⛔ Hết quota Gemini hôm nay, phần còn lại để lần chạy sau.")
            break
        except Exception as e:
            rec = processed.setdefault(vid, {"attempts": 0})
            rec.update(status="failed", attempts=rec.get("attempts", 0) + 1,
                       error=str(e)[:300], date=today)
            log(f"   ❗ lỗi (lần {rec['attempts']}): {str(e)[:200]}")
            if rec["attempts"] >= cfg.get("max_attempts", 3):
                failed_final.append({k: v[k] for k in ("video_id", "title", "channel", "url")})
                save_json(failed_path, failed_final)
        else:
            record = {**v, **summary, "summarized_at": now.isoformat()}
            save_json(day_dir / f"{vid}.json", record)
            processed[vid] = {"status": "done", "date": today}
            new_count += 1
        save_json(STATE_DIR / "processed.json", processed)  # lưu tiến độ sau mỗi video
        if not args.fake:
            time.sleep(cfg.get("delay_between_videos_sec", 6))

    records, digest, failed = webpage.load_day(day_dir) if day_dir.exists() else ([], {}, [])
    if records and (new_count or not (day_dir / "_digest.json").exists()):
        log("🧭 Tổng hợp digest theo chủ đề...")
        if len(records) == 1:
            digest = {"highlights": [records[0]["core"]], "themes": []}
        else:
            try:
                digest = summarizer.build_digest(records)
            except Exception as e:
                log(f"   ❗ không tổng hợp được ({e}); dùng danh sách video thay thế")
                digest = {"highlights": [], "themes": []}
        save_json(day_dir / "_digest.json", digest)

    # Dọn trạng thái cũ để file không phình mãi
    cutoff = (now - dt.timedelta(days=cfg.get("lookback_days", 2) + 30)).astimezone(tz).date().isoformat()
    processed = {k: v for k, v in processed.items() if v.get("date", today) >= cutoff}
    save_json(STATE_DIR / "processed.json", processed)

    webpage.build_site(SUMMARIES_DIR, SITE_DIR, tz)
    log("🌐 Đã dựng trang web trong docs/")

    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if new_count and token and chat and not args.no_telegram:
        url = site_url(cfg)
        msgs = notify.build_messages(today, digest, records, failed, url + f"{today}.html" if url else "",
                                     cfg.get("telegram_detail", "full"))
        notify.send(token, chat, msgs)
        log(f"📨 Đã gửi {len(msgs)} tin Telegram")
    elif not new_count:
        log("😴 Không có video mới, không gửi Telegram.")
    else:
        log("ℹ️  Chưa cấu hình Telegram, bỏ qua bước gửi.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
