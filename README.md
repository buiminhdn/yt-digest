# YT Digest

Tự động tóm tắt video mới từ các kênh YouTube bạn theo dõi. Mỗi sáng bạn nhận một bản digest qua **Telegram**.

Bạn chỉ cần làm một việc: **dán link kênh vào `channels.txt`**. Mọi khâu còn lại đều chạy tự động:

```
05:30 mỗi sáng (GitHub Actions, miễn phí)
  → đọc RSS của từng kênh (RSS lỗi thì đọc trang /videos), tìm video mới (bỏ qua Shorts và video đã tóm)
  → Gemini "xem" từng video và rút kiến thức cốt lõi thành ghi chú ngắn (1-2 phút đọc/video)
    (con số then chốt, công thức, công cụ, các bước), kèm timestamp, để bạn không cần xem video
  → tổng hợp kiến thức trong ngày theo chủ đề (gộp ý trùng giữa các kênh)
  → gửi Telegram
```

---

## Cài đặt một lần (khoảng 15 phút)

### 1. Lấy Gemini API key (miễn phí)
Vào https://aistudio.google.com/apikey, bấm **Create API key** rồi copy key.

### 2. Tạo bot Telegram
1. Mở Telegram, tìm **@BotFather**, gõ `/newbot`, đặt tên. Bạn sẽ nhận được **token** dạng `123456:ABC...`.
2. Mở bot vừa tạo và nhắn cho nó một tin bất kỳ (ví dụ "hi").
3. Lấy chat ID bằng một trong hai cách:
   - Mở trình duyệt: `https://api.telegram.org/bot<TOKEN>/getUpdates`, tìm `"chat":{"id": 123456789`
   - Hoặc chạy: `python digest/get_chat_id.py <TOKEN>`

### 3. Đưa code lên GitHub
Tạo một repo **public** mới trên GitHub (ví dụ `yt-digest`), rồi chạy trong thư mục này:

```bash
git init && git add . && git commit -m "init"
git branch -M main
git remote add origin https://github.com/<username>/yt-digest.git
git push -u origin main
```

> Đừng kéo thả file lên web GitHub: macOS ẩn thư mục `.github`, workflow sẽ bị thiếu.

### 4. Thêm 3 secret
Vào repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Tên | Giá trị |
|---|---|
| `GEMINI_API_KEY` | key ở bước 1 |
| `TELEGRAM_BOT_TOKEN` | token ở bước 2 |
| `TELEGRAM_CHAT_ID` | chat ID ở bước 2 |

### 5. Dán link kênh
Sửa `channels.txt` (sửa thẳng trên web GitHub hoặc app GitHub trên điện thoại cũng được). Mỗi dòng một link, ví dụ `https://www.youtube.com/@tenkenh`.

### 6. Chạy thử
**Actions → YouTube Digest → Run workflow**. Khoảng vài phút sau, Telegram sẽ báo về.
Từ đó trở đi, hệ thống tự chạy lúc 05:30 mỗi sáng.

---

## Dùng hằng ngày
- **Đọc:** mở tin Telegram. Thứ tự đọc: "Kiến thức nổi bật", rồi "Tổng hợp theo chủ đề", rồi ghi chú chi tiết của video nào bạn muốn đào sâu.
- **Thêm hoặc bớt kênh:** sửa `channels.txt`.
- **Xem lại ngày cũ:** cuộn lại tin Telegram, hoặc xem JSON trong `summaries/`.

## Tùy chỉnh (`config.yaml`)
| Mục | Ý nghĩa |
|---|---|
| `language` | Ngôn ngữ tóm tắt |
| `models` | Model Gemini. Đổi khi Google ra model mới |
| `lookback_days` | Lần đầu chỉ lấy video trong N ngày gần nhất |
| `max_videos_per_run` | Giới hạn số video mỗi ngày |
| `skip_shorts` | Bỏ qua Shorts |
| `video_fps`, `low_resolution` | Tiết kiệm token. Tăng `video_fps` (ví dụ 1) nếu kênh nặng về demo màn hình |
| `telegram_detail` | `full` = gửi cả digest, `short` = chỉ kiến thức nổi bật + danh sách link video |

- **Đổi giờ chạy:** sửa dòng `cron` trong `.github/workflows/digest.yml`. Giờ ở đây là UTC, tức giờ VN trừ 7.
- **Đổi phong cách tóm tắt:** sửa `VIDEO_PROMPT` và `DIGEST_PROMPT` trong `digest/summarize.py`.

## Chạy thử trên máy
```bash
pip install -r requirements.txt
python digest/main.py --fake --no-telegram   # tóm tắt giả lập, chỉ để kiểm tra luồng
GEMINI_API_KEY=... python digest/main.py --no-telegram
```

## Giới hạn cần biết
- Gói free của Gemini cho tối đa **8 giờ video YouTube mỗi ngày**. Khi hết quota, phần còn lại tự dời sang hôm sau.
- Chỉ tóm tắt được video **public**. Video riêng tư, chỉ dành cho hội viên, hoặc livestream chưa kết thúc sẽ được thử lại tối đa 3 lần rồi liệt kê ở mục "Không tóm tắt được".
- Lịch chạy của GitHub có thể trễ 5–30 phút so với giờ đặt.
- Repo public nghĩa là ghi chú trong `summaries/` và danh sách kênh ai cũng xem được. Muốn kín thì chuyển repo sang private, vẫn chạy bình thường (tốn phút Actions của gói free).
