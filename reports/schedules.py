# (name, celery task, kwargs, default crontab: minute, hour, day_of_month, day_of_week, description)
PROGRESS = 'reports.tasks.send_progress_report'

SCHEDULES = [
    ('Daily pending work reminder (weekdays 07:00)', 'reports.tasks.send_pending_reminders', {},
     ('0', '7', '*', '1-5'),
     'Data Clerks: their records with missing items and open queries. Data Managers: all of them, plus answered '
     'queries to close. Only sent when something is waiting.'),
    ('Weekly progress and data quality report (Monday 07:30)', PROGRESS, {'period': 'week'},
     ('30', '7', '*', '1'),
     'Last Monday-Sunday plus totals, with a PDF, to Data Managers, Investigators and Admins.'),
    # Crontab has no "last day of month": run on days 28-31 and the task sends only on the last day.
    ('Monthly progress report (last day of the month 18:00)', PROGRESS, {'period': 'month', 'month_end_only': True},
     ('0', '18', '28-31', '*'),
     'The calendar month plus totals, with a PDF, to Data Managers, Investigators and Admins.'),
    ('Delete expired exports (hourly)', 'exports.tasks.delete_expired_exports', {},
     ('15', '*', '*', '*'),
     'Removes finished exports older than EXPORT_FILE_HOURS (default 24).'),
]
DESCRIPTIONS = {name: description for name, *_rest, description in SCHEDULES}
