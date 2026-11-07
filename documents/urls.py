from django.urls import path

from . import views

app_name = "documents"

urlpatterns = [
    path("", views.document_list, name="list"),
    path("upload/", views.upload_document, name="upload"),
    path("<int:document_id>/read/", views.read_document, name="read"),
    path("<int:document_id>/ask/", views.ask_document, name="ask"),
]