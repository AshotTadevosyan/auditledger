from django.db import migrations

# SQLite FK constraints establish existence. These triggers additionally enforce
# engagement equality on INSERT and UPDATE, including direct SQL writes.
SCOPED = ['control', 'test', 'evidence', 'finding', 'action', 'progressupdate', 'activityevent',
          'testevidence', 'findingcontrol', 'findingtest', 'findingevidence',
          'findingclosureevidence', 'actionevidence', 'actionclosureevidence']
PARENTS = {
    'test': [('control', 'control')], 'action': [('finding', 'finding')],
    'progressupdate': [('action', 'action')],
    'testevidence': [('test', 'test'), ('evidence', 'evidence')],
    'findingcontrol': [('finding', 'finding'), ('control', 'control')],
    'findingtest': [('finding', 'finding'), ('test', 'test')],
    'findingevidence': [('finding', 'finding'), ('evidence', 'evidence')],
    'findingclosureevidence': [('finding', 'finding'), ('evidence', 'evidence')],
    'actionevidence': [('action', 'action'), ('evidence', 'evidence')],
    'actionclosureevidence': [('action', 'action'), ('evidence', 'evidence')],
}


def create(apps, schema_editor):
    for table in SCOPED:
        schema_editor.execute(f'''CREATE TRIGGER ledger_{table}_scope_immutable
            BEFORE UPDATE OF engagement_id ON ledger_{table}
            WHEN NEW.engagement_id != OLD.engagement_id
            BEGIN SELECT RAISE(ABORT, 'An existing record cannot move to another engagement'); END''')
    for table, parents in PARENTS.items():
        condition = ' OR '.join(f'NOT EXISTS (SELECT 1 FROM ledger_{parent} WHERE id = NEW.{field}_id AND engagement_id = NEW.engagement_id)' for field, parent in parents)
        for operation in ('INSERT', 'UPDATE'):
            schema_editor.execute(f'''CREATE TRIGGER ledger_{table}_scope_{operation.lower()}
                BEFORE {operation} ON ledger_{table} WHEN {condition}
                BEGIN SELECT RAISE(ABORT, 'Cross-engagement relationship is forbidden'); END''')


def drop(apps, schema_editor):
    for table in SCOPED:
        schema_editor.execute(f'DROP TRIGGER IF EXISTS ledger_{table}_scope_immutable')
    for table in PARENTS:
        for operation in ('insert', 'update'):
            schema_editor.execute(f'DROP TRIGGER IF EXISTS ledger_{table}_scope_{operation}')


class Migration(migrations.Migration):
    dependencies = [('ledger', '0001_initial')]
    operations = [migrations.RunPython(create, drop)]
