import re
from dataclasses import dataclass
from typing import Iterable

@dataclass(frozen=True)
class ParsedChunk:
    content: str
    page_number: int
    chunk_type: str = "Text"


def chunk_text(text: str, max_chars: int = 1_200) -> Iterable[str]:
    """Split extracted text on paragraph boundaries without dropping content."""
    normalized = re.sub(r"[ \t]+", " ", text)
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", normalized) if part.strip()]
    current: list[str] = []
    current_size = 0

    for paragraph in paragraphs:
        pieces = [paragraph[i:i + max_chars] for i in range(0, len(paragraph), max_chars)]
        for piece in pieces:
            separator_size = 2 if current else 0
            if current and current_size + separator_size + len(piece) > max_chars:
                yield "\n\n".join(current)
                current = []
                current_size = 0
            current.append(piece)
            current_size += separator_size + len(piece)

    if current:
        yield "\n\n".join(current)


def parse_pdf(path: str) -> list[ParsedChunk]:
    """Extract text from a text-based PDF and retain one-based page numbers."""
    from pypdf import PdfReader

    reader = PdfReader(path)
    chunks = [
        ParsedChunk(content=content, page_number=page_number)
        for page_number, page in enumerate(reader.pages, start=1)
        for content in chunk_text(page.extract_text() or "")
    ]
    if not chunks:
        raise ValueError(
            "The PDF contains no extractable text. OCR/scanned PDFs are not supported by this lightweight worker."
        )
    return chunks
