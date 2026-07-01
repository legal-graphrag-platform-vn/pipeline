# Hướng Dẫn Chạy Pipeline

- **Bước 1: Cào dữ liệu từ vbpl.vn (Crawl)**
  - Lệnh chạy: `python main.py crawl --url "<url>" --doc-id <doc_id> --number "<so_hieu>"`
  - Dữ liệu lưu tại: `data/raw/<doc_id>/`

- **Bước 2: Phân tích cấu trúc luật (Parse)**
  - Từ dữ liệu đã cào: `python main.py parse --doc-id <doc_id>`
  - Từ file PDF: `python main.py parse --doc-id <doc_id> --pdf <path> [--backend pypdf|auto] [--ocr|--no-ocr]`
    - `--no-ocr` (Mặc định): Trích xuất trực tiếp từ text layer gốc (dành cho file PDF sạch convert từ Word/HTML).
    - `--ocr`: Ép buộc chạy OCR Tesseract (dành cho file PDF dạng ảnh scan/không có text layer, yêu cầu máy đã cài Tesseract OCR).
  - Từ file text (.txt): `python main.py parse --doc-id <doc_id> --txt <path> --number "<so_hieu>" --title "<tieu_de>"`
  - Cấu trúc lưu tại: `data/processed/<doc_id>/hierarchy.json`

- **Bước 3: Trích xuất AI (LLM Extraction)**
  - Cấu hình file `.env`: Chọn `LLM_PROVIDER` là `gemini`, `minimax`, `qwen`, hoặc `openai` và điền API key.
  - Lệnh chạy: `python main.py extract --doc-id <doc_id>`
  - Kết quả lưu tại: `data/processed/<doc_id>/{accepted,review_queue,rejected}.jsonl`

- **Chạy tự động toàn bộ luồng (Crawl -> Parse -> AI):**
  - Lệnh chạy: `python main.py ingest --url "<url>" --doc-id <doc_id> --number "<so_hieu>"`
