from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from ledger.models import Engagement
from ledger.reports import build_report, markdown_report, csv_bundle

class Command(BaseCommand):
    help = 'Check configured database integrity, relationships and report generation for every engagement.'

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            cursor.execute('PRAGMA integrity_check')
            if cursor.fetchall() != [('ok',)]:
                raise CommandError('Database integrity check failed.')
            cursor.execute('PRAGMA foreign_key_check')
            if cursor.fetchall():
                raise CommandError('Foreign key check failed.')
        for e in Engagement.objects.all():
            bundle = build_report(e.pk)
            markdown_report(bundle)
            csv_bundle(bundle)
            self.stdout.write(f'{e.code}: reports generated; {bundle["readiness"]["counts"]}')
        self.stdout.write(self.style.SUCCESS(f'Integrity, foreign keys and report generation verified for {Engagement.objects.count()} engagement(s).'))
