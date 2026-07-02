

from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright

from src.crawler.models import DocumentMetadata

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

_EFFECTIVE_FROM_RE = re.compile(r"Ngày có hiệu lực:\s*\n?\s*(\d{2})/(\d{2})/(\d{4})")
_ISSUED_DATE_RE = re.compile(r"ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})", re.IGNORECASE)
_STATUS_KEYWORDS = [
    "Hết hiệu lực một phần",
    "Hết hiệu lực toàn bộ",
    "Còn hiệu lực",
    "Chưa có hiệu lực",
]
_ISSUERS = ["QUỐC HỘI", "CHÍNH PHỦ", "THỦ TƯỚNG CHÍNH PHỦ", "ỦY BAN THƯỜNG VỤ QUỐC HỘI"]

# Tiền tố ký hiệu số văn bản -> loại văn bản (ADR doc_type enum). Khớp dài nhất trước
# (vd "ND-CP" trước "ND") để tránh nhận nhầm số hiệu ghép.
_DOC_TYPE_BY_PREFIX = [
    ("ND-CP", "Decree"),
    ("QH", "Law"),
    ("TT", "Circular"),
    ("NQ", "Resolution"),
    ("QD", "Decision"),
]


def _infer_doc_type(number: str) -> str:
    last_segment = number.split("/")[-1].upper().replace("Đ", "D")
    for prefix, doc_type in _DOC_TYPE_BY_PREFIX:
        if last_segment.startswith(prefix):
            return doc_type
    return "Law"


def _parse_vn_date(day: str, month: str, year: str) -> date:
    return date(int(year), int(month), int(day))


def _extract_metadata(body_text: str, doc_id: str, number: str, source_url: str) -> DocumentMetadata:
    lines = [line.strip() for line in body_text.splitlines() if line.strip()]
    number_prefix = number.split("/")[0]

    title = next(
        (line for line in lines if "số" in line.lower() and number_prefix in line),
        doc_id,
    )
    status = next((line for line in lines if line in _STATUS_KEYWORDS), "active")
    issued_by = next((line for line in lines if line in _ISSUERS), None)

    effective_from = None
    if m := _EFFECTIVE_FROM_RE.search(body_text):
        effective_from = _parse_vn_date(*m.groups())

    issued_date = None
    if m := _ISSUED_DATE_RE.search(body_text):
        issued_date = _parse_vn_date(*m.groups())

    return DocumentMetadata(
        doc_id=doc_id,
        title=title,
        number=number,
        doc_type=_infer_doc_type(number),
        issued_by=issued_by,
        issued_date=issued_date,
        effective_from=effective_from,
        effective_to=None,
        status=status,
        source_url=source_url,
    )


def _extract_body_lines(full_text: str) -> list[str]:
    """Cắt phần nav/breadcrumb lặp ở đầu trang, giữ lại nội dung văn bản thật.

    vbpl.vn render cụm tab "Nội dung | Thuộc tính | Lược đồ | Văn bản gốc | Tải về"
    hai lần (breadcrumb rồi tới heading khối nội dung) -> nội dung văn bản thật nằm
    SAU lần xuất hiện cuối cùng của dòng "Tải về".
    """
    lines = full_text.splitlines()
    last_tai_ve = -1
    for i, line in enumerate(lines):
        if line.strip() == "Tải về":
            last_tai_ve = i
    if last_tai_ve == -1:
        logger.warning("Không tìm thấy marker 'Tải về' trên trang — dùng toàn bộ text làm nội dung.")
        return lines
    
    body_lines = lines[last_tai_ve + 1 :]
    
    # 1.    Tìm vị trí bắt đầu thực sự của Luật (Chương đầu tiên, Phần đầu tiên, hoặc Điều 1).
    start_index = -1
    start_pattern = re.compile(
        r"^(Chương\s+[IVXLCDM\d]+|Phần\s+(\d+|[IVXLCDM]+|thứ\s+\w+)|Điều\s+1\b)",
        re.IGNORECASE
    )
    for i, line in enumerate(body_lines):
        if start_pattern.match(line.strip()):
            start_index = i
            break
            
    if start_index != -1:
        body_lines = body_lines[start_index:]
        
    # 2.    Tìm vị trí bắt đầu của Điều luật cuối cùng để làm mốc an toàn.
    search_start_index = 0
    for i in range(len(body_lines) - 1, -1, -1):
        if re.match(r"^Điều\s+\d+\.", body_lines[i].strip()):
            search_start_index = i
            break
            
    # 3.    Nếu không tìm thấy Điều nào, mặc định tìm ở nửa sau văn bản.
    if search_start_index == 0:
        search_start_index = len(body_lines) // 2
        
    # 4.    Danh sách các marker chữ ký đặc trưng ở cuối văn bản luật.
    _SIGNATURE_MARKERS = {
        "CHỦ TỊCH QUỐC HỘI",
        "THỦ TƯỚNG CHÍNH PHỦ",
        "KT. THỦ TƯỚNG",
        "KÝ THAY",
        "KT. BỘ TRƯỞNG",
        "QUYỀN CHỦ TỊCH",
        "(Đã ký)",
        "(đã ký)",
    }
    
    truncate_index = -1
    for i in range(search_start_index, len(body_lines)):
        line_clean = body_lines[i].strip()
        is_redundant = (
            line_clean == "CƠ SỞ DỮ LIỆU QUỐC GIA VỀ PHÁP LUẬT"
            or line_clean == "Mục lục"
            or line_clean in _SIGNATURE_MARKERS
            or line_clean.startswith("Luật này được Quốc hội")
            or line_clean.startswith("Luật này đã được Quốc hội")
            or line_clean.startswith("Nghị định này được")
            or any(line_clean.startswith(m) for m in ["KT. THỦ TƯỚNG", "KT. BỘ TRƯỞNG", "KÝ THAY"])
        )
        if is_redundant:
            truncate_index = i
            break
            
    if truncate_index != -1:
        body_lines = body_lines[:truncate_index]
        
    return body_lines


def fetch_document(url: str, doc_id: str, number: str, timeout_ms: int = 30000) -> tuple[str, DocumentMetadata]:
    """Render trang chi tiết vbpl.vn bằng Playwright, trả về (full_text, metadata).

    `full_text` là nội dung văn bản pháp luật thuần, sẵn sàng làm input cho
    `parser.hierarchy_parser.parse_text()`. Dùng `new_context` với user-agent/locale
    thật thay vì `browser.new_page()` mặc định vì vbpl.vn có WAF chặn request có
    fingerprint headless trần (trả về "Web Page Blocked! Attack ID: ...").
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=_USER_AGENT,
            viewport={"width": 1366, "height": 900},
            locale="vi-VN",
        )
        page = context.new_page()
        page.goto(url, wait_until="networkidle", timeout=timeout_ms)
        page.wait_for_timeout(2000)
        body_text = page.inner_text("body")
        browser.close()

    metadata = _extract_metadata(body_text, doc_id=doc_id, number=number, source_url=url)
    full_text = "\n".join(_extract_body_lines(body_text))
    return full_text, metadata


def crawl_and_save(url: str, doc_id: str, number: str, raw_dir: Path) -> DocumentMetadata:
    """Crawl + lưu `data/raw/<doc_id>/source.txt` + `metadata.json`."""
    full_text, metadata = fetch_document(url, doc_id=doc_id, number=number)

    out_dir = raw_dir / doc_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "source.txt").write_text(full_text, encoding="utf-8")
    (out_dir / "metadata.json").write_text(
        metadata.model_dump_json(by_alias=True, indent=2, exclude_none=True),
        encoding="utf-8",
    )
    logger.info("Đã lưu %s vào %s", doc_id, out_dir)
    return metadata
