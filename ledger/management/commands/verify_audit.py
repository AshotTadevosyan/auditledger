from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from ledger.models import Engagement
from ledger.reports import build_report, markdown_report, csv_bundle

class Command(BaseCommand):
    help = 'Check configured database integrity, relationships and report generation for every engagement.'

    def handle(self, *args, **options):
        if connection.vendor == 'sqlite':
            with connection.cursor() as cursor:
                cursor.execute('PRAGMA integrity_check')
                if cursor.fetchall() != [('ok',)]:
                    raise CommandError('Database integrity check failed.')
                cursor.execute('PRAGMA foreign_key_check')
                if cursor.fetchall():
                    raise CommandError('Foreign key check failed.')
        connection.check_constraints()
        # Validate scope in both engines, including imported/legacy rows.
        from importlib import import_module
        parents = import_module('ledger.migrations.0002_engagement_integrity').PARENTS
        with connection.cursor() as cursor:
            for table, relations in parents.items():
                for field, parent in relations:
                    cursor.execute(f"SELECT COUNT(*) FROM ledger_{table} child LEFT JOIN ledger_{parent} parent "
                                   f"ON child.{field}_id = parent.id AND child.engagement_id = parent.engagement_id "
                                   "WHERE parent.id IS NULL")
                    if cursor.fetchone()[0]:
                        raise CommandError(f'Scope integrity failed for {table}.{field}.')
        for e in Engagement.objects.all():
            bundle = build_report(e.pk)
            markdown_report(bundle)
            csv_bundle(bundle)
            self.stdout.write(f'{e.code}: reports generated; {bundle["readiness"]["counts"]}')
        self.stdout.write(self.style.SUCCESS(f'Relationship integrity and report generation verified for {Engagement.objects.count()} engagement(s).'))
