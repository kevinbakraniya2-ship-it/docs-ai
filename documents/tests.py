import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from .answer_service import clean_answer
from .forms import MAX_PDF_SIZE
from .models import Document


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
