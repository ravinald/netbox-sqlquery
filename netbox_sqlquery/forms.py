from django import forms

from .models import SavedQuery


class SavedQueryForm(forms.ModelForm):
    class Meta:
        model = SavedQuery
        fields = ["name", "description", "sql", "visibility", "tags"]
        widgets = {
            "sql": forms.Textarea(attrs={"rows": 10}),
        }


class SavedQueryFilterForm(forms.Form):
    name = forms.CharField(required=False)
    visibility = forms.ChoiceField(
        choices=[("", "---------")] + SavedQuery.VISIBILITY_CHOICES,
        required=False,
    )
