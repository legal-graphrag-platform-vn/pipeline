"""CLI entrypoint cho Graph Construction Pipeline (Milestone 1+2).

    python main.py crawl --url <vbpl_url> --doc-id LDN2020 --number 59/2020/QH14
    python main.py parse --doc-id LDN2020
    python main.py extract --doc-id LDN2020
    python main.py ingest --url <vbpl_url> --doc-id LDN2020 --number 59/2020/QH14

`extract` cần GEMINI_API_KEY trong .env (xem .env.example và README).
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Annotated

import typer

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from src.config import settings
from src.crawler.vbpl_crawler import crawl_and_save
from src.parser.hierarchy_parser import parse_pdf, parse_text
from src.parser.models import DocumentInfo, ParsedDocument
from src.pipeline.orchestrator import run_pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = typer.Typer(help="Legal GraphRAG — Graph Construction Pipeline (Milestone 1+2)")


def _raw_dir(doc_id: str) -> Path:
    return settings.data_raw_dir / doc_id


def _processed_dir(doc_id: str) -> Path:
    return settings.data_processed_dir / doc_id


@app.command()
def crawl(
    url: Annotated[str, typer.Option(help="URL trang chi tiết vbpl.vn")],
    doc_id: Annotated[str, typer.Option(help="Document ID, vd 'LDN2020'")],
    number: Annotated[str, typer.Option(help="Số hiệu văn bản, vd '59/2020/QH14'")],
) -> None:
    """Crawl văn bản từ vbpl.vn -> data/raw/<doc_id>/{source.txt,metadata.json}."""
    metadata = crawl_and_save(url, doc_id=doc_id, number=number, raw_dir=settings.data_raw_dir)
    typer.echo(f"Đã crawl {doc_id}: {metadata.title} ({metadata.status})")


@app.command()
def parse(
    doc_id: Annotated[str, typer.Option(help="Document ID, vd 'LDN2020'")],
    pdf: Annotated[
        Path | None,
        typer.Option(help="Parse trực tiếp từ file PDF (vd PDF gốc tải tay) thay vì source.txt crawl được."),
    ] = None,
    number: Annotated[
        str | None, typer.Option(help="Số hiệu văn bản (chỉ cần khi dùng --pdf và chưa có metadata.json)")
    ] = None,
    title: Annotated[
        str | None, typer.Option(help="Tiêu đề văn bản (chỉ cần khi dùng --pdf và chưa có metadata.json)")
    ] = None,
    backend: Annotated[
        str,
        typer.Option(help="Backend trích PDF: 'auto' (PyMuPDF, tự OCR nếu cần) hoặc 'pypdf' (text layer thật)."),
    ] = "auto",
) -> None:
    """Parse văn bản -> data/processed/<doc_id>/hierarchy.json.

    Mặc định đọc data/raw/<doc_id>/source.txt (output của `crawl`, lấy từ HTML body).
    Dùng `--pdf <path>` để parse trực tiếp từ file PDF (vd PDF gốc .signed.pdf tải tay
    từ vbpl.vn) — tự động OCR (Tesseract) nếu PDF là bản scan không có text layer.
    """
    raw_dir = _raw_dir(doc_id)
    metadata_path = raw_dir / "metadata.json"

    if pdf is not None:
        if metadata_path.exists():
            meta = json.loads(metadata_path.read_text(encoding="utf-8"))
            doc_info = DocumentInfo(
                id=meta["doc_id"],
                title=meta["title"],
                number=meta["number"],
                doc_type=meta["doc_type"],
                issued_by=meta.get("issued_by"),
                issued_date=meta.get("issued_date"),
                effective_from=meta.get("effective_from"),
                effective_to=meta.get("effective_to"),
                status=meta.get("status", "active"),
            )
        else:
            if not number:
                typer.echo(
                    f"Không có {metadata_path} — cần truyền --number (và tuỳ chọn --title) khi dùng --pdf.",
                    err=True,
                )
                raise typer.Exit(code=1)
            doc_info = DocumentInfo(
                id=doc_id,
                title=title or doc_id,
                number=number,
                doc_type="Law",
                status="active",
            )
        parsed = parse_pdf(str(pdf), doc_info, backend=backend)
    else:
        source_path = raw_dir / "source.txt"
        if not source_path.exists() or not metadata_path.exists():
            typer.echo(f"Thiếu {source_path} hoặc {metadata_path} — chạy `crawl` trước (hoặc dùng --pdf).", err=True)
            raise typer.Exit(code=1)

        text = source_path.read_text(encoding="utf-8")
        meta = json.loads(metadata_path.read_text(encoding="utf-8"))
        doc_info = DocumentInfo(
            id=meta["doc_id"],
            title=meta["title"],
            number=meta["number"],
            doc_type=meta["doc_type"],
            issued_by=meta.get("issued_by"),
            issued_date=meta.get("issued_date"),
            effective_from=meta.get("effective_from"),
            effective_to=meta.get("effective_to"),
            status=meta.get("status", "active"),
        )
        parsed = parse_text(text, doc_info)

    out_dir = _processed_dir(doc_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "hierarchy.json").write_text(
        parsed.model_dump_json(indent=2, exclude_none=True), encoding="utf-8"
    )
    typer.echo(f"Parsed {doc_id}: {len(parsed.articles)} Điều -> {out_dir / 'hierarchy.json'}")


@app.command()
def extract(doc_id: Annotated[str, typer.Option(help="Document ID, vd 'LDN2020'")]) -> None:
    """Chạy LLM Extraction + Validation + Scoring trên hierarchy.json đã parse."""
    try:
        settings.require_gemini_api_key()
    except RuntimeError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e

    hierarchy_path = _processed_dir(doc_id) / "hierarchy.json"
    if not hierarchy_path.exists():
        typer.echo(f"Thiếu {hierarchy_path} — chạy `parse` trước.", err=True)
        raise typer.Exit(code=1)

    parsed = ParsedDocument.model_validate_json(hierarchy_path.read_text(encoding="utf-8"))
    run_pipeline(parsed, settings.data_processed_dir)
    typer.echo(
        f"Extraction xong cho {doc_id}: xem data/processed/{doc_id}/"
        "{accepted,review_queue,rejected}.jsonl"
    )


@app.command()
def ingest(
    url: Annotated[str, typer.Option(help="URL trang chi tiết vbpl.vn")],
    doc_id: Annotated[str, typer.Option(help="Document ID, vd 'LDN2020'")],
    number: Annotated[str, typer.Option(help="Số hiệu văn bản, vd '59/2020/QH14'")],
) -> None:
    """Full pipeline: crawl -> parse -> extract."""
    crawl(url, doc_id, number)
    parse(doc_id)
    extract(doc_id)


if __name__ == "__main__":
    app()
