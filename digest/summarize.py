"""Tóm tắt nội dung từng video và tổng hợp kiến thức trong ngày bằng Gemini."""
import json
import time

from pydantic import BaseModel, Field

# ---------------- Khung dữ liệu đầu ra ----------------


class Section(BaseModel):
    heading: str = Field(description="Tên phần nội dung, ngắn gọn")
    timestamp: str = Field(description="Thời điểm phần này bắt đầu, dạng mm:ss hoặc h:mm:ss; rỗng nếu không rõ")
    points: list[str] = Field(description="1-3 ý kiến thức then chốt, mỗi ý một câu ngắn có số liệu")


class VideoSummary(BaseModel):
    core: str = Field(description="1-2 câu: kết luận cốt lõi, viết thẳng nội dung")
    sections: list[Section]
    topics: list[str]


class Theme(BaseModel):
    title: str
    points: list[str]
    video_ids: list[str]


class Digest(BaseModel):
    highlights: list[str]
    themes: list[Theme]


# ---------------- Prompt (sửa ở đây nếu muốn đổi phong cách) ----------------

VIDEO_PROMPT = """Nhiệm vụ: rút KIẾN THỨC CỐT LÕI của video YouTube này thành ghi chú NGẮN,
đọc trong 1-2 phút mà nắm được điều đáng giá nhất, không cần xem video.
(Kênh: {channel} | Tiêu đề: {title})

Trả về JSON:
- core: 1-2 câu nêu thẳng kết luận quan trọng nhất.
- sections: TỐI ĐA 5 phần, theo các phần lớn của video (gộp các mục nhỏ liền nhau thành một phần):
    - heading: tên phần, dưới 8 chữ
    - timestamp: thời điểm phần đó bắt đầu (phần gộp thì lấy lúc mục đầu tiên được gộp bắt đầu)
    - points: 1-3 ý, mỗi ý MỘT câu dưới 30 chữ.
- topics: 1-3 nhãn chủ đề ngắn.

QUY TẮC BẮT BUỘC:
1. Viết TRỰC TIẾP kiến thức, không phải lời giới thiệu video.
   SAI: "Video giới thiệu 3 cách tăng tốc app", "Tác giả chia sẻ về...", "Trong video, anh ấy nói..."
   ĐÚNG: "3 cách tăng tốc app: lazy-load ảnh (-40% thời gian tải), cache API, nén bundle."
2. Chỉ giữ thứ người đọc dùng được: con số then chốt, công thức, tên công cụ, bước làm.
   BỎ: ví dụ minh họa, kể chuyện, diễn giải lý do dài dòng, ý lặp lại, ý hiển nhiên.
3. Video kiểu danh sách (20 thói quen, 10 mẹo...): KHÔNG liệt kê từng mục. Gộp thành vài nhóm
   và chỉ nêu các mục có giá trị nhất kèm con số.
4. Tổng độ dài TOÀN BỘ ghi chú (tính cả core), đếm theo âm tiết:
   dưới 15 phút video: tối đa 150 chữ; 15-45 phút: tối đa 300 chữ; trên 45 phút: tối đa 400 chữ.
5. Bỏ quảng cáo, nhà tài trợ, lời chào, kêu gọi like/subscribe.
6. Chỉ dùng nội dung có trong video, không bịa thêm.
7. Viết bằng {language}, câu cụt kiểu ghi chú; giữ thuật ngữ tiếng Anh khi cần."""

DIGEST_PROMPT = """Dưới đây là ghi chú kiến thức từ các video YouTube mới trong ngày.
Hãy tổng hợp thành bản đọc trong 2 phút, trả về JSON:

- highlights: 3-5 kiến thức quan trọng nhất hôm nay, mỗi ý MỘT câu dưới 30 chữ.
- themes: tối đa 4 nhóm chủ đề, CHỈ tạo nhóm khi có từ 2 video trở lên cùng chủ đề.
  Video không chung chủ đề với video nào khác thì không xếp nhóm (themes có thể rỗng). Mỗi nhóm có:
    - title: tên chủ đề, ngắn
    - points: 2-4 ý gộp/đối chiếu giữa các video, mỗi ý một câu dưới 30 chữ.
      KHÔNG lặp lại ý đã có trong highlights. Kênh nói khác nhau thì nêu cả hai.
    - video_ids: các video_id thuộc nhóm (ít nhất 2)

QUY TẮC: viết trực tiếp kiến thức, không viết kiểu "kênh X giới thiệu...", "video này nói về...".
Chỉ giữ con số then chốt và việc làm được; bỏ ví dụ, diễn giải. Chỉ dùng thông tin trong dữ liệu.
Viết bằng {language}.

DỮ LIỆU:
{data}"""


class QuotaExhausted(Exception):
    """Hết quota Gemini, dừng và để phần còn lại cho lần chạy sau."""


# ---------------- Gọi Gemini ----------------


class GeminiSummarizer:
    def __init__(self, api_key: str, cfg: dict):
        from google import genai  # import muộn để chế độ --fake không cần key

        self.client = genai.Client(api_key=api_key)
        self.cfg = cfg

    def _call(self, contents, schema, extra: dict | None = None):
        from google.genai import errors, types

        last_err = None
        for model in list(self.cfg["models"]):
            for attempt in range(3):
                try:
                    resp = self.client.models.generate_content(
                        model=model,
                        contents=contents,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=schema,
                            temperature=0.3,
                            **(extra or {}),
                        ),
                    )
                    # Nhớ model chạy được để lần gọi sau thử nó trước
                    if self.cfg["models"][0] != model:
                        self.cfg["models"] = [model] + [m for m in self.cfg["models"] if m != model]
                    if isinstance(resp.parsed, schema):
                        return resp.parsed.model_dump()
                    return schema.model_validate_json(resp.text).model_dump()
                except errors.ClientError as e:
                    last_err = e
                    if e.code == 404:  # model không tồn tại -> thử model kế
                        break
                    if e.code == 429:  # quá nhanh hoặc hết quota
                        if attempt == 2:
                            raise QuotaExhausted(str(e)) from e
                        time.sleep(40 * (attempt + 1))
                        continue
                    raise
                except errors.ServerError as e:  # 5xx tạm thời
                    last_err = e
                    time.sleep(20 * (attempt + 1))
        raise last_err or RuntimeError("Không gọi được Gemini")

    def summarize_video(self, video: dict) -> dict:
        from google.genai import types

        prompt = VIDEO_PROMPT.format(
            channel=video["channel"], title=video["title"], language=self.cfg["language"]
        )
        contents = types.Content(
            role="user",
            parts=[
                types.Part(
                    file_data=types.FileData(file_uri=video["url"], mime_type="video/mp4"),
                    video_metadata=types.VideoMetadata(fps=float(self.cfg.get("video_fps", 0.2))),
                ),
                types.Part(text=prompt),
            ],
        )
        extra = {}
        if self.cfg.get("low_resolution", True):
            extra["media_resolution"] = types.MediaResolution.MEDIA_RESOLUTION_LOW
        return self._call(contents, VideoSummary, extra)

    def build_digest(self, records: list[dict]) -> dict:
        data = json.dumps(
            [
                {
                    "video_id": r["video_id"],
                    "channel": r["channel"],
                    "title": r["title"],
                    "core": r["core"],
                    "notes": [p for s in r["sections"] for p in s["points"]],
                }
                for r in records
            ],
            ensure_ascii=False,
        )
        prompt = DIGEST_PROMPT.format(language=self.cfg["language"], data=data)
        return self._call(prompt, Digest)


class FakeSummarizer:
    """Dùng để chạy thử toàn bộ luồng (Telegram) mà không cần Gemini."""

    def __init__(self, cfg: dict):
        self.cfg = cfg

    def summarize_video(self, video: dict) -> dict:
        n = sum(map(ord, video["video_id"]))
        return {
            "core": "[Chạy thử] Đây là chỗ hiện kiến thức cốt lõi của video, viết thẳng nội dung.",
            "sections": [
                {
                    "heading": f"Phần {i + 1}",
                    "timestamp": f"{i * 4}:{(n + i) % 60:02d}",
                    "points": [f"Ý kiến thức {i + 1}.{j + 1}, kèm số liệu và ví dụ cụ thể." for j in range(3)],
                }
                for i in range(3)
            ],
            "topics": [["AI", "Lập trình", "Kinh doanh"][n % 3]],
        }

    def build_digest(self, records: list[dict]) -> dict:
        groups: dict[str, list[str]] = {}
        for r in records:
            groups.setdefault(r["topics"][0], []).append(r["video_id"])
        return {
            "highlights": ["[Chạy thử] Kiến thức nổi bật số 1.", "[Chạy thử] Kiến thức nổi bật số 2."],
            "themes": [
                {"title": t, "points": [f"Ý tổng hợp về {t} (giả lập)."], "video_ids": ids}
                for t, ids in groups.items()
            ],
        }
