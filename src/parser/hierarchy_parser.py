"""Hierarchy Parser — PDF/text văn bản pháp luật VN -> ParsedDocument phân cấp.

Thiết kế tách 2 tầng:
  - `parse_lines()` : state machine thuần text, không phụ thuộc PyMuPDF -> dễ unit test
    với fixture text, không cần PDF thật.
  - `parse_pdf()`   : dùng PyMuPDF lấy text + font size theo từng dòng, dùng font size
    để phân biệt "Chương II" là tiêu đề (đứng riêng dòng, thường in đậm/to hơn thân bài)
    với trường hợp cụm từ "chương II" xuất hiện lẫn trong câu văn thường.

Lý do tách: nếu test với PDF thật ngay từ đầu, không cô lập được lỗi parser logic
với lỗi PDF extraction (đúng nguyên tắc milestone "Lỗi ở đâu phải biết ngay").
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.parser.models import Article, Clause, DocumentInfo, ParsedDocument, Point
from src.parser.patterns import (
    looks_like_title,
    match_article,
    match_chapter,
    match_clause,
    match_point,
)

logger = logging.getLogger(__name__)


@dataclass
class LineRecord:
    text: str
    font_size: float = 0.0
    bold: bool = False


@dataclass
class _ArticleBuilder:
    number: int
    title: str | None
    chapter: str | None
    chapter_title: str | None
    content_lines: list[str] = field(default_factory=list)
    clauses: list[Clause] = field(default_factory=list)

    def to_article(self) -> Article:
        return Article(
            number=self.number,
            title=self.title,
            content_raw="\n".join(self.content_lines).strip(),
            chapter=self.chapter,
            chapter_title=self.chapter_title,
            clauses=self.clauses,
        )


def parse_lines(lines: list[str], lenient_article: bool = False) -> list[Article]:
    """State machine cốt lõi: list các dòng text (đã strip blank thừa) -> list[Article].

    Không quan tâm font size — chỉ dùng regex pattern + heuristic "dòng toàn chữ hoa"
    để bắt tiêu đề chương. Dùng cho cả test fixture (text thuần) và làm fallback khi
    PDF không có font info (vd PDF đã convert từ Word mất metadata font).

    `lenient_article=True`: chấp nhận 1-2 ký tự rác trước "Điều" (dành riêng cho dòng
    lấy từ OCR — KHÔNG bật cho text layer thật, dễ nhận nhầm "Điều X." trích dẫn lồng
    trong dấu ngoặc kép của văn bản sửa đổi/bổ sung thành Điều cấp cao mới).

    Theo dõi trạng thái dấu ngoặc kép (“ ”, dùng trong văn bản "sửa đổi, bổ sung" để
    trích dẫn nguyên văn nội dung mới) bằng 1 counter `quote_depth`: khi đang ở trong
    trích dẫn (`quote_depth > 0`), KHÔNG nhận diện Điều/Khoản/Điểm mới trên dòng đó dù
    format có khớp regex — coi là nội dung tiếp nối của Khoản/Điểm cha. Lý do: nội dung
    trích dẫn thường tự có cấu trúc số/chữ cái riêng ("1.", "a)"...) của chính nó, nếu
    không tách biệt sẽ bị nhận nhầm thành Khoản/Điểm cấp cao mới (xem REPORT.md mục A7).
    """
    articles: list[Article] = []
    current_chapter: str | None = None
    current_chapter_title: str | None = None
    current_article: _ArticleBuilder | None = None
    current_clause: Clause | None = None
    current_point: Point | None = None

    def flush_article() -> None:
        nonlocal current_article, current_clause, current_point
        if current_article is not None:
            flush_clause()
            articles.append(current_article.to_article())
        current_article = None
        current_clause = None
        current_point = None

    def flush_clause() -> None:
        nonlocal current_clause, current_point
        if current_clause is not None and current_article is not None:
            flush_point()
            current_article.clauses.append(current_clause)
        current_clause = None
        current_point = None

    def flush_point() -> None:
        nonlocal current_point
        if current_point is not None and current_clause is not None:
            current_clause.points.append(current_point)
        current_point = None

    pending_chapter_title = False
    # Đếm độ sâu dấu ngoặc kép “ ” đang mở — > 0 nghĩa là dòng hiện tại nằm trong
    # khối trích dẫn nguyên văn (vd nội dung mới của khoản/điểm bị sửa đổi), nên
    # KHÔNG coi cấu trúc số/chữ cái bên trong nó là Khoản/Điểm thật của văn bản.
    quote_depth = 0

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        in_quote = quote_depth > 0
        quote_depth = max(0, quote_depth + line.count("“") - line.count("”"))

        if in_quote:
            # Đang trong trích dẫn -> chỉ coi là nội dung tiếp nối, không nhận diện
            # Chương/Điều/Khoản/Điểm mới trên dòng này.
            if current_article is not None:
                current_article.content_lines.append(line)
                if current_point is not None:
                    current_point.content = f"{current_point.content} {line}".strip()
                elif current_clause is not None:
                    current_clause.content = f"{current_clause.content} {line}".strip()
            continue

        chapter_num = match_chapter(line)
        if chapter_num is not None:
            current_chapter = chapter_num
            current_chapter_title = None
            pending_chapter_title = True
            continue

        if pending_chapter_title:
            pending_chapter_title = False
            if looks_like_title(line):
                current_chapter_title = line
                continue
            # Không phải tiêu đề chương (vd đi thẳng vào Điều) -> rơi qua xử lý bình thường

        article_match = match_article(line, lenient=lenient_article)
        if article_match is not None:
            flush_article()
            number, title = article_match
            current_article = _ArticleBuilder(
                number=number,
                title=title or None,
                chapter=current_chapter,
                chapter_title=current_chapter_title,
            )
            if title:
                current_article.content_lines.append(title)
            continue

        if current_article is None:
            # Dòng trước Điều đầu tiên (header văn bản, mục lục...) -> bỏ qua, log để debug
            logger.debug("Bỏ qua dòng ngoài cấu trúc Điều: %r", line)
            continue

        clause_match = match_clause(line)
        if clause_match is not None:
            flush_clause()
            number, content = clause_match
            current_clause = Clause(number=number, content=content)
            current_article.content_lines.append(line)
            continue

        point_match = match_point(line)
        if point_match is not None and current_clause is not None:
            flush_point()
            label, content = point_match
            current_point = Point(label=label, content=content)
            current_article.content_lines.append(line)
            continue

        # Dòng tiếp nối nội dung (continuation) của point/clause/article hiện tại
        current_article.content_lines.append(line)
        if current_point is not None:
            current_point.content = f"{current_point.content} {line}".strip()
        elif current_clause is not None:
            current_clause.content = f"{current_clause.content} {line}".strip()

    flush_article()
    return articles


def parse_text(text: str, document: DocumentInfo) -> ParsedDocument:
    """Parse từ text thuần (dùng cho unit test, không cần PDF)."""
    lines = text.splitlines()
    articles = parse_lines(lines)
    return ParsedDocument(document=document, articles=articles)


def extract_lines_with_font(pdf_path: str) -> list[LineRecord]:
    """Trích text theo dòng kèm font size lớn nhất trong dòng, dùng PyMuPDF.

    PyMuPDF được chọn (thay vì pdfplumber) vì expose trực tiếp font size/flags
    qua page.get_text("dict") mà không cần xử lý thêm — cần thiết để phân biệt
    tiêu đề Chương (thường to/đậm, đứng riêng dòng) với văn bản thân bài.
    """
    import fitz  # PyMuPDF — import cục bộ để module này import được dù chưa cài fitz

    records: list[LineRecord] = []
    with fitz.open(pdf_path) as doc:
        for page in doc:
            page_dict = page.get_text("dict")
            for block in page_dict.get("blocks", []):
                for line in block.get("lines", []):
                    spans = line.get("spans", [])
                    if not spans:
                        continue
                    text = "".join(s.get("text", "") for s in spans).strip()
                    if not text:
                        continue
                    max_size = max(s.get("size", 0.0) for s in spans)
                    is_bold = any("bold" in s.get("font", "").lower() for s in spans)
                    records.append(LineRecord(text=text, font_size=max_size, bold=is_bold))
    return records


def extract_lines_via_ocr(pdf_path: str, lang: str = "vie", dpi: int = 400) -> list[LineRecord]:
    """Trích text bằng OCR (Tesseract) — dùng khi PDF là bản scan/ảnh, không có text layer.

    Render từng trang ra ảnh độ phân giải cao (PyMuPDF `get_pixmap`) rồi đưa qua
    `pytesseract.image_to_string`. Không có font size/bold (OCR không trả metadata này)
    nên các LineRecord trả về đều có font_size=0.0 — `parse_lines()` đã tự fallback
    sang heuristic `looks_like_title()` (toàn chữ hoa) khi không có font info, nên vẫn
    tái dùng được state machine chung mà không cần sửa logic parse.

    Tiền xử lý ảnh (grayscale + autocontrast) trước khi OCR và DPI 400 (thay vì 300)
    để giảm lỗi nhận diện trên bản scan chất lượng thấp — vẫn không đảm bảo tuyệt đối
    chính xác 100% (xem REPORT.md mục A, OCR có thể đọc nhầm "Điều" thành chuỗi khác).
    """
    import fitz  # PyMuPDF
    import pytesseract
    from PIL import Image, ImageOps

    from src.config import settings

    if settings.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
    ocr_config = f"--tessdata-dir {settings.tessdata_dir} --psm 6" if settings.tessdata_dir else "--psm 6"

    records: list[LineRecord] = []
    zoom = dpi / 72
    matrix = fitz.Matrix(zoom, zoom)
    with fitz.open(pdf_path) as doc:
        for page_index, page in enumerate(doc):
            pix = page.get_pixmap(matrix=matrix)
            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            image = ImageOps.autocontrast(ImageOps.grayscale(image))
            try:
                text = pytesseract.image_to_string(image, lang=lang, config=ocr_config)
            except Exception:
                logger.exception("Lỗi OCR trang %d của %s", page_index + 1, pdf_path)
                continue
            for line in text.splitlines():
                line = line.strip()
                if line:
                    records.append(LineRecord(text=line))
            logger.info("OCR trang %d/%d xong (%d ký tự)", page_index + 1, doc.page_count, len(text))
    return records


def extract_lines_via_pypdf(pdf_path: str) -> list[LineRecord]:
    """Trích text bằng `pypdf` (`PdfReader.extract_text()`), dùng cho PDF có text layer thật
    (selectable/copy được) — không cần font metadata, chỉ dùng làm route thay thế PyMuPDF
    để so sánh/đối chiếu chất lượng trích xuất trên cùng 1 nguồn PDF text-based.
    """
    from pypdf import PdfReader

    records: list[LineRecord] = []
    reader = PdfReader(pdf_path)
    for page_index, page in enumerate(reader.pages):
        try:
            text = page.extract_text()
        except Exception:
            logger.exception("Lỗi pypdf extract trang %d của %s", page_index + 1, pdf_path)
            continue
        for line in (text or "").splitlines():
            line = line.strip()
            if line:
                records.append(LineRecord(text=line))
    return records


def parse_pdf(
    pdf_path: str,
    document: DocumentInfo,
    use_ocr: bool = False,
    backend: str = "auto",
) -> ParsedDocument:
    """Parse trực tiếp từ file PDF -> ParsedDocument.

    `backend`:
      - "auto" (mặc định): dùng PyMuPDF (`extract_lines_with_font`) nếu `use_ocr=False`.
      - "pypdf": dùng `extract_lines_via_pypdf` (PDF có text layer thật, không OCR).

    `use_ocr`:
      - True: chạy OCR (Tesseract).
      - False: dùng text layer thông thường (không OCR).
    """
    if use_ocr:
        logger.info("Chạy OCR (Tesseract) cho PDF: %s", pdf_path)
        records = extract_lines_via_ocr(pdf_path)
    elif backend == "pypdf":
        logger.info("Trích xuất text layer bằng pypdf cho PDF: %s", pdf_path)
        records = extract_lines_via_pypdf(pdf_path)
    else:
        logger.info("Trích xuất text layer bằng PyMuPDF cho PDF: %s", pdf_path)
        try:
            records = extract_lines_with_font(pdf_path)
        except Exception:
            logger.exception("Lỗi khi trích xuất PDF bằng PyMuPDF %s", pdf_path)
            raise

    lines = [r.text for r in records]
    articles = parse_lines(lines, lenient_article=use_ocr)
    if not articles:
        logger.warning("Không tìm thấy Điều nào trong %s — kiểm tra PDF có text layer/OCR đúng không.", pdf_path)
    return ParsedDocument(document=document, articles=articles)
