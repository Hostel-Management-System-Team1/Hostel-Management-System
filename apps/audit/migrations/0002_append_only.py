from django.db import migrations

# The database itself refuses to change or remove an audit entry, whatever code asks.
CREATE = """
CREATE FUNCTION audit_entry_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_auditentry is append-only: % is not allowed', TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_entry_append_only
BEFORE UPDATE OR DELETE ON audit_auditentry
FOR EACH ROW EXECUTE FUNCTION audit_entry_append_only();
"""

DROP = """
DROP TRIGGER IF EXISTS audit_entry_append_only ON audit_auditentry;
DROP FUNCTION IF EXISTS audit_entry_append_only();
"""


class Migration(migrations.Migration):
    dependencies = [("audit", "0001_initial")]
    operations = [migrations.RunSQL(CREATE, DROP)]
