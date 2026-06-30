"""LLM Information Extraction — 2-pass (Entity rồi Relation) qua Gemini.

Dùng `google-genai` (SDK hợp nhất hiện tại, không phải `google-generativeai` cũ
đã deprecated) vì hỗ trợ `response_schema` nhận thẳng Pydantic model -> Gemini bị
ép trả đúng JSON shape ở API level, giảm hẳn lỗi "JSON parse fail" (đo trong
REPORT.md mục A). Retry qua `tenacity` cho `google.genai.errors.APIError`
(timeout, rate limit, lỗi server tạm thời) — task yêu cầu rõ retry logic cho LLM
API calls.
"""

from __future__ import annotations

import logging

from google import genai
from google.genai import types
from google.genai.errors import APIError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.config import settings
from src.extraction.models import (
    EntityExtractionResult,
    ExtractedEntity,
    ExtractedRelation,
    ExtractionResult,
    RelationExtractionResult,
)
from src.extraction.prompts import ENTITY_EXTRACTION_PROMPT, RELATION_EXTRACTION_PROMPT

logger = logging.getLogger(__name__)

_retry_llm_call = retry(
    retry=retry_if_exception_type(APIError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=20),
    reraise=True,
)


def _client() -> genai.Client:
    return genai.Client(api_key=settings.require_gemini_api_key())


@_retry_llm_call
def extract_entities(article_text: str) -> list[ExtractedEntity]:
    """Pass 1 — trích entities (Document/Concept/Entity) được nhắc tới trong 1 Điều."""
    client = _client()
    prompt = ENTITY_EXTRACTION_PROMPT.format(article_text=article_text)
    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=EntityExtractionResult,
        ),
    )
    result = EntityExtractionResult.model_validate_json(response.text)
    return result.entities


@_retry_llm_call
def extract_relations(article_text: str, entities: list[ExtractedEntity]) -> list[ExtractedRelation]:
    """Pass 2 — trích relations giữa các entities đã tìm thấy ở Pass 1."""
    if not entities:
        return []
    client = _client()
    entities_json = EntityExtractionResult(entities=entities).model_dump_json()
    prompt = RELATION_EXTRACTION_PROMPT.format(article_text=article_text, entities_json=entities_json)
    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=RelationExtractionResult,
        ),
    )
    result = RelationExtractionResult.model_validate_json(response.text)
    return result.relations


def extract_article(article_number: int, article_text: str) -> ExtractionResult:
    """Chạy đủ 2 pass cho 1 Article, gói kết quả lại làm input cho Step 3 Schema Validation."""
    logger.info("Extracting entities for Điều %d", article_number)
    entities = extract_entities(article_text)
    logger.info("Điều %d: tìm thấy %d entities, đang extract relations", article_number, len(entities))
    relations = extract_relations(article_text, entities)
    logger.info("Điều %d: tìm thấy %d relations", article_number, len(relations))
    return ExtractionResult(article_number=article_number, entities=entities, relations=relations)
