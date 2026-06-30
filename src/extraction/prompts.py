"""Prompt templates cho 2-pass LLM extraction.

Nguồn: plans/04_graph_construction_pipeline.md mục "Step 2: LLM Information
Extraction". Giữ nguyên nội dung tiếng Việt + relation type list đúng spec gốc,
chỉ bổ sung hướng dẫn format JSON chặt hơn (Gemini structured output qua
`response_schema` đã ép schema, nhưng prompt rõ ràng vẫn giúp giảm nhiễu).
"""

from __future__ import annotations

ENTITY_EXTRACTION_PROMPT = """Cho điều luật sau:
---
{article_text}
---

Trích xuất tất cả entities được đề cập:

1. Documents được viện dẫn (số hiệu văn bản)
2. Concepts pháp lý (khái niệm, thuật ngữ chuyên ngành)
3. Entities (loại hình doanh nghiệp, cơ quan, chủ thể)

Mỗi entity có id duy nhất dạng snake_case, type thuộc \
{{Document, Article, Clause, Point, Concept, Entity}}, label là tên hiển thị.
Chỉ trích xuất entity thực sự được nhắc tới trong văn bản, không suy diễn thêm."""

RELATION_EXTRACTION_PROMPT = """Cho điều luật sau và danh sách entities đã xác định:
---
Article: {article_text}
Entities: {entities_json}
---

Xác định các quan hệ giữa entities.
Chỉ sử dụng các relation types sau:
- AMENDED_BY: A bị sửa đổi bởi B
- REPLACED_BY: A bị thay thế bởi B
- REFERENCES: A viện dẫn B
- DEFINES: Article/Clause định nghĩa Concept
- REGULATES: Article/Clause điều chỉnh Entity
- REQUIRES: Entity yêu cầu/phải có Concept
- IMPLEMENTED_BY: Law được hướng dẫn bởi Decree/Circular

Với mỗi relation, bắt buộc có "evidence" là câu văn nguyên gốc làm cơ sở, và
"confidence" thể hiện mức tự tin của bạn vào quan hệ đó (0.0-1.0).
Chỉ trả về quan hệ có evidence rõ ràng trong văn bản, không suy diễn."""
