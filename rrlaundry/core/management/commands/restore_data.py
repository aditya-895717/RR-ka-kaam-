import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Restore the SQLite database from a backup file produced by backup_data.'

    def add_arguments(self, parser):
        parser.add_argument('backup_file', help='Path to the .sqlite3 backup file to restore.')
        parser.add_argument(
            '--no-confirm',
            action='store_true',
            help='Skip the confirmation prompt (for scripted use).',
        )

    def handle(self, *args, **options):
        backup_path = Path(options['backup_file'])
        if not backup_path.exists():
            raise CommandError(f'Backup file not found: {backup_path}')

        db_path = Path(settings.DATABASES['default']['NAME'])

        if not options['no_confirm']:
            self.stdout.write(
                self.style.WARNING(
                    f'This will OVERWRITE {db_path} with {backup_path}.\n'
                    'All data written after the backup was taken will be lost.'
                )
            )
            confirm = input('Type YES to continue: ')
            if confirm.strip() != 'YES':
                self.stdout.write('Aborted.')
                return

        shutil.copy2(backup_path, db_path)
        self.stdout.write(self.style.SUCCESS(f'Restored {db_path} from {backup_path}'))
