#!/usr/bin/env python3
"""
Generate Hero Transition Images (Residential dusk → Commercial/Urban dusk → Composite)

Patterned after logogen.py for env handling, outputs, and MEMORY_ONLY support.

Inputs:
- Reads BBB profile data from public/data/output/individual/step_1/raw/bbb_profile_data.json

Outputs:
- Saves three images into webgen/img/output/:
  1) hero_residential_dusk.png
  2) hero_urban_dusk.png
  3) hero_composite_transition.png (conceptually a blend via prompt)
- Writes webgen/img/generated_hero.json metadata

Env:
- OPENAI_API_KEY must be set
- MEMORY_ONLY=1 returns base64 data URLs instead of writing files
- HERO_IMAGE_MODEL (default: "image-generate-1")
- HERO_IMAGE_QUALITY (default: "high")
- HERO_IMAGE_SIZE (default: "1536x1024" for image-generate-1; "1792x1024" for dall-e-3)
"""

import os
import json
from pathlib import Path
from datetime import datetime
import base64
import requests
from typing import Optional, List, Dict, Any
import random
import sys
import dotenv
import openai

# Paths (mirror logogen style)
ROOT = Path(__file__).resolve().parents[5]  # projects/roofing-co
OUTPUT_INDIVIDUAL_DIR = ROOT / "public" / "data" / "output" / "individual" / "step_1" / "raw"
BBB_PROFILE_PATH = OUTPUT_INDIVIDUAL_DIR / "bbb_profile_data.json"

STEP2_DIR = Path(__file__).resolve().parent.parent
IMG_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = IMG_DIR / "output"
METADATA_PATH = IMG_DIR / "generated_hero.json"

MEMORY_ONLY = os.environ.get("MEMORY_ONLY", "0") == "1"

# Load API key from .env similar to logogen.py (adapt paths for this location)
try:
    env_path = Path(__file__).resolve().parents[2] / ".env"  # public/data/generation/.env
    dotenv.load_dotenv(env_path)
except Exception:
    pass


def get_api_key() -> Optional[str]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY is not set. Aborting hero image generation.")
        return None
    return api_key


def load_bbb_data() -> dict:
    # Default: disk-based load
    if BBB_PROFILE_PATH.exists():
        try:
            with open(BBB_PROFILE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def read_stdin_payload() -> Dict[str, Any]:
    """Attempt to read a JSON payload from stdin (memory-only integration).
    Expected keys: { bbbProfile?, enhancedColorDataUrl?, enhancedGrayDataUrl?, size? }
    """
    try:
        data = sys.stdin.read()
        if not data:
            return {}
        return json.loads(data)
    except Exception:
        return {}


def extract_location(bbb: dict) -> dict:
    address = (bbb.get("address") or "").strip()
    telephone = (bbb.get("telephone") or "").strip()
    business_name = (bbb.get("business_name") or "Roofing Company").strip()
    # Heuristic city/state extraction
    city = ""
    state = ""
    zip_code = ""
    # Expect patterns like "City, ST 12345" somewhere
    import re
    m = re.search(r"([A-Za-z\s]+),\s*([A-Z]{2})\s*(\d{5})?", address)
    if m:
        city = m.group(1).strip()
        state = m.group(2).strip()
        zip_code = (m.group(3) or "").strip()
    return {
        "business_name": business_name,
        "address": address,
        "telephone": telephone,
        "city": city,
        "state": state,
        "zip": zip_code,
    }


def build_residential_prompt(loc: dict, time_str: str) -> str:
    city = loc.get("city") or "the local area"
    state = loc.get("state") or ""
    location_str = f"{city}, {state}".strip().strip(",")
    return (
        f"Ultra-realistic residential neighborhood near {location_str} at {time_str}. "
        f"Warm golden-hour to early blue-hour light, quiet suburban street with a CONTIGUOUS row of multiple single-family houses, "
        f"pitched roofs with asphalt shingles, trees and tidy lawns, high dynamic range but subtle, copy-safe negative space on left third, 16:9, professional photography."
    )


def build_urban_prompt(loc: dict, time_str: str) -> str:
    city = loc.get("city") or "the nearest city"
    state = loc.get("state") or ""
    location_str = f"{city}, {state}".strip().strip(",")
    return (
        f"Cinematic urban skyline near {location_str} at {time_str}. "
        f"Modern downtown silhouette, gentle twilight gradients, clean architectural lines, "
        f"copy-safe negative space on right third, 16:9, professional photography."
    )


def build_composite_prompt(loc: dict, time_str: str) -> str:
    city = (loc.get("city") or "").strip()
    state = (loc.get("state") or "").strip()
    zip_code = (loc.get("zip") or "").strip()
    address = (loc.get("address") or "").strip()
    parts = []
    if city:
        parts.append(city)
    if state:
        parts.append(state)
    region = ", ".join(parts)
    if zip_code:
        region = (region + f" {zip_code}").strip()
    if not region:
        region = "the local area"

    location_detail = f"near {address}" if address else f"in {region}"

    return (
        f"A wide panoramic PHOTOGRAPH at {time_str} that ORGANICALLY blends a peaceful Southeastern US suburban neighborhood on the LEFT with a modern downtown skyline on the RIGHT {location_detail}. "
        f"No straight seam and no hard vertical split; use a natural, believable transition band around the center third (x≈45–55%) where elements and lighting flow continuously. "
        f"Place ONE prominent commercial high‑rise in the foreground slightly right of center. The top of this building must stay within the LOWER HALF of the frame (do not reach the top edge); its rooftop is clearly visible, bridging both sides while preserving a continuous horizon and perspective. "
        f"Left 0–40%: a CONTIGUOUS sequence of multiple single‑family houses with asphalt shingles, trees, driveways, warm porch lights. Right 60–100%: downtown with office towers and glowing windows. "
        f"Keep the SAME twilight sky, matching horizon line and color temperature across the entire frame to ensure realism. Perspective and lighting should be continuous across the transition. "
        f"Avoid any obvious collage edge, mirrored symmetry, or vertical dividing line. Avoid CGI, illustration, 3D, over‑saturation, text or logos. "
        f"Ultra‑photorealistic, full‑frame DSLR look, 24mm, f/8, ISO 200, tripod, natural color grading, 16:9."
    )


def random_dusk_time_str(start_hour: int = 17, end_hour: int = 20) -> str:
    """Return a random time string between start_hour and end_hour inclusive, formatted like '7:12 PM'."""
    hour_24 = random.randint(start_hour, end_hour)
    minute = random.randint(0, 59)
    ampm = "PM"
    hour_12 = hour_24 - 12 if hour_24 > 12 else hour_24
    if hour_12 == 0:
        hour_12 = 12
    return f"{hour_12}:{minute:02d} {ampm}"


def dalle_generate_image(
    api_key: str,
    prompt: str,
    size: str = "1792x1024",
    model: str = "image-generate-1",
    quality: str = "high",
) -> Optional[bytes]:
    # Use base64 response to avoid external HTTPS fetch (LibreSSL incompat warning path)
    client = openai.OpenAI(api_key=api_key)

    sizes_to_try = [size]
    if size != "1024x1024":
        sizes_to_try.append("1024x1024")

    for sz in sizes_to_try:
        try:
            resp = client.images.generate(
                model=model,
                prompt=prompt,
                size=sz,
                quality=quality,
                n=1,
            )
            result = resp.data[0]
            b64_content = getattr(result, "b64_json", None)
            if b64_content:
                try:
                    return base64.b64decode(b64_content)
                except Exception:
                    pass
            image_url = getattr(result, "url", None)
            if image_url:
                try:
                    img = requests.get(image_url, timeout=120)
                    img.raise_for_status()
                    return img.content
                except Exception as e:
                    print(f"Fallback URL fetch failed at {sz}: {e}")
        except Exception as e:
            print(f"Image generation failed for {model} at {sz} (quality={quality}): {e}")
            continue
    return None


def save_image_bytes(image_bytes: bytes, filename: str) -> str:
    if MEMORY_ONLY:
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        return f"data:image/png;base64,{b64}"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / filename
    with open(out_path, "wb") as f:
        f.write(image_bytes)
    return str(out_path.relative_to(ROOT))


def update_metadata(entries: List[Dict[str, Any]]):
    try:
        meta = {"generated_hero": [], "metadata": {"last_updated": datetime.now().isoformat()}}
        if METADATA_PATH.exists() and not MEMORY_ONLY:
            with open(METADATA_PATH, "r", encoding="utf-8") as f:
                meta = json.load(f)
        meta["generated_hero"].extend(entries)
        meta["metadata"]["last_updated"] = datetime.now().isoformat()
        if not MEMORY_ONLY:
            with open(METADATA_PATH, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Failed to update metadata: {e}")


def main():
    api_key = get_api_key()
    if not api_key:
        return False

    # Prefer memory payload when provided
    payload = read_stdin_payload()
    bbb = payload.get("bbbProfile") or load_bbb_data()
    loc = extract_location(bbb)

    # Randomize an early-evening time between 5:00 PM and 8:59 PM
    time_str = random_dusk_time_str(17, 20)

    residential_prompt = build_residential_prompt(loc, time_str)
    urban_prompt = build_urban_prompt(loc, time_str)
    composite_prompt = build_composite_prompt(loc, time_str)

    # Model and quality are configurable; default to newest image model and high quality
    # Normalize model alias to supported names
    raw_model = (os.environ.get("HERO_IMAGE_MODEL", "gpt-image-1") or "gpt-image-1").strip()
    def normalize_model(name: str) -> str:
        m = (name or "").strip().lower()
        if m in {"image-generate-1", "gpt-image", "gpt-image1", "gpt_image_1"}:
            return "gpt-image-1"
        return name
    model = normalize_model(raw_model)
    # Normalize quality with requested default of "high"
    quality = (os.environ.get("HERO_IMAGE_QUALITY", "high").strip() or "high").lower()
    if quality not in {"low", "medium", "high"}:
        quality = "high"

    # Allow size override like logogen. Pick sensible default by model.
    default_size = "1536x1024" if model in {"image-generate-1", "gpt-image-1"} else "1792x1024"
    size = payload.get("size") or os.environ.get("HERO_IMAGE_SIZE", default_size)

    # Clean up any previous separate outputs to ensure only one final output remains
    try:
        sep1 = OUTPUT_DIR / "hero_residential_dusk.png"
        sep2 = OUTPUT_DIR / "hero_urban_dusk.png"
        if sep1.exists():
            sep1.unlink()
        if sep2.exists():
            sep2.unlink()
    except Exception:
        pass

    print("Generating composite transition image...")
    comp_bytes = dalle_generate_image(api_key, composite_prompt, size, model, quality)

    entries = []
    if comp_bytes:
        comp_path_or_data = save_image_bytes(comp_bytes, "hero_composite_transition.png")
        entries.append({
            "type": "composite_transition",
            "prompt": composite_prompt,
            "output": comp_path_or_data,
            "size": size,
            "time": time_str,
            "generated_at": datetime.now().isoformat(),
        })

    if entries:
        update_metadata(entries)
        if MEMORY_ONLY:
            print("HERO_IMAGES_BASE64_START")
            print(json.dumps(entries))
            print("HERO_IMAGES_BASE64_END")
        else:
            print("\n✅ Hero composite image generated:")
            for e in entries:
                print(f"- {e['type']}: {e['output']}")
            print(f"📄 Metadata: {METADATA_PATH.relative_to(ROOT)}")
        return True

    print("❌ Failed to generate any hero images.")
    return False


if __name__ == "__main__":
    ok = main()
    raise SystemExit(0 if ok else 1)


