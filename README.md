# MNH Liver Study (DCLD): data management system

Data entry, data quality and exports for *Clinical profile, disease severity and need for liver transplantation among
patients with decompensated chronic liver disease at Muhimbili National Hospital*. Django 5.2 + MySQL 8.4, run in
Docker, hosted on the Hostinger server like ncd_penplus (see [DEPLOY.md](DEPLOY.md)).

## What it does

- **Accounts**: people can register themselves with their email (confirmation link, then approval), or an Admin /
  Data Manager creates the account and the person gets a link to choose a password. Forgot password by email; change
  password on the profile. A person can hold **several roles**: Data Clerk and Research Scientist (enter and update
  records; Research Scientists also export de-identified data), Investigator (view only), Data Manager, Admin.
  A Data Manager can give Data Clerk, Research Scientist and Investigator; an Admin can also
  give Data Manager; only a superuser can create Admins. Investigators never see MRNs or phone numbers. Admins can deactivate and reactivate accounts; a
  deactivated person is signed out at once. Position is a drop-down title, for display only.
- **CRF entry**: one page per questionnaire section (A-L). Nothing is mandatory: save what is known and come back
  when laboratory results arrive. Lab and imaging items can be ticked *Not done / not available*. Skip rules hide
  questions that do not apply and clear their answers. Impossible values are refused; results are entered in the
  unit on the lab slip (µmol/L or mg/dL, g/L or g/dL) and converted for the scores.
- **Calculated**: BMI, Child-Pugh points/score/class, MELD and MELD-Na, APRI, HCC within Milan criteria, Child-Pugh C,
  MELD-Na >= 15 and a proposed "transplant indicated" outcome (D37).
- **Reports**: study progress (cards, weekly recruitment, completeness by section, Child-Pugh and MELD-Na charts, a
  section table) and progress per participant (completeness bar, sections, missing items, checks, queries, scores),
  filtered by interview date, with a PDF download. Missing items are shown in red everywhere.
- **Data quality**: completeness per participant and section (following the skip rules), *pending results* grouped
  by test (e.g. everyone still waiting for an INR), automatic range and consistency checks (e.g. encephalopathy Yes
  in Section D but No in Section H, a creatinine that looks like the wrong unit), and queries: a Data Manager raises,
  the Data Clerk answers, the Data Manager closes. A Data Manager can verify and lock a finished record.
- **Audit trail**: every change to every value, with who and when (Change history on the participant page).
- **Exports** (like herbal): one row per section with its record count, plus "all sections" (one sheet per section)
  and "all sections combined" (one sheet). **Labels** (readable answers) or **Codes** (numbers, for Stata/R/SPSS),
  **CSV** or **Excel**. They run in the background with a progress bar, are kept 24 hours, and only the person who
  made one can download it. Hospital IDs and phone numbers only for Data Managers and Admins, when ticked.
- **Codebook / data dictionary** per section or for all sections: Excel (full dictionary) or PDF (codebook).
  `data_dictionary/DCLD_Data_Dictionary_v<version>.xlsx` is built with `build_dictionary` (`--section G`,
  `--all-sections`).
- **Scheduled tasks** (Celery beat, editable in Django admin; listed under *Scheduled tasks* for Admins, with
  *Run now* and a log of sent emails):
  - daily pending-work reminder (weekdays 07:00): Data Clerks get their own records with missing items and open
    queries; Data Managers get all of them plus answered queries to close. Nothing is sent when nothing is waiting.
  - weekly progress and data quality report (Monday 07:30) and monthly report (last day of the month), with a PDF,
    to Data Managers, Investigators and Admins.
  - hourly deletion of expired exports.

## One source for the CRF

`crf/spec.py` describes every question (code, label, type, choices, units, limits, skip rule). The database tables,
forms, checks, exports and the data dictionary are all generated from it, so they cannot drift apart.
`crf/decisions.py` holds the open questions about the CRF (Decisions sheet).

**When an updated CRF or the proposal arrives**:
1. Edit `crf/spec.py` (and `crf/decisions.py`, `crf/derived.py` / `quality/checks.py` if scores or checks change).
2. Raise `VERSION` in `crf/spec.py` and add a line to `CHANGE_LOG` in `crf/dictionary.py`.
3. `python manage.py makemigrations crf` and check the migration (renaming a field: make it a rename, not drop + add,
   so no data is lost).
4. `python manage.py build_dictionary` writes the new workbook into `data_dictionary/` (not in git). Keep the old
   versions there. On the server, copy the files to `/opt/chronic/data_dictionary/`: every earlier version found there
   stays downloadable in the app (Exports & dictionary → earlier versions).
5. `python manage.py test`, then deploy.

## Run on your computer

```bash
cp .env.example .env
docker compose up -d --build
docker compose exec cld-web python manage.py migrate
docker compose exec cld-web python manage.py createsuperuser      # log in with this email
```
Open http://127.0.0.1:8093. Emails (confirmation links, password resets) are written to files:
`docker compose exec cld-web sh -c 'cat sent_emails/*'`.

Without Docker (quick tests on SQLite):
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
DB_ENGINE=sqlite DJANGO_DEBUG=true .venv/bin/python manage.py test
```

## Layout

| Folder | Contents |
|---|---|
| `accounts/` | User (email login), roles, registration, email confirmation, approval, profile |
| `crf/` | `spec.py` (the CRF), generated models and forms, scores (`derived.py`), exports, data dictionary builder |
| `quality/` | Completeness and checks (`checks.py`), queries, data quality pages |
| `data_dictionary/` | Generated dictionary workbooks, one per version (not in git; also downloadable from Exports in the app) |
| `documentations/` | Questionnaire and lab sheets (not in git: they contain patient details) |
