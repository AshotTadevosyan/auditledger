from django.core.management.base import BaseCommand
from ledger.demo import seed_demo

class Command(BaseCommand):
    help = 'Explicitly create repeat-safe fictional DEMO-2026 data; never runs at startup.'

    def handle(self, *args, **options):
        engagement, created = seed_demo()
        self.stdout.write(f'{engagement.code}: {"created fictional demonstration" if created else "already exists; no changes made"}.')
