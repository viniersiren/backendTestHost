#!/usr/bin/env python3
"""
Generate a photorealistic afternoon house image with a simple white cardboard
yard sign. No logo or branding should appear anywhere in the image. The yard
sign in the base render must be completely blank (no text, numbers, logos, or
graphics on either the top half or bottom half). Business name, phone, and
address are overlaid crisply in post (bottom half only).

Output:
- public/data/generation/webgen/img/output/house_with_sign.png
- public/data/generation/webgen/img/generated_signs.json (metadata)

Model/quality are hardcoded to gpt-image-1, high.
"""

import os
import json
from pathlib import Path
from datetime import datetime
import base64
import requests
from typing import Optional, Dict, Any
import sys
import dotenv
import openai
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO


# Paths
ROOT = Path(__file__).resolve().parents[5]
OUTPUT_INDIVIDUAL_DIR = ROOT / "public" / "data" / "output" / "individual" / "step_1" / "raw"
BBB_PROFILE_PATH = OUTPUT_INDIVIDUAL_DIR / "bbb_profile_data.json"

IMG_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = IMG_DIR / "output"
METADATA_PATH = IMG_DIR / "generated_signs.json"

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


def load_bbb_data() -> Dict[str, Any]:
    if BBB_PROFILE_PATH.exists():
        try:
            with open(BBB_PROFILE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def read_stdin_payload() -> Dict[str, Any]:
    try:
        raw = sys.stdin.read()
        if not raw:
            return {}
        return json.loads(raw)
    except Exception:
        return {}


def build_house_sign_prompt(bbb: Dict[str, Any]) -> str:
    # Generate a blank yard sign on a realistic scene. We will overlay exact logo/text ourselves.
    name = (bbb.get("business_name") or bbb.get("businessName") or "").strip()
    tel = (bbb.get("telephone") or "").strip()
    address = (bbb.get("address") or "").strip()

    # Extract city/state for setting
    import re
    city = state = ""
    m = re.search(r"([A-Za-z\s]+),\s*([A-Z]{2})", address)
    if m:
        city = m.group(1).strip()
        state = m.group(2).strip()
    region = ", ".join([p for p in [city, state] if p]) or "the local area"

    return (
        f"Photorealistic afternoon (about 3 PM) curbside scene in {region}: a well‑kept single‑family home with a high‑quality roof (clean asphalt shingles), "
        f"soft directional sunlight, realistic shadows, and tidy landscaping. In the front yard near the sidewalk, a simple white cardboard yard sign is mounted on a metal H‑frame stake. "
        f"YARD SIGN REQUIREMENTS (CRITICAL): The yard sign is plain matte white with ABSOLUTELY NO text, numbers, symbols, icons, QR codes, decals, logos, branding, or graphic overlays anywhere on it. "
        f"NO DESIGN ELEMENTS on the sign surface: no borders, outlines, stripes, shapes, patterns, stickers, or watermarks. The panel must appear as a solid white rectangle. "
        f"TOP HALF: must remain completely blank. BOTTOM HALF: reserved strictly for text‑only (business name, phone, address) to be added later in post‑production; in this generated image, leave it completely blank with no graphics or logos. "
        f"ABSOLUTE RULES: Do not include any logo or branding anywhere in the entire image (including on the sign, house, vehicles, clothing, or background). Do not render any text on the sign in the base image. "
        f"Camera at eye level, 35mm lens, f/5.6, ISO 200, natural color grading, no over‑saturation, no vignette, no watermark. 16:9 composition with copy‑safe space."
    )


def generate_image(api_key: str, prompt: str, size: str = "1536x1024") -> Optional[bytes]:
    client = openai.OpenAI(api_key=api_key)
    # Hardcode model/quality
    model = "gpt-image-1"
    quality = "high"
    try:
        try:
            print(f"[house_sign] Model: {model}, quality: {quality}, size: {size}")
        except Exception:
            pass
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


def download_logo_file(bbb: Dict[str, Any]) -> Optional[Path]:
    url = (bbb.get("logo_url") or "").strip()
    if not url:
        return None
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        logo_dir = IMG_DIR / "output"
        logo_dir.mkdir(parents=True, exist_ok=True)
        path = logo_dir / "bbb_logo.png"
        with open(path, "wb") as f:
            f.write(r.content)
        return path
    except Exception:
        return None


def _hex_to_rgb(s: str) -> tuple:
    try:
        s = s.strip().lstrip('#')
        if len(s) == 3:
            s = ''.join([c*2 for c in s])
        if len(s) != 6:
            return (238, 234, 228)
        return tuple(int(s[i:i+2], 16) for i in (0, 2, 4))
    except Exception:
        return (238, 234, 228)


def _resolve_sign_colors(colors_json: Optional[Dict[str, Any]]) -> Dict[str, tuple]:
    # Force a clean white panel regardless of theme; text only (no borders or graphics)
    return {
        'panel_bg': (255, 255, 255),
        'text': (20, 20, 20),
    }


def _overlay_crisp_on_image(img: Image.Image, bbb: Dict[str, Any], logo_image: Optional[Image.Image], colors_json: Optional[Dict[str, Any]]) -> None:
    draw = ImageDraw.Draw(img)
    w, h = img.size

    # Sign rectangle (bottom-left area)
    sign_w = int(w * 0.26)
    sign_h = int(h * 0.32)
    left = int(w * 0.08)
    top = int(h * 0.56)
    right = left + sign_w
    bottom = top + sign_h

    palette = _resolve_sign_colors(colors_json)

    # Draw a white sign panel with NO border or graphics
    try:
        draw.rectangle([(left, top), (right, bottom)], fill=palette['panel_bg'])
    except Exception:
        pass

    # Load font (fallback to default if TTF not available)
    try:
        font_bold = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", size=max(12, int(sign_h * 0.16)))
        font_text = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", size=max(12, int(sign_h * 0.12)))
    except Exception:
        font_bold = ImageFont.load_default()
        font_text = ImageFont.load_default()

    # Reserve top half of the sign completely blank (no logo/graphics)
    y_cursor = top + int(sign_h * 0.08)

    # Draw business name, phone and address (crisp)
    name = str((bbb.get("business_name") or bbb.get("businessName") or "")).strip()
    # Be tolerant of alternate phone keys present in different scrapers
    tel = str((bbb.get("telephone") or bbb.get("phone") or bbb.get("phone_number") or bbb.get("phoneNumber") or "")).strip()
    address = str((bbb.get("address") or "")).strip()
    text_color = palette['text']

    # Helper to wrap text to fit width
    def draw_wrapped_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> None:
        nonlocal y_cursor
        try:
            words = text.split()
            line = ""
            for word in words:
                test = (line + (" " if line else "") + word).strip()
                tw, _ = draw.textsize(test, font=font)
                if tw <= max_width or not line:
                    line = test
                else:
                    if line:
                        lw, lh = draw.textsize(line, font=font)
                        tx = left + int(sign_w * 0.05)
                        draw.text((tx, y_cursor), line, fill=text_color, font=font)
                        y_cursor += lh + int(sign_h * 0.02)
                    line = word
            if line:
                lw, lh = draw.textsize(line, font=font)
                tx = left + int(sign_w * 0.05)
                draw.text((tx, y_cursor), line, fill=text_color, font=font)
                y_cursor += lh + int(sign_h * 0.02)
        except Exception:
            pass

    # Ensure text starts in bottom half of the sign (fixed position)
    y_cursor = top + int(sign_h * 0.55)

    # Order: Name (bold), Address lines, Phone (bold) — all in bottom half
    if name:
        try:
            name_font = font_bold
        except Exception:
            name_font = font_bold
        draw_wrapped_text(name, name_font, int(sign_w * 0.9))

    if address:
        lines = [part.strip() for part in address.replace("\n", ", ").split(",") if part.strip()]
        for line in lines:
            tw, th = draw.textsize(line, font=font_text)
            tx = left + int(sign_w * 0.05)
            draw.text((tx, y_cursor), line, fill=text_color, font=font_text)
            y_cursor += th + int(sign_h * 0.02)

    if tel:
        tel_text = tel
        tw, th = draw.textsize(tel_text, font=font_bold)
        tx = left + int(sign_w * 0.05)
        draw.text((tx, y_cursor), tel_text, fill=text_color, font=font_bold)
        y_cursor += th + int(sign_h * 0.02)


def overlay_crisp_sign_on_bytes(image_bytes: bytes, bbb: Dict[str, Any], logo_bytes: Optional[bytes], colors_json: Optional[Dict[str, Any]]) -> Optional[bytes]:
    try:
        base = Image.open(BytesIO(image_bytes)).convert("RGB")
        # Explicitly ignore any logo bytes to ensure no logo appears on the sign
        logo_img = None
        try:
            print("[house_sign] Overlay: inputs:", {
                "has_logo_bytes": bool(logo_bytes),
                "has_colors": bool(colors_json),
                "bbb_name": (bbb.get("business_name") or bbb.get("businessName") or None),
                "bbb_tel": bbb.get("telephone"),
                "bbb_addr": bbb.get("address"),
            })
        except Exception:
            pass
        _overlay_crisp_on_image(base, bbb, logo_img, colors_json)
        out = BytesIO()
        base.save(out, format='PNG')
        return out.getvalue()
    except Exception:
        return None


def overlay_crisp_sign(base_path: Path, bbb: Dict[str, Any], logo_path: Optional[Path], colors_json: Optional[Dict[str, Any]] = None) -> None:
    try:
        # Reuse the byte-level helper for consistent behavior
        with open(base_path, 'rb') as fh:
            base_bytes = fh.read()
        logo_bytes = None
        if logo_path and logo_path.exists():
            try:
                with open(logo_path, 'rb') as lf:
                    logo_bytes = lf.read()
            except Exception:
                logo_bytes = None
        over = overlay_crisp_sign_on_bytes(base_bytes, bbb, logo_bytes, colors_json)
        if over:
            with open(base_path, 'wb') as out:
                out.write(over)
    except Exception:
        pass


def update_metadata(entry: Dict[str, Any]) -> None:
    try:
        meta = {"generated_signs": [], "metadata": {"last_updated": datetime.now().isoformat()}}
        if METADATA_PATH.exists() and not MEMORY_ONLY:
            with open(METADATA_PATH, "r", encoding="utf-8") as f:
                meta = json.load(f)
        meta["generated_signs"].append(entry)
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
    payload = read_stdin_payload()
    # Prefer in-memory BBB profile when provided
    bbb = payload.get("bbbProfile") or load_bbb_data()
    # Merge explicit overrides from UI confirmation if present
    try:
        override = payload.get("bbbOverride") or {}
        if isinstance(override, dict):
            # Accept flexible keys
            ov = {
                "business_name": override.get("business_name") or override.get("name"),
                "address": override.get("address"),
                "telephone": override.get("telephone") or override.get("phone") or override.get("phone_number") or override.get("phoneNumber"),
            }
            for k, v in ov.items():
                if v:
                    bbb[k] = v
    except Exception:
        pass

    # Use provided prompt if available, otherwise build default with blank-top instruction
    prompt = payload.get("prompt") or build_house_sign_prompt(bbb)

    size = payload.get("size") or os.environ.get("HOUSE_IMAGE_SIZE", "1536x1024")

    try:
        mem_mode = 'memory-only' if MEMORY_ONLY else 'filesystem'
        print(f"[house_sign] Starting generation (mode: {mem_mode})")
    except Exception:
        pass
    print("Generating house with blank yard sign (no branding)...")
    img_bytes = generate_image(api_key, prompt, size)
    if not img_bytes:
        print("❌ Failed to generate the house image")
        return False

    out_name = payload.get("filename") or "house_with_sign.png"
    path_or_data = save_image_bytes(img_bytes, out_name)
    # Overlay crisp sign with exact phone/address (logos are intentionally ignored)
    enhanced_color_data_url = payload.get("enhancedColorDataUrl")
    chosen_logo_data_url = payload.get("chosenLogoDataUrl")
    colors_json = payload.get("colorsJson")

    def _decode_data_url(data_url: Optional[str]) -> Optional[bytes]:
        try:
            if not data_url or not isinstance(data_url, str):
                return None
            if not data_url.startswith('data:image/'):
                return None
            return base64.b64decode(data_url.split(',', 1)[1])
        except Exception:
            return None

    # Ignore any provided logos entirely
    enhanced_gray_data_url = payload.get("enhancedGrayDataUrl")
    preferred_logo_bytes = None
    try:
        def _mime_of(data_url: Optional[str]) -> Optional[str]:
            try:
                if not data_url or not isinstance(data_url, str):
                    return None
                if not data_url.startswith('data:'):
                    return None
                return data_url.split(';', 1)[0].split(':', 1)[1]
            except Exception:
                return None
        print('[house_sign] Memory inputs (logos ignored):', {
            'enhancedColorType': _mime_of(enhanced_color_data_url),
            'enhancedGrayType': _mime_of(enhanced_gray_data_url),
            'chosenLogoType': _mime_of(chosen_logo_data_url),
            'colorsJsonPresent': bool(colors_json),
        })
    except Exception:
        pass

    if isinstance(path_or_data, str) and path_or_data.startswith('data:image/'):
        base_bytes = _decode_data_url(path_or_data)
        if base_bytes is not None:
            over_b = overlay_crisp_sign_on_bytes(base_bytes, bbb, preferred_logo_bytes, colors_json)
            if over_b is not None:
                path_or_data = f"data:image/png;base64,{base64.b64encode(over_b).decode('utf-8')}"
    elif not MEMORY_ONLY and isinstance(path_or_data, str):
        # Always ignore any logo path; draw only text on a white panel
        overlay_crisp_sign(ROOT / path_or_data, bbb, None, colors_json)
    try:
        print('[house_sign] Completed. Output path/data type:', 'memory-data-url' if isinstance(path_or_data, str) and path_or_data.startswith('data:') else str(path_or_data))
    except Exception:
        pass
    update_metadata({
        "type": "house_with_sign",
        "prompt": prompt,
        "output": path_or_data,
        "size": size,
        "generated_at": datetime.now().isoformat(),
        "model": "gpt-image-1",
        "quality": "high",
    })

    if MEMORY_ONLY:
        print("HOUSE_IMAGE_BASE64_START")
        print(json.dumps({"output": path_or_data}))
        print("HOUSE_IMAGE_BASE64_END")
    else:
        print("\n✅ House image with yard sign generated:")
        print(f"- output: {path_or_data}")
        print(f"📄 Metadata: {METADATA_PATH.relative_to(ROOT)}")
    return True


if __name__ == "__main__":
    ok = main()
    raise SystemExit(0 if ok else 1)


