#!/usr/bin/env python3

import os
import json
import logging
import re
import sys
from typing import Dict, Any, Tuple
import requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def _noop_read_json(_: str) -> Dict[str, Any]:
    return {}


def _noop_write_json(_: str, __: Dict[str, Any]) -> None:
    # memory-only: do not write to disk
    return


def _split_business_name_for_nav(business_name: str) -> Tuple[str, str]:
    if not isinstance(business_name, str) or not business_name.strip():
        return "Roofing Company", ""
    words = re.split(r"\s+", business_name.strip())
    title = business_name.strip()
    subtitle = words[1] if len(words) >= 2 else ""
    return title, subtitle


def _normalize_data_url_to_png(data_url: str) -> str:
    """Force data:image/*;base64 URLs to image/png; keep payload unchanged."""
    if not isinstance(data_url, str):
        return data_url
    try:
        if data_url.startswith('data:image/') and ';base64,' in data_url:
            # Replace MIME prefix only
            return 'data:image/png;base64,' + data_url.split(',')[1]
        return data_url
    except Exception:
        return data_url


def _read_template_nav() -> Dict[str, Any]:
    """Read template_nav.json from repo. Fallback to minimal shape if missing."""
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        public_dir = os.path.abspath(os.path.join(script_dir, '..', '..', '..', '..'))
        template_path = os.path.join(public_dir, 'personal', 'old', 'jsons', 'template_nav.json')
        with open(template_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"[Nav] Failed to read template_nav.json, using minimal template: {e}")
        return {
            "Content": {"title": "", "subtitle": "", "images": []}
        }


def generate_nav():
    # Attempt to read memory-only payload from STDIN
    stdin_payload: Dict[str, Any] = {}
    try:
        raw = sys.stdin.read()
        if raw and raw.strip():
            stdin_payload = json.loads(raw)
            logger.info("[Nav] Loaded input from STDIN")
    except Exception as e:
        logger.warning(f"[Nav] Failed to read STDIN payload: {e}")

    # Inputs (memory-driven)
    gray_logo_url = None

    # Prefer in-memory BBB profile provided via STDIN; fallback to disk
    bbb_profile: Dict[str, Any] = {}
    if isinstance(stdin_payload, dict):
        # Accept multiple key names for flexibility
        if isinstance(stdin_payload.get('bbbProfile'), dict):
            bbb_profile = stdin_payload.get('bbbProfile') or {}
        elif isinstance(stdin_payload.get('profileData'), dict):
            bbb_profile = stdin_payload.get('profileData') or {}
        # Or accept a direct businessName
        if not bbb_profile and isinstance(stdin_payload.get('businessName'), str):
            bbb_profile = { 'business_name': stdin_payload.get('businessName') }

    # Load template from disk (simple file copy of nav.json)
    nav_template = _read_template_nav()

    business_name = (
        bbb_profile.get("business_name")
        or bbb_profile.get("lead_business_name")
        or "Roofing Company"
    )

    # Derive title/subtitle using simple heuristic only
    title, subtitle = _split_business_name_for_nav(business_name)

    # Apply required updates to template (new structure under Content)
    nav_payload = json.loads(json.dumps(nav_template))  # deep copy via json
    if not isinstance(nav_payload.get('Content'), dict):
        nav_payload['Content'] = {}
    nav_payload['Content']['title'] = title
    nav_payload['Content']['subtitle'] = subtitle

    # Accept grayscale logo data URL from STDIN under multiple possible keys
    gray_logo_url = (
        stdin_payload.get('clippedGrayDataUrl') or
        stdin_payload.get('enhancedGrayDataUrl') or
        stdin_payload.get('enhancedGrayUrl') or
        stdin_payload.get('grayLogoDataUrl') or
        stdin_payload.get('grayLogo') or
        stdin_payload.get('logoGrayDataUrl') or
        stdin_payload.get('logoGray') or
        None
    )
    if isinstance(gray_logo_url, str) and gray_logo_url.strip():
        normalized_url = _normalize_data_url_to_png(gray_logo_url.strip())
        content = nav_payload['Content']
        images = content.get('images')
        if not isinstance(images, list):
            images = []
        if images:
            # Replace first image URL only; keep other keys
            if isinstance(images[0], dict):
                images[0]['url'] = normalized_url
                # Prefer a png-ish name
                if 'name' in images[0]:
                    images[0]['name'] = 'logo-gray.png'
                else:
                    images[0]['name'] = 'logo-gray.png'
            else:
                images[0] = { 'url': normalized_url, 'name': 'logo-gray.png', 'file': None }
        else:
            images.append({ 'url': normalized_url, 'name': 'logo-gray.png', 'file': None })
        content['images'] = images

    # memory-only: emit to stdout markers so backend can capture directly
    try:
        print('NAV_JSON_START')
        print(json.dumps(nav_payload, ensure_ascii=False))
        print('NAV_JSON_END')
    except Exception:
        pass


def main():
    try:
        generate_nav()
        logger.info("Nav generation completed successfully.")
    except Exception as e:
        logger.error(f"Nav generation failed: {e}")
        raise


if __name__ == "__main__":
    main()


