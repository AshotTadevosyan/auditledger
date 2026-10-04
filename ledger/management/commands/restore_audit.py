from django.core.management.base import BaseCommand, CommandError
from ledger.backup import consistent_copy

class Command(BaseCommand):
    help = 'Verify and restore a backup into a NEW independent database path. Stop the app before switching paths.'

    def add_arguments(self, parser):
        parser.add_argument('source')
        parser.add_argument('destination')

    def handle(self, *args, **options):
        try:
            manifest = consistent_copy(options['source'], options['destination'], 'restore')
        except Exception as exc:
            raise CommandError(f'Restore failed: {exc}') from exc
        self.stdout.write(self.style.SUCCESS(f'Restore integrity and foreign keys verified: {options["destination"]}; {manifest["counts"]["engagement"]} engagement(s). Set AUDIT_DB_PATH to this path, run migrate, then verify_audit and inspect reports before switching.'))
