# YT Digest — bối cảnh cho Claude Code

## Mục tiêu
Tự động hóa 100% việc nắm kiến thức từ các kênh YouTube Minh theo dõi. Minh chỉ dán link kênh
vào `channels.txt`; mỗi sáng hệ thống tự tìm video mới, chép lại **toàn bộ kiến thức** thành ghi chú,
tổng hợp theo chủ đề, gửi Telegram và dựng trang web. Mục tiêu đọc 10–30 phút/ngày thay vì xem video.

**Yêu cầu cốt lõi (Minh đã nhấn mạnh):** đầu ra là *kiến thức của video* (viết thẳng nội dung,
giữ số liệu/công cụ/các bước/ví dụ/lập luận), KHÔNG phải giới thiệu video ("video này nói về…")
và KHÔNG phải gợi ý video nên xem. Đừng thêm lại điểm "đáng xem" hay mục "nên xem".

## Kiến trúc
```
GitHub Actions cron 22:30 UTC (05:30 giờ VN)
  digest/main.py
    youtube.py   : link kênh → channel ID (cache state/channels.json) → RSS
                   (youtube.com/feeds/videos.xml?channel_id=...) → lọc Shorts (HEAD /shorts/<id>: 200 = Short)
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
- VideoSummary: `core` (str), `sections[] {heading, timestamp, points[]}`, `takeaways[]`, `topics[]`
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
- Code hoàn chỉnh; đã test với dữ liệu giả lập (parse RSS, chống trùng, render web mobile/dark, chia tin Telegram,
  dựng request Gemini và fallback model bằng stub).
- **Chưa chạy thật** với Gemini và YouTube (môi trường dựng code không truy cập được). Lần chạy thật đầu tiên
  cần kiểm tra: tên model trong `config.yaml` còn hợp lệ, `video_metadata.fps` + `media_resolution` được chấp nhận
  với URL YouTube, resolve channel ID từ HTML kênh, nhận diện Shorts.
- Chưa có: repo GitHub, secrets, bot Telegram, danh sách kênh thật.

## Việc tiếp theo gợi ý
1. Thêm vài kênh vào `channels.txt`, chạy local với key thật, xem chất lượng ghi chú và chỉnh `VIDEO_PROMPT`.
2. Tạo repo GitHub, push, thêm secrets, bật Pages (Source: GitHub Actions), Run workflow.
3. Sau đó: tìm kiếm lại kiến thức cũ trên trang web; hỏi đáp trên kho ghi chú; thêm kênh qua lệnh Telegram bot.
