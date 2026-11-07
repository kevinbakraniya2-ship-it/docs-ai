from pathlib import Path

from django import forms
from django.core.exceptions import ValidationError

from .models import Document

MAX_PDF_SIZE = 10 * 1024 * 1024


class DocumentUploadForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ["title", "file"]

    def clean_file(self):
        uploaded_file = self.cleaned_data["file"]

        if Path(uploaded_file.name).suffix.lower() != ".pdf":
            raise ValidationError("Choose a file with the .pdf extension.")

        if uploaded_file.size > MAX_PDF_SIZE:
            raise ValidationError("The PDF must be 10 MB or smaller.")

        # The browser's MIME type can be forged, so also check the file signature.
        signature = uploaded_file.read(5)
        uploaded_file.seek(0)
        if signature != b"%PDF-":
            raise ValidationError("This file does not look like a PDF.")

        return uploaded_file

class QuestionForm(forms.Form):
    question = forms.CharField(
        max_length=300,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Ask something from this PDF...",
            }
        ),
    )