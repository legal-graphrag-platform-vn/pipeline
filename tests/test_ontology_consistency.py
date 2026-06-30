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


def test_references_not_rejected() -> None:
    """REFERENCES là relation phổ biến nhất — phải pass validator."""
    ok, err = validate_relation("Article", "REFERENCES", "Article")
    assert ok, f"REFERENCES bị reject: {err}"


def test_requires_not_rejected() -> None:
    ok, err = validate_relation("Entity", "REQUIRES", "Concept")
    assert ok, f"REQUIRES bị reject: {err}"


def test_replaced_by_same_type_enforced() -> None:
    """REPLACED_BY chỉ hợp lệ khi head/tail cùng cấp (Document-Document, Article-Article)."""
    ok, err = validate_relation(
        "Article", "REPLACED_BY", "Document", properties={"effective_from": "2021-01-01"}
    )
    assert not ok
    ok, err = validate_relation(
        "Article", "REPLACED_BY", "Article", properties={"effective_from": "2021-01-01"}
    )
    assert ok, f"REPLACED_BY Article-Article bị reject sai: {err}"


def test_repealed_by_tail_always_document() -> None:
    """REPEALED_BY: tail luôn phải là Document, bất kể head type nào."""
    ok, err = validate_relation(
        "Document", "REPEALED_BY", "Article", properties={"effective_from": "2021-01-01"}
    )
    assert not ok
    ok, err = validate_relation(
        "Document", "REPEALED_BY", "Document", properties={"effective_from": "2021-01-01"}
    )
    assert ok, f"REPEALED_BY Document-Document bị reject sai: {err}"


def test_amended_by_document_to_document_rejected() -> None:
    """AMENDED_BY ở cấp Document đã bị bỏ — phải dùng REPLACED_BY/REPEALED_BY thay thế."""
    ok, err = validate_relation(
        "Document", "AMENDED_BY", "Document", properties={"effective_from": "2021-01-01"}
    )
    assert not ok


def test_amended_by_missing_effective_from_rejected() -> None:
    """AMENDED_BY bắt buộc required_properties=[effective_from]."""
    ok, err = validate_relation("Article", "AMENDED_BY", "Clause", properties={})
    assert not ok
    assert "effective_from" in (err or "")


def test_implemented_by_level_rule() -> None:
    """IMPLEMENTED_BY: head_doc_level phải lớn hơn tail_doc_level (Law > Decree > Circular)."""
    ok, err = validate_relation(
        "Document", "IMPLEMENTED_BY", "Document", head_doc_level=3, tail_doc_level=2
    )
    assert ok, f"Law->Decree bị reject sai: {err}"
    ok, err = validate_relation(
        "Document", "IMPLEMENTED_BY", "Document", head_doc_level=1, tail_doc_level=3
    )
    assert not ok, "Circular->Law không hợp lệ nhưng validator lại pass"


def test_unknown_relation_rejected() -> None:
    ok, err = validate_relation("Article", "GUIDED_BY", "Document")
    assert not ok
    assert "RELATION_ENUM" in (err or "")


def test_contains_no_self_loop() -> None:
    ok, err = validate_relation(
        "Document", "CONTAINS", "Article", head_id="dieu_1", tail_id="dieu_1"
    )
    assert not ok
