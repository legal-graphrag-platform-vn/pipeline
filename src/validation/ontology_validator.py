"""Ontology Validator — Step 4 of the extraction pipeline.

This validator accepts the pre-writer extraction labels (`Entity`, `Concept`,
`Action`) but enforces the canonical active-voice relation vocabulary from
plans/legal_ontology.md v1.4.0.
"""

from __future__ import annotations

DOCUMENT_LEVELS: dict[str, int] = {
    "Law": 3,
    "Resolution": 3,
    "Decree": 2,
    "Decision": 2,
    "Circular": 1,
}

GUIDES_WHITELIST: set[tuple[str, str]] = {
    ("Constitution", "Law"),
    ("Constitution", "Ordinance"),
    ("Law", "Decree"),
    ("Law", "Decision"),
    ("Law", "Circular"),
    ("Ordinance", "Decree"),
    ("Resolution", "Decree"),
    ("Decree", "Circular"),
    ("Decree", "Decision"),
    ("Decree", "JointCircular"),
    ("Decision", "Circular"),
}

LEGACY_RELATION_ALIASES: dict[str, str] = {
    "AMENDED_BY": "AMENDS",
    "REPEALED_BY": "REPEALS",
    "REPLACED_BY": "REPLACES",
    "IMPLEMENTED_BY": "GUIDES",
    "GUIDED_BY": "GUIDES",
    "REFERENCES": "REFERS_TO",
}

RELATION_ENUM: set[str] = {
    "CONTAINS",
    "AMENDS",
    "REPEALS",
    "REPLACES",
    "GUIDES",
    "REFERS_TO",
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
    "AMENDS": {
        "valid_pairs": [
            ("Document", "Document"),
            ("Document", "Article"),
            ("Document", "Clause"),
            ("Article", "Document"),
            ("Article", "Article"),
            ("Article", "Clause"),
            ("Clause", "Document"),
            ("Clause", "Clause"),
            ("Clause", "Article"),
        ],
        "no_self_loop": True,
        "required_properties": ["effective_from"],
    },
    "REPEALS": {
        "valid_pairs": [
            ("Document", "Document"),
            ("Document", "Article"),
            ("Document", "Clause"),
        ],
        "no_self_loop": True,
        "required_properties": ["effective_from"],
    },
    "REPLACES": {
        "valid_pairs": [("Document", "Document")],
        "no_self_loop": True,
        "required_properties": ["effective_from"],
    },
    "GUIDES": {
        "valid_pairs": [("Document", "Document")],
        "rule": "guides_whitelist",
    },
    "REFERS_TO": {
        "valid_pairs": [
            ("Article", "Article"),
            ("Article", "Clause"),
            ("Article", "Point"),
            ("Article", "Document"),
            ("Clause", "Article"),
            ("Clause", "Clause"),
            ("Clause", "Point"),
            ("Clause", "Document"),
            ("Point", "Article"),
            ("Point", "Clause"),
            ("Point", "Point"),
            ("Point", "Document"),
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
            ("Article", "Action"),
            ("Clause", "Entity"),
            ("Clause", "Action"),
        ],
    },
    "REQUIRES": {
        "valid_pairs": [("Entity", "Concept")],
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
    head_doc_type: str | None = None,
    tail_doc_type: str | None = None,
) -> tuple[bool, str | None]:
    constraint = CONSTRAINTS.get(relation)
    if not constraint:
        canonical = LEGACY_RELATION_ALIASES.get(relation)
        if canonical:
            return False, f"Legacy relation type {relation}; use canonical {canonical}"
        return False, (
            f"Unknown relation type: {relation}. "
            "Check RELATION_ENUM == set(CONSTRAINTS.keys())"
        )

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

    if relation == "GUIDES":
        if head_doc_type is not None and tail_doc_type is not None:
            if (head_doc_type, tail_doc_type) not in GUIDES_WHITELIST:
                return False, f"GUIDES does not allow {head_doc_type} -> {tail_doc_type}"
            return True, None
        if head_doc_level is None or tail_doc_level is None:
            return False, "GUIDES requires head_doc_type and tail_doc_type"
        if not head_doc_level > tail_doc_level:
            return False, f"GUIDES violates head_doc_level > tail_doc_level ({head_doc_level} <= {tail_doc_level})"

    return True, None
