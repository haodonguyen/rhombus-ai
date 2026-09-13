from django.urls import path

from apps.files import views

urlpatterns = [
    path("files/", views.FileListView.as_view(), name="file-list"),
    path("files/columns/", views.FilePreviewView.as_view(), name="file-preview"),
]
