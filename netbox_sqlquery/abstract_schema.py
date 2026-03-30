"""
Generate PostgreSQL VIEWs that present NetBox data with resolved foreign keys
and aggregated M2M relationships (tags), matching how the GUI displays data.
"""

import logging

from django.apps import apps
from django.db import connection

logger = logging.getLogger("netbox_sqlquery")

# Apps to include in abstract views
INCLUDED_APPS = {
    "circuits",
    "dcim",
    "ipam",
    "tenancy",
    "virtualization",
    "vpn",
    "wireless",
}

# Models to skip (through tables, internal models, templates)
EXCLUDED_MODELS = {
    "dcim.cablepath",
    "dcim.cabletermination",
    "dcim.consoleporttemplate",
    "dcim.consoleserverporttemplate",
    "dcim.devicebaytemplate",
    "dcim.frontporttemplate",
    "dcim.interfacetemplate",
    "dcim.inventoryitemtemplate",
    "dcim.modulebaytemplate",
    "dcim.portmapping",
    "dcim.porttemplatemapping",
    "dcim.poweroutlettemplate",
    "dcim.powerporttemplate",
    "dcim.rearporttemplate",
}

# Columns to skip (internal, denormalized, or handled specially)
SKIP_COLUMNS = {
    "custom_field_data",
    "lft",
    "rght",
    "tree_id",
    "level",
}

# FK columns that are internal/denormalized and should not appear in the view
INTERNAL_FK_PREFIXES = ("_",)

# Override the display expression for specific target tables
# Default is to use the "name" column from the target table
FK_DISPLAY_OVERRIDES = {
    "ipam_vlan": "CONCAT({alias}.vid, ' (', {alias}.name, ')')",
    "django_content_type": "CONCAT({alias}.app_label, '.', {alias}.model)",
    "users_owner": "{alias}.id",
}

# Override the view name for specific models
VIEW_NAME_OVERRIDES = {
    "ipam.ipaddress": "nb_ip_addresses",
    "ipam.fhrpgroup": "nb_fhrp_groups",
    "ipam.fhrpgroupassignment": "nb_fhrp_group_assignments",
    "ipam.asnrange": "nb_asn_ranges",
    "ipam.vlangroup": "nb_vlan_groups",
    "ipam.vlantranslationpolicy": "nb_vlan_translation_policies",
    "ipam.vlantranslationrule": "nb_vlan_translation_rules",
    "ipam.routetarget": "nb_route_targets",
    "ipam.servicetemplate": "nb_service_templates",
    "dcim.devicebay": "nb_device_bays",
    "dcim.devicerole": "nb_device_roles",
    "dcim.devicetype": "nb_device_types",
    "dcim.frontport": "nb_front_ports",
    "dcim.consoleport": "nb_console_ports",
    "dcim.consoleserverport": "nb_console_server_ports",
    "dcim.inventoryitem": "nb_inventory_items",
    "dcim.inventoryitemrole": "nb_inventory_item_roles",
    "dcim.macaddress": "nb_mac_addresses",
    "dcim.modulebay": "nb_module_bays",
    "dcim.moduletype": "nb_module_types",
    "dcim.moduletypeprofile": "nb_module_type_profiles",
    "dcim.powerfeed": "nb_power_feeds",
    "dcim.poweroutlet": "nb_power_outlets",
    "dcim.powerpanel": "nb_power_panels",
    "dcim.powerport": "nb_power_ports",
    "dcim.rackreservation": "nb_rack_reservations",
    "dcim.rackrole": "nb_rack_roles",
    "dcim.racktype": "nb_rack_types",
    "dcim.rearport": "nb_rear_ports",
    "dcim.sitegroup": "nb_site_groups",
    "dcim.virtualchassis": "nb_virtual_chassis",
    "dcim.virtualdevicecontext": "nb_virtual_device_contexts",
    "circuits.circuitgroup": "nb_circuit_groups",
    "circuits.circuitgroupassignment": "nb_circuit_group_assignments",
    "circuits.circuittype": "nb_circuit_types",
    "circuits.circuittermination": "nb_circuit_terminations",
    "circuits.provideraccount": "nb_provider_accounts",
    "circuits.providernetwork": "nb_provider_networks",
    "circuits.virtualcircuit": "nb_virtual_circuits",
    "circuits.virtualcircuittype": "nb_virtual_circuit_types",
    "circuits.virtualcircuittermination": "nb_virtual_circuit_terminations",
    "tenancy.contactassignment": "nb_contact_assignments",
    "tenancy.contactgroup": "nb_contact_groups",
    "tenancy.contactrole": "nb_contact_roles",
    "tenancy.tenantgroup": "nb_tenant_groups",
    "virtualization.clustergroup": "nb_cluster_groups",
    "virtualization.clustertype": "nb_cluster_types",
    "virtualization.virtualdisk": "nb_virtual_disks",
    "virtualization.virtualmachine": "nb_virtual_machines",
    "virtualization.vminterface": "nb_vm_interfaces",
    "vpn.ikepolicy": "nb_ike_policies",
    "vpn.ikeproposal": "nb_ike_proposals",
    "vpn.ipsecpolicy": "nb_ipsec_policies",
    "vpn.ipsecprofile": "nb_ipsec_profiles",
    "vpn.ipsecproposal": "nb_ipsec_proposals",
    "vpn.l2vpn": "nb_l2vpns",
    "vpn.l2vpntermination": "nb_l2vpn_terminations",
    "vpn.tunnelgroup": "nb_tunnel_groups",
    "vpn.tunneltermination": "nb_tunnel_terminations",
    "wireless.wirelesslan": "nb_wireless_lans",
    "wireless.wirelesslangroup": "nb_wireless_lan_groups",
    "wireless.wirelesslink": "nb_wireless_links",
}

# Column renames (internal name -> friendly name)
COLUMN_RENAMES = {
    "_children": "children",
    "_depth": "depth",
    "_name": "name",
}

# Maps nb_* view name -> set of underlying table names (populated by ensure_views)
ABSTRACT_TO_TABLES = {}


def _get_view_name(model):
    """Generate the nb_* view name for a model."""
    label = f"{model._meta.app_label}.{model._meta.model_name}"
    if label in VIEW_NAME_OVERRIDES:
        return VIEW_NAME_OVERRIDES[label]
    # Default: nb_ + verbose_name_plural with spaces/hyphens replaced by underscores
    plural = str(model._meta.verbose_name_plural).lower()
    slug = plural.replace(" ", "_").replace("-", "_")
    return f"nb_{slug}"


def _get_table_columns(table_name):
    """Get column info from information_schema for a table."""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position
        """, [table_name])
        return cursor.fetchall()


def _get_fk_map(table_name):
    """Get FK column -> target table mapping from information_schema."""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT kcu.column_name, ccu.table_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu
              ON tc.constraint_name = ccu.constraint_name
             AND tc.table_schema = ccu.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = 'public'
              AND kcu.table_name = %s
        """, [table_name])
        return {row[0]: row[1] for row in cursor.fetchall()}


def _target_has_column(table_name, column_name):
    """Check if a table has a specific column."""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = %s
              AND column_name = %s
            LIMIT 1
        """, [table_name, column_name])
        return cursor.fetchone() is not None


def _has_tags(model):
    """Check if a model uses NetBox's tagging system."""
    for field in model._meta.get_fields():
        if hasattr(field, "related_model") and field.related_model is not None:
            related = field.related_model
            if related._meta.db_table == "extras_taggeditem":
                return True
            if (related._meta.app_label == "extras"
                    and related._meta.model_name == "taggeditem"):
                return True
    # Also check via the through table pattern
    try:
        model._meta.get_field("tags")
        return True
    except Exception:
        return False


def build_view_sql(model):
    """
    Build a CREATE OR REPLACE VIEW statement for a Django model.
    Returns (view_name, sql, underlying_tables) or None if the model should be skipped.
    """
    db_table = model._meta.db_table
    view_name = _get_view_name(model)
    alias = "t"

    columns_info = _get_table_columns(db_table)
    if not columns_info:
        return None

    fk_map = _get_fk_map(db_table)

    select_parts = []
    join_parts = []
    underlying_tables = {db_table}
    join_counter = 0
    used_names = set()

    def _unique_name(name):
        """Ensure output column names are unique by appending _2, _3, etc."""
        if name not in used_names:
            used_names.add(name)
            return name
        i = 2
        while f"{name}_{i}" in used_names:
            i += 1
        unique = f"{name}_{i}"
        used_names.add(unique)
        return unique

    for col_name, col_type, is_nullable in columns_info:
        if col_name in SKIP_COLUMNS:
            continue

        # Determine the output column name
        out_name = COLUMN_RENAMES.get(col_name, col_name)

        # Skip internal FK columns (prefixed with _) that point to denormalized caches
        if col_name.startswith("_") and col_name in fk_map:
            continue

        if col_name in fk_map and col_name.endswith("_id"):
            target_table = fk_map[col_name]
            friendly_name = col_name[:-3]  # strip _id

            # Skip content_type FK for generic foreign keys (handled separately)
            if target_table == "django_content_type" and col_name == "scope_type_id":
                join_counter += 1
                j_alias = f"j{join_counter}"
                expr = FK_DISPLAY_OVERRIDES["django_content_type"].format(alias=j_alias)
                col_alias = _unique_name("scope_type")
                select_parts.append(f"  {expr} AS {col_alias}")
                join_parts.append(
                    f"LEFT JOIN {target_table} {j_alias} ON {j_alias}.id = {alias}.{col_name}"
                )
                underlying_tables.add(target_table)
                continue

            if target_table == "django_content_type":
                join_counter += 1
                j_alias = f"j{join_counter}"
                ct_friendly = col_name.replace("_id", "").replace("content_type", "type")
                expr = FK_DISPLAY_OVERRIDES["django_content_type"].format(alias=j_alias)
                col_alias = _unique_name(ct_friendly)
                select_parts.append(f"  {expr} AS {col_alias}")
                join_parts.append(
                    f"LEFT JOIN {target_table} {j_alias} ON {j_alias}.id = {alias}.{col_name}"
                )
                underlying_tables.add(target_table)
                continue

            # Resolve FK to display value
            join_counter += 1
            j_alias = f"j{join_counter}"
            underlying_tables.add(target_table)

            if target_table in FK_DISPLAY_OVERRIDES:
                expr = FK_DISPLAY_OVERRIDES[target_table].format(alias=j_alias)
            elif _target_has_column(target_table, "name"):
                expr = f"{j_alias}.name"
            elif _target_has_column(target_table, "_name"):
                expr = f"{j_alias}._name"
            else:
                # No name column -- fall back to showing the ID
                col_alias = _unique_name(friendly_name)
                select_parts.append(f"  {alias}.{col_name} AS {col_alias}")
                continue

            col_alias = _unique_name(friendly_name)
            select_parts.append(f"  {expr} AS {col_alias}")
            join_parts.append(
                f"LEFT JOIN {target_table} {j_alias} ON {j_alias}.id = {alias}.{col_name}"
            )
        else:
            # Regular column
            col_alias = _unique_name(out_name)
            if col_alias != col_name:
                select_parts.append(f"  {alias}.{col_name} AS {col_alias}")
            else:
                select_parts.append(f"  {alias}.{col_name}")

    # Add tags subquery if the model supports tags
    if _has_tags(model):
        app_label = model._meta.app_label
        model_name = model._meta.model_name
        select_parts.append(f"""  (SELECT STRING_AGG(tag.name, ', ' ORDER BY tag.name)
   FROM extras_taggeditem ti
   JOIN extras_tag tag ON tag.id = ti.tag_id
   WHERE ti.content_type_id = (
     SELECT id FROM django_content_type
     WHERE app_label = '{app_label}' AND model = '{model_name}'
   )
   AND ti.object_id = {alias}.id
  ) AS tags""")
        underlying_tables.add("extras_taggeditem")
        underlying_tables.add("extras_tag")

    select_clause = ",\n".join(select_parts)
    from_clause = f"{db_table} {alias}"
    join_clause = "\n".join(join_parts)

    sql = f"CREATE OR REPLACE VIEW {view_name} AS\nSELECT\n{select_clause}\nFROM {from_clause}"
    if join_clause:
        sql += f"\n{join_clause}"
    sql += ";"

    return view_name, sql, underlying_tables


def get_included_models():
    """Return all Django models that should get abstract views."""
    models = []
    for model in apps.get_models():
        app_label = model._meta.app_label
        if app_label not in INCLUDED_APPS:
            continue
        label = f"{app_label}.{model._meta.model_name}"
        if label in EXCLUDED_MODELS:
            continue
        # Skip auto-created through tables for M2M fields
        if model._meta.auto_created:
            continue
        models.append(model)
    return models


def ensure_views(dry_run=False):
    """Create or replace all abstract views. Returns list of (view_name, sql) tuples."""
    results = []
    ABSTRACT_TO_TABLES.clear()

    models = get_included_models()

    for model in models:
        try:
            result = build_view_sql(model)
        except Exception as exc:
            logger.warning("Failed to build view for %s: %s", model._meta.label, exc)
            continue

        if result is None:
            continue

        view_name, sql, underlying_tables = result
        ABSTRACT_TO_TABLES[view_name] = underlying_tables
        results.append((view_name, sql))

        if not dry_run:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(sql)
                logger.debug("Created view %s", view_name)
            except Exception as exc:
                logger.warning("Failed to create view %s: %s", view_name, exc)

    return results


def drop_views():
    """Drop all nb_* views."""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT table_name FROM information_schema.views
            WHERE table_schema = 'public' AND table_name LIKE 'nb\\_%'
            ORDER BY table_name
        """)
        view_names = [row[0] for row in cursor.fetchall()]
        for name in view_names:
            cursor.execute(f"DROP VIEW IF EXISTS {name} CASCADE")
            logger.info("Dropped view %s", name)
    ABSTRACT_TO_TABLES.clear()
    return view_names
