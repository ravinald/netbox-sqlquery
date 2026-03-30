import json
import logging

from django.contrib.auth.mixins import UserPassesTestMixin
from django.db import DatabaseError, connection, transaction
from django.http import JsonResponse
from django.views import View
from django.utils import timezone
from django.views.generic import TemplateView

from netbox.plugins import get_plugin_config
from netbox.views.generic import (
    ObjectDeleteView,
    ObjectEditView,
    ObjectListView,
    ObjectView,
)

from .access import (
    ALL_TABLES, check_access, can_execute_write, extract_tables,
    _allowed_tables, _hard_denies_set,
)
from .filtersets import SavedQueryFilterSet
from .forms import SavedQueryFilterForm, SavedQueryForm
from .models import SavedQuery
from .schema import get_abstract_schema, get_schema
from .tables import SavedQueryTable

logger = logging.getLogger("netbox_sqlquery")


class QueryView(UserPassesTestMixin, TemplateView):
    template_name = "netbox_sqlquery/query.html"

    def test_func(self):
        user = self.request.user
        if not user.is_active:
            return False
        if user.is_superuser:
            return True
        if get_plugin_config("netbox_sqlquery", "require_superuser"):
            return False
        return user.has_perm("netbox_sqlquery.view_querypermission")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        # Determine mode from request
        mode = self.request.GET.get("mode") or self.request.POST.get("mode", "")
        if mode not in ("raw", "abstract"):
            mode = self.request.session.get("sqlquery_mode", "raw")
        self.request.session["sqlquery_mode"] = mode
        ctx["mode"] = mode

        # Raw schema (always needed for raw mode)
        schema = get_schema()
        allowed = _allowed_tables(self.request.user)
        denied = _hard_denies_set()

        if allowed is ALL_TABLES:
            raw_schema = {
                t: cols for t, cols in schema.items() if t not in denied
            }
        else:
            raw_schema = {
                t: cols for t, cols in schema.items()
                if t in allowed and t not in denied
            }
        ctx["raw_schema"] = raw_schema

        # Abstract schema
        abstract_schema = get_abstract_schema()
        ctx["abstract_schema"] = abstract_schema

        # Set active schema based on mode
        if mode == "abstract":
            ctx["schema"] = abstract_schema
        else:
            ctx["schema"] = raw_schema

        # JSON for the JS editor autocomplete (both modes)
        raw_dict = {t: [c[0] for c in cols] for t, cols in raw_schema.items()}
        abstract_dict = {t: [c[0] for c in cols] for t, cols in abstract_schema.items()}
        ctx["schema_json"] = json.dumps(raw_dict)
        ctx["abstract_schema_json"] = json.dumps(abstract_dict)

        # Load saved query if ?load=<pk> is in the URL
        load_pk = self.request.GET.get("load")
        if load_pk:
            try:
                sq = SavedQuery.visible_to(self.request.user).get(pk=load_pk)
                ctx["sql"] = sq.sql
            except (SavedQuery.DoesNotExist, ValueError):
                pass

        # Syntax highlighting preferences
        user_config = self.request.user.config
        hl_defaults = {
            "highlight_enabled": "on",
            "color_keyword": "2196f3",
            "color_function": "9c27b0",
            "color_string": "2f6a31",
            "color_number": "ff5722",
            "color_operator": "aa1409",
            "color_comment": "9e9e9e",
            "skip_write_confirm": "off",
        }
        # Pre-populate defaults so the preferences page shows correct values
        if not user_config.get("plugins.netbox_sqlquery.highlight_enabled"):
            for key, val in hl_defaults.items():
                user_config.set(f"plugins.netbox_sqlquery.{key}", val)
            user_config.save()

        ctx["highlight_prefs_json"] = json.dumps({
            "enabled": user_config.get(
                "plugins.netbox_sqlquery.highlight_enabled", "on") == "on",
            "keyword": user_config.get(
                "plugins.netbox_sqlquery.color_keyword", "2196f3"),
            "function": user_config.get(
                "plugins.netbox_sqlquery.color_function", "9c27b0"),
            "string": user_config.get(
                "plugins.netbox_sqlquery.color_string", "2f6a31"),
            "number": user_config.get(
                "plugins.netbox_sqlquery.color_number", "ff5722"),
            "operator": user_config.get(
                "plugins.netbox_sqlquery.color_operator", "aa1409"),
            "comment": user_config.get(
                "plugins.netbox_sqlquery.color_comment", "9e9e9e"),
        })

        # Write query support flags
        ctx["can_write"] = can_execute_write(self.request.user)
        ctx["is_superuser"] = self.request.user.is_superuser
        ctx["skip_write_confirm"] = user_config.get(
            "plugins.netbox_sqlquery.skip_write_confirm", "off") == "on"

        return ctx

    def post(self, request):
        sql = request.POST.get("sql", "").strip()
        ctx = self.get_context_data()
        ctx["sql"] = sql

        if not sql:
            ctx["error"] = "No SQL provided."
            return self.render_to_response(ctx)

        normalized = sql.lstrip().upper()
        is_select = normalized.startswith("SELECT") or normalized.startswith("WITH")
        is_write = (
            normalized.startswith("INSERT")
            or normalized.startswith("UPDATE")
            or normalized.startswith("DELETE")
        )

        if not is_select and not is_write:
            ctx["error"] = "Only SELECT, INSERT, UPDATE, and DELETE queries are permitted."
            return self.render_to_response(ctx)

        if is_write and not can_execute_write(request.user):
            ctx["error"] = "Write queries require the 'execute_write' permission or superuser status."
            return self.render_to_response(ctx)

        if is_write and request.POST.get("confirmed") != "1":
            ctx["needs_confirm"] = True
            return self.render_to_response(ctx)

        denied = check_access(request.user, extract_tables(sql))
        if denied:
            ctx["error"] = f"Access denied to: {', '.join(sorted(denied))}"
            return self.render_to_response(ctx)

        max_rows = get_plugin_config("netbox_sqlquery", "max_rows")
        timeout_ms = get_plugin_config("netbox_sqlquery", "statement_timeout_ms")

        if is_write:
            ctx = self._execute_write(ctx, sql, timeout_ms)
        else:
            ctx = self._execute_read(ctx, sql, timeout_ms, max_rows)

        _record_query(request.user, sql)
        return self.render_to_response(ctx)

    def _execute_read(self, ctx, sql, timeout_ms, max_rows):
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(f"SET LOCAL statement_timeout = '{timeout_ms}'")
                    cursor.execute("SET TRANSACTION READ ONLY")
                    cursor.execute(sql)
                    columns = [col[0] for col in cursor.description]
                    rows = cursor.fetchmany(max_rows)
                raise _ReadOnlyRollback()
        except _ReadOnlyRollback:
            ctx.update(columns=columns, rows=rows, row_count=len(rows))
        except DatabaseError as exc:
            ctx["error"] = str(exc)
        return ctx

    def _execute_write(self, ctx, sql, timeout_ms):
        max_rows = get_plugin_config("netbox_sqlquery", "max_rows")
        try:
            # Append RETURNING * if the user didn't include a RETURNING clause
            exec_sql = sql
            has_returning = "RETURNING" in sql.upper()
            normalized = sql.lstrip().upper()
            if not has_returning and (
                normalized.startswith("UPDATE") or normalized.startswith("DELETE")
            ):
                exec_sql = sql.rstrip().rstrip(";") + " RETURNING *"

            with connection.cursor() as cursor:
                cursor.execute(f"SET LOCAL statement_timeout = '{timeout_ms}'")
                cursor.execute(exec_sql)
                row_count = cursor.rowcount

                if cursor.description:
                    columns = [col[0] for col in cursor.description]
                    rows = cursor.fetchmany(max_rows)
                    ctx.update(columns=columns, rows=rows, row_count=len(rows))

            ctx["write_result"] = f"{row_count} row{'s' if row_count != 1 else ''} affected."
        except DatabaseError as exc:
            ctx["error"] = str(exc)
        return ctx


class _ReadOnlyRollback(Exception):
    """Raised to force rollback of the read-only transaction."""


def _record_query(user, sql):
    truncated = sql[:500] if len(sql) > 500 else sql
    logger.info("query user=%s sql=%s", user.username, truncated)


class _SavedQueryPermMixin:
    """Use the plugin's view_querypermission instead of model-derived permissions."""

    def get_required_permission(self):
        return "netbox_sqlquery.view_querypermission"


class SavedQueryListView(_SavedQueryPermMixin, ObjectListView):
    queryset = SavedQuery.objects.all()
    table = SavedQueryTable
    filterset = SavedQueryFilterSet
    filterset_form = SavedQueryFilterForm

    def get_queryset(self, request):
        return SavedQuery.visible_to(request.user)


class SavedQueryDetailView(_SavedQueryPermMixin, ObjectView):
    queryset = SavedQuery.objects.all()
    template_name = "netbox_sqlquery/saved_query.html"


class SavedQueryEditView(_SavedQueryPermMixin, ObjectEditView):
    queryset = SavedQuery.objects.all()
    form = SavedQueryForm

    def get_required_permission(self):
        return "netbox_sqlquery.view_querypermission"

    def alter_object(self, obj, request, url_args, url_kwargs):
        if not obj.pk:
            obj.owner = request.user
        return obj


class SavedQueryDeleteView(_SavedQueryPermMixin, ObjectDeleteView):
    queryset = SavedQuery.objects.all()


class SavedQueryAjaxSave(UserPassesTestMixin, View):
    """AJAX endpoint to save a query from the editor."""

    def test_func(self):
        return self.request.user.is_active and self.request.user.is_authenticated

    def post(self, request):
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        name = (data.get("name") or "").strip()
        sql = (data.get("sql") or "").strip()
        visibility = data.get("visibility", SavedQuery.VISIBILITY_PRIVATE)
        description = (data.get("description") or "").strip()

        if not name or not sql:
            return JsonResponse({"error": "Name and SQL are required."}, status=400)

        if len(name) > 100:
            return JsonResponse({"error": "Name must be 100 characters or fewer."}, status=400)

        # Validate name against injection
        import re
        if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9 _\-\.]*$', name):
            return JsonResponse({
                "error": "Name must start with a letter or number and contain only "
                         "letters, numbers, spaces, hyphens, underscores, and periods."
            }, status=400)

        if visibility not in dict(SavedQuery.VISIBILITY_CHOICES):
            return JsonResponse({"error": "Invalid visibility."}, status=400)

        query = SavedQuery.objects.create(
            name=name,
            sql=sql,
            description=description,
            visibility=visibility,
            owner=request.user,
        )
        return JsonResponse({
            "id": query.pk,
            "name": query.name,
            "message": f"Query '{query.name}' saved.",
        })


class SavedQueryAjaxList(UserPassesTestMixin, View):
    """AJAX endpoint to list saved queries for the load dialog."""

    def test_func(self):
        return self.request.user.is_active and self.request.user.is_authenticated

    def get(self, request):
        search = request.GET.get("q", "").strip()
        queries = SavedQuery.visible_to(request.user)
        if search:
            queries = queries.filter(name__icontains=search)
        queries = queries.order_by("name")[:50]
        return JsonResponse({
            "results": [
                {
                    "id": q.pk,
                    "name": q.name,
                    "description": q.description,
                    "sql": q.sql,
                    "visibility": q.get_visibility_display(),
                    "owner": q.owner.username,
                    "is_own": q.owner_id == request.user.pk,
                }
                for q in queries
            ]
        })
