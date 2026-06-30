# Hướng Dẫn Chạy Parse

* **Parse từ dữ liệu đã cào:** `python main.py parse --doc-id <doc_id>`
* **Parse từ PDF (Copy được chữ):** `python main.py parse --doc-id <doc_id> --pdf <path> --backend pypdf`
* **Parse từ PDF (Bản scan/ảnh):** `python main.py parse --doc-id <doc_id> --pdf <path> --backend auto` (yêu cầu Tesseract OCR)
* **Kết quả:** Cấu trúc Điều/Khoản/Điểm lưu tại `data/processed/<doc_id>/hierarchy.json`
