# Permissions

## Plugin access

Access to the SQL query editor is controlled by two mechanisms.

### Quick lockdown: `require_superuser`

When `require_superuser` is `True` (the default), only superusers can access the plugin. All other users get a 403 error. This is the simplest configuration for deployments where only admins need SQL access.

### ObjectPermission-based access

When `require_superuser` is `False`, access is controlled by NetBox's native ObjectPermission system.

To grant a user or group access to the query editor:

1. Go to Admin > Permissions > Add
2. Set the name (e.g., "SQL Query - Read Access")
3. Under Object Types, select `netbox_sqlquery > SQL query permission`
4. Under Actions, check **Can view**
5. Assign to the desired users or groups
6. Save

To also grant write query access (INSERT, UPDATE, DELETE), check **Can change** on the same permission (or create a separate one). "Can change" means the user can change database data via write queries.

<img src="images/permissions.png" alt="Permission setup example" width="700">

Superusers always have full access regardless of ObjectPermission assignments.

## Table access

Which database tables a user can query is determined by three layers, evaluated in order.

### Layer 1: Hard deny list

Tables listed in the `deny_tables` plugin setting are blocked for all users, including superusers. These cannot be overridden by any other mechanism.

Default deny list: `auth_user`, `users_token`, `users_userconfig`.

### Layer 2: Menu-group permissions

For non-superusers, table access is tied to NetBox's existing view permissions via a menu-group mapping. If a user has view permission on a representative model in a group, they can query all database tables associated with that group.

| NetBox permission                    | Tables granted                                                                                                                                                                                                                                                                                                   |
|--------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `dcim.view_site`                     | `dcim_region`, `dcim_sitegroup`, `dcim_site`, `dcim_location`                                                                                                                                                                                                                                                    |
| `dcim.view_rack`                     | `dcim_rack`, `dcim_rackrole`, `dcim_rackreservation`, `dcim_racktype`                                                                                                                                                                                                                                            |
| `dcim.view_device`                   | `dcim_device`, `dcim_interface`, `dcim_module*`, `dcim_cable`, `dcim_consoleport`, `dcim_powerport`, `dcim_frontport`, `dcim_rearport`, `dcim_inventoryitem*`, `dcim_macaddress`, `dcim_platform`, `dcim_devicerole`, `dcim_devicetype`, `dcim_manufacturer`, `dcim_virtualchassis`, `dcim_virtualdevicecontext` |
| `dcim.view_powerfeed`                | `dcim_powerfeed`, `dcim_powerpanel`                                                                                                                                                                                                                                                                              |
| `ipam.view_ipaddress`                | All `ipam_*` tables (prefixes, IP addresses, VLANs, VRFs, ASNs, etc.)                                                                                                                                                                                                                                            |
| `circuits.view_circuit`              | All `circuits_*` tables (circuits, providers, terminations)                                                                                                                                                                                                                                                      |
| `virtualization.view_virtualmachine` | All `virtualization_*` tables (VMs, clusters, VM interfaces)                                                                                                                                                                                                                                                     |
| `vpn.view_tunnel`                    | All `vpn_*` tables (tunnels, IPSec, IKE, L2VPN)                                                                                                                                                                                                                                                                  |
| `wireless.view_wirelesslan`          | All `wireless_*` tables (wireless LANs, links)                                                                                                                                                                                                                                                                   |

Superusers can query all tables (subject to the hard deny list).

### Shared tables

Some tables are referenced as foreign key targets by models across multiple apps. For example, many NetBox models have an `owner` field that points to `users_owner`, and most models link to `tenancy_tenant` for tenant assignment. The abstract views (`nb_*`) JOIN to these tables automatically.

These tables are always accessible to any user with plugin access, regardless of their menu-group permissions:

| Table                   | Why it is shared                                                            |
|-------------------------|-----------------------------------------------------------------------------|
| `django_content_type`   | Used by generic foreign keys and the tagging system to identify model types |
| `extras_tag`            | Tag definitions, referenced by the tags column in abstract views            |
| `extras_taggeditem`     | Junction table linking tags to objects via content type + object ID         |
| `extras_configtemplate` | Configuration templates referenced by devices and VMs                       |
| `users_owner`           | Owner assignments, present on most NetBox models as an optional FK          |
| `users_ownergroup`      | Owner group assignments                                                     |
| `tenancy_tenant`        | Tenant assignments, one of the most common FKs across all NetBox models     |
| `tenancy_tenantgroup`   | Tenant group hierarchy                                                      |
| `tenancy_contact`       | Contact records referenced via contact assignments                          |
| `tenancy_contactgroup`  | Contact group hierarchy                                                     |
| `tenancy_contactrole`   | Contact role definitions                                                    |

Without shared table access, queries against abstract views would fail because the views JOIN to these tables for foreign key resolution. The shared tables contain organizational metadata (tenants, owners, tags), not sensitive operational data.

### Layer 3: TablePermission overrides

The `TablePermission` model allows explicit per-table allow or deny rules that supplement the menu-group mapping. These are optional and can be managed through the NetBox admin interface. An explicit deny in a `TablePermission` record removes a table from the user's allowed set even if it was granted by a menu-group permission.

## Abstract views and table access

When a user queries an abstract view (e.g., `nb_prefixes`), the plugin expands the view name to all underlying tables it references (the main table plus all JOIN targets). The user must have access to all of those tables. In practice, this means:

- The main table must be in an allowed menu group (e.g., `ipam_prefix` requires `ipam.view_ipaddress`)
- Join targets are either in the same group or in the shared tables list

If any underlying table is denied, the query is blocked with an "Access denied" error listing the specific tables.

## Schema sidebar filtering

The schema hints sidebar only shows tables the user has permission to query. Users cannot see that a table exists if they do not have access to it. This applies to both the Raw SQL and Views modes.

## Write queries

INSERT, UPDATE, and DELETE queries require either superuser status or the **Can change** action on `SQL query permission`. A confirmation dialog is shown before executing write queries. Users can opt to skip the confirmation in their preferences (User Preferences > SQL Query: Skip write confirmation).

## OIDC and external identity providers

The plugin reads `request.user`, which is a standard Django user regardless of authentication backend. If you use an OIDC provider like Okta, group claims must be mapped to Django groups in your social-auth pipeline at login time. Once groups are mapped, ObjectPermission rules assigned to those groups work without any plugin changes.
