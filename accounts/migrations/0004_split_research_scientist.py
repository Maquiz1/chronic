from django.db import migrations


def split(apps, schema_editor):
    """The combined "Research Scientist / Investigator" group becomes "Investigator" (same view-only rights);
    "Research Scientist" is a new group that may also enter data."""
    Group = apps.get_model('auth', 'Group')
    old = Group.objects.filter(name='Research Scientist / Investigator').first()
    if old and not Group.objects.filter(name='Investigator').exists():
        old.name = 'Investigator'
        old.save(update_fields=['name'])
    Group.objects.get_or_create(name='Investigator')
    Group.objects.get_or_create(name='Research Scientist')


def unsplit(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.filter(name='Investigator').update(name='Research Scientist / Investigator')


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_deactivation_position'),
    ]

    operations = [migrations.RunPython(split, unsplit)]
