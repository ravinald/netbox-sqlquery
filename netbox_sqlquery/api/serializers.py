from rest_framework import serializers

from netbox_sqlquery.models import SavedQuery


class SavedQuerySerializer(serializers.ModelSerializer):
    class Meta:
        model = SavedQuery
        fields = [
            "id",
            "name",
            "description",
            "sql",
            "owner",
            "visibility",
            "created",
            "last_run",
            "run_count",
        ]
        read_only_fields = ["created", "last_run", "run_count"]

    def validate_owner(self, value):
        request = self.context.get("request")
        if request and value != request.user:
            raise serializers.ValidationError("You cannot set owner to another user.")
        return value

    def validate_visibility(self, value):
        request = self.context.get("request")
        if value == SavedQuery.VISIBILITY_GLOBAL_EDITABLE:
            if request and not request.user.is_staff:
                raise serializers.ValidationError(
                    "Only staff users can set global-editable visibility."
                )
        return value
