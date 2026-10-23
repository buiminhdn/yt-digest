"""Tóm tắt nội dung từng video và tổng hợp kiến thức trong ngày bằng Gemini."""
import json
import time

from pydantic import BaseModel, Field

# ---------------- Khung dữ liệu đầu ra ----------------


class Section(BaseModel):
    heading: str = Field(description="Tên phần nội dung, ngắn gọn")
    timestamp: str = Field(description="Thời điểm phần này bắt đầu, dạng mm:ss hoặc h:mm:ss; rỗng nếu không rõ")
    points: list[str] = Field(description="Các ý kiến thức của phần này, viết trực tiếp, đầy đủ chi tiết")


class VideoSummary(BaseModel):
    core: str = Field(description="2-4 câu: kiến thức/kết luận cốt lõi, viết thẳng nội dung")
    sections: list[Section]
    takeaways: list[str]
    topics: list[str]


class Theme(BaseModel):
    title: str
    points: list[str]
    video_ids: list[str]


class Digest(BaseModel):
    highlights: list[str]
    themes: list[Theme]


# ---------------- Prompt (sửa ở đây nếu muốn đổi phong cách) ----------------

VIDEO_PROMPT = """Nhiệm vụ: chuyển toàn bộ NỘI DUNG KIẾN THỨC của video YouTube này thành ghi chú,
để người đọc nắm được hết kiến thức mà KHÔNG cần xem video.
(Kênh: {channel} | Tiêu đề: {title})

Trả về JSON:
- core: 2-4 câu nêu thẳng kiến thức/kết luận cốt lõi của video.
- sections: đi theo cấu trúc của video, mỗi phần nội dung chính là một section:
    - heading: tên phần
    - timestamp: thời điểm phần đó bắt đầu
    - points: các ý kiến thức của phần đó. Mỗi ý là một câu hoàn chỉnh, có đủ chi tiết.
- takeaways: những việc cụ thể có thể áp dụng ngay (mảng rỗng nếu video không có).
- topics: 1-3 nhãn chủ đề ngắn.

QUY TẮC BẮT BUỘC:
1. Viết TRỰC TIẾP kiến thức, như ghi chú của người học, không phải lời giới thiệu video.
   SAI: "Video giới thiệu 3 cách tăng tốc app", "Tác giả chia sẻ về...", "Trong video, anh ấy nói..."
   ĐÚNG: "Có 3 cách tăng tốc app: (1) lazy-load ảnh, giảm 40% thời gian tải; (2) ...; (3) ..."
2. Giữ nguyên mọi chi tiết cụ thể: số liệu, tên công cụ/sản phẩm/người, câu lệnh, công thức,
   các bước làm theo thứ tự, ví dụ minh họa, lý do và lập luận đằng sau mỗi kết luận.
3. Bao phủ TOÀN BỘ nội dung có giá trị, không chỉ vài ý đầu. Độ dài tỉ lệ với video:
   khoảng 150-300 từ cho video 5-10 phút, 400-800 từ cho 20-30 phút, 800-1500 từ cho video trên 1 giờ.
4. Bỏ qua quảng cáo, nhà tài trợ, lời chào, kêu gọi like/subscribe, đoạn nói lan man.
5. Chỉ dùng nội dung có trong video, không bịa thêm.
6. Viết bằng {language}; giữ nguyên thuật ngữ kỹ thuật tiếng Anh khi cần."""

DIGEST_PROMPT = """Dưới đây là ghi chú kiến thức từ các video YouTube mới trong ngày.
Hãy tổng hợp thành bản kiến thức đọc trong vài phút, trả về JSON:

- highlights: 3-6 kiến thức quan trọng/mới nhất hôm nay, mỗi ý 1-2 câu, nêu thẳng nội dung.
- themes: 2-6 nhóm chủ đề. Mỗi nhóm có:
    - title: tên chủ đề
    - points: 3-10 ý kiến thức tổng hợp của nhóm. Gộp các ý trùng nhau giữa các kênh thành một;
      khi các kênh có quan điểm hoặc số liệu khác nhau thì nêu rõ cả hai.
    - video_ids: các video_id thuộc nhóm (mỗi video thuộc đúng 1 nhóm)

QUY TẮC: viết trực tiếp kiến thức, không viết kiểu "kênh X giới thiệu...", "video này nói về...".
Giữ số liệu, tên công cụ, bước làm cụ thể. Chỉ dùng thông tin trong dữ liệu. Viết bằng {language}.

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
    """Dùng để chạy thử toàn bộ luồng (trang web, Telegram) mà không cần Gemini."""

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
            "takeaways": ["Việc cụ thể có thể làm ngay (giả lập)."],
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
