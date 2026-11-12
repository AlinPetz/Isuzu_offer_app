from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

from fastapi import UploadFile


class DocumentExtractionError(Exception):
    user_message = "Documentul nu a putut fi procesat."


class UnsupportedDocumentError(DocumentExtractionError):
    def __init__(self, message: str):
        self.user_message = message


class EmptyDocumentError(DocumentExtractionError):
    user_message = "Documentul nu contine text extractabil."


class ScannedDocumentError(DocumentExtractionError):
    user_message = "Documentul pare sa fie scanat. Extragerea OCR nu este implementata momentan."


class DocumentTooLargeError(DocumentExtractionError):
    user_message = "Documentul depaseste limita de 20 MB."


class DocumentExtractionService:
    SUPPORTED_EXTENSIONS = {".pdf", ".docx"}
    LEGACY_DOC_MESSAGE = (
        "Formatul DOC vechi nu este suportat momentan. "
        "Va rugam sa convertiti documentul in PDF sau DOCX."
    )

    def __init__(self, upload_dir: Path, max_size_bytes: int):
        self.upload_dir = upload_dir
        self.max_size_bytes = max_size_bytes

    async def save_upload(self, upload: UploadFile) -> Path:
        extension = Path(upload.filename or "").suffix.lower()
        self._validate_extension(extension)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        destination = self._next_upload_path(extension)

        total = 0
        with destination.open("wb") as output:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > self.max_size_bytes:
                    output.close()
                    destination.unlink(missing_ok=True)
                    raise DocumentTooLargeError()
                output.write(chunk)
        return destination

    def extract_text(self, document_path: Path) -> str:
        extension = document_path.suffix.lower()
        self._validate_extension(extension)
        if extension == ".pdf":
            return self._extract_pdf_text(document_path)
        if extension == ".docx":
            return self._extract_docx_text(document_path)
        raise UnsupportedDocumentError(self.LEGACY_DOC_MESSAGE)

    def _validate_extension(self, extension: str) -> None:
        if extension == ".doc":
            raise UnsupportedDocumentError(self.LEGACY_DOC_MESSAGE)
        if extension not in self.SUPPORTED_EXTENSIONS:
            raise UnsupportedDocumentError("Format nesuportat. Incarcati un fisier PDF sau DOCX.")

    def _next_upload_path(self, extension: str) -> Path:
        stamp = datetime.now().strftime("%Y%m%d")
        index = 1
        while True:
            candidate = self.upload_dir / f"BODY_IMPORT_{stamp}_{index:03d}{extension}"
            if not candidate.exists():
                return candidate
            index += 1

    def _extract_pdf_text(self, document_path: Path) -> str:
        try:
            from pypdf import PdfReader
        except ImportError as error:
            raise EmptyDocumentError("Libraria pypdf nu este instalata.") from error

        try:
            reader = PdfReader(str(document_path))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as error:
            raise EmptyDocumentError("PDF-ul este corupt sau nu poate fi citit.") from error
        return self._clean_extracted_text(text, scanned_message=True)

    def _extract_docx_text(self, document_path: Path) -> str:
        try:
            from docx import Document
        except ImportError as error:
            raise EmptyDocumentError("Libraria python-docx nu este instalata.") from error

        try:
            document = Document(str(document_path))
            parts = [paragraph.text for paragraph in document.paragraphs]
            for table in document.tables:
                for row in table.rows:
                    parts.append(" | ".join(cell.text for cell in row.cells))
        except Exception as error:
            raise EmptyDocumentError("Documentul DOCX este corupt sau nu poate fi citit.") from error
        return self._clean_extracted_text("\n".join(parts), scanned_message=False)

    def _clean_extracted_text(self, text: str, scanned_message: bool) -> str:
        cleaned = re.sub(r"[ \t]+", " ", text or "").strip()
        meaningful = re.sub(r"\s+", "", cleaned)
        if len(meaningful) < 30:
            if scanned_message:
                raise ScannedDocumentError()
            raise EmptyDocumentError()
        return cleaned


def relative_upload_path(path: Path, base_dir: Path) -> str:
    try:
        return str(path.resolve().relative_to(base_dir.resolve())).replace("\\", "/")
    except ValueError:
        return path.name


def copy_local_file_for_test(source: Path, upload_dir: Path) -> Path:
    upload_dir.mkdir(parents=True, exist_ok=True)
    destination = upload_dir / source.name
    shutil.copy2(source, destination)
    return destination
