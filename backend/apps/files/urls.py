from django.urls import path

from apps.files import views

urlpatterns = [
    path("s3/connections/", views.S3ConnectionView.as_view(), name="s3-connect"),
    path("s3/connections/demo/", views.S3DemoConnectionView.as_view(), name="s3-demo"),
    path("files/", views.FileListView.as_view(), name="file-list"),
    path("files/columns/", views.FilePreviewView.as_view(), name="file-preview"),
]
