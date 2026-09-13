from django.urls import include, path

urlpatterns = [
    path("api/", include("apps.core.urls")),
    path("api/", include("apps.files.urls")),
    path("api/", include("apps.jobs.urls")),
]
