import re
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from .forms import DocumentUploadForm, QuestionForm
from .models import Document, DocumentPage
from .pdf_reader import PDFProcessingError, extract_pdf_pages
from .answer_service import (
    AnswerGenerationError,
    generate_answer,
    is_code_question,
)

from .vector_search import VectorSearchError, search_document_pages

_TOPIC_FILLER_WORDS = {
    "what", "when", "where", "which", "who", "why", "how",
    "is", "are", "was", "were", "a", "an", "the", "of",
    "for", "to", "in", "on", "and", "or", "from", "with",
    "explain", "describe", "tell", "me", "about", "please",
    "show", "give", "does", "do", "can", "could",
}

_GENERIC_TOPIC_WORDS = {
    "management", "system", "systems", "php", "mysql",
    "code", "file", "website", "application",
}


def _has_specific_topic_match(question, results):
    words = set(re.findall(r"\w+", question.casefold()))

    topic_words = words - _TOPIC_FILLER_WORDS - _GENERIC_TOPIC_WORDS

    # Generic sawaalon, jaise "What is SQL?", ke liye fallback.
    if not topic_words:
        topic_words = words - _TOPIC_FILLER_WORDS

    source_words = set()
    for result in results:
        text = result.get("context", "") + " " + " ".join(result.get("snippets", []))
        source_words.update(re.findall(r"\w+", text.casefold()))

    # employees/managers jaise plural shabdon ko bhi match karo.
    source_words.update(
        word[:-1] for word in tuple(source_words)
        if word.endswith("s") and len(word) > 4
    )
    topic_words.update(
        word[:-1] for word in tuple(topic_words)
        if word.endswith("s") and len(word) > 4
    )

    return bool(topic_words & source_words)


@login_required
def document_list(request):
    documents = Document.objects.filter(owner=request.user)
    return render(
        request,
        "documents/document_list.html",
        {"documents": documents},
    )


@login_required
def upload_document(request):
    if request.method == "POST":
        form = DocumentUploadForm(request.POST, request.FILES)

        if form.is_valid():
            document = form.save(commit=False)
            document.owner = request.user
            document.save()
            return redirect("documents:list")
    else:
        form = DocumentUploadForm()

    return render(request, "documents/upload.html", {"form": form})


@login_required
def read_document(request, document_id):
    document = get_object_or_404(
        Document,
        id=document_id,
        owner=request.user,
    )

    try:
        if not document.pages.exists():
            extracted_pages = extract_pdf_pages(document)

            with transaction.atomic():
                DocumentPage.objects.bulk_create(
                    [
                        DocumentPage(
                            document=document,
                            page_number=page["page_number"],
                            text=page["text"],
                        )
                        for page in extracted_pages
                    ]
                )

        pages = document.pages.all()
        error = None
    except PDFProcessingError as problem:
        pages = []
        error = str(problem)

    return render(
        request,
        "documents/read_document.html",
        {"document": document, "pages": pages, "error": error},
    )


@login_required
def ask_document(request, document_id):
    document = get_object_or_404(
        Document,
        id=document_id,
        owner=request.user,
    )
    form = QuestionForm(request.POST or None)
    results = []
    error = None
    answer = None
    answer_is_code = False

    if not document.pages.exists():
        error = "Open Read text by page once before asking a question."

    if request.method == "POST" and form.is_valid() and not error:
        try:
            results = search_document_pages(
                document,
                form.cleaned_data["question"],
            )
            results = [
                result
                for result in results
                if _has_specific_topic_match(
                    form.cleaned_data["question"],
                    [result],
                )
            ]

            if results:
                answer = generate_answer(
                    form.cleaned_data["question"],
                    results,
                )
        except (VectorSearchError, AnswerGenerationError) as problem:
            error = str(problem)

            if results:
                try:
                    answer = generate_answer(
                        form.cleaned_data["question"],
                        results,
                    )
                    answer_is_code = is_code_question(
                        form.cleaned_data["question"]
                    )
                except AnswerGenerationError as problem:
                    error = str(problem)

    return render(
        request,
        "documents/ask_document.html",
        {
            "document": document,
            "form": form,
            "results": results,
            "answer": answer,
            "answer_is_code": answer_is_code,
            "error": error,
        },
    )