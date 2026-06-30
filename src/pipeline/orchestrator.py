"""Pipeline Orchestrator — nối Parser -> LLM Extraction -> Schema/Ontology Validation
-> Confidence Scoring -> Decision Gate.

Phạm vi M1+M2: dừng ở ghi accepted/review/rejected JSONL — KHÔNG ghi Neo4j, KHÔNG
tạo embedding (Milestone 3, ngoài phạm vi task hiện tại).

LƯU Ý GIỚI HẠN: `IMPLEMENTED_BY` cần `head_doc_level`/`tail_doc_level` của ĐÚNG
văn bản được tham chiếu (vd Decree mà Article này dẫn tới), nhưng ở M1+M2 chưa có
document registry (đó là việc của Neo4j/M3) nên orchestrator chỉ suy ra level khi
entity type là chính document đang xử lý; còn lại level=None -> validator reject
-> relation rơi vào review queue thay vì bị auto-accept sai. Đây là hành vi an
toàn có chủ đích, không phải bug.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.config import settings
from src.extraction.llm_extractor import extract_article
from src.extraction.models import ExtractedEntity
from src.parser.models import Article, DocumentInfo, ParsedDocument
from src.pipeline.review_queue import AcceptedLog, RejectionLog, ReviewQueue
from src.scoring.confidence_scorer import score
from src.validation.ontology_validator import DOCUMENT_LEVELS
from src.validation.ontology_validator import validate_relation as validate_ontology
from src.validation.schema_validator import validate_relation as validate_schema

logger = logging.getLogger(__name__)


def _entity_type_lookup(entities: list[ExtractedEntity]) -> dict[str, str]:
    return {e.id: e.type for e in entities}


def process_article(
    article: Article,
    document: DocumentInfo,
    accepted: AcceptedLog,
    review: ReviewQueue,
    rejected: RejectionLog,
) -> int:
    """Chạy Pass 1+2 extraction + validation + scoring cho 1 Article. Trả về số relations xử lý."""
    article_text = article.content_raw
    result = extract_article(article.number, article_text)

    entity_types = _entity_type_lookup(result.entities)
    self_id = f"dieu_{article.number}"
    entity_types[self_id] = "Article"
    known_ids = set(entity_types.keys())

    for raw_relation in result.relations:
        relation_dict = raw_relation.model_dump()
        parsed_relation, schema_err = validate_schema(relation_dict)
        schema_valid = parsed_relation is not None

        head_type = entity_types.get(raw_relation.head, "Entity")
        tail_type = entity_types.get(raw_relation.tail, "Entity")
        head_level = DOCUMENT_LEVELS.get(document.doc_type) if head_type == "Document" else None
        tail_level = DOCUMENT_LEVELS.get(document.doc_type) if tail_type == "Document" else None

        ontology_ok, ontology_err = validate_ontology(
            head_type,
            raw_relation.relation,
            tail_type,
            head_id=raw_relation.head,
            tail_id=raw_relation.tail,
            properties={},
            head_doc_level=head_level,
            tail_doc_level=tail_level,
        )

        breakdown = score(
            schema_valid=schema_valid,
            ontology_valid=ontology_ok,
            evidence=raw_relation.evidence,
            article_text=article_text,
            head_id=raw_relation.head,
            tail_id=raw_relation.tail,
            known_entity_ids=known_ids,
        )

        record = {
            "document_id": document.id,
            "article_number": article.number,
            "relation": relation_dict,
            "schema_valid": schema_valid,
            "schema_error": schema_err,
            "ontology_valid": ontology_ok,
            "ontology_error": ontology_err,
            "confidence": breakdown.total,
        }

        if breakdown.total >= settings.confidence_threshold_auto:
            accepted.append(record)
        elif breakdown.total >= settings.confidence_threshold_review:
            review.append(record)
        else:
            rejected.append(record)

    return len(result.relations)


def run_pipeline(parsed: ParsedDocument, processed_dir: Path) -> None:
    out_dir = processed_dir / parsed.document.id
    accepted = AcceptedLog(out_dir / "accepted.jsonl")
    review = ReviewQueue(out_dir / "review_queue.jsonl")
    rejected = RejectionLog(out_dir / "rejected.jsonl")

    for article in parsed.articles:
        logger.info("Processing Điều %d / %d", article.number, len(parsed.articles))
        process_article(article, parsed.document, accepted, review, rejected)
