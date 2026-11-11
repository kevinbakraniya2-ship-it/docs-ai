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
from collections import Counter


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
        stop_words = {
            "what", "when", "where", "which", "who", "why", "how",
            "the", "is", "are", "was", "were", "a", "an", "of",
            "for", "to", "in", "on", "and", "or", "from", "with",
            "management", "system", "systems", "details", "detail",
            "explain", "describe", "tell", "about", "please", "show",
            "give", "me", "pdf", "document", "mujhe", "muje", "isme",
            "mein", "me", "ki", "ka", "ke", "batao", "do", "chahiye",
            "hai", "he", "kya", "ko",
        }
        query_terms = {
            word
            for word in re.findall(
                r"\w+",
                form.cleaned_data["question"].casefold(),
            )
            if len(word) > 1 and word not in stop_words
        }

        if not query_terms:
            form.add_error("question", "Add a few meaningful words.")
        else:
            for page in document.pages.all():
                page_word_counts = Counter(
                    re.findall(r"\w+", page.text.casefold())
                )
                score = sum(
                    min(page_word_counts[term], 3)
                    for term in query_terms
                )

                if score:
                    sentences = [
                        sentence.strip()
                        for sentence in re.split(
                            r"(?<=[.!?])\s+|\n+",
                            page.text,
                        )
                        if sentence.strip()
                    ]
                    matching_sentences = [
                        sentence
                        for sentence in sentences
                        if query_terms.intersection(
                            re.findall(r"\w+", sentence.casefold())
                        )
                    ]

                    results.append(
                        {
                            "page_number": page.page_number,
                            "snippets": matching_sentences[:6]
                            or [page.text[:1000]],
                            "context": page.text[:6000],
                            "score": score,
                        }
                    )

            results.sort(
                key=lambda result: (-result["score"], result["page_number"])
            )
            results = results[:3]

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