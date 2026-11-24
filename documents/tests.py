import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from .answer_service import AnswerGenerationError, clean_answer, generate_answer,is_code_question
from .forms import MAX_PDF_SIZE
from .models import Document, DocumentPage, QuestionAnswer

from unittest.mock import patch

import httpx

from unittest.mock import patch
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

from .pdf_reader import extract_pdf_pages
from .vector_search import (
    delete_document_vectors,
    index_document_pages,
    search_document_pages,
)
from .views import _has_specific_topic_match

from unittest.mock import patch

User = get_user_model()


class DocumentUploadTests(TestCase):
    def setUp(self):
        project_root = Path(__file__).resolve().parent.parent
        self.temp_media = tempfile.TemporaryDirectory(dir=project_root)
        self.addCleanup(self.temp_media.cleanup)
        self.media_override = override_settings(MEDIA_ROOT=self.temp_media.name)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.user = User.objects.create_user(username="maya", password="N4v!gation-Leaf-27")
        self.other_user = User.objects.create_user(username="arjun", password="N4v!gation-Leaf-28")
        self.client.force_login(self.user)

    def make_pdf(self, name="notes.pdf", content=b"%PDF-1.4\nExample PDF content"):
        return SimpleUploadedFile(name, content, content_type="application/pdf")

    def test_upload_is_saved_under_logged_in_owner(self):
        response = self.client.post(
            reverse("documents:upload"),
            {"title": "Physics notes", "file": self.make_pdf(), "owner": self.other_user.pk},
        )

        self.assertRedirects(response, reverse("documents:list"))
        document = Document.objects.get()
        self.assertEqual(document.owner, self.user)
        self.assertTrue(document.file.name.startswith(f"documents/user_{self.user.pk}/"))
        self.assertTrue(document.file.name.endswith(".pdf"))
        self.assertNotIn("notes.pdf", document.file.name)

    def test_list_only_shows_the_logged_in_users_documents(self):
        Document.objects.create(owner=self.other_user, title="Private notes", file=self.make_pdf())

        response = self.client.get(reverse("documents:list"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Private notes")

    def test_user_cannot_open_another_users_ask_page(self):
        private_document = Document.objects.create(
            owner=self.other_user,
            title="Arjun private notes",
            file=self.make_pdf(name="private.pdf"),
        )

        response = self.client.get(
            f"/documents/{private_document.pk}/ask/"
        )

        self.assertEqual(response.status_code, 404)

    def test_upload_rejects_non_pdf_extension(self):
        response = self.client.post(
            reverse("documents:upload"),
            {"title": "Wrong type", "file": self.make_pdf(name="notes.txt")},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Document.objects.exists())

    def test_upload_rejects_file_without_pdf_signature(self):
        response = self.client.post(
            reverse("documents:upload"),
            {"title": "Fake PDF", "file": self.make_pdf(content=b"not a PDF")},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Document.objects.exists())

    def test_upload_rejects_files_over_size_limit(self):
        too_large = self.make_pdf(content=b"%PDF-" + b"x" * MAX_PDF_SIZE)

        response = self.client.post(
            reverse("documents:upload"),
            {"title": "Too large", "file": too_large},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Document.objects.exists())

    def test_upload_requires_login(self):
        self.client.logout()

        response = self.client.get(reverse("documents:upload"))

        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next={reverse('documents:upload')}",
        )

    def test_upload_requires_csrf_token(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)

        response = csrf_client.post(
            reverse("documents:upload"),
            {"title": "Blocked", "file": self.make_pdf()},
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Document.objects.exists())

    @patch("documents.views.delete_document_vectors")
    def test_delete_removes_document_file_and_vectors(self, mock_delete_vectors):
        document = Document.objects.create(
            owner=self.user,
            title="Delete test",
            file=self.make_pdf(name="delete-test.pdf"),
        )
        document_id = document.pk
        file_path = Path(document.file.path)

        response = self.client.post(
            reverse("documents:delete", args=[document_id])
        )

        self.assertRedirects(response, reverse("documents:list"))
        self.assertFalse(Document.objects.filter(pk=document_id).exists())
        self.assertFalse(file_path.exists())
        mock_delete_vectors.assert_called_once()

    def test_delete_requires_post(self):
        document = Document.objects.create(
            owner=self.user,
            title="Keep this PDF",
            file=self.make_pdf(name="keep-test.pdf"),
        )

        response = self.client.get(
            reverse("documents:delete", args=[document.pk])
        )

        self.assertRedirects(response, reverse("documents:list"))
        self.assertTrue(Document.objects.filter(pk=document.pk).exists())

    def test_user_cannot_delete_another_users_document(self):
        document = Document.objects.create(
            owner=self.other_user,
            title="Private PDF",
            file=self.make_pdf(name="private-test.pdf"),
        )

        response = self.client.post(
            reverse("documents:delete", args=[document.pk])
        )

        self.assertEqual(response.status_code, 404)
        self.assertTrue(Document.objects.filter(pk=document.pk).exists())

class AnswerFormattingTests(SimpleTestCase):
    def test_plain_answer_removes_markdown_markers(self):
        answer = "**Employee system**\n- Adds employee records."
        self.assertEqual(
            clean_answer(answer),
            "Employee system\n• Adds employee records.",
        )

    def test_code_answer_removes_fences_and_keeps_line_breaks(self):
        fence = chr(96) * 3
        answer = f'{fence}php\n<?php\n$name = "Maya";\n{fence}'
        self.assertEqual(
            clean_answer(answer, code_response=True),
            '<?php\n$name = "Maya";',
        )

class AnswerTimeoutTests(SimpleTestCase):
    @patch("documents.answer_service.Client")
    def test_timeout_returns_friendly_error(self, mock_client_class):
        mock_client = mock_client_class.return_value
        mock_client.chat.side_effect = httpx.ReadTimeout("timed out")

        results = [
            {
                "page_number": 1,
                "context": "SQL means Structured Query Language.",
            }
        ]

        with self.assertRaises(AnswerGenerationError) as error:
            generate_answer("What is SQL?", results)

        self.assertIn(
            "Ollama ne samay par jawab nahi diya",
            str(error.exception),
        )

class CodeQuestionDetectionTests(SimpleTestCase):
    def test_explanation_question_is_not_code_only(self):
        self.assertFalse(is_code_question("What is SQL?"))

    def test_sql_query_request_uses_code_mode(self):
        self.assertTrue(is_code_question("SQL query"))

    def test_mixed_explanation_and_query_is_not_code_only(self):
        question = "What is SQL? Give me an example for any SQL query"
        self.assertFalse(is_code_question(question))


class MixedAnswerFormattingTests(SimpleTestCase):
    def test_embedded_code_fences_are_removed_from_explanation(self):
        answer = "Query:\n```sql\nSELECT * FROM employees;\n```"
        self.assertEqual(
            clean_answer(answer),
            "Query:\nSELECT * FROM employees;",
        )

class DocumentSearchTests(TestCase):
    def setUp(self):
        project_root = Path(__file__).resolve().parent.parent
        self.temp_media = tempfile.TemporaryDirectory(dir=project_root)
        self.addCleanup(self.temp_media.cleanup)

        self.media_override = override_settings(MEDIA_ROOT=self.temp_media.name)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)

        self.user = User.objects.create_user(
            username="searcher",
            password="Test-password-123!",
        )
        self.client.force_login(self.user)

        pdf = SimpleUploadedFile(
            "search.pdf",
            b"%PDF-1.4\nSearch test",
            content_type="application/pdf",
        )
        self.document = Document.objects.create(
            owner=self.user,
            title="SQL notes",
            file=pdf,
        )

    @patch("documents.views.search_document_pages")
    @patch("documents.views.generate_answer", return_value="Fake answer")
    def test_search_selects_page_matching_query_terms(
        self,
        mock_generate,
        mock_search,
    ):
        DocumentPage.objects.create(
            document=self.document,
            page_number=1,
            text="This page discusses databases generally.",
        )
        DocumentPage.objects.create(
            document=self.document,
            page_number=2,
            text="SQL query examples are shown on this page.",
        )
        mock_search.return_value = [
            {
                "page_number": 2,
                "snippets": ["SQL query examples are shown on this page."],
                "context": "SQL query examples are shown on this page.",
                "score": 0.8,
            }
        ]

        response = self.client.post(
            reverse("documents:ask", args=[self.document.pk]),
            {"question": "SQL query"},
        )

        self.assertEqual(response.status_code, 200)
        page_numbers = [
            result["page_number"]
            for result in response.context["results"]
        ]
        self.assertEqual(page_numbers, [2])
        mock_search.assert_called_once_with(self.document, "SQL query")
        mock_generate.assert_called_once()
        saved_answer = QuestionAnswer.objects.get(document=self.document)
        self.assertEqual(saved_answer.question, "SQL query")
        self.assertEqual(saved_answer.answer, "Fake answer")
        self.assertEqual(saved_answer.source_pages, [2])

    def test_get_shows_saved_question_history(self):
        saved_answer = QuestionAnswer.objects.create(
            document=self.document,
            question="What is SQL?",
            answer="SQL means Structured Query Language.",
            source_pages=[1],
        )

        response = self.client.get(
            reverse("documents:ask", args=[self.document.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Question history")
        self.assertContains(response, saved_answer.question)
        self.assertContains(response, saved_answer.answer)
        self.assertEqual(
            list(response.context["question_history"]),
            [saved_answer],
        )

    @patch("documents.views.search_document_pages", return_value=[])
    @patch("documents.views.generate_answer")
    def test_no_match_shows_message_without_calling_ai(
        self,
        mock_generate,
        mock_search,
    ):
        DocumentPage.objects.create(
            document=self.document,
            page_number=1,
            text="SQL query examples are shown on this page.",
        )

        response = self.client.post(
            reverse("documents:ask", args=[self.document.pk]),
            {"question": "volcano astronomy"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["results"], [])
        self.assertContains(response, "No matching text found.")
        mock_search.assert_called_once_with(
            self.document,
            "volcano astronomy",
        )
        mock_generate.assert_not_called()

class TopicRelevanceTests(SimpleTestCase):
    def test_rejects_mobile_shop_page_for_employee_question(self):
        question = "What is an Employee Management System and explain index.php"
        result = {
            "context": (
                "Mobile Shop Management System. Create a website using "
                "PHP, MySQL, and AJAX to manage mobile phone records."
            ),
            "snippets": [],
        }

        self.assertFalse(
            _has_specific_topic_match(question, [result])
        )

    def test_accepts_employee_management_page(self):
        question = "What is an Employee Management System and explain index.php"
        result = {
            "context": (
                "Employee Management System. Insert, display, update, and "
                "delete employee records containing name, email, department, "
                "designation, and salary."
            ),
            "snippets": [],
        }

        self.assertTrue(
            _has_specific_topic_match(question, [result])
        )

class PDFOCRTests(SimpleTestCase):
    def make_document(self):
        file_object = SimpleNamespace(
            open=Mock(return_value=BytesIO(b"%PDF test"))
        )
        return SimpleNamespace(file=file_object)

    def test_scanned_page_uses_ocr(self):
        page = SimpleNamespace(extract_text=Mock(return_value=""))
        reader = SimpleNamespace(is_encrypted=False, pages=[page])

        with (
            patch("documents.pdf_reader.PdfReader", return_value=reader),
            patch(
                "documents.pdf_reader.convert_from_bytes",
                return_value=[object()],
            ) as convert,
            patch(
                "documents.pdf_reader.pytesseract.image_to_string",
                return_value="Recognized scanned text",
            ) as ocr,
        ):
            pages = extract_pdf_pages(self.make_document())

        self.assertEqual(pages[0]["text"], "Recognized scanned text")
        convert.assert_called_once()
        ocr.assert_called_once()

    def test_text_pdf_does_not_use_ocr(self):
        page = SimpleNamespace(
            extract_text=Mock(return_value="Selectable PDF text")
        )
        reader = SimpleNamespace(is_encrypted=False, pages=[page])

        with (
            patch("documents.pdf_reader.PdfReader", return_value=reader),
            patch("documents.pdf_reader.convert_from_bytes") as convert,
            patch(
                "documents.pdf_reader.pytesseract.image_to_string"
            ) as ocr,
        ):
            pages = extract_pdf_pages(self.make_document())

        self.assertEqual(pages[0]["text"], "Selectable PDF text")
        convert.assert_not_called()
        ocr.assert_not_called()

class VectorSearchTests(SimpleTestCase):
    def setUp(self):
        self.document = SimpleNamespace(pk=5, owner_id=2)

    def test_search_is_scoped_to_document_and_filters_weak_matches(self):
        collection = Mock()
        collection.get.return_value = {"ids": ["page-3", "page-9"]}
        collection.query.return_value = {
            "documents": [[
                "Information systems help managers make decisions.",
                "This passage is not very similar.",
            ]],
            "metadatas": [[
                {"page_number": 3},
                {"page_number": 9},
            ]],
            "distances": [[0.15, 0.75]],
        }

        with (
            patch("documents.vector_search.index_document_pages") as index_pages,
            patch(
                "documents.vector_search._get_collection",
                return_value=collection,
            ),
            patch(
                "documents.vector_search._embed",
                return_value=[[0.1, 0.2]],
            ),
        ):
            results = search_document_pages(
                self.document,
                "How do information systems help managers?",
            )

        expected_filter = {
            "$and": [
                {"owner_id": {"$eq": "2"}},
                {"document_id": {"$eq": "5"}},
            ]
        }

        index_pages.assert_called_once_with(self.document)
        collection.get.assert_called_once_with(
            where=expected_filter,
            include=["metadatas"],
        )
        collection.query.assert_called_once_with(
            query_embeddings=[[0.1, 0.2]],
            where=expected_filter,
            n_results=2,
            include=["documents", "metadatas", "distances"],
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["page_number"], 3)
        self.assertAlmostEqual(results[0]["score"], 0.85)

    def test_search_returns_empty_when_document_has_no_indexed_pages(self):
        collection = Mock()
        collection.get.return_value = {"ids": []}

        with (
            patch("documents.vector_search.index_document_pages"),
            patch(
                "documents.vector_search._get_collection",
                return_value=collection,
            ),
            patch("documents.vector_search._embed") as embed,
        ):
            results = search_document_pages(
                self.document,
                "What is the topic?",
            )

        self.assertEqual(results, [])
        embed.assert_not_called()
        collection.query.assert_not_called()

class VectorIndexLifecycleTests(SimpleTestCase):
    def make_document(self):
        pages = [
            SimpleNamespace(page_number=1, text="Employee records"),
            SimpleNamespace(page_number=2, text="Course records"),
        ]

        page_query = Mock()
        page_query.exclude.return_value = page_query
        page_query.only.return_value = page_query
        page_query.order_by.return_value = pages

        document = SimpleNamespace(
            pk=5,
            owner_id=2,
            pages=page_query,
        )
        return document

    def test_index_saves_pages_with_document_and_owner_ids(self):
        document = self.make_document()
        collection = Mock()
        collection.get.return_value = {"ids": []}

        with (
            patch(
                "documents.vector_search._get_collection",
                return_value=collection,
            ),
            patch(
                "documents.vector_search._embed",
                return_value=[[0.1, 0.2], [0.3, 0.4]],
            ) as embed,
        ):
            added_count = index_document_pages(document)

        self.assertEqual(added_count, 2)
        embed.assert_called_once_with(["Employee records", "Course records"])
        collection.upsert.assert_called_once_with(
            ids=["document-5-page-1", "document-5-page-2"],
            embeddings=[[0.1, 0.2], [0.3, 0.4]],
            documents=["Employee records", "Course records"],
            metadatas=[
                {
                    "owner_id": "2",
                    "document_id": "5",
                    "page_number": 1,
                },
                {
                    "owner_id": "2",
                    "document_id": "5",
                    "page_number": 2,
                },
            ],
        )

    def test_index_does_not_embed_pages_already_saved(self):
        document = self.make_document()
        collection = Mock()
        collection.get.return_value = {
            "ids": ["document-5-page-1", "document-5-page-2"],
        }

        with (
            patch(
                "documents.vector_search._get_collection",
                return_value=collection,
            ),
            patch("documents.vector_search._embed") as embed,
        ):
            added_count = index_document_pages(document)

        self.assertEqual(added_count, 0)
        embed.assert_not_called()
        collection.upsert.assert_not_called()

    def test_delete_removes_only_this_documents_vectors(self):
        document = SimpleNamespace(pk=5, owner_id=2)
        collection = Mock()

        with patch(
            "documents.vector_search._get_collection",
            return_value=collection,
        ):
            delete_document_vectors(document)

        collection.delete.assert_called_once_with(
            where={
                "$and": [
                    {"owner_id": {"$eq": "2"}},
                    {"document_id": {"$eq": "5"}},
                ]
            }
        )
