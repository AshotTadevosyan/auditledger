from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from ledger.backup import consistent_copy

class Command(BaseCommand):
    help = 'Back up the configured SQLite database using the consistent SQLite backup API.'

    def add_arguments(self, parser):
        parser.add_argument('destination', help='New .sqlite3 file; existing files will not be overwritten.')

    def handle(self, *args, **options):
        try:
            manifest = consistent_copy(settings.DATABASES['default']['NAME'], options['destination'], 'backup')
        except Exception as exc:
            raise CommandError(f'Backup failed: {exc}') from exc
        self.stdout.write(self.style.SUCCESS(f'Backup verified: {options["destination"]}; {manifest["counts"]["engagement"]} engagement(s). Companion manifest written.'))
