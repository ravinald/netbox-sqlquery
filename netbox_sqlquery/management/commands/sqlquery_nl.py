from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from netbox_sqlquery.llm import generate_sql
from netbox_sqlquery.nl_agent import generate_sql_agentic

User = get_user_model()


class Command(BaseCommand):
    help = "Generate SQL from a natural language question (drives the AI agent loop)"

    def add_arguments(self, parser):
        parser.add_argument("question", help="Natural language question")
        parser.add_argument(
            "--user",
            help="Username to run as (defaults to the first superuser, for permission filtering)",
        )
        parser.add_argument(
            "--oneshot",
            action="store_true",
            help="Use the legacy one-shot text-to-SQL path instead of the agent loop",
        )

    def handle(self, *args, **options):
        username = options.get("user")
        if username:
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist as exc:
                raise CommandError(f"No such user: {username}") from exc
        else:
            user = User.objects.filter(is_superuser=True).first()
            if user is None:
                raise CommandError("No superuser found; pass --user explicitly.")

        question = options["question"]
        self.stdout.write(f"User:     {user.username}")
        self.stdout.write(f"Question: {question}")
        self.stdout.write("")

        if options["oneshot"]:
            sql = generate_sql(question, user)
        else:
            sql = generate_sql_agentic(question, user)

        self.stdout.write(self.style.SUCCESS("Generated SQL:"))
        self.stdout.write(sql)
