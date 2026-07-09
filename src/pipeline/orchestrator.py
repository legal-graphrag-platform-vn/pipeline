"""Pipeline Orchestrator — nối Parser -> LLM Extraction -> Schema/Ontology Validation
-> Confidence Scoring -> Decision Gate.

Phạm vi M1+M2: dừng ở ghi accepted/review/rejected JSONL — KHÔNG ghi Neo4j, KHÔNG
tạo embedding (Milestone 3, ngoài phạm vi task hiện tại).

LƯU Ý GIỚI HẠN: `GUIDES` cần `head_doc_type`/`tail_doc_type` của ĐÚNG
văn bản được tham chiếu (vd Decree mà Article này dẫn tới), nhưng ở M1+M2 chưa có
document registry (đó là việc của Neo4j/M3) nên orchestrator chỉ suy ra doc_type khi
entity type là chính document đang xử lý; còn lại doc_type=None -> validator reject
-> relation rơi vào review queue thay vì bị auto-accept sai. Đây là hành vi an
toàn có chủ đích, không phải bug.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from src.config import settings
from src.extraction.llm_extractor import extract_article
from src.extraction.models import ExtractedEntity
from src.parser.models import Article, DocumentInfo, ParsedDocument
from src.pipeline.review_queue import AcceptedLog, RejectionLog, ReviewQueue
from src.scoring.confidence_scorer import score
from src.validation.ontology_validator import validate_relation as validate_ontology
from src.validation.schema_validator import validate_relation as validate_schema

logger = logging.getLogger(__name__)


def _entity_type_lookup(entities: list[ExtractedEntity]) -> dict[str, str]:
    return {e.id: e.type for e in entities}


def _ontology_label(extraction_label: str) -> str:
    return {
        "Entity": "LegalSubject",
        "Concept": "LegalConcept",
        "Action": "LegalAction",
    }.get(extraction_label, extraction_label)


def _configured_llm_model() -> str:
    provider = settings.llm_provider.lower()
    model_by_provider = {
        "gemini": settings.gemini_model,
        "minimax": settings.minimax_model,
        "qwen": settings.qwen_model,
        "openai": settings.openai_model,
        "ollama": settings.ollama_model,
    }
    model = model_by_provider.get(provider, "")
    return f"{provider}:{model}" if model else provider


def _relation_properties(raw_relation, article: Article, document: DocumentInfo) -> dict:
    relation_properties = {}
    created_at = datetime.now(timezone.utc).isoformat()

    if raw_relation.relation in {"AMENDS", "REPEALS", "REPLACES"} and document.effective_from:
        relation_properties["effective_from"] = str(document.effective_from)
    if raw_relation.relation == "AMENDS":
        relation_properties["source_doc_id"] = document.id
    if raw_relation.relation == "REFERS_TO":
        relation_properties["citation_text"] = raw_relation.evidence
        relation_properties["citation_type"] = "DIRECT"
    if raw_relation.relation in {"DEFINES", "REGULATES", "REQUIRES"}:
        relation_properties["confidence"] = raw_relation.confidence
        relation_properties["llm_model"] = _configured_llm_model()
        relation_properties["created_at"] = created_at
    if raw_relation.relation == "REQUIRES":
        relation_properties["source_article"] = f"{document.id}_art{article.number}"

    return relation_properties


def process_article(
    article: Article,
    document: DocumentInfo,
    all_records: list[dict],
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

        head_type = _ontology_label(entity_types.get(raw_relation.head, "Entity"))
        tail_type = _ontology_label(entity_types.get(raw_relation.tail, "Entity"))
        head_doc_type = document.doc_type if head_type == "Document" else None
        tail_doc_type = document.doc_type if tail_type == "Document" else None

        # 1.   Construct actual relationship properties from document metadata and context
        relation_properties = _relation_properties(raw_relation, article, document)

        # 2.   Enrich the relation dictionary with actual properties
        relation_dict["properties"] = relation_properties

        ontology_ok, ontology_err = validate_ontology(
            head_type,
            raw_relation.relation,
            tail_type,
            head_id=raw_relation.head,
            tail_id=raw_relation.tail,
            properties=relation_properties,
            head_doc_type=head_doc_type,
            tail_doc_type=tail_doc_type,
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
        all_records.append(record)

    return len(result.relations)


def _process_article_worker(article: Article, document: DocumentInfo) -> list[dict]:
    records = []
    process_article(article, document, records)
    return records


def run_pipeline(parsed: ParsedDocument, processed_dir: Path) -> None:
    out_dir = processed_dir / parsed.document.id
    out_dir.mkdir(parents=True, exist_ok=True)
    
    import json
    from concurrent.futures import ThreadPoolExecutor, as_completed

    all_records = []
    max_workers = settings.extraction_max_workers
    logger.info("Bắt đầu trích xuất tri thức song song với %d workers...", max_workers)

    results_by_article = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_article = {
            executor.submit(_process_article_worker, article, parsed.document): article
            for article in parsed.articles
        }

        total = len(parsed.articles)
        completed = 0
        for future in as_completed(future_to_article):
            article = future_to_article[future]
            completed += 1
            try:
                records = future.result()
                results_by_article[article.number] = records
                logger.info("Đã trích xuất xong Điều %d / %d", article.number, total)
            except Exception as e:
                logger.error("Lỗi khi trích xuất Điều %d: %s", article.number, e)

    # Đảm bảo giữ đúng thứ tự các Điều trong văn bản gốc
    for article in parsed.articles:
        if article.number in results_by_article:
            all_records.extend(results_by_article[article.number])

    # 1. Ghi tất cả ra file extract.jsonl (mỗi dòng 1 bản ghi JSON)
    extract_jsonl_path = out_dir / "extract.jsonl"
    with extract_jsonl_path.open("w", encoding="utf-8") as f:
        for record in all_records:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    # 2. Ghi ra file prettier_extract.json (định dạng đẹp, dễ đọc)
    prettier_json_path = out_dir / "prettier_extract.json"
    with prettier_json_path.open("w", encoding="utf-8") as f:
        json.dump(all_records, f, ensure_ascii=False, indent=2, default=str)
