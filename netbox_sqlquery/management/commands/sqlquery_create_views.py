from django.core.management.base import BaseCommand

from netbox_sqlquery.abstract_schema import drop_views, ensure_views


class Command(BaseCommand):
    help = "Create or replace abstract SQL views for the netbox-sqlquery plugin"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the SQL without executing",
        )
        parser.add_argument(
            "--drop",
            action="store_true",
            help="Drop all nb_* views instead of creating them",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Rebuild views even if they already exist",
        )

    def handle(self, *args, **options):
        if options["drop"]:
            dropped = drop_views()
            for name in dropped:
                self.stdout.write(f"Dropped {name}")
            self.stdout.write(self.style.SUCCESS(f"Dropped {len(dropped)} views"))
            return

        results = ensure_views(
            dry_run=options["dry_run"],
            force=options["force"] or options["dry_run"],
        )

        for view_name, sql in results:
            if options["dry_run"]:
                self.stdout.write(f"\n-- {view_name}")
                self.stdout.write(sql)
            else:
                self.stdout.write(f"Created {view_name}")

        action = "Generated" if options["dry_run"] else "Created"
        self.stdout.write(self.style.SUCCESS(f"{action} {len(results)} views"))
