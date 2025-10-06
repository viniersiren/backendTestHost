#!/usr/bin/env python3
# public/data/generation/webgen/step_5/generate_site_images.py

import os
import json
import random
import logging
import sys
from pathlib import Path
from datetime import datetime

import dotenv
import openai


# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("step_5.generate_site_images")


# --- Paths ---
THIS_DIR = Path(__file__).parent
WEBGEN_DIR = THIS_DIR.parent
GENERATION_DIR = WEBGEN_DIR.parent
PROJECT_ROOT = Path(__file__).resolve().parents[5]

# Match step_2 env loading pattern: ../../../.env from this file
ENV_PATH = GENERATION_DIR / ".env"
dotenv.load_dotenv(ENV_PATH)

# Source JSONs
COMBINED_PATH = PROJECT_ROOT / "public/personal/old/jsons/combined_data.json"
ABOUT_PATH = PROJECT_ROOT / "public/personal/old/jsons/about_page.json"
SERVICES_PATH = PROJECT_ROOT / "public/personal/old/jsons/services.json"

# Output locations
OUTPUT_DIR = PROJECT_ROOT / "public/data/output/individual/step_5"
IMAGES_DIR = OUTPUT_DIR / "generated_images"
MANIFEST_PATH = OUTPUT_DIR / "generated_images_manifest.json"
os.makedirs(IMAGES_DIR, exist_ok=True)


def get_api_key():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY not set. Set it in environment or in %s", str(ENV_PATH))
        return None
    return api_key


def load_json(path: Path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Could not read %s: %s", str(path), e)
        return None


def _extract_old_paths(node) -> list[str]:
    paths: list[str] = []
    if isinstance(node, dict):
        for v in node.values():
            paths.extend(_extract_old_paths(v))
    elif isinstance(node, list):
        for v in node:
            paths.extend(_extract_old_paths(v))
    elif isinstance(node, str):
        if node.startswith("/personal/old/"):
            paths.append(node)
    return paths


def iter_imageprops_from_combined(data: dict):
    blocks = (data or {}).get("mainPageBlocks", [])
    for idx, block in enumerate(blocks):
        cfg = (block or {}).get("config", {})
        imgprops = cfg.get("ImageProps")
        if imgprops:
            related_paths = _extract_old_paths(cfg)
            yield {
                "source": "combined_data.json",
                "blockName": block.get("blockName"),
                "index": idx,
                "imageProps": imgprops,
                "context_path": f"combined.mainPageBlocks[{idx}].{block.get('blockName')}",
                "old_paths": related_paths
            }


def iter_imageprops_from_about(data: dict):
    imgprops = (data or {}).get("ImageProps")
    if imgprops:
        related_paths = _extract_old_paths(data)
        yield {
            "source": "about_page.json",
            "blockName": "AboutPage",
            "index": 0,
            "imageProps": imgprops,
            "context_path": "about.ImageProps",
            "old_paths": related_paths
        }


def iter_imageprops_from_services(data: dict):
    for group_key in ["commercial", "residential"]:
        group = (data or {}).get(group_key, [])
        for svc_idx, svc in enumerate(group):
            blocks = (svc or {}).get("blocks", [])
            for blk_idx, blk in enumerate(blocks):
                if blk.get("blockName") == "HeroBlock":
                    cfg = (blk or {}).get("config", {})
                    imgprops = cfg.get("ImageProps")
                    if imgprops:
                        related_paths = _extract_old_paths(cfg)
                        yield {
                            "source": "services.json",
                            "blockName": f"{group_key}:{svc.get('name')}::HeroBlock",
                            "index": svc_idx,
                            "imageProps": imgprops,
                            "context_path": f"services.{group_key}[{svc_idx}].HeroBlock[{blk_idx}]",
                            "old_paths": related_paths
                        }


def list_variants(variants: dict) -> list[tuple[str, str]]:
    keys = [k for k, v in variants.items() if isinstance(v, str)]
    # stable, but could random.shuffle(keys) if random order desired
    keys.sort()
    return [(k, variants[k]) for k in keys]


def pick_size_for_prompt(prompt: str) -> str:
    # Prefer wide 16:9 when mentioned; else square
    p = (prompt or "").lower()
    if "16:9" in p or "wide" in p or "panor" in p or "aerial" in p or "hero" in p:
        return "1792x1024"
    return "1024x1024"


def ensure_manifest():
    if MANIFEST_PATH.exists():
        try:
            with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"generated": [], "metadata": {"last_updated": None}}


def save_manifest(manifest: dict):
    manifest["metadata"]["last_updated"] = datetime.now().isoformat()
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)


def save_image_bytes(image_bytes: bytes, filename: str) -> str:
    out_path = IMAGES_DIR / filename
    with open(out_path, "wb") as f:
        f.write(image_bytes)
    return str(out_path)


def save_to_generation_path(image_bytes: bytes, old_path_str: str) -> str:
    # Replace /personal/old/ with /personal/generation/
    if not old_path_str.startswith("/personal/old/"):
        return ""
    rel = old_path_str.replace("/personal/old/", "/personal/generation/")
    abs_path = PROJECT_ROOT / ("public" + rel) if rel.startswith("/personal/") else PROJECT_ROOT / rel
    abs_dir = abs_path.parent
    os.makedirs(abs_dir, exist_ok=True)
    with open(abs_path, "wb") as f:
        f.write(image_bytes)
    return str(abs_path)


def generate_image(client: openai.OpenAI, prompt: str, size: str) -> bytes | None:
    try:
        resp = client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size=size,
            quality="standard",  # lowest-quality tier
            n=1,
        )
        b64 = resp.data[0].b64_json
        import base64
        return base64.b64decode(b64)
    except Exception as e:
        logger.error("Image generation failed: %s", e)
        return None


def main():
    api_key = get_api_key()
    if not api_key:
        return 1

    client = openai.OpenAI(api_key=api_key)
    manifest = ensure_manifest()

    combined = load_json(COMBINED_PATH)
    about = load_json(ABOUT_PATH)
    services = load_json(SERVICES_PATH)

    image_jobs = []
    for item in iter_imageprops_from_combined(combined):
        image_jobs.append(item)
    for item in iter_imageprops_from_about(about):
        image_jobs.append(item)
    for item in iter_imageprops_from_services(services):
        image_jobs.append(item)

    if not image_jobs:
        logger.info("No ImageProps found to process.")
        return 0

    logger.info("Found %d ImageProps groups to process", len(image_jobs))

    success_count = 0
    for job_idx, job in enumerate(image_jobs, 1):
        imgprops: dict = job["imageProps"]
        old_paths: list[str] = job.get("old_paths", [])
        path_cursor = 0

        # For each imag_genN under this ImageProps, generate ALL variants (v1..vN)
        for key, val in imgprops.items():
            if not key.startswith("imag_gen"):
                continue
            if not isinstance(val, dict):
                continue

            for variant_key, prompt in list_variants(val):
                if not prompt:
                    continue

                size = pick_size_for_prompt(prompt)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_block = (job.get("blockName") or "block").replace(" ", "_").replace("/", "-")
                filename = f"{job['source']}_{safe_block}_{key}_{variant_key}_{ts}.png"

                logger.info("[%d/%d] Generating %s %s:%s -> %s", job_idx, len(image_jobs), job["source"], key, variant_key, filename)

                img_bytes = generate_image(client, prompt, size)
                if not img_bytes:
                    continue

                # Save archive copy in step_5 folder
                path_archive = save_image_bytes(img_bytes, filename)

                # If we have related old paths, overwrite corresponding file under /personal/generation/ path
                generation_saved = ""
                if old_paths:
                    old_path = old_paths[path_cursor % len(old_paths)]
                    path_cursor += 1
                    generation_saved = save_to_generation_path(img_bytes, old_path)

                manifest["generated"].append({
                    "source": job["source"],
                    "context": job["context_path"],
                    "blockName": job.get("blockName"),
                    "imag_gen": key,
                    "variant": variant_key,
                    "size": size,
                    "prompt": prompt,
                    "file": os.path.relpath(path_archive, OUTPUT_DIR),
                    "overwrote_generation_path": generation_saved
                })
                success_count += 1

    save_manifest(manifest)
    logger.info("Generated %d images. Output: %s", success_count, str(IMAGES_DIR))
    print(f"\n✅ step_5: generated {success_count} images -> {IMAGES_DIR}")
    print(f"📄 manifest -> {MANIFEST_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())


