from django.urls import path

from apps.jobs import views

urlpatterns = [
    path("jobs/", views.JobCreateView.as_view(), name="job-create"),
    path("jobs/<uuid:job_id>/", views.JobDetailView.as_view(), name="job-detail"),
    path("jobs/<uuid:job_id>/cancel/", views.JobCancelView.as_view(), name="job-cancel"),
    path("jobs/<uuid:job_id>/results/", views.JobResultsView.as_view(), name="job-results"),
]
