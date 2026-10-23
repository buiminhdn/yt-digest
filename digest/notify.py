"""Gửi digest về Telegram."""
import html
import re
import time

import requests

from webpage import vn_date

LIMIT = 3900  # Telegram giới hạn 4096 ký tự/tin


def _e(s) -> str:
    return html.escape(str(s or ""), quote=False)


def _chunks(blocks: list[str]) -> list[str]:
    out, cur = [], ""
    for b in blocks:
        if len(b) > LIMIT:  # khối quá dài: bỏ thẻ HTML rồi cắt cứng
            plain = re.sub(r"<[^>]+>", "", b)
            pieces = [_e(plain[i:i + LIMIT]) for i in range(0, len(plain), LIMIT)]
        else:
            pieces = [b]
        for p in pieces:
            if cur and len(cur) + len(p) + 2 > LIMIT:
                out.append(cur)
                cur = ""
            cur = f"{cur}\n\n{p}" if cur else p
    if cur:
        out.append(cur)
    return out


def build_messages(date: str, digest: dict, records: list[dict], failed: list[dict],
                   page_url: str, detail: str = "full") -> list[str]:
    records = sorted(records, key=lambda r: (r["channel"], r.get("published", "")))
    by_id = {r["video_id"]: r for r in records}
    channels = len({r["channel"] for r in records})
    blocks = [f"📺 <b>YT Digest · {_e(vn_date(date))}</b>\n{len(records)} video mới · {channels} kênh"]
    if digest.get("highlights"):
        blocks.append("💡 <b>KIẾN THỨC NỔI BẬT</b>\n" + "\n".join(f"• {_e(h)}" for h in digest["highlights"]))

    if detail == "full":
        if digest.get("themes"):
            blocks.append("🧭 <b>TỔNG HỢP THEO CHỦ ĐỀ</b>")
            for i, t in enumerate(digest["themes"], 1):
                src = ", ".join(sorted({_e(by_id[v]["channel"]) for v in t.get("video_ids", []) if v in by_id}))
                pts = "\n".join(f"• {_e(p)}" for p in t.get("points", []))
                blocks.append(f"<b>{i}. {_e(t['title'])}</b>\n{pts}" + (f"\n<i>Nguồn: {src}</i>" if src else ""))
        blocks.append("📝 <b>GHI CHÚ CHI TIẾT TỪNG VIDEO</b>")
        for r in records:
            parts = [f'<b><a href="{_e(r["url"])}">{_e(r["title"])}</a></b>\n<i>{_e(r["channel"])}</i>',
                     f"<b>{_e(r.get('core'))}</b>"]
            for sec in r.get("sections", []):
                ts = f" ({_e(sec['timestamp'])})" if sec.get("timestamp") else ""
                parts.append(f"▸ <u>{_e(sec['heading'])}</u>{ts}\n" +
                             "\n".join(f"• {_e(p)}" for p in sec.get("points", [])))
            if r.get("takeaways"):
                parts.append("✅ <u>Áp dụng ngay</u>\n" + "\n".join(f"• {_e(t)}" for t in r["takeaways"]))
            blocks.append("\n\n".join(parts))

    if failed:
        blocks.append("⚠️ <b>Không tóm tắt được</b>\n" + "\n".join(
            f'• <a href="{_e(f["url"])}">{_e(f["title"])}</a>' for f in failed))
    if page_url:
        blocks.append(f'🔗 <a href="{_e(page_url)}">Đọc trên web</a>')
    return _chunks(blocks)


def send(token: str, chat_id: str, messages: list[str]) -> None:
    for m in messages:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": m, "parse_mode": "HTML",
                  "disable_web_page_preview": True},
            timeout=30,
        )
        if not r.ok:
            raise RuntimeError(f"Telegram lỗi {r.status_code}: {r.text[:300]}")
        time.sleep(1)
