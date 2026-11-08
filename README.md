# DCLD Study: data management system

Data entry, data quality and exports for *Clinical profile, disease severity and need for liver transplantation among
patients with decompensated chronic liver disease at Muhimbili National Hospital*. Django 5.2 + MySQL 8.4, run in
Docker, hosted on the Hostinger server like ncd_penplus (see [DEPLOY.md](DEPLOY.md)).

## What it does

- **Accounts**: people register with their email, confirm it through a link, then an Admin gives them a role
  (a Data Manager can approve Data Clerks and Investigators). Forgot password by email; change password on the profile.
  Roles: **Data Clerk**, **Investigator**, **Data Manager**, **Admin**. The roles page in the app shows exactly
  what each one can do. Investigators never see phone numbers.
- **CRF entry**: one page per questionnaire section (A-L). Nothing is mandatory: save what is known and come back
  when laboratory results arrive. Lab and imaging items can be ticked *Not done / not available*. Skip rules hide
  questions that do not apply and clear their answers. Impossible values are refused; results are entered in the
  unit on the lab slip (µmol/L or mg/dL, g/L or g/dL) and converted for the scores.
- **Calculated**: BMI, Child-Pugh points/score/class, MELD and MELD-Na, APRI, K1 (Child-Pugh C), K2 (MELD-Na >= 15).
- **Data quality**: completeness per participant and section (following the skip rules), *pending results* grouped
  by test (e.g. everyone still waiting for an INR), automatic range and consistency checks (e.g. encephalopathy Yes
  in Section D but No in Section H, a creatinine that looks like the wrong unit), and queries: a Data Manager raises,
  the Data Clerk answers, the Data Manager closes. A Data Manager can verify and lock a finished record.
- **Audit trail**: every change to every value, with who and when (Change history on the participant page).
- **Exports**: Excel, one row per participant with coded values, scores and quality columns; with or without phone numbers.
- **Data dictionary**: `data_dictionary/DCLD_Data_Dictionary_v<version>.xlsx`, also downloadable in the app.

## One source for the CRF

`crf/spec.py` describes every question (code, label, type, choices, units, limits, skip rule). The database tables,
forms, checks, exports and the data dictionary are all generated from it, so they cannot drift apart.
`crf/decisions.py` holds the open questions about the CRF (Decisions sheet).

**When an updated CRF or the proposal arrives**:
1. Edit `crf/spec.py` (and `crf/decisions.py`, `crf/derived.py` / `quality/checks.py` if scores or checks change).
2. Raise `VERSION` in `crf/spec.py` and add a line to `CHANGE_LOG` in `crf/dictionary.py`.
3. `python manage.py makemigrations crf` and check the migration (renaming a field: make it a rename, not drop + add,
   so no data is lost).
4. `python manage.py build_dictionary` writes the new workbook; keep the old versions in `data_dictionary/`.
5. `python manage.py test`, then deploy.

## Run on your computer

```bash
cp .env.example .env
docker compose up -d --build
docker compose exec cld-web python manage.py migrate
docker compose exec cld-web python manage.py createsuperuser      # log in with this email
```
Open http://127.0.0.1:8092. Emails (confirmation links, password resets) are written to files:
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
