"""Tìm kênh, đọc RSS và nhận diện Shorts. Không cần API key."""
import datetime as dt
import re
import xml.etree.ElementTree as ET

import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
# Tránh trang xin cookie consent ở một số khu vực
COOKIES = {"CONSENT": "YES+1", "SOCS": "CAI"}

NS = {
    "a": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}

_ID_PATTERNS = [
    r'<link rel="canonical" href="https://www\.youtube\.com/channel/(UC[\w-]{22})"',
    r'<meta itemprop="identifier" content="(UC[\w-]{22})"',
    r'"externalId":"(UC[\w-]{22})"',
    r'"browseId":"(UC[\w-]{22})"',
    r'"channelId":"(UC[\w-]{22})"',
]


def normalize_link(link: str) -> str:
    link = link.strip()
    if link.startswith("@"):
        return "https://www.youtube.com/" + link
    if not link.startswith("http"):
        return "https://" + link
    return link


def resolve_channel_id(link: str, cache: dict) -> str:
    """Đổi mọi dạng link kênh thành channel ID (UC...). Kết quả được cache."""
    if link in cache:
        return cache[link]
    m = re.search(r"/channel/(UC[\w-]{22})", link) or re.fullmatch(r"(UC[\w-]{22})", link.strip())
    if m:
        cid = m.group(1)
    else:
        r = requests.get(normalize_link(link), headers=HEADERS, cookies=COOKIES, timeout=30)
        r.raise_for_status()
        cid = None
        for pat in _ID_PATTERNS:
            m = re.search(pat, r.text)
            if m:
                cid = m.group(1)
                break
        if not cid:
            raise ValueError(f"Không tìm được channel ID từ link: {link}")
    cache[link] = cid
    return cid


def parse_feed(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    feed_title = root.findtext("a:title", default="", namespaces=NS)
    videos = []
    for e in root.findall("a:entry", NS):
        vid = e.findtext("yt:videoId", namespaces=NS)
        if not vid:
            continue
        published = e.findtext("a:published", namespaces=NS) or ""
        videos.append({
            "video_id": vid,
            "title": e.findtext("a:title", default="", namespaces=NS),
            "channel": e.findtext("a:author/a:name", namespaces=NS) or feed_title,
            "channel_id": e.findtext("yt:channelId", default="", namespaces=NS),
            "published": published,
            "url": f"https://www.youtube.com/watch?v={vid}",
            "thumbnail": f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
        })
    return videos


def fetch_feed(channel_id: str) -> list[dict]:
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return parse_feed(r.content)


def is_short(video_id: str) -> bool:
    """Shorts trả 200 ở /shorts/<id>; video thường bị chuyển hướng sang /watch."""
    try:
        r = requests.head(
            f"https://www.youtube.com/shorts/{video_id}",
            headers=HEADERS, cookies=COOKIES, allow_redirects=False, timeout=15,
        )
        return r.status_code == 200
    except requests.RequestException:
        return False


def parse_time(s: str) -> dt.datetime:
    t = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)
