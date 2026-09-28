"""Name/phone normalization, match scoring, and tier classification."""
import re
from difflib import SequenceMatcher

# --- normalization -----------------------------------------------------------

_STOP = {
    "inc", "llc", "llp", "lp", "co", "corp", "corporation", "company", "the", "of",
    "and", "svc", "svcs", "services", "service", "ctr", "center", "centre", "ca",
    "upland", "rancho", "cucamonga", "ontario", "claremont", "montclair", "pomona",
    "la", "verne", "office", "regional",
}


def digits10(phone):
    d = re.sub(r"\D", "", phone or "")
    return d[-10:] if len(d) >= 10 else ""


def clean_name(name):
    """Lowercase, drop parenthetical location hints, punctuation and filler words."""
    name = re.sub(r"\(.*?\)", " ", name or "").lower().replace("&", " and ")
    name = re.sub(r"[^a-z0-9 ]+", " ", name)
    return " ".join(t for t in name.split() if t not in _STOP)


def name_similarity(a, b):
    a, b = clean_name(a), clean_name(b)
    if not a or not b:
        return 0.0
    ta, tb = set(a.split()), set(b.split())
    jaccard = len(ta & tb) / len(ta | tb)
    contained = 1.0 if (a in b or b in a) else 0.0
    return max(SequenceMatcher(None, a, b).ratio(), jaccard, 0.9 * contained)


def search_query(name):
    """Keep parenthetical hints like '(1619 N Mountain)' — they help Google."""
    return re.sub(r"[()`]", " ", name).strip()


# --- tier classification -----------------------------------------------------

TIER_A_RULES = [
    # (category, google types, name regex)
    ("Gym / fitness", {"gym", "fitness_center"},
     r"\b(gym|fitness|crossfit|cross fit|f45|orangetheory|orange theory|bootcamp|boot camp|"
     r"athletic club|strength|training facility|hotworx|sweat|boxing)\b"),
    ("Yoga", {"yoga_studio"}, r"\byoga\b"),
    ("Pilates", {"pilates_studio"}, r"\bpilates\b"),
    ("Church / faith", {"church", "place_of_worship", "synagogue", "mosque", "hindu_temple",
                        "buddhist_temple"},
     r"\b(church|chapel|parish|ministr(y|ies)|fellowship|congregation|cathedral|"
     r"synagogue|mosque|temple|calvary|baptist|lutheran|methodist|presbyterian|"
     r"catholic|episcopal|assembly of god)\b"),
    ("Civic club", set(),
     r"\b(rotary|kiwanis|lions club|elks|moose lodge|american legion|vfw|"
     r"veterans of foreign wars|chamber of commerce|optimist club|soroptimist|"
     r"woman'?s club|women'?s club|masonic|lodge no|exchange club)\b"),
    ("Senior community", {"senior_citizen_center", "assisted_living_facility", "retirement_home",
                          "nursing_home"},
     r"\b(senior (living|center|community|apartments|village)|retirement|assisted living|"
     r"memory care|55\+|active adult|independent living)\b"),
]

# Retail/food that matched a fitness word only by accident (e.g. "Fitness equipment store").
NOT_A_PRIMARY_TYPES = {
    "store", "grocery_store", "supermarket", "home_improvement_store", "sporting_goods_store",
    "health_food_store", "food_store", "clothing_store", "department_store", "restaurant",
}

# Places with no on-site audience for an event.
NO_FIT_TYPES = {
    "atm", "parking", "parking_lot", "park", "storage", "self_storage", "apartment_building",
    "apartment_complex", "condominium_complex", "housing_complex", "cemetery", "bus_station",
    "bus_stop", "transit_station", "train_station", "light_rail_station", "post_box",
    "premise", "subpremise", "street_address", "route", "intersection", "locality",
    "political", "postal_code", "electric_vehicle_charging_station",
}


# Places that look like a talk room but aren't. Checked before any Tier A rule.
EXCLUDE_NAME_RULES = [
    (r"\bfitness court\b", "Outdoor fitness court (no host)"),
    (r"\b(day|med|medical) spa\b", "Day spa"),
    (r"\b(sober|rehab|detox|addiction|halfway house|recovery (home|residence|house|center|centre|ctr)|"
     r"treatment (center|centre|ctr)|transitional (living|housing|home))\b", "Sober living / recovery home"),
]
# Big gyms carry a secondary "spa" type for their saunas, so only the primary type counts.
SPA_PRIMARY_TYPES = {"spa", "day_spa", "massage_spa"}

# Tier A priority (1 = call first). Categories not listed rank last.
PRIORITY = {"Gym / fitness": 1, "Yoga": 1, "Pilates": 1, "Church / faith": 2, "Civic club": 3}
PRIORITY_OTHER = 4

# Google has no place type for civic clubs or chambers, so a name match is the
# strongest evidence available; these stay Tier A instead of going to review.
NAME_ONLY_OK = {"Civic club"}

# "X Independent Living" with no senior-care type on Google is often sober living.
SENIOR_TYPES = TIER_A_RULES[-1][1]

# Trade businesses filed under a talk-room type (e.g. roofers listed as "yoga
# studio") are Maps spam. Only applied when a Tier A type matched.
SPAM_NAME = r"\b(roof(s|er|ers|ing)?|plumb(er|ers|ing)|hvac|locksmiths?|garage doors?|pest control|towing|electricians?)\b"


def priority(category):
    return PRIORITY.get(category, PRIORITY_OTHER)


def classify(name, place):
    """Return (tier, category, no_fit_reason). place may be None (unverified).

    tier is "A", "Review" (Tier A only by name — needs a human look), "B", or ""
    (excluded; no_fit_reason says why).

    Tier A is decided from Google's place types first, then the business name.
    The legacy CSV 'type' column is ignored — it is unreliable (e.g. Lowe's and
    Trader Joe's are tagged 'fitness studio').
    """
    types = set((place or {}).get("types") or [])
    primary = (place or {}).get("primaryType") or ""
    label = ((place or {}).get("primaryTypeDisplayName") or {}).get("text", "")
    gname = ((place or {}).get("displayName") or {}).get("text", "")
    text = f"{name} {gname}".lower()

    for pattern, reason in EXCLUDE_NAME_RULES:
        if re.search(pattern, text):
            return "", label or primary, reason
    if primary in SPA_PRIMARY_TYPES:
        return "", label or primary, "Day spa"

    for category, a_types, pattern in TIER_A_RULES:
        if types & a_types:
            if re.search(SPAM_NAME, text):
                return "", label or primary, "Likely spam listing (trade business under a talk-room category)"
            return "A", category, ""
    if primary not in NOT_A_PRIMARY_TYPES:
        for category, _a_types, pattern in TIER_A_RULES:
            if re.search(pattern, text):
                if category in NAME_ONLY_OK:
                    return "A", category, ""
                return "Review", category, ""

    if place is not None:
        specific = types - {"point_of_interest", "establishment"}
        if primary in NO_FIT_TYPES or (specific and specific <= NO_FIT_TYPES):
            return "", label or primary, f"No audience fit ({label or primary or 'address only'})"
    return "B", label or primary or "Employer", ""


def review_note(name, place, category):
    """Why a name-only match needs a human look."""
    types = set((place or {}).get("types") or [])
    if re.search(r"independent living", f"{name}".lower()) and not types & SENIOR_TYPES:
        return "Needs review: 'independent living' with no senior-care type on Google — may be sober living"
    kind = ((place or {}).get("primaryTypeDisplayName") or {}).get("text", "") or "unverified"
    return f"Needs review: matched {category} by name only (Google lists it as {kind})"
