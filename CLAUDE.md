# YT Digest — bối cảnh cho Claude Code

## Mục tiêu
Tự động hóa 100% việc nắm kiến thức từ các kênh YouTube Minh theo dõi. Minh chỉ dán link kênh
vào `channels.txt`; mỗi sáng hệ thống tự tìm video mới, rút **kiến thức cốt lõi** thành ghi chú ngắn,
tổng hợp theo chủ đề, gửi Telegram và dựng trang web. Mục tiêu đọc 10–30 phút/ngày thay vì xem video.

**Yêu cầu cốt lõi (Minh đã nhấn mạnh):** đầu ra là *kiến thức của video* (viết thẳng nội dung,
giữ con số then chốt/công thức/công cụ/các bước), KHÔNG phải giới thiệu video ("video này nói về…")
và KHÔNG phải gợi ý video nên xem. Đừng thêm lại điểm "đáng xem" hay mục "nên xem".

**Ngắn, không lan man (Minh chốt 23/10/2026):** bản "chép toàn bộ" ra ~45 chữ/phút video (3 video = 34 phút đọc),
Minh thấy quá dài. Prompt hiện đặt trần 150/300/400 chữ mỗi video (<15 / 15–45 / >45 phút), tối đa 5 phần,
video dạng danh sách thì gộp nhóm, bỏ ví dụ/kể chuyện. Gemini thường vượt trần 10–40%. Đừng nới lại.
Đã bỏ mục "Áp dụng ngay" (takeaways) vì Gemini luôn chép lại ý trong sections; "Tổng hợp theo chủ đề"
chỉ giữ nhóm gom từ ≥2 video (lọc trong main.py), vì nhóm 1 video chỉ lặp lại ghi chú của video đó.

## Kiến trúc
```
GitHub Actions cron 22:30 UTC (05:30 giờ VN)
  digest/main.py
    youtube.py   : link kênh → channel ID (cache state/channels.json) → RSS
                   (youtube.com/feeds/videos.xml?channel_id=...) → lọc Shorts (HEAD /shorts/<id>: 200 = Short)
                   RSS trả 404 thất thường (đo 10/2026: phần lớn request) → thử 3 lần rồi đọc trang
                   /channel/<id>/videos (ytInitialData, lockupViewModel; ngày đăng suy từ "Nd ago", gần đúng)
    summarize.py : Gemini API, truyền thẳng URL YouTube làm file_data (không cần transcript,
                   không bị chặn IP cloud). fps=0.2 + MEDIA_RESOLUTION_LOW để tiết kiệm token.
                   Đầu ra JSON có schema (pydantic): VideoSummary, Digest. Model fallback theo config.
    webpage.py   : dựng HTML tĩnh vào docs/ (index.html = ngày mới nhất, YYYY-MM-DD.html mỗi ngày)
    notify.py    : gửi Telegram (HTML parse mode, chia tin < 3900 ký tự)
  → commit state/ summaries/ docs/ → deploy GitHub Pages (actions/deploy-pages)
```

## File
| File | Vai trò |
|---|---|
| `channels.txt` | Link kênh, mỗi dòng một link (`@handle`, `/channel/UC…`, `/c/…`) |
| `config.yaml` | language, models, lookback_days, max_videos_per_run, skip_shorts, video_fps, low_resolution, max_attempts, telegram_detail, site_url |
| `digest/summarize.py` | `VIDEO_PROMPT`, `DIGEST_PROMPT`, schema, `GeminiSummarizer`, `FakeSummarizer` |
| `state/processed.json` | `{video_id: {status: done/failed/skipped, attempts, date}}`, tự dọn sau lookback+30 ngày |
| `summaries/YYYY-MM-DD/` | `<video_id>.json` (metadata + tóm tắt), `_digest.json`, `_failed.json` |
| `docs/` | Trang web sinh ra, không sửa tay |
| `.github/workflows/digest.yml` | Cron + commit + Pages |

## Khung dữ liệu (đổi thì phải sửa cả webpage.py, notify.py, FakeSummarizer)
- VideoSummary: `core` (str), `sections[] {heading, timestamp, points[]}`, `topics[]`
- Digest: `highlights[]`, `themes[] {title, points[], video_ids[]}`

## Lệnh
```bash
pip install -r requirements.txt
python digest/main.py --fake --no-telegram   # chạy cả luồng với tóm tắt giả lập, không cần key
GEMINI_API_KEY=... python digest/main.py --no-telegram
open docs/index.html
python digest/get_chat_id.py <BOT_TOKEN>     # lấy TELEGRAM_CHAT_ID
```
Secrets cần trên GitHub: `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.

## Luật
- Không bao giờ commit API key/token; chỉ đọc từ biến môi trường.
- Một kênh hoặc video lỗi không được làm hỏng cả lượt chạy (bắt lỗi theo từng mục, lưu tiến độ sau mỗi video).
- Hết quota Gemini (429 lặp lại) → `QuotaExhausted`, dừng, để phần còn lại cho lần sau.
- Tên module tránh trùng thư viện chuẩn Python (vì vậy là `webpage.py`/`notify.py`, không phải `site.py`/`telegram.py`).
- Trang web và Telegram viết tiếng Việt; prompt cấm câu kiểu "video giới thiệu…".

## Trạng thái (23/10/2026)
- **Đã chạy thật local (Windows) với Gemini + YouTube**: resolve channel ID, RSS/fallback, nhận diện Shorts,
  `fps` + `media_resolution` với URL YouTube đều chạy. Timestamp khớp mục lục chương của tác giả (±1 giây).
- ID video có thể bắt đầu bằng `_` → `load_day` chỉ loại đúng `_digest.json`/`_failed.json`.
- Kênh mẫu: @AnhBaTaiChinh-88. Chạy local: `$env:GEMINI_API_KEY="..."; python digest/main.py --no-telegram`.
- **Đã lên GitHub**: repo public `buiminhdn/yt-digest`, đủ 3 secrets, Pages (Source: GitHub Actions) ở
  https://buiminhdn.github.io/yt-digest/. Telegram gửi được (từ local). Workflow chạy tay đầu tiên thành công,
  YouTube không chặn IP runner. Bot commit kết quả mỗi lượt → nhớ `git pull` trước khi sửa local.

## Việc tiếp theo gợi ý
1. Theo dõi vài lượt cron 05:30 đầu tiên (Telegram có về không, RSS/fallback trên runner).
2. Cân nhắc `telegram_detail: short` (điểm nhấn + link web) khi đã quen đọc trên web.
3. Sau đó: tìm kiếm lại kiến thức cũ trên trang web; hỏi đáp trên kho ghi chú; thêm kênh qua lệnh Telegram bot.
