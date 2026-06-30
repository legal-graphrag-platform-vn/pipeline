from datetime import date
from pathlib import Path

from src.crawler.vbpl_crawler import _extract_body_lines, _extract_metadata, _infer_doc_type

FIXTURE = Path(__file__).parent / "fixtures" / "vbpl_rendered_body.txt"


def _body_text() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_extract_metadata_fields() -> None:
    meta = _extract_metadata(
        _body_text(), doc_id="LDN2020", number="59/2020/QH14", source_url="https://vbpl.vn/x"
    )
    assert meta.doc_id == "LDN2020"
    assert meta.title == "Luật doanh nghiệp số 59/2020/QH14"
    assert meta.status == "Hết hiệu lực một phần"
    assert meta.effective_from == date(2021, 1, 1)
    assert meta.issued_date == date(2020, 7, 1)
    assert meta.issued_by == "QUỐC HỘI"
    assert meta.doc_type == "Law"


def test_extract_body_lines_strips_nav_and_tabs() -> None:
    lines = _extract_body_lines(_body_text())
    joined = "\n".join(lines)
    assert "Trang chủ" not in joined
    assert "Tải về" not in joined
    assert "Điều 1. Phạm vi điều chỉnh" in joined


def test_infer_doc_type() -> None:
    assert _infer_doc_type("59/2020/QH14") == "Law"
    assert _infer_doc_type("01/2021/NĐ-CP") == "Decree"
    assert _infer_doc_type("01/2021/TT-BKHDT") == "Circular"
