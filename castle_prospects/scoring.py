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


def classify(name, place):
    """Return (tier, category, no_fit_reason). place may be None (unverified).

    Tier A is decided from Google's place types first, then the business name.
    The legacy CSV 'type' column is ignored — it is unreliable (e.g. Lowe's and
    Trader Joe's are tagged 'fitness studio').
    """
    types = set((place or {}).get("types") or [])
    primary = (place or {}).get("primaryType") or ""
    label = ((place or {}).get("primaryTypeDisplayName") or {}).get("text", "")
    gname = ((place or {}).get("displayName") or {}).get("text", "")
    text = f"{name} {gname}".lower()

    for category, a_types, pattern in TIER_A_RULES:
        if types & a_types:
            return "A", category, ""
    if primary not in NOT_A_PRIMARY_TYPES:
        for category, _a_types, pattern in TIER_A_RULES:
            if re.search(pattern, text):
                return "A", category, ""

    if place is not None:
        specific = types - {"point_of_interest", "establishment"}
        if primary in NO_FIT_TYPES or (specific and specific <= NO_FIT_TYPES):
            return "", label or primary, f"No audience fit ({label or primary or 'address only'})"
    return "B", label or primary or "Employer", ""
