from rest_framework.viewsets import ModelViewSet

from netbox_sqlquery.models import SavedQuery

from .serializers import SavedQuerySerializer


class SavedQueryViewSet(ModelViewSet):
    serializer_class = SavedQuerySerializer

    def get_queryset(self):
        return SavedQuery.visible_to(self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)
