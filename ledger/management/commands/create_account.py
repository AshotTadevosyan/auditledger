from getpass import getpass
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = 'Create a non-administrator account with an interactively entered, validated password.'

    def add_arguments(self, parser):
        parser.add_argument('username')
        parser.add_argument('--can-create-engagements', action='store_true')

    @transaction.atomic
    def handle(self, *args, **options):
        user = get_user_model()(username=options['username'])
        password = getpass('Password: ')
        if password != getpass('Password (again): '):
            raise CommandError('Passwords do not match.')
        try:
            validate_password(password, user)
            user.set_password(password)
            user.full_clean()
            user.save()
        except ValidationError as exc:
            raise CommandError('; '.join(exc.messages)) from exc
        if options['can_create_engagements']:
            user.user_permissions.add(Permission.objects.get(content_type__app_label='ledger', codename='add_engagement'))
        self.stdout.write(self.style.SUCCESS('Account created. Assign engagement access with grant_access.'))
