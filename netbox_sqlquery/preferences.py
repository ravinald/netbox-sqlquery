from users.preferences import UserPreference

from netbox.choices import ColorChoices

COLOR_CHOICES = ColorChoices.CHOICES

preferences = {
    "highlight_enabled": UserPreference(
        label="SQL Query: Syntax highlighting",
        choices=(
            ("on", "On"),
            ("off", "Off"),
        ),
        default="on",
        description="Enable SQL syntax highlighting and auto-uppercase in the query editor.",
    ),
    "color_keyword": UserPreference(
        label="SQL Query: Keyword color",
        choices=COLOR_CHOICES,
        default=ColorChoices.COLOR_BLUE,
        description="Color for SQL keywords (SELECT, FROM, WHERE, etc.).",
    ),
    "color_function": UserPreference(
        label="SQL Query: Function color",
        choices=COLOR_CHOICES,
        default=ColorChoices.COLOR_PURPLE,
        description="Color for SQL functions (COUNT, SUM, AVG, etc.).",
    ),
    "color_string": UserPreference(
        label="SQL Query: String color",
        choices=COLOR_CHOICES,
        default=ColorChoices.COLOR_DARK_GREEN,
        description="Color for string literals ('active', 'test', etc.).",
    ),
    "color_number": UserPreference(
        label="SQL Query: Number color",
        choices=COLOR_CHOICES,
        default=ColorChoices.COLOR_DARK_ORANGE,
        description="Color for numeric literals (42, 3.14, etc.).",
    ),
    "color_operator": UserPreference(
        label="SQL Query: Operator color",
        choices=COLOR_CHOICES,
        default=ColorChoices.COLOR_DARK_RED,
        description="Color for operators (=, <>, >=, etc.).",
    ),
    "color_comment": UserPreference(
        label="SQL Query: Comment color",
        choices=COLOR_CHOICES,
        default=ColorChoices.COLOR_GREY,
        description="Color for SQL comments (-- line comments).",
    ),
    "skip_write_confirm": UserPreference(
        label="SQL Query: Skip write confirmation",
        choices=(
            ("off", "Off (always confirm)"),
            ("on", "On (skip confirmation)"),
        ),
        default="off",
        description="Skip the confirmation dialog when running INSERT, UPDATE, or DELETE queries. Superuser only.",
    ),
}
