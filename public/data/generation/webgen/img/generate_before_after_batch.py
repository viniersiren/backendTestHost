#!/usr/bin/env python3
"""
Generate a batch of realistic BEFORE/AFTER roofing images (memory-only).

Inputs via STDIN (JSON):
{
  "serviceNames": {...},
  "bbbProfile": {...} | null,
  "count": 60,
  "quality": "medium",  # hint only
  "size": "1024x768"
}

Process:
1) Build a pool of 60 candidate prompt pairs (before/after) across many material/condition variants.
2) Randomly select 6 distinct pairs.
3) Ask the LLM to validate/edit those 6 to ensure they align with services in serviceNames.
4) Generate the requested count of pairs by cycling through the validated set.

Output to STDOUT markers:
BEFORE_AFTER_BATCH_START
{ "items": [ { "before": "data:image/...", "after": "data:image/...", "prompt_before": "...", "prompt_after": "...", "serviceHint": "Shingling" }, ... ] }
BEFORE_AFTER_BATCH_END
"""

import sys, json, os, base64, random, requests
from typing import Any, Dict, List
import dotenv
import openai


def read_stdin_json() -> Dict[str, Any]:
    try:
        raw = sys.stdin.read()
        print('[BA] Received STDIN length:', len(raw or ''))
        return json.loads(raw) if raw and raw.strip() else {}
    except Exception:
        print('[BA] Failed to parse STDIN JSON')
        return {}


def get_api_key() -> str:
    try:
        env_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
        dotenv.load_dotenv(os.path.abspath(env_path))
    except Exception:
        pass
    key = os.environ.get("OPENAI_API_KEY", "")
    print('[BA] OPENAI key present:', bool(key))
    return key


def to_data_url(png_bytes: bytes) -> str:
    return f"data:image/png;base64,{base64.b64encode(png_bytes).decode('utf-8')}"


def gen_image_bytes(client: openai.OpenAI, prompt: str, size: str, quality_hint: str) -> bytes:
    model = "gpt-image-1"
    # Map quality to values supported by current API: 'low' | 'medium' | 'high' | 'auto'
    qin = str(quality_hint or "").lower()
    oq = 'high' if qin in ('high','hd') else ('low' if qin in ('low','standard') else 'medium')
    # Prefer calling the backend generic endpoint (known-good path in this env)
    try:
        resp2 = requests.post(
            'http://localhost:5001/backend/generate-generic-image',
            headers={'Content-Type': 'application/json'},
            json={ 'prompt': prompt, 'size': size, 'quality': oq, 'model': model },
            timeout=180
        )
        if resp2.ok:
            j = resp2.json()
            du = j.get('image')
            if isinstance(du, str) and du.startswith('data:image/'):
                try:
                    b64 = du.split(',',1)[1]
                    return base64.b64decode(b64)
                except Exception:
                    pass
        else:
            print('[BA] Generic endpoint HTTP error:', resp2.status_code, str(resp2.text)[:200])
    except Exception as e2:
        print('[BA] Generic endpoint exception:', str(e2)[:200])
    # Secondary: direct OpenAI images.generate
    try:
        resp = client.images.generate(
            model=model,
            prompt=f"{prompt}\n\n(quality: {quality_hint})",
            size=size,
            quality=oq,
            n=1,
        )
        item = resp.data[0]
        if getattr(item, "b64_json", None):
            return base64.b64decode(item.b64_json)
        if getattr(item, "url", None):
            r = requests.get(item.url, timeout=120)
            r.raise_for_status()
            return r.content
    except Exception as e:
        print('[BA] OpenAI images.generate failed:', str(e)[:200])
    raise RuntimeError("No image returned")


# Expanded BEFORE/AFTER variant pools (>=30 each, combined → 60 candidates)
BEFORE_VARIANTS = [
    "Older asphalt 3‑tab shingles with curling and granular loss; dark streaks; lifted edges; mismatched repairs; overcast light.",
    "Aging architectural shingles; valleys show debris; mild moss growth; flashing stain trails; flat midday light.",
    "Worn cedar shake roof; uneven weathering; minor moss in shaded areas; a few shakes split; subdued sky.",
    "Tired corrugated metal roof; oxidation and patch plates; waviness along fastener lines; dull ambient light.",
    "EPDM flat roof with ponding marks and patched seams; parapet staining; utilities clutter; low-contrast daylight.",
    "Built‑up roof (BUR) showing blistering and patched areas; faded surface aggregate; dull sky.",
    "Tile roof with cracked/missing tiles; inconsistent tone; dust accumulation; diffuse lighting.",
    "Old slate with chipped edges; some slipped pieces; uneven sheen; grey skies.",
    "Aged gutter/fascia detail with peeling paint; rust near hangers; streaks on soffit.",
    "Dated skylight curb with deteriorated sealant; fogged glazing; debris around curb.",
    "Outdated ventilation (box vents) with rusted caps; erratic layout; staining down-slope.",
    "Worn flashing at chimney; step flashing paint peeling; mortar joints weathered; soot staining.",
    "Metal roof with mismatched panels after prior repairs; foam sealant visible; chalking finish.",
    "PVC single‑ply with yellowing; uneven lap seams; footprints and scuffs; light haze.",
    "Modified bitumen with scuffed cap sheet; wrinkling near edges; patched base sheet.",
    "Composite shingles with hail bruising evident; subtle impact marks; dinged ridge; flat light.",
    "Hip and ridge shingles uneven; some ridge caps cracked; fasteners exposed.",
    "Skylight well interior water staining; exterior curb flashing aged; leaves trapped.",
    "Gutter clogged with leaves; streak lines on fascia; sag near corner; downspout dented.",
    "Drip edge bent/undersized; water staining on starter course; sloppy miter.",
    "Soffit vents blocked; uneven attic airflow signs; ridge vent missing; shingle bake.",
    "Uncoated fasteners on metal roof; red rust haloing; caulk dabbed repairs; dull tone.",
    "Flashing kick-out missing; siding staining; shingle butt joints aligned; amateur install clues.",
    "Ice dam residue staining; degranulated courses near eave; underlayment ridges telegraphed.",
    "Flat roof scupper clogged; water mark rings; patched around rooftop units.",
    "Parapet coping loose; irregular sealant beads; membrane base tie-in wrinkled.",
    "Tile valley with debris; pan tile chipped; mortar patches near ridge; faded tone.",
    "Shake ridge dried and split; ridge nail heads exposed; uneven reveal.",
    "Gutter apron missing; starter course irregular; low curb appeal; neutral light.",
    "Dormer sidewall flashing improvised; siding discoloration; minor algae trails.",
]

AFTER_VARIANTS = [
    "New architectural shingles in modern colorway; crisp ridge; aligned courses; clean flashing; warm, realistic light.",
    "Premium standing seam metal roof; sleek vertical seams; concealed fasteners; tight trims; soft golden hour.",
    "Cedar shake replacement with even reveal; treated, warm tone; clean valleys; professional finish.",
    "TPO (single‑ply) on flat roof; taut membrane; heat‑welded seams; clean drains; bright yet natural daylight.",
    "BUR resurfaced with even aggregate; neat edges; corrected blisters; realistic, neutral daylight.",
    "Clay/concrete tile replacements; uniform color; precise hips/ridges; neat under-eave details.",
    "Composite slate system; crisp edges; uniform texture; refined flashing details; modern curb appeal.",
    "Seamless gutters matched to fascia; hidden hangers; crisp corners; clean soffit and fascia.",
    "Low-profile skylight with new curb and flashing; crystal-clear glazing; tidy perimeter.",
    "Ridge vent installed; balanced intake at soffit; shingle layout optimized; subtle highlight.",
    "Step flashing and counterflashing replaced at chimney; fresh mortar joints; properly tooled.",
    "Metal roof refinished with factory color; aligned panels; uniform sheen; modern tone.",
    "PVC membrane re‑roof with uniform laps; neat terminations; organized rooftop conduit paths.",
    "Mod bitumen cap sheet new; smooth torch seams; straight edge terminations; professional craft.",
    "Impact‑resistant shingles; crisp ridge caps; hail resilience messaging; refined aesthetic.",
    "Hip/ridge system upgraded; ventilation integrated; consistent cap spacing; clean silhouette.",
    "Gutter protection installed; downspouts enlarged; re‑pitched runs; spotless fascia.",
    "Drip edge corrected and color‑matched; flawless starter course; sharp eave line.",
    "Continuous ridge vent; optimized intake; cooler attic signature; crisp sky.",
    "Rust‑proof fasteners; matched paint; corrected panel alignment; clean finish.",
    "Kick‑out flashing added; siding protected; crisp water management; no staining.",
    "Eave protection optimized; underlayment enhanced; straightened shingle lines; renewed curb appeal.",
    "Scupper cleared and re‑built; tapered insulation improves drainage; neat terminations.",
    "Parapet coping replaced; uniform sealant lines; correct counterflashing; consistent look.",
    "Valleys cleared; new W‑valley or closed‑cut; tile replacements; color‑balanced finish.",
    "Shake ridge upgraded; stainless fasteners; aligned reveals; warm toned finish.",
    "Gutter apron installed; starter fixed; crisp eaves; cohesive facade.",
    "Dormer step flashing corrected; moisture path resolved; neat siding transitions.",
    "Modern color palette; clean lines; trimmed landscaping; magazine‑ready curb appeal.",
    "Solar‑ready roof layout; penetrations neatly flashed; wire management tidy; future‑proof.",
]


def pick_service_hints(service_names: Dict[str, Any]) -> List[str]:
    out = []
    try:
        for section in ["residential", "commercial"]:
            hero = service_names.get("heroBlock", {}).get(section, {}).get("subServices")
            if isinstance(hero, list):
                for s in hero:
                    name = s.get("title") or s.get("name")
                    if isinstance(name, str) and name.strip():
                        out.append(name.strip())
        for sec in [
            service_names.get("universal", {}).get("residential", {}).get("services"),
            service_names.get("universal", {}).get("commercial", {}).get("services"),
            service_names.get("serviceSliderBlock", {}).get("residential"),
            service_names.get("serviceSliderBlock", {}).get("commercial"),
        ]:
            if isinstance(sec, list):
                for s in sec:
                    n = s.get("title") or s.get("name")
                    if isinstance(n, str) and n.strip():
                        out.append(n.strip())
    except Exception:
        pass
    # Deduplicate and limit
    seen = set()
    uniq = []
    for n in out:
        if n not in seen:
            uniq.append(n)
            seen.add(n)
    return uniq[:64]


def craft_pool(service_hints: List[str], size: int = 60) -> List[Dict[str, str]]:
    pool: List[Dict[str, str]] = []
    # Combine service hints with variant text to create diverse pairs
    combos = []
    for b in BEFORE_VARIANTS:
        for a in AFTER_VARIANTS:
            combos.append((b, a))
    random.shuffle(combos)
    i = 0
    while len(pool) < size and i < len(combos):
        b, a = combos[i]
        i += 1
        hint = random.choice(service_hints) if service_hints else "Roofing Service"
        base = f"Roofing service context: {hint}. Photorealistic, clean composition, no watermark, natural lighting, realistic materials."
        pool.append({
            "serviceHint": hint,
            "prompt_before": f"BEFORE — {base} {b}",
            "prompt_after": f"AFTER — {base} {a}",
        })
    out = pool[:size]
    print('[BA] Crafted prompt pool size:', len(out))
    return out


def call_llm_validate(api_key: str, service_names: Dict[str, Any], selected: List[Dict[str, str]]) -> List[Dict[str, str]]:
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    # Keep payload compact
    services_flat = pick_service_hints(service_names)
    content = {
        "services": services_flat,
        "pairs": [{
            "serviceHint": it.get("serviceHint"),
            "before": it.get("prompt_before"),
            "after": it.get("prompt_after"),
        } for it in selected]
    }
    prompt = (
        "You are a roofing content QA assistant. Given a list of roofing services and 6 before/after prompt pairs, "
        "edit any pairs that do not align with the services. Keep them concise, realistic, and professional. "
        "Return ONLY JSON with key 'pairs' as an array of 6 objects like: "
        "{\"serviceHint\": string, \"before\": string, \"after\": string}."
    )
    body = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(content)}
        ],
        "temperature": 0.4,
        "max_tokens": 1200
    }
    try:
        resp = requests.post(url, headers=headers, json=body, timeout=60)
        if resp.status_code != 200:
            print('[BA] LLM validate HTTP error:', resp.status_code, resp.text[:200])
            return selected
        msg = resp.json()["choices"][0]["message"]["content"]
        start = msg.find('{')
        end = msg.rfind('}') + 1
        if start < 0 or end <= start:
            print('[BA] LLM validate returned no JSON; using original picks')
            return selected
        parsed = json.loads(msg[start:end])
        pairs = parsed.get("pairs")
        if not isinstance(pairs, list) or len(pairs) != 6:
            print('[BA] LLM validate pairs shape invalid; using original picks')
            return selected
        validated: List[Dict[str, str]] = []
        for it in pairs:
            validated.append({
                "serviceHint": it.get("serviceHint") or "Roofing Service",
                "prompt_before": it.get("before") or selected[0]["prompt_before"],
                "prompt_after": it.get("after") or selected[0]["prompt_after"],
            })
        print('[BA] LLM validate produced 6 pairs')
        return validated
    except Exception:
        print('[BA] LLM validate exception; using original picks')
        return selected


def main():
    payload = read_stdin_json()
    service_names = payload.get("serviceNames") or {}
    count = int(payload.get("count") or 60)
    quality = str(payload.get("quality") or "medium")
    size = str(payload.get("size") or "1024x768")
    # Normalize size to supported values for gpt-image-1
    try:
        if size not in ("256x256","512x512","1024x1024"):
            print('[BA] Normalizing unsupported size', size, 'to 1024x1024')
            size = "1024x1024"
    except Exception:
        size = "1024x1024"
    print('[BA] Inputs summary:', {
        'serviceNamesKeys': list(service_names.keys()) if isinstance(service_names, dict) else type(service_names).__name__,
        'count': count,
        'quality': quality,
        'size': size
    })

    api_key = get_api_key()
    if not api_key:
        print("ERROR: OPENAI_API_KEY is not set.")
        sys.exit(1)

    client = openai.OpenAI(api_key=api_key)

    hints = pick_service_hints(service_names)
    if not hints:
        hints = ["Shingling", "Roof Repair", "Gutters", "Ventilation", "Metal Roof", "Coatings", "Inspection", "Flashing"]
    print('[BA] Service hints:', hints[:8], '... total', len(hints))

    # Step 1-2: Pool of 60, then select 6
    pool = craft_pool(hints, size=60)
    picked6 = random.sample(pool, 6) if len(pool) >= 6 else pool
    print('[BA] Picked6 size:', len(picked6))

    # Step 3: LLM validate/edit the 6
    validated6 = call_llm_validate(api_key, service_names, picked6)
    if not validated6 or len(validated6) < 6:
        validated6 = picked6

    # Step 4: Generate 'count' by cycling through validated set
    items: List[Dict[str, Any]] = []
    for i in range(count):
        variant = validated6[i % len(validated6)]
        try:
            before_bytes = gen_image_bytes(client, variant["prompt_before"], size, quality)
            after_bytes = gen_image_bytes(client, variant["prompt_after"], size, quality)
            items.append({
                "serviceHint": variant["serviceHint"],
                "prompt_before": variant["prompt_before"],
                "prompt_after": variant["prompt_after"],
                "before": to_data_url(before_bytes),
                "after": to_data_url(after_bytes),
            })
        except Exception as e:
            print('[BA] Generation failed at index', i, 'error:', str(e)[:200])
            continue
    print('[BA] Generated items:', len(items), 'requested pairs:', count)

    print("BEFORE_AFTER_BATCH_START")
    print(json.dumps({ "items": items }, ensure_ascii=False))
    print("BEFORE_AFTER_BATCH_END")


if __name__ == "__main__":
    main()

