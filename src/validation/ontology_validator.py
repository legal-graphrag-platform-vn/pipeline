"""Ontology Validator — Step 4 của pipeline.

CONSTRAINTS copy nguyên từ plans/04_graph_construction_pipeline.md mục
"Step 4: Ontology Validation". Đồng bộ bắt buộc với `tests/test_ontology_consistency.py`
(invariant RELATION_ENUM == set(CONSTRAINTS.keys())).

LƯU Ý: spec gốc có 2 chỗ liệt kê RELATION_ENUM khác nhau — bản ở Step 4 (9 relations,
GUIDED_BY đã hợp nhất vào IMPLEMENTED_BY) và bản RELATION_ENUM_EXPECTED ở cuối file
spec (10 relations, còn GUIDED_BY riêng, rõ ràng chưa cập nhật theo ghi chú "ADR
session 2026-06-29"). Module này dùng bản 9-relation vì đó là bản có CONSTRAINTS đầy
đủ và có ghi chú ADR rõ ràng hơn — xem REPORT.md mục B.
"""

from __future__ import annotations

DOCUMENT_LEVELS: dict[str, int] = {
    "Law": 3,
    "Resolution": 3,
    "Decree": 2,
    "Decision": 2,
    "Circular": 1,
}

RELATION_ENUM: set[str] = {
    "CONTAINS",
    "AMENDED_BY",
    "REPLACED_BY",
    "REPEALED_BY",
    "IMPLEMENTED_BY",
    "REFERENCES",
    "DEFINES",
    "REGULATES",
    "REQUIRES",
}

CONSTRAINTS: dict[str, dict] = {
    "CONTAINS": {
        "valid_pairs": [
            ("Document", "Article"),
            ("Article", "Clause"),
            ("Clause", "Point"),
        ],
        "no_self_loop": True,
    },
    "AMENDED_BY": {
        # Document->Document đã bỏ: cấp Document dùng REPLACED_BY hoặc REPEALED_BY.
        "valid_pairs": [
            ("Article", "Article"),
            ("Article", "Clause"),
            ("Clause", "Clause"),
            ("Clause", "Article"),
        ],
        "no_self_loop": True,
        "required_properties": ["effective_from"],
    },
    "REPLACED_BY": {
        "head_tail_same_type": True,
        "valid_pairs": [
            ("Document", "Document"),
            ("Article", "Article"),
        ],
        "no_self_loop": True,
        "required_properties": ["effective_from"],
    },
    "REPEALED_BY": {
        "allowed_tail": ["Document"],
        "head_tail_same_type": False,
        "required_properties": ["effective_from"],
    },
    "IMPLEMENTED_BY": {
        # Level-based rule: head.level > tail.level (xem DOCUMENT_LEVELS).
        "rule": "head_doc_level > tail_doc_level",
    },
    "REFERENCES": {
        "valid_pairs": [
            ("Article", "Article"),
            ("Article", "Clause"),
            ("Article", "Document"),
            ("Clause", "Article"),
            ("Clause", "Clause"),
            ("Clause", "Document"),
        ],
    },
    "DEFINES": {
        "valid_pairs": [
            ("Article", "Concept"),
            ("Clause", "Concept"),
        ],
    },
    "REGULATES": {
        "valid_pairs": [
            ("Article", "Entity"),
            ("Article", "Concept"),
            ("Clause", "Entity"),
            ("Clause", "Concept"),
        ],
    },
    "REQUIRES": {
        "valid_pairs": [
            ("Entity", "Concept"),
            ("Entity", "Entity"),
        ],
    },
}


def validate_relation(
    head_type: str,
    relation: str,
    tail_type: str,
    *,
    head_id: str | None = None,
    tail_id: str | None = None,
    properties: dict | None = None,
    head_doc_level: int | None = None,
    tail_doc_level: int | None = None,
) -> tuple[bool, str | None]:
    constraint = CONSTRAINTS.get(relation)
    if not constraint:
        return False, (
            f"Unknown relation type: {relation}. "
            "Check RELATION_ENUM == set(CONSTRAINTS.keys())"
        )

    if relation == "IMPLEMENTED_BY":
        if head_doc_level is None or tail_doc_level is None:
            return False, "IMPLEMENTED_BY yêu cầu head_doc_level và tail_doc_level"
        if not head_doc_level > tail_doc_level:
            return False, (
                f"IMPLEMENTED_BY vi phạm rule head_doc_level > tail_doc_level "
                f"({head_doc_level} <= {tail_doc_level})"
            )
        return True, None

    valid_pairs = constraint.get("valid_pairs")
    if valid_pairs and (head_type, tail_type) not in valid_pairs:
        return False, f"Invalid pair: {head_type}-[{relation}]->{tail_type}"

    allowed_tail = constraint.get("allowed_tail")
    if allowed_tail and tail_type not in allowed_tail:
        return False, f"Invalid tail type for {relation}: {tail_type} not in {allowed_tail}"

    if constraint.get("no_self_loop") and head_id is not None and tail_id is not None:
        if head_id == tail_id:
            return False, f"Self-loop not allowed for {relation}"

    required_props = constraint.get("required_properties", [])
    if required_props:
        props = properties or {}
        missing = [p for p in required_props if not props.get(p)]
        if missing:
            return False, f"Missing required properties for {relation}: {missing}"

    return True, None
