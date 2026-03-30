import django_tables2 as tables
from netbox.tables import NetBoxTable, columns

from .models import SavedQuery


class SavedQueryTable(NetBoxTable):
    name = tables.Column(linkify=True)
    owner = tables.Column()
    visibility = tables.Column()
    run_count = tables.Column()
    last_run = tables.DateTimeColumn()
    actions = columns.ActionsColumn(actions=("edit", "delete"))

    class Meta(NetBoxTable.Meta):
        model = SavedQuery
        fields = ("pk", "name", "owner", "visibility", "run_count", "last_run", "actions")
        default_columns = ("name", "owner", "visibility", "run_count", "last_run", "actions")
