import os
import subprocess
import sys
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import DatabaseError, IntegrityError
from django.test import Client, TestCase, SimpleTestCase, override_settings
from django.urls import reverse
from ledger.demo import seed_demo
from ledger.models import Engagement, EngagementMembership, Control, Action, ActivityEvent, ProgressUpdate


@override_settings(HOSTED=True, SECURE_SSL_REDIRECT=True,
                   SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https'),
                   SESSION_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True)
class HostedAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.e, _ = seed_demo()
        cls.other = Engagement.objects.create(code='PRIVATE', title='Hidden client audit', owner='Hidden owner',
            client_or_unit='Hidden client', period_start='2026-01-01', period_end='2026-12-31')
        cls.user = get_user_model().objects.create_user('auditor', password='A-complex-test-password-765')
        cls.member = EngagementMembership.objects.create(user=cls.user, engagement=cls.e, role='viewer')

    def setUp(self):
        self.client = Client(HTTP_HOST='localhost', HTTP_X_FORWARDED_PROTO='https', REMOTE_ADDR='192.0.2.10')

    def read_urls(self, e):
        return [reverse('overview', args=[e.pk]), reverse('history', args=[e.pk]),
                reverse('report', args=[e.pk]), reverse('register', args=[e.pk, 'control']),
                reverse('export', args=[e.pk, 'md']), reverse('export', args=[e.pk, 'csv'])]

    def write_urls(self):
        c = Control.objects.filter(engagement=self.e).first()
        a = Action.objects.filter(engagement=self.e).first()
        return [reverse('edit_engagement', args=[self.e.pk]),
                reverse('engagement_transition', args=[self.e.pk, 'in_review']),
                reverse('create', args=[self.e.pk, 'control']),
                reverse('edit', args=[self.e.pk, 'control', c.pk]),
                reverse('delete', args=[self.e.pk, 'control', c.pk]),
                reverse('transition', args=[self.e.pk, 'control', c.pk, 'retire']),
                reverse('progress', args=[self.e.pk, a.pk])]

    def test_anonymous_denied_every_data_and_mutation_route(self):
        c = Control.objects.first()
        for url in ['/', reverse('create_engagement'), c.get_absolute_url()] + self.read_urls(self.e) + self.write_urls():
            for method in ('get', 'post'):
                with self.subTest(url=url, method=method):
                    response = getattr(self.client, method)(url)
                    self.assertEqual(response.status_code, 302)
                    self.assertTrue(response.url.startswith('/accounts/login/'))
                    self.assertEqual(response['Cache-Control'], 'no-store')

    def test_viewer_reads_but_cannot_write_and_other_engagement_is_hidden(self):
        self.client.force_login(self.user)
        for url in self.read_urls(self.e):
            self.assertEqual(self.client.get(url).status_code, 200)
        for url in self.read_urls(self.other):
            self.assertEqual(self.client.get(url).status_code, 404)
        for url in self.write_urls() + [reverse('create_engagement')]:
            for method in ('get', 'post'):
                self.assertEqual(getattr(self.client, method)(url).status_code, 403)
        response = self.client.get('/')
        self.assertNotContains(response, 'Hidden')
        self.assertEqual(response.context['stats']['engagements'], 1)
        self.assertNotContains(self.client.get(self.e.get_absolute_url()), 'Edit engagement')

    def test_editor_cannot_cross_scope_or_forge_actor(self):
        EngagementMembership.objects.filter(pk=self.member.pk).update(role='editor')
        self.client.force_login(self.user)
        response = self.client.post(reverse('create', args=[self.e.pk, 'control']),
                                    {'title': 'Authenticated control', 'actor': 'Impersonated'})
        self.assertEqual(response.status_code, 302)
        event = ActivityEvent.objects.get(entity_id=Control.objects.get(title='Authenticated control').pk)
        self.assertEqual(event.actor_label, f'user:{self.user.pk}:auditor')
        self.assertEqual(self.client.post(reverse('create', args=[self.other.pk, 'control']),
                                         {'title': 'Forbidden', 'actor': 'Impersonated'}).status_code, 404)
        # A child ID from another engagement is not accessible under an allowed URL.
        foreign = Control.objects.create(engagement=self.other, code='CTL-X', title='Private control')
        self.assertEqual(self.client.get(reverse('detail', args=[self.e.pk, 'control', foreign.pk])).status_code, 404)
        a = Action.objects.filter(engagement=self.e, finding__status='open').exclude(status='completed').first()
        response = self.client.post(reverse('progress', args=[self.e.pk, a.pk]),
            {'version': a.version, 'author': 'Forged', 'text': 'Signed progress'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ProgressUpdate.objects.get(text='Signed progress').author, f'user:{self.user.pk}:auditor')

    def test_creation_permission_and_membership(self):
        self.user.user_permissions.add(Permission.objects.get(codename='add_engagement', content_type__app_label='ledger'))
        self.client.force_login(self.user)
        response = self.client.post(reverse('create_engagement'), {'title': 'New private engagement',
            'client_or_unit': 'Unit', 'owner': 'Owner', 'period_start': '2026-01-01', 'period_end': '2026-12-31'})
        self.assertEqual(response.status_code, 302)
        e = Engagement.objects.get(title='New private engagement')
        self.assertEqual(e.memberships.get(user=self.user).role, 'editor')
        self.assertEqual(self.client.get(e.get_absolute_url()).status_code, 200)

    def test_creation_rolls_back_if_membership_cannot_be_saved(self):
        self.user.is_superuser = True
        self.user.save()
        self.client.force_login(self.user)
        with patch('ledger.views.EngagementMembership.objects.create', side_effect=IntegrityError('grant failed')):
            response = self.client.post(reverse('create_engagement'), {'title': 'Must roll back',
                'client_or_unit': 'Unit', 'owner': 'Owner', 'period_start': '2026-01-01', 'period_end': '2026-12-31'})
        self.assertEqual(response.status_code, 422)
        self.assertFalse(Engagement.objects.filter(title='Must roll back').exists())

    def test_revocation_and_inactive_user(self):
        self.client.force_login(self.user)
        self.member.delete()
        self.assertEqual(self.client.get(self.e.get_absolute_url()).status_code, 404)
        self.user.is_active = False
        self.user.save()
        self.assertEqual(self.client.get('/').status_code, 302)

    def test_superuser_can_access_existing_engagements(self):
        self.user.is_superuser = True
        self.user.save()
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.other.get_absolute_url()).status_code, 200)

    def test_login_logout_csrf_safe_redirect_and_cookies(self):
        client = Client(enforce_csrf_checks=True, HTTP_HOST='localhost', HTTP_X_FORWARDED_PROTO='https', HTTP_ORIGIN='https://localhost')
        self.assertEqual(client.post('/accounts/login/', {}).status_code, 403)
        client.get('/accounts/login/')
        token = client.cookies['csrftoken'].value
        response = client.post('/accounts/login/', {'username': 'auditor', 'password': 'A-complex-test-password-765',
            'next': 'https://evil.example/', 'csrfmiddlewaretoken': token})
        self.assertEqual(response.url, '/')
        self.assertTrue(response.cookies['sessionid']['secure'])
        self.assertTrue(response.cookies['sessionid']['httponly'])
        self.assertEqual(client.post(reverse('create', args=[self.e.pk, 'control']), {}).status_code, 403)
        self.assertEqual(client.get('/accounts/logout/').status_code, 405)
        token = client.cookies['csrftoken'].value
        self.assertEqual(client.post('/accounts/logout/', {'csrfmiddlewaretoken': token}).status_code, 302)
        self.assertEqual(client.get('/').status_code, 302)

    def test_https_health_and_host_validation(self):
        self.assertEqual(self.client.get('/', HTTP_X_FORWARDED_PROTO='http').status_code, 301)
        self.assertEqual(self.client.get('/accounts/login/').status_code, 200)
        response = self.client.get('/healthz/', HTTP_X_FORWARDED_PROTO='http')
        self.assertEqual(response.json(), {'status': 'ok'})
        self.assertEqual(self.client.get('/healthz/', HTTP_HOST='evil.example').status_code, 400)
        with patch('ledger.auth_views.connection.cursor', side_effect=DatabaseError('secret credentials')):
            response = self.client.get('/healthz/')
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(b'secret', response.content)


class ConfigurationTests(SimpleTestCase):
    def test_hosted_configuration_fails_closed(self):
        base = {k: v for k, v in os.environ.items() if not k.startswith(('AUDIT_', 'RENDER', 'DATABASE_URL'))}
        cases = [({'AUDIT_MODE': 'hosted'}, 'AUDIT_SECRET_KEY'),
                 ({'AUDIT_MODE': 'hosted', 'AUDIT_SECRET_KEY': 'x' * 64}, 'DATABASE_URL'),
                 ({'RENDER': 'true', 'AUDIT_MODE': 'local'}, 'Render requires hosted mode'),
                 ({'AUDIT_MODE': 'typo'}, 'AUDIT_MODE must')]
        for extra, message in cases:
            result = subprocess.run([sys.executable, '-c', 'import config.settings'], env={**base, **extra}, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(message, result.stderr)

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from django.db import connection, connections
from django.test import TransactionTestCase
from ledger import services


@skipUnless(connection.vendor == 'postgresql', 'PostgreSQL concurrency semantics')
class ConcurrentWriteTests(TransactionTestCase):
    def setUp(self):
        self.e = Engagement.objects.create(code='CONCURRENT', title='Concurrent audit', owner='Owner',
            client_or_unit='Unit', period_start='2026-01-01', period_end='2026-12-31')

    def run_together(self, operation):
        barrier = Barrier(2)
        def worker(index):
            connections.close_all()
            try:
                barrier.wait(timeout=10)
                return operation(index)
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(worker, range(2)))

    def test_concurrent_creation_allocates_distinct_codes(self):
        codes = self.run_together(lambda i: services.save_record('control', {'title': f'Control {i}'},
            'test', self.e.pk).code)
        self.assertEqual(len(set(codes)), 2)
        self.assertEqual(ActivityEvent.objects.count(), 2)

    def test_concurrent_edits_detect_stale_version(self):
        control = services.save_record('control', {'title': 'Initial'}, 'test', self.e.pk)
        def edit(index):
            try:
                services.save_record('control', {'title': f'Edit {index}'}, 'test', self.e.pk,
                                     control.pk, control.version)
                return 'saved'
            except services.Conflict:
                return 'conflict'
        self.assertCountEqual(self.run_together(edit), ['saved', 'conflict'])
        control.refresh_from_db()
        self.assertEqual(control.version, 2)
        self.assertEqual(ActivityEvent.objects.count(), 2)
