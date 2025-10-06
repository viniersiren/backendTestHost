#!/usr/bin/env python3
import json
import os
import re
import sys
import requests
import dotenv
from pathlib import Path
from typing import Dict, List, Any, Tuple

# Load the OpenAI API key from .env file (kept for compatibility, but file IO is not required)
env_path = Path(__file__).parent.parent.parent / ".env"
try:
    dotenv.load_dotenv(env_path)
except Exception:
    pass

# Get API key from environment variable (match logogen behavior exactly)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
API_ENDPOINT = "https://api.openai.com/v1/chat/completions"

# NOTE: Memory-only mode: no reading/writing local files. Input is received via STDIN; output is printed to STDOUT.
MEMORY_ONLY = os.environ.get("MEMORY_ONLY", "1") == "1"

# Added runtime diagnostics
print(f"[ServiceNames] OpenAI key present: {bool(OPENAI_API_KEY)}")
print(f"[ServiceNames] MEMORY_ONLY: {MEMORY_ONLY}")

# No backups: AI must be used. If unavailable, the script will error.

def call_openai_api(prompt: str) -> str:
    """Call the OpenAI API with a given prompt and return the response."""
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 4000
    }
    
    response = requests.post(API_ENDPOINT, headers=headers, json=data, timeout=60)
    
    if response.status_code == 200:
        print("[ServiceNames] OpenAI call: 200 OK")
        return response.json()["choices"][0]["message"]["content"]
    else:
        print(f"[ServiceNames] OpenAI call error: {response.status_code}")
        print(response.text)
        # Raise to ensure caller treats this as a failure
        raise RuntimeError(f"OpenAI API request failed with status {response.status_code}")

# ---------------------------------------------
# Heuristics for plausibility filtering
# ---------------------------------------------

# Obvious non-service markers frequently scraped from sites like Yelp/BBB
BAD_PHRASE_MARKERS = {
    "yelp", "users", "asked", "questions", "yet", "about", "photos", "reviews",
    "review", "rating", "hours", "open now", "closed", "claim this business",
    "location", "directions", "message the business", "people", "community",
}

# Common roofing/service keywords to positively signal plausibility
SERVICE_KEYWORDS = {
    # generic service verbs/nouns
    "roof", "roofing", "shingle", "shingles", "tile", "slate", "shake", "metal",
    "flat", "low slope", "gutter", "gutters", "downspout", "skylight", "skylights",
    "chimney", "flashing", "soffit", "fascia", "vent", "ventilation", "attic",
    "leak", "leaks", "coating", "coatings", "seal", "sealing", "waterproof",
    "waterproofing", "ice dam", "storm", "hail", "wind",
    # actions
    "install", "installation", "replace", "replacement", "repair", "repairs",
    "inspect", "inspection", "inspections", "maintain", "maintenance",
    # commercial systems
    "tpo", "epdm", "pvc", "modified bitumen", "built-up", "bur", "spf",
    # siding et al
    "siding",
}

def has_service_keyword(text: str) -> bool:
    n = (text or "").lower()
    for kw in SERVICE_KEYWORDS:
        if kw in n:
            return True
    return False

def contains_bad_marker(text: str) -> bool:
    n = (text or "").lower()
    for marker in BAD_PHRASE_MARKERS:
        if marker in n:
            return True
    return False

def is_plausible_service(name: str) -> bool:
    """Return True if the string plausibly names a roofing-related service.
    Filters out UI/UX sentences like "Yelp users haven't asked any questions yet...".
    """
    if not isinstance(name, str):
        return False
    n = name.strip()
    if not n:
        return False
    # Hard filter: contains obviously non-service markers
    if contains_bad_marker(n):
        return False
    # Too long without keywords → likely a sentence, not a service
    if len(n.split()) > 8 and not has_service_keyword(n):
        return False
    # Require at least one service keyword unless the word is a short known trade like siding, chimney
    if not has_service_keyword(n):
        return False
    # Avoid pure company or person names (very weak heuristic: no spaces and no service keyword already handled)
    return True

def normalize_service_name(name: str) -> str:
    """Normalize a service name for comparison and display (basic, language-agnostic).
    - Trim whitespace
    - Collapse internal spaces
    - Title-case words of reasonable length
    - Remove extraneous punctuation (retain alphanumerics and spaces)
    """
    if not isinstance(name, str):
        return ""
    cleaned = re.sub(r"[^A-Za-z0-9\s\-/&]", "", name).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    # Title case but preserve known acronyms
    words = cleaned.split(" ")
    def fix_word(w: str) -> str:
        if w.upper() in {"EPDM", "TPO", "PVC", "BUR", "SPF", "ISO", "UV"}:
            return w.upper()
        if len(w) <= 2:
            return w.lower()
        return w.capitalize()
    return " ".join(fix_word(w) for w in words if w)

def is_too_broad(name: str) -> bool:
    """Heuristic filter for overly broad/non-specific service labels."""
    if not name:
        return True
    n = name.lower().strip()
    # Single-token generic or very broad categories
    broad_tokens = {
        "roofing", "roof", "construction", "remodeling", "maintenance", "repairs",
        "repair", "services", "home improvement", "general contractor", "contractor",
        "handyman", "installations", "installation", "restoration"
    }
    if n in broad_tokens:
        return True
    # Extremely short or just generic plurals
    if len(n) < 5 and n not in {"tpo", "epdm", "pvc", "bur"}:
        return True
    # Vague combos
    vague_patterns = [
        r"^roof(ing)?\s+services$",
        r"^general\s+roof(ing)?$",
        r"^roof(ing)?\s+work$",
        r"^home\s+services$",
    ]
    for pat in vague_patterns:
        if re.search(pat, n):
            return True
    return False

def filter_plausible_services(candidates: List[str]) -> List[str]:
    out = []
    for c in candidates:
        if not c:
            continue
        if is_too_broad(c):
            continue
        if not is_plausible_service(c):
            continue
        out.append(c)
    return unique_ordered(out)

def classify_service(name: str) -> str:
    """Very simple heuristic to split into residential vs commercial buckets.
    Commercial indicators include flat/low-slope systems and membranes.
    """
    n = name.lower()
    commercial_markers = [
        "epdm", "tpo", "pvc", "modified bitumen", "built-up", "bur",
        "coating", "coatings", "flat roof", "low slope", "commercial",
        "roof deck", "spf"
    ]
    for m in commercial_markers:
        if m in n:
            return "commercial"
    return "residential"

def unique_ordered(seq):
    seen = set()
    out = []
    for item in seq:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out

def select_top_four(candidates):
    """Pick up to 4 candidates preferring specificity and diversity.
    Scoring heuristic: more words, presence of specific tokens, longer length.
    """
    spec_tokens = {"inspection", "inspections", "flashing", "skylight", "skylights", "chimney",
                   "soffit", "fascia", "gutter", "gutters", "vent", "ridge", "attic",
                   "metal", "coating", "coatings", "modified", "bitumen", "tpo", "epdm", "pvc",
                   "built-up", "bur", "flat"}
    def score(name: str) -> int:
        base = len(name)
        words = len(name.split())
        tokens_bonus = sum(3 for t in spec_tokens if t in name.lower())
        return base + (words * 5) + tokens_bonus
    # Boost entries that contain explicit service keywords
    def boosted_score(n: str) -> int:
        base = score(n)
        return base + (20 if has_service_keyword(n) else 0)
    ranked = sorted(candidates, key=lambda n: (-boosted_score(n), n))
    # Promote diversity by avoiding very similar stems (simple containment check)
    chosen = []
    for n in ranked:
        if len(chosen) >= 4:
            break
        if any(n.lower() in c.lower() or c.lower() in n.lower() for c in chosen):
            continue
        chosen.append(n)
    return chosen[:4]

def load_input_data_from_stdin() -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
    """Memory-only: Load data from STDIN JSON.
    Expected shape: {"yelpData": {...}, "bbbData": {...}, "profileData": {"services": [...]}}
    Returns (yelp_data, bbb_data, profile_services)
    """
    try:
        raw = sys.stdin.read()
        if not raw:
            return {}, {}, []
        payload = json.loads(raw)
        yelp_data = payload.get("yelpData", {}) or {}
        bbb_data = payload.get("bbbData", {}) or {}
        profile_services = []
        # Prefer explicit profileData.services
        try:
            pd = payload.get("profileData", {}) or {}
            if isinstance(pd.get("services"), list):
                profile_services = [s for s in pd.get("services") if isinstance(s, str)]
        except Exception:
            profile_services = []
        # Fallback: allow yelp/bbb to include embedded services list under alternate keys
        if not profile_services:
            for k in ("profile_services", "profileServices"):
                if isinstance(payload.get(k), list):
                    profile_services = [s for s in payload.get(k) if isinstance(s, str)]
                    break
        return yelp_data, bbb_data, profile_services
    except Exception:
        # If anything goes wrong, fall back to empty dicts
        return {}, {}, []

def slugify(text):
    """Convert text to URL-friendly slug"""
    if not text:
        return ""
    text = str(text).lower()
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'\s+', '-', text.strip())
    return text

def generate_services_with_ai(yelp_data, bbb_data, profile_services: List[str] = None):
    """Use a single ChatGPT prompt to produce MECE residential/commercial services.
    - Accepts raw scraped services (Yelp/BBB) and profile-provided services
    - Normalizes and de-duplicates inputs (no keyword filtering)
    - Delegates plausibility and partitioning to the LLM
    - Returns exactly 4 residential and 4 commercial items
    """
    # Gather raw lists
    raw_yelp = yelp_data.get("yelp_services") or yelp_data.get("services") or []
    raw_bbb = bbb_data.get("additional_services") or bbb_data.get("services") or []
    raw_profile = profile_services or []

    # Ensure lists
    if not isinstance(raw_yelp, list):
        raw_yelp = []
    if not isinstance(raw_bbb, list):
        raw_bbb = []

    # Normalize and de-duplicate (no keyword gating)
    candidates: List[str] = []
    for src in (raw_profile + raw_bbb + raw_yelp):
        n = normalize_service_name(src)
        if n:
            candidates.append(n)
    candidates = unique_ordered(candidates)

    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set; LLM-based service generation requires it")

    business_name = bbb_data.get("business_name", "Roofing Company")
    container_text = (bbb_data.get("container_text") or "").strip()

    prompt = f"""
    You are organizing a contractor's services into two MECE lists: Residential and Commercial.

    Requirements:
    - Use the provided candidate services and business context to determine plausibility.
    - Preserve explicitly provided items whenever reasonable (e.g., Painting, Decks). Do not drop them just because they aren't strictly roofing.
    - Ensure the two lists are mutually exclusive and collectively exhaustive for the business.
    - Prefer concise names (1-5 words), avoid duplicates, unify synonyms.
    - If candidates are insufficient, add reasonable services that fit the business.
    - Output exactly 4 items in each list.

    Business Name: {business_name}
    Candidates: {candidates if candidates else '[]'}

    Business Context (may include text scraped from BBB/Yelp):
    {container_text}

    Return ONLY JSON in this exact shape and nothing else:
    {{
      "residential": ["Service1", "Service2", "Service3", "Service4"],
      "commercial": ["Service1", "Service2", "Service3", "Service4"]
    }}
    """

    response = call_openai_api(prompt)
    s = response.find('{')
    e = response.rfind('}') + 1
    if s < 0 or e <= s:
        raise ValueError("AI response did not contain JSON block")
    parsed = json.loads(response[s:e])

    res = [normalize_service_name(x) for x in (parsed.get("residential") or [])]
    com = [normalize_service_name(x) for x in (parsed.get("commercial") or [])]

    # Initial within-list de-duplication
    res = unique_ordered([x for x in res if x])
    com = unique_ordered([x for x in com if x])

    # Enforce mutual exclusivity across residential/commercial and backfill if needed
    def enforce_mutual_exclusivity(residential_list: List[str], commercial_list: List[str]) -> Tuple[List[str], List[str]]:
        # Remove cross-duplicates, keeping the category suggested by classifier
        existing_res = [normalize_service_name(x) for x in (residential_list or []) if x]
        existing_com = [normalize_service_name(x) for x in (commercial_list or []) if x]

        res_set = {x.lower() for x in existing_res}
        com_set = {x.lower() for x in existing_com}
        cross_dupes = {x for x in res_set.intersection(com_set)}

        if cross_dupes:
            # Decide the preferred bucket for each duplicate
            for dup_lower in list(cross_dupes):
                # Find canonical case
                canonical = (
                    next((x for x in existing_res if x.lower() == dup_lower), None)
                    or next((x for x in existing_com if x.lower() == dup_lower), None)
                )
                preferred = classify_service(canonical)
                if preferred == "commercial":
                    # Remove from residential
                    existing_res = [x for x in existing_res if x.lower() != dup_lower]
                else:
                    # Default keep in residential
                    existing_com = [x for x in existing_com if x.lower() != dup_lower]

        # Backfill pools (curated, only used to maintain counts post-dedup)
        residential_pool = [
            "Roof Repair", "Roof Replacement", "Shingle Roofing", "Skylight Installation",
            "Gutter Installation", "Chimney Flashing Repair", "Attic Ventilation", "Soffit and Fascia"
        ]
        commercial_pool = [
            "Flat Roof Repair", "TPO Roofing", "EPDM Roofing", "PVC Roofing",
            "Modified Bitumen Roofing", "Built-Up Roofing", "Roof Coatings", "Commercial Roof Inspection"
        ]

        def fill_to_four(current: List[str], other: List[str], pool: List[str]) -> List[str]:
            current_norm = {x.lower() for x in current}
            other_norm = {x.lower() for x in other}
            for item in pool:
                if len(current) >= 4:
                    break
                n = normalize_service_name(item)
                if not n:
                    continue
                lc = n.lower()
                if lc in current_norm or lc in other_norm:
                    continue
                current.append(n)
                current_norm.add(lc)
            return current

        if len(existing_res) < 4:
            existing_res = fill_to_four(existing_res, existing_com, residential_pool)
        if len(existing_com) < 4:
            existing_com = fill_to_four(existing_com, existing_res, commercial_pool)

        # Final trim and ensure no cross-dup remains after fills
        existing_res = unique_ordered(existing_res)[:4]
        existing_com = unique_ordered(existing_com)[:4]
        res_norm = {x.lower() for x in existing_res}
        existing_com = [x for x in existing_com if x.lower() not in res_norm]
        if len(existing_com) < 4:
            existing_com = fill_to_four(existing_com, existing_res, commercial_pool)
            existing_com = unique_ordered(existing_com)[:4]

        return existing_res, existing_com

    res, com = enforce_mutual_exclusivity(res, com)

    if len(res) != 4 or len(com) != 4:
        raise ValueError("Unable to produce 4 unique residential and 4 unique commercial items")

    return {"residential": res, "commercial": com}

def create_service_names_json(services):
    """Create the service_names.json structure using the new standardized categories format."""
    
    # Create the new standardized structure with categories array
    service_names = {
        "meta": { "version": 2, "maxCategories": 5 },
        "categories": [
            {
                "key": "residential",
                "label": "Residential", 
                "icon": "Home",
                "iconPack": "lucide",
                "order": 0,
                "services": []
            },
            {
                "key": "commercial",
                "label": "Commercial",
                "icon": "Building2", 
                "iconPack": "lucide",
                "order": 1,
                "services": []
            }
        ],
        # Keep legacy flat structure for backward compatibility
        "residential": {
            "label": "Residential",
            "icon": "Home",
            "iconPack": "lucide",
            "services": []
        },
        "commercial": {
            "label": "Commercial", 
            "icon": "Building2",
            "iconPack": "lucide",
            "services": []
        },
        "servicePage": {
            "residential": [],
            "commercial": []
        }
    }
    
    # Populate residential services in both new categories structure and legacy structure
    for i, service in enumerate(services["residential"]):
        # ✅ UPDATED: Use kebab-case service ID instead of numeric
        service_id = slugify(service)
        
        # Add to new categories structure
        service_names["categories"][0]["services"].append({
            "id": service_id,
            "title": service,
            "route": f"/services/residential/{service_id}",
            "icon": "ShieldCheck",  # Default icon, will be updated by assign_service_icons.py
            "iconPack": "lucide"
        })
        
        # Add to legacy flat structure for backward compatibility
        service_names["residential"]["services"].append({
            "id": service_id,
            "title": service,
            "route": f"/services/residential/{service_id}",
            "icon": "ShieldCheck",
            "iconPack": "lucide"
        })
        
        # Add to service page structure
        service_names["servicePage"]["residential"].append({
            "id": service_id,
            "title": service,
            "name": service,
            "heroTitle": f"Professional {service}",
            "route": f"/services/residential/{service_id}"
        })
    
    # Populate commercial services in both new categories structure and legacy structure  
    for i, service in enumerate(services["commercial"]):
        # ✅ UPDATED: Use kebab-case service ID instead of numeric
        service_id = slugify(service)
        
        # Add to new categories structure
        service_names["categories"][1]["services"].append({
            "id": service_id,
            "title": service,
            "route": f"/services/commercial/{service_id}",
            "icon": "Building2",  # Default icon, will be updated by assign_service_icons.py
            "iconPack": "lucide"
        })
        
        # Add to legacy flat structure for backward compatibility
        service_names["commercial"]["services"].append({
            "id": service_id,
            "title": service,
            "route": f"/services/commercial/{service_id}",
            "icon": "Building2",
            "iconPack": "lucide"
        })
        
        # Add to service page structure
        service_names["servicePage"]["commercial"].append({
            "id": service_id,
            "title": service,
            "name": service,
            "heroTitle": f"Commercial {service}",
            "route": f"/services/commercial/{service_id}"
        })
    
    return service_names

def main():
    """Memory-only entry point: read from STDIN, write to STDOUT."""
    try:
        # Load input data from STDIN only (no filesystem IO)
        yelp_data, bbb_data, profile_services = load_input_data_from_stdin()

        # Build meta
        meta = {
            "hasOpenAIKey": bool(OPENAI_API_KEY),
            "yelpServicesCount": (len((yelp_data or {}).get("yelp_services", [])) if isinstance((yelp_data or {}).get("yelp_services", []), list) else len((yelp_data or {}).get("services", [])) if isinstance((yelp_data or {}).get("services", []), list) else 0),
            "bbbServicesCount": (len((bbb_data or {}).get("additional_services", [])) if isinstance((bbb_data or {}).get("additional_services", []), list) else len((bbb_data or {}).get("services", [])) if isinstance((bbb_data or {}).get("services", []), list) else 0),
            "businessName": (bbb_data or {}).get("business_name") or "",
            "usedBackup": False,
            "profileServicesCount": len(profile_services or [])
        }

        # Generate services using AI (no backups)
        services = generate_services_with_ai(yelp_data, bbb_data, profile_services)

        # Create the service_names.json structure
        service_names_json = create_service_names_json(services)

        # No default comparison since backups are removed

        # Emit result to STDOUT with markers for robust parsing (memory-only pipeline)
        print("SERVICE_NAMES_START")
        print(json.dumps(service_names_json, indent=2))
        print("SERVICE_NAMES_END")
        # Emit meta block to help caller log/debug
        print("SERVICE_NAMES_META_START")
        print(json.dumps(meta, indent=2))
        print("SERVICE_NAMES_META_END")
        print("[ServiceNames] Emitted to STDOUT (memory mode)")
    except Exception as e:
        # Emit a structured error to STDOUT so the caller can handle it
        err = {"error": str(e)}
        print("SERVICE_NAMES_START")
        print(json.dumps(err))
        print("SERVICE_NAMES_END")
        print("SERVICE_NAMES_META_START")
        print(json.dumps({"error": str(e), "usedBackup": True, "fallbackReason": "exception"}))
        print("SERVICE_NAMES_META_END")
        # Exit non-zero so the parent process can detect failure
        sys.exit(1)

if __name__ == "__main__":
    main()