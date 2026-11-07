from pypdf import PdfReader


MAX_PDF_PAGES = 100
MAX_TEXT_PER_PAGE = 5000


class PDFProcessingError(Exception):
    """A PDF could not be safely read for text preview."""


def extract_pdf_pages(document):
    try:
        with document.file.open("rb") as pdf_file:
            reader = PdfReader(pdf_file)

            if reader.is_encrypted:
                raise PDFProcessingError(
                    "Password-protected PDFs are not supported yet."
                )

            if len(reader.pages) > MAX_PDF_PAGES:
                raise PDFProcessingError(
                    f"This preview supports up to {MAX_PDF_PAGES} pages."
                )

            pages = []

            for page_number, page in enumerate(reader.pages, start=1):
                text = (page.extract_text() or "").strip()
                pages.append(
                    {
                        "page_number": page_number,
                        "text": text[:MAX_TEXT_PER_PAGE],
                    }
                )

            if not pages:
                raise PDFProcessingError("This PDF does not contain any pages.")

            return pages

    except PDFProcessingError:
        raise
    except Exception as error:
        raise PDFProcessingError(
            "We couldn't read this PDF. Try another valid PDF."
        ) from error