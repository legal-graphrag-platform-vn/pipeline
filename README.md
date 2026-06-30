# Legal GraphRAG VN — Graph Construction Pipeline (Milestone 1 + 2)

Crawler (vbpl.vn) → Hierarchy Parser (Chương/Điều/Khoản/Điểm) → LLM Extraction
(Gemini, two-pass) → Schema/Ontology Validation → Confidence Scoring → Decision
Gate. Xem [`REPORT.md`](REPORT.md) cho thiết kế chi tiết, lý do kỹ thuật, và
data flow đầy đủ.

## Quick start

```bash
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env   # điền GEMINI_API_KEY — xem hướng dẫn lấy key bên dưới

python main.py crawl --url "https://vbpl.vn/van-ban/chi-tiet/luat-doanh-nghiep-so-59-2020-qh14--142881" \
    --doc-id LDN2020 --number "59/2020/QH14"
python main.py parse --doc-id LDN2020
python main.py extract --doc-id LDN2020   # cần GEMINI_API_KEY

python -m pytest tests/ -v
```

## Parse trực tiếp từ PDF (vd PDF gốc tải tay từ vbpl.vn)

Ngoài luồng `crawl` (lấy text từ HTML body), có thể parse thẳng một file PDF đã tải
sẵn — kể cả PDF dạng **scan/ảnh** (không có text layer), tự động OCR bằng Tesseract:

```bash
python main.py parse --doc-id LDN2020 --pdf data/VanBanGoc_59.signed.pdf \
    --number "59/2020/QH14" --title "Luật Doanh nghiệp 2020"
```

`parse_pdf()` tự phát hiện PDF có text layer hay không (đo số ký tự trích được
trung bình mỗi trang); nếu không đủ (PDF scan) sẽ tự fallback sang OCR.

Nếu PDF chắc chắn có text layer thật (bôi đen/copy được, không phải bản scan),
dùng `--backend pypdf` để trích bằng `pypdf` thay vì PyMuPDF — nhanh hơn, không
cần OCR, chính xác gần như tuyệt đối với PDF dạng này:

```bash
python main.py parse --doc-id LDN762025QH15 --pdf data/LDN762025QH15.pdf \
    --number "76/2025/QH15" --title "..." --backend pypdf
```

**Yêu cầu cài Tesseract OCR engine** (binary riêng, không cài qua `pip`):

- Windows: tải installer tại https://github.com/UB-Mannheim/tesseract/wiki (cần quyền
  admin), nhớ tick chọn gói ngôn ngữ **Vietnamese (vie)** lúc cài, hoặc cài qua
  Chocolatey: `choco install tesseract -y` (chạy terminal với quyền Administrator).
- Nếu Tesseract không nằm trong `PATH`, set đường dẫn trong code/`.env`:
  `pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"`.
- Kiểm tra cài thành công: `tesseract --version` và `tesseract --list-langs` (phải
  thấy `vie` trong danh sách).

## Lấy Gemini API key

1. Vào https://aistudio.google.com/apikey
2. Đăng nhập Google, bấm "Create API key"
3. Dán vào `.env`: `GEMINI_API_KEY=<key của bạn>`

Không có key vẫn chạy được `crawl`/`parse`; `extract`/`ingest` sẽ báo lỗi rõ ràng
ngay lập tức nếu thiếu key.

Chi tiết đầy đủ (thách thức thực tế, quyết định kỹ thuật, code walkthrough): xem
[`REPORT.md`](REPORT.md).
