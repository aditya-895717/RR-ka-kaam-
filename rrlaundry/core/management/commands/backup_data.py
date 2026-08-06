import shutil
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Back up the SQLite database to a timestamped file on the same disk.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dest-dir',
            default=None,
            help='Directory to write the backup. Defaults to the same directory as the DB.',
        )

    def handle(self, *args, **options):
        db_path = Path(settings.DATABASES['default']['NAME'])

        if not db_path.exists():
            raise CommandError(f'Database not found: {db_path}')

        dest_dir = Path(options['dest_dir']) if options['dest_dir'] else db_path.parent
        dest_dir.mkdir(parents=True, exist_ok=True)

        stamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        backup_path = dest_dir / f'db_backup_{stamp}.sqlite3'

        shutil.copy2(db_path, backup_path)
        self.stdout.write(self.style.SUCCESS(f'Backup written to {backup_path}'))
