import re

from netbox.plugins import get_plugin_config

from .models import TablePermission

ALL_TABLES = object()

# Menu-group-based table access: each entry maps a NetBox permission to
# a set of table prefixes the user can query if they hold that permission.
MENU_GROUP_TABLE_MAP = {
    "dcim.view_site": {
        "dcim_region",
        "dcim_sitegroup",
        "dcim_site",
        "dcim_location",
        "tenancy_tenant",
        "tenancy_tenantgroup",
        "tenancy_contact",
        "tenancy_contactgroup",
        "tenancy_contactrole",
        "tenancy_contactassignment",
    },
    "dcim.view_rack": {
        "dcim_rack",
        "dcim_rackrole",
        "dcim_rackreservation",
        "dcim_racktype",
    },
    "dcim.view_device": {
        "dcim_device",
        "dcim_devicebay",
        "dcim_devicerole",
        "dcim_devicetype",
        "dcim_module",
        "dcim_modulebay",
        "dcim_moduletype",
        "dcim_moduletypeprofile",
        "dcim_manufacturer",
        "dcim_platform",
        "dcim_interface",
        "dcim_frontport",
        "dcim_rearport",
        "dcim_consoleport",
        "dcim_consoleserverport",
        "dcim_powerport",
        "dcim_poweroutlet",
        "dcim_inventoryitem",
        "dcim_inventoryitemrole",
        "dcim_virtualchassis",
        "dcim_virtualdevicecontext",
        "dcim_macaddress",
        "dcim_cable",
    },
    "dcim.view_powerfeed": {
        "dcim_powerfeed",
        "dcim_powerpanel",
    },
    "ipam.view_ipaddress": {
        "ipam_aggregate",
        "ipam_asn",
        "ipam_asnrange",
        "ipam_fhrpgroup",
        "ipam_fhrpgroupassignment",
        "ipam_ipaddress",
        "ipam_iprange",
        "ipam_prefix",
        "ipam_rir",
        "ipam_role",
        "ipam_routetarget",
        "ipam_service",
        "ipam_servicetemplate",
        "ipam_vlan",
        "ipam_vlangroup",
        "ipam_vlantranslationpolicy",
        "ipam_vlantranslationrule",
        "ipam_vrf",
    },
    "circuits.view_circuit": {
        "circuits_circuit",
        "circuits_circuitgroup",
        "circuits_circuitgroupassignment",
        "circuits_circuittermination",
        "circuits_circuittype",
        "circuits_provider",
        "circuits_provideraccount",
        "circuits_providernetwork",
        "circuits_virtualcircuit",
        "circuits_virtualcircuittype",
        "circuits_virtualcircuittermination",
    },
    "virtualization.view_virtualmachine": {
        "virtualization_cluster",
        "virtualization_clustergroup",
        "virtualization_clustertype",
        "virtualization_virtualdisk",
        "virtualization_virtualmachine",
        "virtualization_vminterface",
    },
    "vpn.view_tunnel": {
        "vpn_ikepolicy",
        "vpn_ikeproposal",
        "vpn_ipsecpolicy",
        "vpn_ipsecprofile",
        "vpn_ipsecproposal",
        "vpn_l2vpn",
        "vpn_l2vpntermination",
        "vpn_tunnel",
        "vpn_tunnelgroup",
        "vpn_tunneltermination",
    },
    "wireless.view_wirelesslan": {
        "wireless_wirelesslan",
        "wireless_wirelesslangroup",
        "wireless_wirelesslink",
    },
}

# Shared tables always accessible to any authenticated plugin user.
# These are referenced by abstract views via JOINs for common relationships
# that span multiple apps.
SHARED_TABLES = {
    "django_content_type",
    "extras_tag",
    "extras_taggeditem",
    "extras_configtemplate",
    "users_owner",
    "users_ownergroup",
    "tenancy_tenant",
    "tenancy_tenantgroup",
    "tenancy_contact",
    "tenancy_contactgroup",
    "tenancy_contactrole",
}


def extract_tables(sql):
    """Extract table names referenced in FROM, JOIN, INTO, and UPDATE clauses.

    For abstract views (nb_* names), expands to the set of underlying tables
    so access control checks apply against the real tables.
    """
    from .abstract_schema import ABSTRACT_TO_TABLES

    pattern = r"\b(?:FROM|JOIN|INTO|UPDATE)\s+([\w_]+)"
    raw_tables = set(re.findall(pattern, sql, re.IGNORECASE))

    expanded = set()
    for t in raw_tables:
        if t in ABSTRACT_TO_TABLES:
            expanded.update(ABSTRACT_TO_TABLES[t])
        else:
            expanded.add(t)
    return expanded


def check_access(user, tables):
    """
    Returns the subset of tables the user is not permitted to query.
    An empty set means all requested tables are accessible.
    """
    denied = _hard_denies(tables)
    if denied:
        return denied
    allowed = _allowed_tables(user)
    if allowed is ALL_TABLES:
        return set()
    return tables - allowed


def _hard_denies(tables):
    deny_list = set(get_plugin_config("netbox_sqlquery", "deny_tables"))
    return tables & deny_list


def _allowed_tables(user):
    if user.is_superuser:
        return ALL_TABLES

    allowed = set(SHARED_TABLES)

    # Menu-group-based access: check NetBox permissions
    for perm, tables in MENU_GROUP_TABLE_MAP.items():
        if user.has_perm(perm):
            allowed.update(tables)

    # TablePermission overrides (explicit allow/deny per table)
    user_groups = set(user.groups.values_list("pk", flat=True))
    for perm in TablePermission.objects.all():
        if perm.require_superuser and not user.is_superuser:
            continue

        perm_groups = set(perm.groups.values_list("pk", flat=True))
        if perm_groups and not (perm_groups & user_groups):
            continue

        if perm.allow:
            allowed.add(perm.pattern)
        else:
            allowed.discard(perm.pattern)

    return allowed


def _hard_denies_set():
    return set(get_plugin_config("netbox_sqlquery", "deny_tables"))


def can_execute_write(user):
    """Check if user can run write queries (requires 'change' on QueryPermission)."""
    if user.is_superuser:
        return True
    return user.has_perm("netbox_sqlquery.change_querypermission")
