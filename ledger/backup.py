import json
import os
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from django.conf import settings


def consistent_copy(source, destination, operation):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not source.is_file():
        raise ValueError('Source database does not exist.')
    if source == destination or destination.exists() or destination.with_suffix(destination.suffix + '.manifest.json').exists():
        raise ValueError('Choose a new destination. Existing databases and backups are never overwritten.')
    destination.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    src = sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)
    try:
        if src.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError('Source database failed its integrity check.')
        if src.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('Source database has foreign-key violations.')
        # Create exclusively to protect current data, even if a second process races.
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
        dst = sqlite3.connect(destination)
        try:
            src.backup(dst)
            migrations = dst.execute('SELECT app, name FROM django_migrations ORDER BY app, name').fetchall()
            if dst.execute('PRAGMA integrity_check').fetchall() != [('ok',)] or dst.execute('PRAGMA foreign_key_check').fetchall():
                raise ValueError('Copied database failed integrity verification; do not switch to it.')
            counts = {table: dst.execute(f'SELECT count(*) FROM ledger_{table}').fetchone()[0]
                      for table in ['engagement', 'control', 'test', 'evidence', 'finding', 'action', 'progressupdate', 'activityevent']}
        finally:
            dst.close()
    finally:
        src.close()
    manifest = {'operation': operation, 'app_version': settings.APP_VERSION, 'timestamp_utc': datetime.now(timezone.utc).isoformat(),
                'migrations': migrations, 'counts': counts, 'integrity_check': 'ok', 'foreign_key_check': 'ok'}
    with destination.with_suffix(destination.suffix + '.manifest.json').open('x') as stream:
        json.dump(manifest, stream, indent=2)
    return manifest
