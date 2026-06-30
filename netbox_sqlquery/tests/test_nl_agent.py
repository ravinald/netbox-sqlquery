from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from netbox_sqlquery import nl_agent
from netbox_sqlquery.models import NLExample, SavedQuery

User = get_user_model()

SCHEMA = {
    "nb_devices": [("name", "text"), ("site", "text"), ("tenant", "text")],
    "nb_sites": [("name", "text"), ("facility", "text")],
}

PLUGIN_CONFIG = {
    "netbox_sqlquery": {
        "deny_tables": ["auth_user", "users_token", "users_userconfig"],
        "ai_model": "test-model",
        "ai_max_iterations": 5,
        "ai_dry_run_limit": 20,
        "ai_fewshot_k": 3,
    }
}


def _turn(text=None, tool_calls=None):
    return {"text": text, "tool_calls": tool_calls or []}


def _call(name, args, cid="c1"):
    return {"id": cid, "name": name, "arguments": args}


@override_settings(PLUGINS_CONFIG=PLUGIN_CONFIG)
class AgentLoopTest(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_user("super", password="t", is_superuser=True)
        self.regular = User.objects.create_user("reg", password="t")

    def _run(self, turns, user=None):
        user = user or self.superuser
        with (
            mock.patch.object(nl_agent.llm, "chat_with_tools", side_effect=turns) as chat,
            mock.patch.object(nl_agent, "get_abstract_schema", return_value=SCHEMA),
        ):
            sql = nl_agent.generate_sql_agentic("list devices in NYC", user)
        return sql, chat

    def test_list_then_submit_returns_sql(self):
        turns = [
            _turn(tool_calls=[_call("list_tables", {})]),
            _turn(tool_calls=[_call("submit_query", {"sql": "SELECT name FROM nb_devices"})]),
        ]
        sql, chat = self._run(turns)
        self.assertEqual(sql, "SELECT name FROM nb_devices")
        self.assertEqual(chat.call_count, 2)

    def test_invalid_submit_is_rejected_then_retried(self):
        turns = [
            _turn(tool_calls=[_call("submit_query", {"sql": "DELETE FROM nb_devices"})]),
            _turn(tool_calls=[_call("submit_query", {"sql": "SELECT name FROM nb_devices"})]),
        ]
        sql, chat = self._run(turns)
        self.assertEqual(sql, "SELECT name FROM nb_devices")
        self.assertEqual(chat.call_count, 2)

    def test_plain_text_answer_is_accepted(self):
        turns = [_turn(text="SELECT site FROM nb_devices")]
        sql, _chat = self._run(turns)
        self.assertEqual(sql, "SELECT site FROM nb_devices")

    @override_settings(
        PLUGINS_CONFIG={
            "netbox_sqlquery": dict(PLUGIN_CONFIG["netbox_sqlquery"], ai_max_iterations=2)
        }
    )
    def test_exhaustion_raises(self):
        # Model keeps probing and never submits.
        probe = _turn(tool_calls=[_call("run_sql_dry", {"sql": "SELECT name FROM nb_devices"})])
        dry_result = {
            "columns": ["name"],
            "rows": [["a"]],
            "row_count": 1,
            "truncated": False,
            "error": None,
        }
        with (
            mock.patch.object(nl_agent.llm, "chat_with_tools", side_effect=[probe, probe]),
            mock.patch.object(nl_agent, "get_abstract_schema", return_value=SCHEMA),
            mock.patch.object(nl_agent, "execute_read_query", return_value=dry_result),
        ):
            with self.assertRaises(RuntimeError):
                nl_agent.generate_sql_agentic("list devices", self.superuser)


@override_settings(PLUGINS_CONFIG=PLUGIN_CONFIG)
class ToolDispatchTest(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_user("super", password="t", is_superuser=True)
        self.regular = User.objects.create_user("reg", password="t")

    def test_describe_table_unknown(self):
        out = nl_agent._tool_describe_table(SCHEMA, "nb_bogus")
        self.assertIn("Unknown or inaccessible", out)

    def test_describe_table_known(self):
        out = nl_agent._tool_describe_table(SCHEMA, "nb_devices")
        self.assertIn("name", out)
        self.assertIn("site", out)

    def test_lookup_values_rejects_unknown_table(self):
        args = {"table": "x", "column": "y", "search": "z"}
        out = nl_agent._tool_lookup_values(self.superuser, SCHEMA, args)
        self.assertIn("Unknown or inaccessible", out)

    def test_lookup_values_rejects_unknown_column(self):
        out = nl_agent._tool_lookup_values(
            self.superuser, SCHEMA, {"table": "nb_devices", "column": "nope", "search": "z"}
        )
        self.assertIn("Unknown column", out)

    def test_run_sql_dry_rejects_non_select(self):
        out = nl_agent._tool_run_sql_dry(self.superuser, SCHEMA, "DELETE FROM nb_devices")
        self.assertIn("read-only SELECT", out)

    def test_run_sql_dry_formats_rows(self):
        fake = {
            "columns": ["name"],
            "rows": [["dev1"], ["dev2"]],
            "row_count": 2,
            "truncated": False,
            "error": None,
        }
        with mock.patch.object(nl_agent, "execute_read_query", return_value=fake):
            out = nl_agent._tool_run_sql_dry(self.superuser, SCHEMA, "SELECT name FROM nb_devices")
        self.assertIn("dev1", out)
        self.assertIn("sample row", out)


@override_settings(PLUGINS_CONFIG=PLUGIN_CONFIG)
class ValidationAndExamplesTest(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_user("super", password="t", is_superuser=True)
        self.regular = User.objects.create_user("reg", password="t")

    def test_validate_denies_for_regular_user(self):
        err = nl_agent._validate_candidate(self.regular, SCHEMA, "SELECT name FROM nb_devices")
        self.assertIsNotNone(err)
        self.assertIn("access denied", err)

    def test_validate_passes_for_superuser(self):
        err = nl_agent._validate_candidate(self.superuser, SCHEMA, "SELECT name FROM nb_devices")
        self.assertIsNone(err)

    def test_validate_flags_unknown_column(self):
        err = nl_agent._validate_candidate(self.superuser, SCHEMA, "SELECT nope FROM nb_devices")
        self.assertIn("do not exist", err)

    def test_record_example_persists(self):
        nl_agent.record_example(self.superuser, "show devices", "SELECT name FROM nb_devices")
        self.assertEqual(NLExample.objects.count(), 1)

    def test_record_example_ignores_blank(self):
        nl_agent.record_example(self.superuser, "", "")
        self.assertEqual(NLExample.objects.count(), 0)

    def test_fewshot_excludes_inaccessible_examples(self):
        SavedQuery.objects.create(
            name="devices in NYC",
            sql="SELECT name FROM nb_devices",
            owner=self.superuser,
            visibility=SavedQuery.VISIBILITY_GLOBAL,
        )
        # Superuser can access -> example retrieved.
        got_super = nl_agent._retrieve_examples(self.superuser, "devices in NYC")
        self.assertEqual(len(got_super), 1)
        # Regular user cannot query the underlying table -> filtered out.
        got_regular = nl_agent._retrieve_examples(self.regular, "devices in NYC")
        self.assertEqual(got_regular, [])
