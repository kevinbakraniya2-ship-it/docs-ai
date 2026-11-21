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

            if results:
                answer = generate_answer(
                    form.cleaned_data["question"],
                    results,
                )
                answer_is_code = is_code_question(
                    form.cleaned_data["question"]
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