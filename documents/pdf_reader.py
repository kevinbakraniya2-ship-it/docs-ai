from io import BytesIO

import pytesseract
from pdf2image import convert_from_bytes
from pypdf import PdfReader
from django.conf import settings


MAX_PDF_PAGES = 100
MAX_TEXT_PER_PAGE = 5000
OCR_DPI = 200
OCR_TIMEOUT_SECONDS = 45

class PDFProcessingError(Exception):
    """A PDF could not be safely read for text preview."""


def extract_pdf_pages(document):
    try:
        with document.file.open("rb") as pdf_file:
            pdf_bytes = pdf_file.read()

        reader = PdfReader(BytesIO(pdf_bytes))

        if reader.is_encrypted:
            raise PDFProcessingError(
                "Password-protected PDFs are not supported yet."
            )

        if len(reader.pages) > MAX_PDF_PAGES:
            raise PDFProcessingError(
                f"This preview supports up to {MAX_PDF_PAGES} pages."
            )

        if not reader.pages:
            raise PDFProcessingError("This PDF does not contain any pages.")

        pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD
        pages = []

        for page_number, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()

            # Scanned/image-only pages have no selectable text.
            if not text:
                try:
                    images = convert_from_bytes(
                        pdf_bytes,
                        first_page=page_number,
                        last_page=page_number,
                        dpi=OCR_DPI,
                        fmt="png",
                        thread_count=1,
                        poppler_path=settings.POPPLER_PATH,
                        timeout=60,
                    )
                    if images:
                        text = pytesseract.image_to_string(
                            images[0],
                            lang="eng",
                            timeout=OCR_TIMEOUT_SECONDS,
                        ).strip()
                except Exception as error:
                    raise PDFProcessingError(
                        "Scanned page OCR failed. Check the Tesseract and "
                        "Poppler paths in documents/pdf_reader.py."
                    ) from error

            pages.append(
                {
                    "page_number": page_number,
                    "text": text[:MAX_TEXT_PER_PAGE],
                }
            )

        return pages

    except PDFProcessingError:
        raise
    except Exception as error:
        raise PDFProcessingError(
            "We couldn't read this PDF. Try another valid PDF."
        ) from error