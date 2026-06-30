from django.urls import path

from . import views

urlpatterns = [
    path("", views.QueryView.as_view(), name="query"),
    path("saved-queries/", views.SavedQueryListView.as_view(), name="savedquery_list"),
    path("saved-queries/add/", views.SavedQueryEditView.as_view(), name="savedquery_add"),
    path("saved-queries/<int:pk>/", views.SavedQueryDetailView.as_view(), name="savedquery"),
    path(
        "saved-queries/<int:pk>/edit/",
        views.SavedQueryEditView.as_view(),
        name="savedquery_edit",
    ),
    path(
        "saved-queries/<int:pk>/delete/",
        views.SavedQueryDeleteView.as_view(),
        name="savedquery_delete",
    ),
    path("ajax/save-query/", views.SavedQueryAjaxSave.as_view(), name="ajax_save_query"),
    path("ajax/list-queries/", views.SavedQueryAjaxList.as_view(), name="ajax_list_queries"),
    path("export-csv/", views.CSVExportView.as_view(), name="export_csv"),
    path("ajax/ai-query/", views.NLQueryAjaxView.as_view(), name="ajax_ai_query"),
]
