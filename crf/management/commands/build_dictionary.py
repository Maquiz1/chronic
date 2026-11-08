from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from crf import spec
from crf.dictionary import build_workbook, dictionary_filename, write


class Command(BaseCommand):
    help = ('Write data_dictionary/DCLD_Data_Dictionary_v<VERSION>.xlsx from crf/spec.py and crf/decisions.py. '
            '--section G writes only that section; --all-sections also writes one file per section.')

    def add_arguments(self, parser):
        parser.add_argument('--dir', default=None, help='Output folder (default: data_dictionary/).')
        parser.add_argument('--section', default=None, help='Only this section (A-L).')
        parser.add_argument('--all-sections', action='store_true', help='Also write one workbook per section.')

    def handle(self, *args, **options):
        directory = Path(options['dir'] or Path(__file__).resolve().parents[3] / 'data_dictionary')
        directory.mkdir(parents=True, exist_ok=True)
        if options['section']:
            code = options['section'].upper()
            if code not in spec.SECTION_BY_CODE:
                raise CommandError(f'Unknown section {code}.')
            codes = [code]
        else:
            self.stdout.write(self.style.SUCCESS(f'Written {write(directory)}'))
            codes = [s.code for s in spec.SECTIONS] if options['all_sections'] else []
        for code in codes:
            path = directory / dictionary_filename(code)
            build_workbook(code).save(path)
            self.stdout.write(self.style.SUCCESS(f'Written {path}'))
