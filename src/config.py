"""Cấu hình tập trung cho pipeline, đọc từ biến môi trường / .env (pydantic-settings).

Lý do dùng pydantic-settings thay vì os.getenv rải rác: type-checking tại
thời điểm khởi động, lỗi thiếu config rõ ràng ngay (fail-fast) thay vì lỗi
mơ hồ giữa chừng khi gọi Gemini API.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    gemini_api_key: str = Field(default="", description="API key cho Gemini, lấy tại aistudio.google.com/apikey")
    gemini_model: str = Field(default="gemini-2.5-flash")

    data_raw_dir: Path = Field(default=Path("data/raw"))
    data_processed_dir: Path = Field(default=Path("data/processed"))

    confidence_threshold_auto: float = Field(default=0.7, ge=0.0, le=1.0)
    confidence_threshold_review: float = Field(default=0.3, ge=0.0, le=1.0)

    tesseract_cmd: str = Field(
        default="", description="Đường dẫn tesseract.exe nếu không nằm trong PATH (vd Windows)."
    )
    tessdata_dir: str = Field(
        default="",
        description="Thư mục chứa *.traineddata (vd gói ngôn ngữ vie.traineddata tải riêng, "
        "không ghi được vào thư mục cài đặt Tesseract mặc định do thiếu quyền admin).",
    )

    def require_gemini_api_key(self) -> str:
        """Trả về API key hoặc raise lỗi rõ ràng nếu thiếu (dùng trước khi gọi LLM)."""
        if not self.gemini_api_key:
            raise RuntimeError(
                "Thiếu GEMINI_API_KEY. Lấy key tại https://aistudio.google.com/apikey "
                "rồi đặt vào file .env (xem .env.example)."
            )
        return self.gemini_api_key


settings = Settings()
