from rest_framework.routers import DefaultRouter

from .views import SavedQueryViewSet

router = DefaultRouter()
router.register("saved-queries", SavedQueryViewSet, basename="savedquery")

urlpatterns = router.urls
