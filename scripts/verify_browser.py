#!/usr/bin/env python3
"""Optional Chromium regression checks; install playwright separately.

Runs only on a temporary fictional DB. Uses installed Chrome; no browser download.
AUDIT_BROWSER_OUTPUT optionally retains screenshots and the print PDF.
"""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def serve():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()
    from django.core.management import call_command
    from django.core.wsgi import get_wsgi_application
    from django.contrib.staticfiles.handlers import StaticFilesHandler
    from django.db import DatabaseError
    from wsgiref.simple_server import make_server
    from ledger.demo import seed_demo
    from ledger import services
    call_command('migrate', verbosity=0)
    engagement, _ = seed_demo()
    original_save = services.save_record
    def failing_save(kind, data, actor, *args, **kwargs):
        if actor == 'Simulated disk failure':
            raise DatabaseError('Test-only injected failure')
        return original_save(kind, data, actor, *args, **kwargs)
    services.save_record = failing_save
    with make_server('127.0.0.1', int(sys.argv[2]), StaticFilesHandler(get_wsgi_application())) as server:
        server.serve_forever()


def main():
    from playwright.sync_api import sync_playwright, TimeoutError as BrowserTimeout
    with tempfile.TemporaryDirectory(prefix='audit-browser-') as temporary:
        tmp = Path(temporary)
        output = Path(os.environ.get('AUDIT_BROWSER_OUTPUT', temporary))
        output.mkdir(parents=True, exist_ok=True)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        base = f'http://127.0.0.1:{port}'
        env = os.environ | {'AUDIT_DB_PATH': str(tmp / 'fictional.sqlite3')}
        with (tmp / 'server.log').open('w') as log:
            server = subprocess.Popen([sys.executable, __file__, '--serve', str(port)], cwd=ROOT, env=env, stdout=log, stderr=log)
            try:
                for _ in range(100):
                    try:
                        urlopen(base, timeout=1)
                        break
                    except OSError:
                        time.sleep(.1)
                else:
                    raise AssertionError('Browser fixture server failed: ' + (tmp / 'server.log').read_text())
                # Derive actual routes from the rendered app, not assumed route shapes.
                with sync_playwright() as p:
                    browser = p.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless=True)
                    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                    page.set_default_timeout(8000)
                    page.goto(base)
                    page.get_by_role('link', name='DEMO-2026', exact=False).first.click()
                    engagement_url = page.url
                    page.get_by_role('link', name='Findings', exact=True).click()
                    page.get_by_role('link', name='Add finding', exact=False).click()
                    create_url = page.url
                    report_url = page.get_by_role('link', name='Report', exact=True).get_attribute('href')
                    dialogs = []
                    def dismiss(dialog):
                        dialogs.append(dialog.type)
                        dialog.dismiss()
                    page.on('dialog', dismiss)
                    page.get_by_role('link', name='Report', exact=True).click()
                    assert not dialogs, 'Untouched form warned'
                    page.goto(create_url)
                    page.get_by_label('Condition', exact=False).fill('Browser retained narrative')
                    page.get_by_role('button', name='Save finding').click()
                    assert page.get_by_role('alert').is_visible()
                    assert page.get_by_role('alert').evaluate('(el) => el === document.activeElement')
                    page.set_viewport_size({'width': 390, 'height': 844})
                    page.screenshot(path=str(output / 'rejected-form-narrow.png'))
                    page.set_viewport_size({'width': 1440, 'height': 1000})
                    assert page.get_by_label('Condition', exact=False).input_value() == 'Browser retained narrative'
                    rejected_url = page.url
                    page.get_by_role('link', name='Report', exact=True).click()
                    assert dialogs == ['confirm'] and page.url == rejected_url
                    try:
                        page.reload(timeout=1000)
                    except BrowserTimeout:
                        pass  # Dismissing beforeunload intentionally cancels navigation.
                    assert 'beforeunload' in dialogs, 'Reload failed to warn'
                    page.locator('[name="title"]').fill('Browser draft')
                    page.get_by_label('Your name / actor label').fill('Simulated disk failure')
                    page.get_by_role('button', name='Save finding').click()
                    assert 'database could not save' in page.get_by_role('alert').inner_text()
                    before = len(dialogs)
                    page.get_by_role('link', name='Report', exact=True).click()
                    assert len(dialogs) == before + 1 and page.url == rejected_url
                    page.get_by_label('Your name / actor label').fill('Browser auditor')
                    page.get_by_role('button', name='Save finding').click()
                    assert 'saved=1' in page.url
                    before = len(dialogs)
                    page.get_by_role('link', name='Report', exact=True).click()
                    assert len(dialogs) == before
                    # Stale edit: a second real browser tab updates the same record.
                    page.goto(engagement_url)
                    page.get_by_role('link', name='Findings', exact=True).click()
                    page.get_by_role('link', name='Browser draft', exact=False).click()
                    page.get_by_role('link', name='Edit finding', exact=True).click()
                    edit_url = page.url
                    other = browser.new_page()
                    other.goto(edit_url)
                    other.locator('[name="title"]').fill('Updated in second tab')
                    other.get_by_role('button', name='Save finding').click()
                    page.get_by_label('Condition', exact=False).fill('Retained stale narrative')
                    page.get_by_role('button', name='Save finding').click()
                    assert 'another tab' in page.get_by_role('alert').inner_text()
                    before = len(dialogs)
                    page.get_by_role('link', name='Report', exact=True).click()
                    assert len(dialogs) == before + 1
                    # Explicit discard permits leaving; successful persistence did above.
                    page.remove_listener('dialog', dismiss)
                    page.once('dialog', lambda d: d.accept())
                    page.get_by_role('link', name='Report', exact=True).click()
                    assert page.url.endswith(report_url)
                    # Source snapshot conflict, custom reconciliation, contextual finding.
                    page.goto(engagement_url)
                    page.get_by_role('link', name='Controls & tests', exact=True).click()
                    page.locator('a.record-link').first.click()
                    control_url = page.url
                    page.get_by_role('link', name='Add test', exact=False).click()
                    original = page.get_by_label('Procedure snapshot', exact=False).input_value()
                    other.goto(control_url)
                    other.get_by_role('link', name='Edit control', exact=True).click()
                    other.get_by_label('Testing procedure', exact=False).fill('Changed in browser second tab')
                    other.get_by_role('button', name='Save control').click()
                    page.get_by_role('button', name='Save test').click()
                    assert 'source control' in page.get_by_role('alert').inner_text()
                    assert page.get_by_label('Procedure snapshot', exact=False).input_value() == original
                    page.get_by_label('Procedure snapshot', exact=False).fill('Customized after explicit comparison')
                    page.get_by_label('I compared the selected').check()
                    page.get_by_role('button', name='Save test').click()
                    assert 'saved=1' in page.url
                    page.get_by_role('link', name='Raise finding', exact=True).click()
                    assert page.locator('input[name="controls"]:checked').count() == 1
                    assert page.locator('input[name="tests"]:checked').count() == 1
                    # Long narrative/reference print fixture, written through the UI.
                    page.goto(engagement_url)
                    page.get_by_role('link', name='Edit engagement', exact=True).click()
                    long_text = '\n\n'.join(f'Paragraph {i:02d}. Fictional audit narrative for print verification. ' + 'Reviewable supporting detail. ' * 12 for i in range(45)) + '\nFINAL-NARRATIVE-MARKER'
                    page.get_by_label('Executive summary', exact=False).fill(long_text)
                    page.get_by_role('button', name='Save engagement').click()
                    page.get_by_role('link', name='Evidence', exact=True).click()
                    page.get_by_role('link', name='Add evidence reference', exact=False).click()
                    page.locator('[name="title"]').fill('Long fictional source')
                    page.locator('[name="description"]').fill('Long reference for print inspection')
                    page.locator('[name="type"]').select_option('document_path')
                    page.locator('[name="source"]').fill('/fictional/' + 'long-segment/' * 145 + 'FINAL-SOURCE-MARKER')
                    page.get_by_label('Collection date', exact=False).fill(__import__('datetime').date.today().isoformat())
                    page.locator('[name="owner"]').fill('Browser auditor')
                    page.get_by_role('button', name='Save evidence reference').click()
                    assert 'saved=1' in page.url
                    page.goto(base + report_url)
                    assert page.get_by_role('heading', name='Control–test–result–finding traceability').is_visible()
                    page.screenshot(path=str(output / 'report-desktop.png'), full_page=True)
                    page.set_viewport_size({'width': 390, 'height': 844})
                    page.screenshot(path=str(output / 'report-narrow.png'), full_page=True)
                    page.set_viewport_size({'width': 1100, 'height': 900})
                    page.emulate_media(media='print')
                    page.pdf(path=str(output / 'report-print.pdf'), format='A4', print_background=True)
                    browser.close()
                    try:
                        import pymupdf
                    except ImportError:
                        print('Print extraction not checked: install pymupdf to enable it.')
                    else:
                        document = pymupdf.open(output / 'report-print.pdf')
                        text = ''.join(''.join(page.get_text() for page in document).split())
                        assert 'FINAL-NARRATIVE-MARKER' in text
                        assert '/fictional/' + 'long-segment/' * 145 + 'FINAL-SOURCE-MARKER' in text
                        for i, printed in enumerate(document):
                            for word in printed.get_text('words'):
                                assert word[0] >= 0 and word[1] >= 0 and word[2] <= printed.rect.width + .5 and word[3] <= printed.rect.height + .5, (i + 1, word)
                            printed.get_pixmap().save(str(output / f'print-{i+1:02d}.png'))
                        print(f'PRINT PASS: {len(document)} A4 pages, complete narrative/source markers, no out-of-page text; rendered pages available for visual inspection.')
                    print('BROWSER PASS: untouched/successful forms, validation/database/conflict retention, navigation/reload warning, explicit discard, stale procedure reconciliation, contextual finding, desktop/narrow/print capture.')
                    print('Artifacts:', output)
            finally:
                server.terminate()
                server.wait(timeout=10)


if __name__ == '__main__':
    serve() if '--serve' in sys.argv else main()
