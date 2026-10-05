from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from ledger.models import Engagement, EngagementMembership


class Command(BaseCommand):
    help = 'Grant or revoke one existing account’s access to an engagement (administrator shell only).'

    def add_arguments(self, parser):
        parser.add_argument('username')
        parser.add_argument('engagement_code')
        parser.add_argument('role', choices=['viewer', 'editor', 'revoke'])

    def handle(self, *args, **options):
        try:
            user = get_user_model().objects.get(username=options['username'])
            engagement = Engagement.objects.get(code=options['engagement_code'])
        except (get_user_model().DoesNotExist, Engagement.DoesNotExist) as exc:
            raise CommandError('Account or engagement does not exist.') from exc
        if options['role'] == 'revoke':
            EngagementMembership.objects.filter(user=user, engagement=engagement).delete()
        else:
            EngagementMembership.objects.update_or_create(user=user, engagement=engagement,
                                                         defaults={'role': options['role']})
        self.stdout.write(self.style.SUCCESS('Engagement access updated.'))
