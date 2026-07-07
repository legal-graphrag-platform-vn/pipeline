"""Bắt buộc theo tasks/task-1.graph-construction-pipeline.md — invariant ontology.

Chạy: pytest tests/test_ontology_consistency.py
Tốc độ: <1ms, không cần DB hay LLM.
"""

from src.validation.ontology_validator import CONSTRAINTS, RELATION_ENUM, validate_relation


def test_all_relations_have_constraints() -> None:
    """Mọi relation trong enum phải có đúng 1 key trong CONSTRAINTS."""
    missing = RELATION_ENUM - set(CONSTRAINTS.keys())
    assert missing == set(), f"Relations thiếu constraint: {missing}"


def test_no_orphan_constraints() -> None:
    """Không có constraint nào cho relation không tồn tại trong enum."""
    orphans = set(CONSTRAINTS.keys()) - RELATION_ENUM
    assert orphans == set(), f"Constraints thừa (không có trong enum): {orphans}"


def test_refers_to_not_rejected() -> None:
    """REFERS_TO là relation phổ biến nhất — phải pass validator."""
    ok, err = validate_relation("Article", "REFERS_TO", "Article")
    assert ok, f"REFERS_TO bị reject: {err}"


def test_requires_not_rejected() -> None:
    ok, err = validate_relation("Entity", "REQUIRES", "Concept")
    assert ok, f"REQUIRES bị reject: {err}"


def test_replaces_document_only() -> None:
    """REPLACES chỉ hợp lệ ở cấp Document theo ontology canonical."""
    ok, err = validate_relation(
        "Article", "REPLACES", "Article", properties={"effective_from": "2021-01-01"}
    )
    assert not ok
    ok, err = validate_relation(
        "Document", "REPLACES", "Document", properties={"effective_from": "2021-01-01"}
    )
    assert ok, f"REPLACES Document-Document bị reject sai: {err}"


def test_repeals_document_head() -> None:
    """REPEALS đi từ Document sang Document/Article/Clause."""
    ok, err = validate_relation(
        "Article", "REPEALS", "Document", properties={"effective_from": "2021-01-01"}
    )
    assert not ok
    ok, err = validate_relation(
        "Document", "REPEALS", "Article", properties={"effective_from": "2021-01-01"}
    )
    assert ok, f"REPEALS Document-Article bị reject sai: {err}"


def test_amends_document_to_document_allowed() -> None:
    """AMENDS là active voice và cho phép cấp Document khi văn bản sửa đổi văn bản khác."""
    ok, err = validate_relation(
        "Document", "AMENDS", "Document", properties={"effective_from": "2021-01-01"}
    )
    assert ok, f"AMENDS Document-Document bị reject sai: {err}"


def test_amends_missing_effective_from_rejected() -> None:
    """AMENDS bắt buộc required_properties=[effective_from]."""
    ok, err = validate_relation("Article", "AMENDS", "Clause", properties={})
    assert not ok
    assert "effective_from" in (err or "")


def test_guides_whitelist_rule() -> None:
    """GUIDES dùng whitelist doc_type thay cho level property trong Neo4j."""
    ok, err = validate_relation(
        "Document", "GUIDES", "Document", head_doc_type="Law", tail_doc_type="Decree"
    )
    assert ok, f"Law->Decree bị reject sai: {err}"
    ok, err = validate_relation(
        "Document", "GUIDES", "Document", head_doc_type="Circular", tail_doc_type="Law"
    )
    assert not ok, "Circular->Law không hợp lệ nhưng validator lại pass"


def test_unknown_relation_rejected() -> None:
    ok, err = validate_relation("Article", "GUIDED_BY", "Document")
    assert not ok
    assert "use canonical GUIDES" in (err or "")


def test_contains_no_self_loop() -> None:
    ok, err = validate_relation(
        "Document", "CONTAINS", "Article", head_id="dieu_1", tail_id="dieu_1"
    )
    assert not ok
