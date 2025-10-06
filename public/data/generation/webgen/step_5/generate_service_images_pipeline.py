#!/usr/bin/env python3
"""
Pipeline: Generate service images based on block rules.

- Default disk mode:
  - Reads services.json (default: public/personal/old/jsons/services.json)
  - For each service block, generates images and writes bytes to target paths
  - Detects MIME and corrects file extensions in JSON
  - Updates services.json in-place unless --output is provided

- Memory-only mode (no disk IO):
  - Accept JSON over STDIN with --stdin (or keep disk input with --input)
  - Generate images entirely in memory
  - Do not write any files or JSON
  - Emit a single JSON payload between markers:
      SERVICE_IMAGES_PIPELINE_START
      { "services": <updated_json>, "assets": [ { "targetPath", "mime", "dataUrl" } ] }
      SERVICE_IMAGES_PIPELINE_END

Notes:
- Targets common image fields: heroImage, backgroundImage, image, imageUrl, path, and arrays named images
- Also scans nested arrays like items[].imageUrl
- Uses ImageProps.imag_gen1.v1 as prompt when available for 'with_ai'

Usage:
  # Disk mode
  python generate_service_images_pipeline.py \
    --input /path/to/services.json \
    --output (optional path) \
    --dry-run (to preview without writing)

  # Memory-only mode (no disk)
  python generate_service_images_pipeline.py --stdin --memory-only < services.json
"""

import os
import sys
import json
import base64
import subprocess
import shlex
import argparse
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

try:
    import dotenv  # type: ignore
except Exception:
    dotenv = None

try:
    import requests  # type: ignore
except Exception:
    requests = None

try:
    import openai  # type: ignore
except Exception:
    openai = None


ROOT = Path(__file__).resolve().parents[5]
DEFAULT_INPUT = ROOT / "public/personal/old/jsons/services.json"
SWATCH_SCRIPT = ROOT / "public/data/generation/webgen/img/generate_swatch.py"

def get_generation_rule_from_block(block: Dict[str, Any]) -> str:
    """
    ✅ NEW: Get generation rule from block's ImageProps.AI_script instead of hardcoded rules.
    This allows the template to control which generator (AI vs swatch vs none) each block uses.
    """
    try:
        config = block.get("config", {})
        image_props = config.get("ImageProps", {})
        ai_script = image_props.get("AI_script", "")
        
        # Map template AI_script values to pipeline rules
        if ai_script == "AI":
            return "with_ai"
        elif ai_script == "swatch":
            return "swatch"
        elif ai_script == "false" or not ai_script:
            return "none"
        else:
            # Unknown AI_script value, default to with_ai
            print(f"WARNING: Unknown AI_script value '{ai_script}', defaulting to 'with_ai'")
            return "with_ai"
    except Exception:
        return "none"

# ✅ LEGACY FALLBACK: Keep hardcoded rules for blocks without ImageProps
BLOCK_GENERATION_RULES_FALLBACK = {
    # none
    "AccordionBlock": "none",
    "OverviewAndAdvantagesBlock": "with_ai",  # ✅ FIXED: Template shows AI_script: "AI"
    "SectionBannerBlock": "with_ai",          # ✅ FIXED: Template shows AI_script: "AI"
    "VideoCTA": "none",
    "VideoHighlightBlock": "with_ai",         # ✅ FIXED: Template shows AI_script: "AI"

    # swatch
    "CardGridBlock": "swatch",
    "OptionSelectorBlock": "swatch",
    "PricingGrid": "swatch",
    "ShingleSelectorBlock": "swatch",
    "SwatchShowcase": "swatch",
    "ThreeGridWithRichTextBlock": "swatch",

    # with_ai
    "CallToActionButtonBlock": "with_ai",
    "GeneralList": "with_ai",
    "HeroBlock": "with_ai",
    "GeneralListVariant2": "with_ai",
    "ImageFeatureListBlock": "with_ai",
    "ListImageVerticalBlock": "with_ai",
    "NumberedImageTextBlock": "with_ai",
    "TextImageBlock": "with_ai",
}

IMAGE_KEYS = {
    "heroImage",
    "backgroundImage",
    "image",
    "imageUrl",
    "path",  # e.g., Design.Bg.path
}
IMAGE_ARRAY_KEYS = {
    "images",
}


def load_env(env_dir: Path) -> None:
    if dotenv is None:
        return
    env_path = env_dir / ".env"
    try:
        dotenv.load_dotenv(env_path, override=True)
    except Exception:
        pass


def ensure_dir_for_file(file_path: Path) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)


def sniff_mime(image_bytes: bytes) -> str:
    # Very small and robust header-based detection
    if len(image_bytes) >= 8 and image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(image_bytes) >= 3 and image_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    # Fallback
    return "image/png"


def ext_for_mime(mime: str) -> str:
    m = (mime or "").lower()
    if "jpeg" in m or m.endswith("/jpg"):
        return ".jpg"
    if "png" in m:
        return ".png"
    if "webp" in m:
        return ".webp"
    return ".png"


def replace_extension(path_str: str, new_ext: str) -> str:
    p = Path(path_str)
    return str(p.with_suffix(new_ext))


def collect_image_targets_from_block(block: Dict[str, Any]) -> List[Tuple[List[str], str]]:
    """
    Returns a list of (json_path_segments, current_value) for image fields.
    json_path_segments is a list of keys/indexes to reach the string field.
    ✅ NEW: Scans both old flat structure AND new Content/Design/Formatting structure
    """
    results: List[Tuple[List[str], str]] = []

    def walk(obj: Any, path: List[str]) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                new_path = path + [k]
                if k in IMAGE_KEYS and isinstance(v, str):
                    results.append((new_path, v))
                elif k in IMAGE_ARRAY_KEYS and isinstance(v, list):
                    # Collect string paths in arrays named 'images'
                    for idx, item in enumerate(v):
                        if isinstance(item, str):
                            results.append((new_path + [str(idx)], item))
                        elif isinstance(item, dict):
                            # if array of objects with url/originalUrl
                            if isinstance(item.get("url"), str):
                                results.append((new_path + [str(idx), "url"], item["url"]))
                            if isinstance(item.get("originalUrl"), str):
                                results.append((new_path + [str(idx), "originalUrl"], item["originalUrl"]))
                else:
                    walk(v, new_path)
        elif isinstance(obj, list):
            for idx, item in enumerate(obj):
                walk(item, path + [str(idx)])

    cfg = block.get("config", {})
    
    # ✅ NEW: Scan Content/Design/Formatting structure (new standardized format)
    content = cfg.get("Content", {})
    if isinstance(content, dict):
        walk(content, ["config", "Content"])
    
    design = cfg.get("Design", {})
    if isinstance(design, dict):
        walk(design, ["config", "Design"])
    
    formatting = cfg.get("Formatting", {})
    if isinstance(formatting, dict):
        walk(formatting, ["config", "Formatting"])
    
    # ✅ BACKWARD COMPATIBILITY: Also scan top-level config for old flat structure
    walk(cfg, ["config"])
    
    return results


def get_prompt_for_block(block_name: str, config: Dict[str, Any]) -> str:
    # ✅ NEW: Check for prompt_1, prompt_2, etc. created by generate_service_jsons.py
    image_props = config.get("ImageProps") if isinstance(config, dict) else None
    if isinstance(image_props, dict):
        # First priority: template-generated prompts (prompt_1, prompt_2, etc.)
        for i in range(1, 10):
            prompt_key = f"prompt_{i}"
            if prompt_key in image_props and isinstance(image_props[prompt_key], str) and image_props[prompt_key].strip():
                return image_props[prompt_key].strip()
        
        # Second priority: legacy imag_gen1.v1 structure (backward compatibility)
        group = image_props.get("imag_gen1")
        if isinstance(group, dict):
            for key_choice in ("v1", "v2", "v3", "v4", "v5"):
                if isinstance(group.get(key_choice), str) and group[key_choice].strip():
                    return group[key_choice].strip()

    # Fallback prompts per block type
    generic = {
        "HeroBlock": "Hero: high-quality roofing scene, 16:9, photorealistic, professional lighting",
        "GeneralList": "Professional roofing related image for marketing context, clean composition",
        "GeneralListVariant2": "Professional roofing service showcase photo, high detail, clean background",
        "ImageFeatureListBlock": "Photorealistic product/service image illustrating listed feature, neutral background",
        "ListImageVerticalBlock": "Vertical service feature image, professional, crisp details",
        "NumberedImageTextBlock": "Step-by-step process image, clear subject, informative, clean",
        "TextImageBlock": "Text + image layout supporting image, professional, clean background",
        "CallToActionButtonBlock": "CTA supportive product photo, minimalistic, high contrast, clean background",
    }
    return generic.get(block_name, "Professional roofing marketing image, photorealistic, clean background")


def openai_generate_image_bytes(api_key: str, prompt: str, size: str = "1024x1024", model: str = "gpt-image-1", quality: str = "high") -> Optional[bytes]:
    if openai is None:
        print("ERROR: openai package not available.")
        return None
    try:
        client = openai.OpenAI(api_key=api_key)
        resp = client.images.generate(
            model=model,
            prompt=prompt,
            size=size,
            quality=quality,
            n=1,
        )
        data = resp.data[0]
        b64 = getattr(data, "b64_json", None)
        if b64:
            return base64.b64decode(b64)
        url = getattr(data, "url", None)
        if url and requests is not None:
            r = requests.get(url, timeout=120)
            r.raise_for_status()
            return r.content
    except Exception as e:
        print(f"OpenAI image generation failed: {e}")
    return None


def run_swatch_and_get_bytes(material: str = "asphalt shingles", swatch_name: Optional[str] = None, size: str = "1024x1024", custom_prompt: Optional[str] = None) -> Optional[bytes]:
    """
    ✅ ENHANCED: Run generate_swatch.py in MEMORY_ONLY=1 mode and capture the base64 image.
    Now supports custom prompts from template for more specific swatch generation.
    """
    if not SWATCH_SCRIPT.exists():
        print(f"ERROR: Swatch script not found at {SWATCH_SCRIPT}")
        return None

    # ✅ NEW: If custom prompt provided, extract material hint from it
    if custom_prompt and isinstance(custom_prompt, str):
        prompt_lower = custom_prompt.lower()
        # Try to extract material type from prompt
        if "cedar" in prompt_lower:
            material = "cedar shingles"
        elif "metal" in prompt_lower:
            material = "metal roofing"
        elif "slate" in prompt_lower:
            material = "slate shingles"
        elif "tile" in prompt_lower:
            material = "clay tile"
        elif "concrete" in prompt_lower:
            material = "concrete tile"
        # Default to asphalt shingles if no specific material detected

    payload = {
        "material": material,
        "name": swatch_name or "",
        "size": size,
    }
    env = os.environ.copy()
    env["MEMORY_ONLY"] = "1"
    cmd = f"{shlex.quote(sys.executable)} {shlex.quote(str(SWATCH_SCRIPT))}"
    try:
        proc = subprocess.run(
            cmd,
            input=json.dumps(payload).encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            shell=True,
            check=False,
        )
        out = proc.stdout.decode("utf-8", errors="ignore")
        # Look for marker from generate_swatch.py
        start_tag = "SWATCH_IMAGE_BASE64_START"
        end_tag = "SWATCH_IMAGE_BASE64_END"
        if start_tag in out and end_tag in out:
            json_part = out.split(start_tag, 1)[1].split(end_tag, 1)[0].strip()
            data_obj = json.loads(json_part)
            data_url = data_obj.get("output", "")
            if isinstance(data_url, str) and data_url.startswith("data:image/"):
                try:
                    meta, b64data = data_url.split(",", 1)
                    return base64.b64decode(b64data)
                except Exception:
                    return None
        # Fallback: try to parse alternative prints
        # Not found
        print("WARNING: Could not parse swatch output; stderr:", proc.stderr.decode("utf-8", errors="ignore"))
        return None
    except Exception as e:
        print(f"Failed running swatch script: {e}")
        return None


def set_in(obj: Any, path: List[str], value: Any) -> None:
    cur = obj
    for i, key in enumerate(path):
        is_last = i == len(path) - 1
        # index or key?
        if isinstance(cur, list):
            idx = int(key)
            if is_last:
                cur[idx] = value
            else:
                cur = cur[idx]
        else:
            if is_last:
                cur[key] = value
            else:
                if key not in cur:
                    # create container based on next path type guess
                    try:
                        nxt = int(path[i + 1])
                        cur[key] = []
                    except Exception:
                        cur[key] = {}
                cur = cur[key]


def get_from(obj: Any, path: List[str]) -> Any:
    cur = obj
    for key in path:
        if isinstance(cur, list):
            cur = cur[int(key)]
        else:
            cur = cur.get(key)
    return cur


def parse_in_images_count(value: Any) -> int:
    """
    ✅ NEW: Parse in_images value like '3-6' or '2-4' or '0' into an integer image count.
    Special rule: for '2-4', choose either 2 or 4 (never 3) to match generate_service_jsons.py logic.
    """
    try:
        if isinstance(value, int):
            return max(0, value)
        s = str(value).strip()
        if not s:
            return 0
        if '-' in s:
            parts = s.split('-')
            lo = int(parts[0].strip())
            hi = int(parts[1].strip())
            # ✅ SPECIAL RULE: 2-4 → choose 2 or 4 (match generate_service_jsons.py line 228-229)
            if lo == 2 and hi == 4:
                import random
                return random.choice([2, 4])
            if hi < lo:
                lo, hi = hi, lo
            import random
            return random.randint(lo, hi)
        return max(0, int(s))
    except Exception:
        return 0

def get_image_count_from_block(block: Dict[str, Any]) -> int:
    """
    ✅ NEW: Get the number of images to generate for this block from ImageProps.in_images.
    """
    try:
        config = block.get("config", {})
        image_props = config.get("ImageProps", {})
        in_images = image_props.get("in_images", "0")
        return parse_in_images_count(in_images)
    except Exception:
        return 0

def choose_size(block_name: str, field_key_path: List[str]) -> str:
    if block_name == "HeroBlock" or (len(field_key_path) and field_key_path[-1] == "heroImage"):
        return "1536x1024"
    return "1024x1024"


def map_old_to_generation_path(p: str) -> str:
    """
    ✅ NEW: Map paths to match generate_service_jsons.py output structure.
    Converts: /personal/old/img/services/residential/1/HeroBlock/file.jpg
    To: /generation/img/services/residential/svc_1/HeroBlock/file.jpg
    """
    if isinstance(p, str):
        # Handle service-specific paths with svc_{id} pattern
        if p.startswith("/personal/old/img/services/"):
            # Split: /personal/old/img/services/category/id/block/file.jpg
            parts = p.split('/')
            if len(parts) >= 7:  # Ensure we have enough parts
                category = parts[5]  # residential/commercial
                service_id = parts[6]  # 1, 2, 3, 4
                remaining = '/'.join(parts[7:])  # HeroBlock/file.jpg or just file.jpg
                return f"/generation/img/services/{category}/svc_{service_id}/{remaining}"
        
        # Handle other /personal/old/ paths
        elif p.startswith("/personal/old/"):
            return "/generation/" + p[len("/personal/old/"):]
    
    return p


def _to_data_url(mime: str, image_bytes: bytes) -> str:
    import base64 as _b64
    try:
        return f"data:{mime};base64,{_b64.b64encode(image_bytes).decode('utf-8')}"
    except Exception:
        return ""


def process_services(services: Dict[str, Any], dry_run: bool = False, memory_only: bool = False) -> Tuple[Dict[str, Any], int, int, List[Dict[str, Any]]]:
    """
    Iterate through services JSON, generate images, write to target paths, and update JSON with corrected extensions.
    Returns (updated_json, num_generated, num_skipped, assets)
    - assets is a list of { targetPath, mime, dataUrl } in memory_only mode; otherwise empty.
    """
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        print("WARNING: OPENAI_API_KEY not set; 'with_ai' generations will be skipped.")

    total_generated = 0
    total_skipped = 0
    assets: List[Dict[str, Any]] = []

    for category_key in ("commercial", "residential"):
        groups = services.get(category_key) or []
        if not isinstance(groups, list):
            continue
        for svc in groups:
            blocks = svc.get("blocks") or []
            if not isinstance(blocks, list):
                continue
            for block in blocks:
                block_name = block.get("blockName")
                # ✅ NEW: Get rule from block's ImageProps.AI_script first, fallback to hardcoded
                rule = get_generation_rule_from_block(block)
                if rule == "none":
                    # Try fallback rules for blocks without ImageProps
                    rule = BLOCK_GENERATION_RULES_FALLBACK.get(block_name, "none")
                
                if rule == "none":
                    total_skipped += 1
                    continue

                # ✅ NEW: Generate images based on template's in_images count instead of existing paths
                cfg = block.get("config", {})
                image_count = get_image_count_from_block(block)
                
                # Skip blocks with 0 images or no generation rule
                if image_count <= 0:
                    total_skipped += 1
                    continue

                # Get existing targets to understand path structure, but generate based on count
                targets = collect_image_targets_from_block(block)
                
                # Generate the specified number of images for this block
                for img_index in range(image_count):
                    # Determine base path structure from existing targets or create formulaic path
                    if targets and img_index < len(targets):
                        # Use existing path as template
                        path_segments, current_str = targets[img_index]
                        base_path = current_str
                    else:
                        # ✅ FORMULAIC PATH: Create path following old structure, will be mapped to generation
                        service_id = svc.get("id", 1)
                        base_path = f"/personal/old/img/services/{category_key}/{service_id}/{block_name}/{img_index + 1}.jpg"
                        
                        # ✅ SMART PATH SEGMENTS: Determine where to store this image in the JSON structure
                        if cfg.get("Content") and "images" in cfg.get("Content", {}):
                            # Add to Content.images array
                            path_segments = ["config", "Content", "images", str(img_index)]
                        elif cfg.get("Design", {}).get("Bg") and img_index == 0:
                            # First image goes to Design.Bg.path for background images
                            path_segments = ["config", "Design", "Bg", "path"]
                        elif cfg.get("Content"):
                            # Create Content.images array if it doesn't exist
                            if "images" not in cfg.get("Content", {}):
                                cfg.setdefault("Content", {})["images"] = []
                            path_segments = ["config", "Content", "images", str(img_index)]
                        else:
                            # Fallback: create top-level images array
                            if "images" not in cfg:
                                cfg["images"] = []
                            path_segments = ["config", "images", str(img_index)]

                    # Decide generation method
                    size = choose_size(block_name, path_segments)
                    image_bytes: Optional[bytes] = None
                    
                    if rule == "swatch":
                        # ✅ ENHANCED: Use template prompt for swatch if available
                        swatch_prompt = get_prompt_for_block(block_name, cfg)
                        material = "asphalt shingles"  # Default material
                        image_bytes = run_swatch_and_get_bytes(material=material, swatch_name=None, size=size, custom_prompt=swatch_prompt)
                    elif rule == "with_ai" and api_key:
                        prompt = get_prompt_for_block(block_name, cfg)
                        image_bytes = openai_generate_image_bytes(api_key=api_key, prompt=prompt, size=size)

                    if image_bytes is None:
                        total_skipped += 1
                        continue

                    # ✅ MIME CORRECTION: Update path extension to match generated MIME
                    mime = sniff_mime(image_bytes)
                    new_ext = ext_for_mime(mime)
                    mapped = map_old_to_generation_path(base_path)
                    updated_path_str = replace_extension(mapped, new_ext)
                    abs_target = ROOT / "public" / updated_path_str.lstrip("/")

                    if not dry_run and not memory_only:
                        ensure_dir_for_file(abs_target)
                        try:
                            with open(abs_target, "wb") as f:
                                f.write(image_bytes)
                        except Exception as e:
                            print(f"Failed to write {abs_target}: {e}")
                            total_skipped += 1
                            continue
                    elif memory_only:
                        # Collect a memory asset with data URL so callers can persist/preview as needed
                        assets.append({
                            "targetPath": updated_path_str,
                            "mime": mime,
                            "dataUrl": _to_data_url(mime, image_bytes),
                        })

                    # ✅ UPDATE JSON: Set the corrected path in the services JSON
                    if updated_path_str != base_path:
                        set_in(block, path_segments, updated_path_str)

                    total_generated += 1
                    print(f"Generated: {updated_path_str} ({rule}, {mime})")

    return services, total_generated, total_skipped, assets


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate service images based on block rules and update JSON paths.")
    parser.add_argument("--input", type=str, default=str(DEFAULT_INPUT), help="Path to services.json")
    parser.add_argument("--output", type=str, default=None, help="Optional path to write updated JSON (defaults to overwrite input)")
    parser.add_argument("--dry-run", action="store_true", help="Do not write files or JSON; just print plan")
    parser.add_argument("--stdin", action="store_true", help="Read services JSON from STDIN instead of --input path")
    parser.add_argument("--memory-only", action="store_true", help="Do not write any files or JSON; emit results with markers to STDOUT")
    args = parser.parse_args()

    # Load env from public/data/generation/.env to match other scripts
    load_env(ROOT / "public/data/generation")

    memory_only = bool(args.memory_only or os.environ.get("MEMORY_ONLY") == "1")

    # Load services data
    if args.stdin:
        try:
            raw = sys.stdin.read()
            data = json.loads(raw)
        except Exception as e:
            print(f"ERROR: Failed to read JSON from STDIN: {e}")
            return 1
    else:
        input_path = Path(args.input)
        if not input_path.exists():
            print(f"ERROR: Input JSON not found: {input_path}")
            return 1
        try:
            with open(input_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"ERROR: Failed to read JSON: {e}")
            return 1

    updated, generated, skipped, assets = process_services(data, dry_run=args.dry_run, memory_only=memory_only)

    print(f"Generated: {generated} images; Skipped: {skipped}")

    # Memory-only: emit markers and do not write
    if memory_only:
        try:
            print("SERVICE_IMAGES_PIPELINE_START")
            print(json.dumps({
                "services": updated,
                "assets": assets,
            }, ensure_ascii=False))
            print("SERVICE_IMAGES_PIPELINE_END")
        except Exception as e:
            print(f"ERROR: Failed to emit memory-only payload: {e}")
            return 1
        return 0

    if args.dry_run:
        print("Dry-run: not writing JSON.")
        return 0

    output_path = Path(args.output) if args.output else input_path
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(updated, f, ensure_ascii=False, indent=2)
        print(f"Updated JSON written to: {output_path}")
    except Exception as e:
        print(f"ERROR: Failed to write updated JSON: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())


