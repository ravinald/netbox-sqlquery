import logging

from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from netbox_sqlquery.access import can_execute_write, check_access, extract_tables
from netbox_sqlquery.models import SavedQuery
from netbox_sqlquery.query import execute_read_query, execute_write_query, is_write_query

from .serializers import SavedQuerySerializer

logger = logging.getLogger("netbox_sqlquery")


class SavedQueryViewSet(ModelViewSet):
    serializer_class = SavedQuerySerializer

    def get_queryset(self):
        return SavedQuery.visible_to(self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    @action(detail=True, methods=["post"])
    def execute(self, request, pk=None):
        """Execute a saved query and return results as JSON."""
        saved_query = self.get_object()
        sql = saved_query.sql.strip()
        user = request.user

        if not sql:
            return Response(
                {"error": "Saved query has no SQL."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        is_write = is_write_query(sql)

        # Check write permission
        if is_write and not can_execute_write(user):
            return Response(
                {"error": "Write queries require the 'change' permission or superuser status."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Require confirmation for write queries
        if is_write:
            confirmed = request.data.get("confirmed")
            if not confirmed:
                return Response(
                    {
                        "error": "Write queries require explicit confirmation.",
                        "detail": 'Include {"confirmed": true} in the request body.',
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Table access check
        denied = check_access(user, extract_tables(sql))
        if denied:
            return Response(
                {"error": f"Access denied to: {', '.join(sorted(denied))}"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Execute
        if is_write:
            result = execute_write_query(sql)
        else:
            result = execute_read_query(sql)

        if result.get("error"):
            return Response(
                {"error": result["error"]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Update run tracking
        saved_query.run_count += 1
        saved_query.last_run = timezone.now()
        saved_query.save(update_fields=["run_count", "last_run"])

        # Audit log
        truncated_sql = sql[:500]
        logger.info(
            "api query user=%s query=%s sql=%s",
            user.username,
            saved_query.name,
            truncated_sql,
        )

        # Build response
        response_data = {
            "query_name": saved_query.name,
            "columns": result["columns"],
            "rows": result["rows"],
            "row_count": result["row_count"],
        }
        if is_write:
            response_data["rows_affected"] = result.get("rows_affected", 0)
        else:
            response_data["truncated"] = result.get("truncated", False)

        return Response(response_data)
