#!/usr/bin/env python3
"""
Generate Employee Headshot Images from combined_data.json (memory-only friendly)

Inputs (via stdin JSON when MEMORY_ONLY=1):
- combinedJson: the in-memory combined_data.json payload (object)
- templatePath: optional absolute path to a reference image template to guide style
- quality: optional image quality (low|medium|high). Default: medium
- size: optional output size (e.g., 1024x1024). Default: 1024x1024

Environment:
- OPENAI_API_KEY must be set
- MEMORY_ONLY=1 → emit base64 data URLs instead of writing files
- EMP_IMAGE_MODEL (default: "gpt-image-1")
- EMP_IMAGE_QUALITY (default: "medium")
- EMP_IMAGE_SIZE (default: "1024x1024")

Output:
- When MEMORY_ONLY=1, prints markers EMPLOYEE_IMAGES_BASE64_START/END around JSON list
  of objects: [{ name, output, originalJsonPath, updatedJsonPath }]

Notes:
- This script mirrors the structure used by generate_hero_transition.py
- If a template image is provided, it is acknowledged in prompts. The current
  OpenAI images.generate API does not support passing a reference bitmap directly
  in the same call path we use here; we therefore use textual guidance about style.
"""

import os
import sys
import json
import base64
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional

import dotenv
import openai
import requests


ROOT = Path(__file__).resolve().parents[5]  # projects/roofing-co
MEMORY_ONLY = os.environ.get("MEMORY_ONLY", "0") == "1"

# Load .env located under public/data/generation/.env (same convention as hero)
try:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    dotenv.load_dotenv(env_path)
except Exception:
    pass


def get_api_key() -> Optional[str]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY is not set. Aborting employee image generation.")
        return None
    return api_key


def read_stdin_payload() -> Dict[str, Any]:
    try:
        data = sys.stdin.read()
        if not data:
            return {}
        return json.loads(data)
    except Exception:
        return {}


def normalize_model(name: str) -> str:
    m = (name or "").strip().lower()
    if m in {"image-generate-1", "gpt-image", "gpt-image1", "gpt_image_1"}:
        return "gpt-image-1"
    return name or "gpt-image-1"


def determine_employees(combined: Dict[str, Any]) -> List[Dict[str, Any]]:
    # Look for EmployeesBlock in combined.mainPageBlocks
    employees: List[Dict[str, Any]] = []
    try:
        blocks = combined.get("mainPageBlocks") or []
        for blk in blocks:
            if (blk or {}).get("blockName") == "EmployeesBlock":
                cfg = (blk or {}).get("config") or {}
                # New structure
                if cfg.get("Content") and isinstance(cfg["Content"].get("employees"), list):
                    for idx, emp in enumerate(cfg["Content"]["employees"]):
                        employees.append({
                            "index": idx,
                            "name": (emp or {}).get("name") or (emp or {}).get("fullName") or "",
                            "role": (emp or {}).get("role") or (emp or {}).get("title") or "",
                            "image": (emp or {}).get("image"),
                            # Provide a JSON path string to the image location for patching
                            "jsonPath": f"mainPageBlocks[{blocks.index(blk)}].config.Content.employees[{idx}].image",
                        })
                else:
                    # Old structure fallback: blk.config.employee array
                    emp_list = (cfg or {}).get("employee") or []
                    for idx, emp in enumerate(emp_list):
                        employees.append({
                            "index": idx,
                            "name": (emp or {}).get("name") or (emp or {}).get("fullName") or "",
                            "role": (emp or {}).get("role") or (emp or {}).get("title") or "",
                            "image": (emp or {}).get("image"),
                            "jsonPath": f"mainPageBlocks[{blocks.index(blk)}].config.employee[{idx}].image",
                        })
                break
    except Exception:
        pass
    return employees


def image_value_to_path(val: Any) -> Optional[str]:
    # Convert string or {url, originalUrl} structures to a concrete string path if possible
    try:
        if isinstance(val, str):
            return val
        if isinstance(val, dict):
            if isinstance(val.get("originalUrl"), str):
                return val["originalUrl"]
            if isinstance(val.get("url"), str):
                return val["url"]
    except Exception:
        pass
    return None


def replace_ext(filename: str, new_ext: str) -> str:
    try:
        base = filename
        if "." in filename:
            base = filename[: filename.rfind(".")]
        if new_ext.startswith("."):
            return base + new_ext
        return base + "." + new_ext
    except Exception:
        return filename


def old_to_generation(path: Optional[str]) -> Optional[str]:
    try:
        if isinstance(path, str) and path.startswith('/personal/old/'):
            return '/generation/' + path[len('/personal/old/'):]
        return path
    except Exception:
        return path


def images_generate(
    api_key: str,
    prompt: str,
    size: str = "1024x1024",
    model: str = "gpt-image-1",
    quality: str = "medium",
) -> Optional[bytes]:
    client = openai.OpenAI(api_key=api_key)
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
            try:
                img = requests.get(image_url, timeout=120)
                img.raise_for_status()
                return img.content
            except Exception:
                return None
    except Exception:
        return None
    return None


def to_data_url(image_bytes: bytes, mime: str = "image/png") -> str:
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def main() -> bool:
    api_key = get_api_key()
    if not api_key:
        return False

    payload = read_stdin_payload()
    combined = payload.get("combinedJson") or {}
    template_path = payload.get("templatePath") or ""
    requested_quality = (payload.get("quality") or os.environ.get("EMP_IMAGE_QUALITY") or "medium").strip().lower()
    if requested_quality not in {"low", "medium", "high"}:
        requested_quality = "medium"
    size = payload.get("size") or os.environ.get("EMP_IMAGE_SIZE") or "1024x1024"
    model = normalize_model(os.environ.get("EMP_IMAGE_MODEL", "gpt-image-1"))

    # Attempt to load reference template if present (used for prompt guidance)
    template_hint = ""
    try:
        if template_path and Path(template_path).exists():
            template_hint = " Use the provided reference template as a guide for composition, lighting, and framing."
        else:
            template_path = ""
    except Exception:
        template_path = ""

    employees = determine_employees(combined)
    outputs: List[Dict[str, Any]] = []

    for emp in employees:
        name = (emp.get("name") or "").strip()
        role = (emp.get("role") or "").strip()
        img_val = emp.get("image")
        original_path = image_value_to_path(img_val) or "/personal/old/img/main_page_images/EmployeesBlock/employee.png"
        file_name = Path(original_path).name or "employee.png"
        base_name = file_name

        # Role-aware wardrobe guardrails: always roofer aesthetic (never formal)
        role_note = ""
        try:
            low = (role or "").lower()
            if any(k in low for k in ["manager", "owner", "sales", "coo", "ceo", "cmo", "cfo", "director"]):
                role_note = " Keep attire field-ready and roofer-like; avoid suits, ties, or formal office wear."
        except Exception:
            pass

        # Detailed avatar description (semi-realistic 3D avatar, roofer aesthetic)
        avatar_desc = (
            "Create a chest-up 3D avatar portrait of a roofer. Semi-realistic but simplified (no visible skin pores or micro-wrinkles). "
            "Soft, natural lighting with a subtle 45° key light and gentle rim light. Subject centered, looking at camera, friendly expression.\n"
            "Attire guidance: Maintain a roofer aesthetic and appropriate field/PPE look (e.g., hard hat or workwear may be present), "
            "but DO NOT make all portraits appear in the exact same outfit. Subtly vary colors and garments across different employees. "
            "Avoid brand logos and avoid formal business attire (no suits/ties). Wardrobe should be suggested, not strictly enforced.\n"
            "Style & geometry: Smooth, simplified facial features (rounded nose, simple eyebrows, oval eyes, soft beard shape); "
            "clean, sculpted forms; minimal surface detail; soft shadowing; slight subsurface look; materials read as plastic/clay-like with gentle speculars (not photoreal).\n"
            "Framing & background: Head and shoulders only (no hands); warm beige gradient background with a faint circular halo behind the head; "
            "shallow depth of field with softly blurred background; no text, no watermark, no extra objects.\n"
            "Color & mood: Warm, approachable palette; balanced exposure; no harsh contrast; no dramatic effects.\n"
            "Output: Square aspect 1:1, 1024x1024, sRGB."
        )

        # Build prompt with name/role context and template guidance, never enforcing corporate attire
        prompt = (
            f"{avatar_desc} Subject: {(name or 'employee')}."
            + (f" Role: {role}." if role else "")
            + role_note
            + " Ensure this portrait's attire is not identical to other employees' portraits."
            + (" Use a similar composition and lighting style to the provided reference template." if template_hint else "")
        )

        # Force square
        size_to_use = "1024x1024"
        img_bytes = images_generate(api_key, prompt=prompt, size=size_to_use, model=model, quality=requested_quality)
        if not img_bytes:
            # Skip on failure
            continue

        # Default to PNG output data URL
        mime = "image/png"
        data_url = to_data_url(img_bytes, mime=mime)
        new_ext = "png"
        updated_file_name = replace_ext(base_name, new_ext)

        # We do not alter the JSON path prefix; only update the extension to match mime
        # The frontend will patch combinedJson at the image string path occurrence
        outputs.append({
            "name": updated_file_name,
            "output": data_url,
            "originalJsonPath": original_path,
            "updatedJsonPath": replace_ext(original_path, new_ext),
            "generationVirtualPath": old_to_generation(replace_ext(original_path, new_ext)),
        })

    if outputs:
        if MEMORY_ONLY:
            print("EMPLOYEE_IMAGES_BASE64_START")
            print(json.dumps(outputs))
            print("EMPLOYEE_IMAGES_BASE64_END")
        else:
            # Non-memory mode (not used currently): would persist images to disk.
            for o in outputs:
                print(f"Generated: {o['updatedJsonPath']}")
        return True

    print("No employee images generated.")
    return False


if __name__ == "__main__":
    ok = main()
    raise SystemExit(0 if ok else 1)


