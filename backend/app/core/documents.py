import io
import zipfile
from xml.etree import ElementTree

from fastapi import HTTPException
from pypdf import PdfReader

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

_DOCX_TEXT_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"
_DOCX_PARA_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"


def extract_text_from_upload(filename: str, content: bytes) -> tuple[str, str]:
    """Extract UTF-8 text from uploaded .pdf, .docx, .txt, or .md contract documents."""
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Uploaded file exceeds 10 MB limit")

    lowered = (filename or "").strip().lower()
    if lowered.endswith(".pdf"):
        try:
            reader = PdfReader(io.BytesIO(content))
            pages = [page.extract_text() or "" for page in reader.pages]
            extracted = "\n".join(p.strip() for p in pages if p.strip()).strip()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"Invalid PDF file: {exc}") from exc
        if len(extracted) < 10:
            raise HTTPException(status_code=400, detail="Could not extract readable text from PDF")
        return extracted, "pdf"

    if lowered.endswith(".docx"):
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                if "word/document.xml" not in archive.namelist():
                    raise HTTPException(status_code=400, detail="DOCX missing word/document.xml")
                info = archive.getinfo("word/document.xml")
                if info.file_size > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413, detail="DOCX XML content exceeds 10 MB limit"
                    )
                xml_bytes = archive.read("word/document.xml")
            root = ElementTree.fromstring(xml_bytes)
            paragraphs: list[str] = []
            for para in root.iter(_DOCX_PARA_NS):
                runs = [node.text for node in para.iter(_DOCX_TEXT_NS) if node.text]
                line = "".join(runs).strip()
                if line:
                    paragraphs.append(line)
            extracted = "\n".join(paragraphs).strip()
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"Invalid DOCX file: {exc}") from exc
        if len(extracted) < 10:
            raise HTTPException(status_code=400, detail="Could not extract readable text from DOCX")
        return extracted, "docx"

    if lowered.endswith(".txt") or lowered.endswith(".md"):
        try:
            extracted = content.decode("utf-8").strip()
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status_code=400, detail="Text contract must be UTF-8 encoded"
            ) from exc
        if len(extracted) < 10:
            raise HTTPException(status_code=400, detail="Contract text is too short")
        return extracted, "txt"

    raise HTTPException(
        status_code=415,
        detail="Unsupported file format. Upload .pdf, .docx, .txt, or .md.",
    )
