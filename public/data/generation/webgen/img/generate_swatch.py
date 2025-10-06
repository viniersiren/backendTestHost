#!/usr/bin/env python3
"""
Generate a photorealistic square material swatch (top‑down) for asphalt shingles.

Default swatch:
- Dark gray asphalt shingles with subtle lighter/brown accents
- Perfectly orthogonal, top‑down view (no perspective tilt)
- No context (no house/roof/background) – pure material sample
- Uniform repeating layout, gritty texture

Outputs:
- public/data/generation/webgen/img/output/shingle_swatch.png
- public/data/generation/webgen/img/generated_swatches.json (metadata)

You can override size with SWATCH_SIZE (e.g., 1024x1024, 1536x1536).
Model/quality are hardcoded to gpt-image-1, medium for consistency with other assets.
"""

import os
import json
from pathlib import Path
from datetime import datetime
import base64
import requests
from typing import Optional, Dict, Any
import sys
import argparse
import dotenv
import openai
import random


# Paths
ROOT = Path(__file__).resolve().parents[5]
IMG_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = IMG_DIR / "output"
METADATA_PATH = IMG_DIR / "generated_swatches.json"

MEMORY_ONLY = os.environ.get("MEMORY_ONLY", "0") == "1"

# Load API key from .env
try:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    dotenv.load_dotenv(env_path, override=True)
except Exception:
    pass


def get_api_key() -> Optional[str]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY is not set.")
        return None
    return api_key


def build_swatch_prompt(material: str, swatch_name: Optional[str]) -> str:
    mat = (material or "asphalt shingles").strip().lower()
    name_clause = f" Style/Name: '{swatch_name}'." if swatch_name else ""

    # Small helper to pick one descriptor from a list for variety
    def pick(*choices: str) -> str:
        return random.choice(list(choices))

    # Material-specific templates to amplify visual diversity
    if "architectural asphalt" in mat or ("asphalt" in mat and "architectural" in mat):
        tone = pick("charcoal", "weathered wood", "slate", "driftwood", "midnight black", "bark brown")
        return (
            f"A square, orthographic TOP‑DOWN SAMPLE of ARCHITECTURAL asphalt shingles in {tone} tones. "
            "Dimensional laminated tabs with staggered lengths, crisp granule texture, subtle color variation across courses. "
            "Even studio lighting, no perspective, no roof context, no logos; uniform repeating layout with realistic mineral sparkle." + name_clause
        )
    if "3-tab" in mat or ("asphalt" in mat and "3" in mat):
        tone = pick("slate gray", "pewter", "desert tan", "harbor blue")
        return (
            f"A top‑down PRODUCT SWATCH of 3‑TAB asphalt shingles in {tone}. "
            "Rectangular tabs perfectly aligned in repeating rows; crisp cutouts, minimal shadowing, fine granule detail. "
            "No background or house; flat orthographic view; evenly lit, high detail, photorealistic." + name_clause
        )
    if "luxury asphalt" in mat or ("asphalt" in mat and "luxury" in mat):
        tone = pick("rich graphite", "dark mocha", "antique slate")
        return (
            f"An orthographic SAMPLE of LUXURY asphalt shingles in {tone}, deep dimensional cuts and thick shadow lines. "
            "High-contrast granule mix, premium finish; uniform repeating pattern, no perspective, no roof context." + name_clause
        )
    if "impact" in mat:
        return (
            "Orthographic SAMPLE of IMPACT‑RESISTANT asphalt shingles; dense, robust mat with tightly packed granules, "
            "low sheen; repeating layout with subtle micro‑color flecks; even lighting, no perspective or background." + name_clause
        )
    if "cool roof" in mat:
        return (
            "Orthographic SAMPLE of COOL‑ROOF asphalt shingles; high‑albedo light gray/stone blend with reflective granules; "
            "uniform repeating layout, crisp detail, even studio light; no context, no logos." + name_clause
        )
    if "cedar shake" in mat or "cedar" in mat:
        tone = pick("golden honey", "driftwood gray", "cinnamon brown")
        texture = pick("hand‑split", "tapersawn")
        return (
            f"A square, top‑down SAMPLE of {texture} CEDAR shake shingles in {tone}. "
            "Visible wood grain, slight thickness variation, tight rows with small gaps; natural matte finish; uniform repeating layout. "
            "No roof context, no perspective, high detail." + name_clause
        )
    if "composite" in mat:
        return (
            "Top‑down SAMPLE of COMPOSITE shingle material: subtle embossing, consistent coloration with gentle variegation, "
            "clean edges and repeatable pattern; even light; no context; photorealistic granularity." + name_clause
        )
    if "rubber" in mat:
        return (
            "Orthographic SAMPLE of RECYCLED RUBBER shingles: fine speckled texture, slightly soft edges, low sheen; "
            "uniform repeating layout under even studio light; no perspective, no context." + name_clause
        )
    if "standing seam" in mat or ("metal" in mat and "standing" in mat):
        color = pick("matte charcoal", "forest green", "barn red", "slate blue")
        return (
            f"Orthographic SAMPLE panel of STANDING‑SEAM METAL roofing in {color}; crisp vertical ribs at regular spacing, "
            "light micro‑texture on paint finish; flat lit, no perspective; repeating pattern only." + name_clause
        )
    if "corrugated" in mat or ("metal" in mat and "corrugated" in mat):
        return (
            "Top‑down SAMPLE of CORRUGATED METAL paneling: rhythmic sine‑wave corrugations, zinc‑coated steel with light patina; "
            "even studio lighting; repeating layout only; no building context." + name_clause
        )
    if "stone-coated steel" in mat or ("stone" in mat and "steel" in mat):
        return (
            "Orthographic SAMPLE of STONE‑COATED STEEL tile: granulated surface with speckled multi‑tone chips, interlocking profile repeated; "
            "matte finish; flat lighting; no context." + name_clause
        )
    if "aluminum" in mat:
        return (
            "Top‑down SAMPLE of ALUMINUM shingle: crisp stamped pattern with slight emboss, satin metallic finish; "
            "repeating grid, uniform lighting; no perspective or background." + name_clause
        )
    if "copper" in mat:
        return (
            "Orthographic SAMPLE of COPPER roofing tile: warm metallic tones with subtle brushed texture; repeating tile layout; "
            "even studio lighting; no context." + name_clause
        )
    if "slate" in mat:
        hue = pick("blue‑gray", "charcoal", "greenish slate")
        return (
            f"Top‑down SAMPLE of NATURAL SLATE shingles in {hue}; irregular micro‑cleft texture, crisp chiseled edges, "
            "staggered joints; uniform repeating layout; flat light; no context." + name_clause
        )
    if "clay" in mat:
        return (
            "Orthographic SAMPLE of CLAY barrel tiles: rounded profiles with warm terracotta hues, slight glaze; "
            "regular repeating arcs; even light; no context." + name_clause
        )
    if "concrete" in mat:
        return (
            "Top‑down SAMPLE of CONCRETE roof tiles: subtle sand texture, muted gray/tan tones, crisp molded edges; "
            "uniform repeating rows; no perspective; no context." + name_clause
        )
    if "synthetic tile" in mat or ("synthetic" in mat and "tile" in mat):
        return (
            "Orthographic SAMPLE of SYNTHETIC roof tile: finely controlled texture with slight surface sheen, consistent color, "
            "repeatable interlock pattern; even light; no context." + name_clause
        )
    # Default: asphalt shingles top‑down swatch
    base_tone = pick("dark gray", "graphite", "warm brown", "slate mix")
    return (
        f"A flat, square SAMPLE SWATCH image of asphalt roof shingles in {base_tone}, viewed straight down from above (perfect orthographic top‑down). "
        "Show ONLY the shingle material pattern and texture — no house, no roof, no background. "
        "Uniform repeating layout, detailed gritty mineral granules with subtle multi‑tone variation. "
        "No perspective tilt, no shadowed edges, no logos or text. Photorealistic, evenly lit, high detail." + name_clause
    )


def generate_image(api_key: str, prompt: str, size: str = "1024x1024") -> Optional[bytes]:
    client = openai.OpenAI(api_key=api_key)
    model = "gpt-image-1"
    quality = "medium"
    try:
        resp = client.images.generate(
            model=model,
            prompt=prompt,
            size=size,
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
            img = requests.get(image_url, timeout=120)
            img.raise_for_status()
            return img.content
    except Exception as e:
        print(f"Image generation failed: {e}")
        return None
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


def update_metadata(entry: Dict[str, Any]) -> None:
    try:
        meta = {"generated_swatches": [], "metadata": {"last_updated": datetime.now().isoformat()}}
        if METADATA_PATH.exists() and not MEMORY_ONLY:
            with open(METADATA_PATH, "r", encoding="utf-8") as f:
                meta = json.load(f)
        meta["generated_swatches"].append(entry)
        meta["metadata"]["last_updated"] = datetime.now().isoformat()
        if not MEMORY_ONLY:
            with open(METADATA_PATH, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Failed to update metadata: {e}")


def main():
    parser = argparse.ArgumentParser(description="Generate an asphalt shingle swatch (top‑down)")
    parser.add_argument("--name", dest="swatch_name", type=str, default=os.environ.get("SWATCH_NAME", ""), help="Optional material style/name, e.g., 'Weathered Wood'")
    parser.add_argument("--material", dest="material", type=str, default=os.environ.get("SWATCH_MATERIAL", "asphalt shingles"), help="Material type, e.g., 'asphalt shingles' or 'aluminum gutter'")
    parser.add_argument("--size", dest="swatch_size", type=str, default=os.environ.get("SWATCH_SIZE", "1024x1024"), help="Swatch size, e.g., 1024x1024")
    args = parser.parse_args()
    # Allow stdin JSON for memory-only orchestration (e.g., selected material/name)
    stdin_payload: Dict[str, Any] = {}
    try:
        raw = sys.stdin.read()
        if raw:
            stdin_payload = json.loads(raw)
    except Exception:
        stdin_payload = {}
    api_key = get_api_key()
    if not api_key:
        return False

    material = (stdin_payload.get("material") or args.material)
    swatch_name = (stdin_payload.get("name") or (args.swatch_name.strip() if args.swatch_name else None))
    prompt = build_swatch_prompt(material, swatch_name)
    size = stdin_payload.get("size") or args.swatch_size

    print("Generating shingle swatch (top‑down sample)...")
    img_bytes = generate_image(api_key, prompt, size)
    if not img_bytes:
        print("❌ Failed to generate swatch image")
        return False

    path_or_data = save_image_bytes(img_bytes, "shingle_swatch.png")
    update_metadata({
        "type": "shingle_swatch",
        "name": args.swatch_name.strip() if args.swatch_name else None,
        "prompt": prompt,
        "output": path_or_data,
        "size": size,
        "generated_at": datetime.now().isoformat(),
        "model": "gpt-image-1",
        "quality": "medium",
    })

    if MEMORY_ONLY:
        print("SWATCH_IMAGE_BASE64_START")
        print(json.dumps({"output": path_or_data}))
        print("SWATCH_IMAGE_BASE64_END")
    else:
        print("\n✅ Swatch image generated:")
        print(f"- output: {path_or_data}")
        print(f"📄 Metadata: {METADATA_PATH.relative_to(ROOT)}")
    return True


if __name__ == "__main__":
    ok = main()
    raise SystemExit(0 if ok else 1)


