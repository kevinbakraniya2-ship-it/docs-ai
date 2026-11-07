from uuid import uuid4

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models


def document_upload_path(instance, filename):
    """Store files under their owner's folder with a random server filename."""
    return f"documents/user_{instance.owner_id}/{uuid4().hex}.pdf"


class Document(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    title = models.CharField(max_length=200)
    file = models.FileField(
        upload_to=document_upload_path,
        validators=[FileExtensionValidator(allowed_extensions=["pdf"])],
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return self.title

# Create your models here.
class DocumentPage(models.Model):
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="pages",
    )
    page_number = models.PositiveIntegerField()
    text = models.TextField(blank=True)

    class Meta:
        ordering = ["page_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "page_number"],
                name="unique_page_number_per_document",
            )
        ]

    def __str__(self):
        return f"{self.document.title} — page {self.page_number}"