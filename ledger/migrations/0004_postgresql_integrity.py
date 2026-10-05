"""Add concurrency-safe composite foreign keys without rewriting existing rows."""
from importlib import import_module
from django.db import migrations

legacy = import_module('ledger.migrations.0002_engagement_integrity')
PARENTS = legacy.PARENTS
SCOPED = legacy.SCOPED
TARGETS = sorted({parent for parents in PARENTS.values() for _, parent in parents})


def create(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute('''CREATE FUNCTION ledger_scope_immutable() RETURNS trigger AS $$
        BEGIN
            IF NEW.engagement_id IS DISTINCT FROM OLD.engagement_id THEN
                RAISE EXCEPTION 'An existing record cannot move to another engagement' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END; $$ LANGUAGE plpgsql''')
    for table in SCOPED:
        schema_editor.execute(f'''CREATE TRIGGER ledger_{table}_scope_immutable
            BEFORE UPDATE OF engagement_id ON ledger_{table}
            FOR EACH ROW EXECUTE FUNCTION ledger_scope_immutable()''')
    for table in TARGETS:
        schema_editor.execute(f'ALTER TABLE ledger_{table} ADD CONSTRAINT {table}_id_scope UNIQUE (id, engagement_id)')
    for table, parents in PARENTS.items():
        for field, parent in parents:
            schema_editor.execute(f'''ALTER TABLE ledger_{table} ADD CONSTRAINT {table}_{field}_scope_fk
                FOREIGN KEY ({field}_id, engagement_id) REFERENCES ledger_{parent} (id, engagement_id)''')


def drop(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    for table, parents in PARENTS.items():
        for field, _ in parents:
            schema_editor.execute(f'ALTER TABLE ledger_{table} DROP CONSTRAINT {table}_{field}_scope_fk')
    for table in TARGETS:
        schema_editor.execute(f'ALTER TABLE ledger_{table} DROP CONSTRAINT {table}_id_scope')
    for table in SCOPED:
        schema_editor.execute(f'DROP TRIGGER ledger_{table}_scope_immutable ON ledger_{table}')
    schema_editor.execute('DROP FUNCTION ledger_scope_immutable()')


class Migration(migrations.Migration):
    dependencies = [('ledger', '0003_engagementmembership')]
    operations = [migrations.RunPython(create, drop)]
