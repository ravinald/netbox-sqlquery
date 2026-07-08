# Local-dev image: NetBox + this plugin installed editable, so a runtime bind
# mount of the working tree makes template and Python edits live (with DEBUG on).
ARG NETBOX_IMAGE=netboxcommunity/netbox:v4.5.10
FROM ${NETBOX_IMAGE}

# Minimal metadata for the editable install; the full package is bind-mounted at runtime.
COPY pyproject.toml README.md /opt/netbox-sqlquery/
COPY netbox_sqlquery /opt/netbox-sqlquery/netbox_sqlquery
RUN /usr/local/bin/uv pip install -e /opt/netbox-sqlquery

# Register the plugin at build so collectstatic can find its editor JS/CSS.
COPY dev/plugins.py /etc/netbox/config/plugins.py
RUN DEBUG="true" SECRET_KEY="collectstatic-build-key-not-for-production-0123456789" \
    /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py collectstatic --no-input
