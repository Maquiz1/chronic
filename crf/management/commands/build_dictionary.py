from django.core.management.base import BaseCommand

from crf.dictionary import write


class Command(BaseCommand):
    help = 'Write data_dictionary/DCLD_Data_Dictionary_v<VERSION>.xlsx from crf/spec.py and crf/decisions.py.'

    def add_arguments(self, parser):
        parser.add_argument('--dir', default=None, help='Output folder (default: data_dictionary/).')

    def handle(self, *args, **options):
        path = write(options['dir'])
        self.stdout.write(self.style.SUCCESS(f'Written {path}'))
