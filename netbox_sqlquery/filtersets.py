import django_filters

from .models import SavedQuery


class SavedQueryFilterSet(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr="icontains")
    visibility = django_filters.ChoiceFilter(choices=SavedQuery.VISIBILITY_CHOICES)

    class Meta:
        model = SavedQuery
        fields = ["name", "visibility"]
