"""Settings for the Castle Chiropractic prospect pipeline.

Edit values here rather than in the pipeline code.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"          # input CSV exports (gitignored)
OUTPUT_DIR = ROOT / "output"      # generated workbook + intermediate JSON (gitignored)
WORK_DIR = OUTPUT_DIR / "work"
CACHE_DIR = ROOT / "cache"        # cached API/web responses so re-runs don't re-bill (gitignored)
ENV_FILE = ROOT / ".env"

ALL_RECORDS_CSV = DATA_DIR / "outreach-list-all-2026-09-28.csv"
DO_NOT_CONTACT_CSV = DATA_DIR / "outreach-list-excluded-2026-09-28.csv"

API_KEY_VAR = "GOOGLE_MAPS_API_KEY"

CLINIC_ADDRESS = "659 E 15th St Ste H, Upland, CA 91786"
MAX_DRIVE_MINUTES = 15.0
# Bias verification searches toward the clinic; results farther than this are ignored.
SEARCH_RADIUS_METERS = 40_000

# Discovery: cities within roughly 15 minutes of the clinic. Results are still
# filtered by the real drive time, so a generous list is fine.
DISCOVERY_CITIES = [
    "Upland, CA", "Rancho Cucamonga, CA", "Claremont, CA", "Montclair, CA",
    "Ontario, CA", "La Verne, CA", "Pomona, CA",
]
# (query, per_city) — per_city queries are run once for each city above because
# dense categories hit the 60-results-per-query cap otherwise.
DISCOVERY_QUERIES = [
    ("gym", True),
    ("CrossFit gym", True),
    ("yoga studio", True),
    ("Pilates studio", True),
    ("church", True),
    ("senior living community", True),
    ("senior center", False),
    ("retirement community 55+", False),
    ("Rotary Club", False),
    ("Kiwanis Club", False),
    ("Lions Club", False),
    ("Elks Lodge", False),
    ("American Legion post", False),
    ("VFW post", False),
    ("Chamber of Commerce", False),
    ("Optimist Club", False),
    ("Soroptimist", False),
    ("Woman's Club", False),
    ("Masonic lodge", False),
]
DISCOVERY_MAX_PAGES = 3   # Text Search returns at most 60 results (3 pages of 20)

# Google Maps Platform list prices (USD per 1,000 calls) and monthly free calls per SKU.
# Best knowledge as of mid-2026 — confirm at https://mapsplatform.google.com/pricing
# before running. Text Search is billed at the Enterprise SKU because we request
# phone number and website.
PRICING = {
    "text_search_enterprise": {"per_1000": 35.00, "free_per_month": 1_000},
    "route_matrix_element": {"per_1000": 5.00, "free_per_month": 10_000},
}

TEXT_SEARCH_FIELDS = ",".join(
    "places." + f for f in [
        "id", "displayName", "formattedAddress", "addressComponents",
        "nationalPhoneNumber", "internationalPhoneNumber", "websiteUri",
        "businessStatus", "primaryType", "primaryTypeDisplayName", "types",
        "location", "googleMapsUri",
    ]
) + ",nextPageToken"

HTTP_USER_AGENT = (
    "Mozilla/5.0 (compatible; CastleChiroProspectBot/1.0; +contact via clinic website)"
)
