# Castle Chiropractic prospect pipeline

Builds the **Castle Outreach List** workbook from the outreach CSV exports. It:

1. verifies each business on Google Places (open or closed, address, phone, website, category)
2. measures drive time from the clinic (659 E 15th St Ste H, Upland, CA)
3. pulls a contact email from each website
4. scores each business Tier A (talk rooms) or Tier B (employers), or excludes it
5. searches for new Tier A organizations within a 15-minute drive

The output has five tabs: Contacts, Excluded, Daily Log, Events and Event Leads.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env        # then paste your Google Maps Platform key into .env
```

Put the CSV exports in `data/`. The filenames are set in `castle_prospects/config.py`:

- `outreach-list-all-YYYY-MM-DD.csv` holds every record, with its outreach history.
- `outreach-list-excluded-YYYY-MM-DD.csv` is the do-not-contact list. These are never verified or re-added.

`.env`, `data/`, `output/` and `cache/` are gitignored.

## Run

```bash
python -m castle_prospects.pipeline estimate   # cost estimate, no API calls
python -m castle_prospects.pipeline all        # verify → discover → emails → build
```

Each step can also run on its own: `verify`, `discover`, `emails`, `build`. API responses and fetched
web pages are cached in `cache/`, so a re-run only pays for new lookups. Add `--refresh` to force fresh
data.

The output goes to `output/castle-outreach-list-<date>.xlsx`, with the tier and exclusion summary in `output/summary.txt`.

## Rules

| Result | Rule |
|---|---|
| Tier A | Gyms, CrossFit, yoga, Pilates, churches, civic clubs, senior communities. Decided from Google place types first, then the business name. The legacy CSV `type` column is ignored because it is unreliable. |
| Tier B | Any other open business with a physical location, meaning an employer with staff on-site. |
| Excluded | On the do-not-contact list, closed on Google, over 15 min drive (traffic-unaware; see below), no audience fit (address only, parking, storage, apartments and similar), or not found on Google (flagged for a manual check). |

Existing outreach history (attempts, outcomes, notes, gatekeeper, decision maker and so on) is carried over unchanged. The
original phone is kept in `phone_on_file`. When it differs from Google's, `verify_note` says so.

Drive time comes from the Google Routes API. If the key isn't allowed to use it, the pipeline
estimates drive time from straight-line distance instead (`ROAD_FACTOR` and `AVG_SPEED_KMH` in
`config.py`). The `drive_time_source` column says which was used, and estimates within 3 minutes of
the cutoff get a note to check on Google Maps.

Tests: `python -m unittest discover tests`
