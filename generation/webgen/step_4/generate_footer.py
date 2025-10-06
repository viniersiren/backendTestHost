#!/usr/bin/env python3

import os
import sys
import json
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def _noop_read_json(_: str):
  return None


def _noop_write_json(_: str, __: dict):
  # memory-only: do not write to disk
  pass

def build_footer_payload(stdin_payload: dict = None):
  # memory-only: no disk reads
  script_dir = None
  data_dir = None
  raw_data_dir = None

  # Prefer BBB profile data for deterministic business info
  bbb_path = None
  bbb = {}
  # Memory-only: accept BBB profile via STDIN payload
  if isinstance(stdin_payload, dict):
    if isinstance(stdin_payload.get('bbbProfile'), dict):
      bbb = stdin_payload.get('bbbProfile') or {}
    elif isinstance(stdin_payload.get('profileData'), dict):
      bbb = stdin_payload.get('profileData') or {}
    # Allow direct fields to override
    if not bbb:
      name = stdin_payload.get('businessName')
      address = stdin_payload.get('address')
      telephone = stdin_payload.get('telephone') or stdin_payload.get('phone')
      if name or address or telephone:
        bbb = {
          'business_name': name,
          'address': address,
          'telephone': telephone
        }
  # memory-only: do not read from disk

  business_name = bbb.get('business_name') or 'Roofing Company'
  address = bbb.get('address') or ''
  phone = bbb.get('telephone') or ''
  email = 'exampleemailgmail.com'

  year = str(datetime.now().year)

  # Accept grayscale logo data URL from STDIN under multiple possible keys
  def _normalize_data_url_to_png(data_url: str) -> str:
    try:
      if isinstance(data_url, str) and data_url.startswith('data:image/') and ';base64,' in data_url:
        return 'data:image/png;base64,' + data_url.split(',')[1]
    except Exception:
      pass
    return data_url

  gray_logo_url = None
  try:
    gray_logo_url = (
      (stdin_payload or {}).get('clippedGrayDataUrl') or
      (stdin_payload or {}).get('enhancedGrayDataUrl') or
      (stdin_payload or {}).get('enhancedGrayUrl') or
      (stdin_payload or {}).get('grayLogoDataUrl') or
      (stdin_payload or {}).get('grayLogo') or
      (stdin_payload or {}).get('logoGrayDataUrl') or
      (stdin_payload or {}).get('logoGray') or
      None
    )
  except Exception:
    gray_logo_url = None

  # Social links: defer to socials.json pipeline; do not auto-populate here
  social_links = []

  # --- Build structured footer payload to match nav.json style (Content / Design_default / Formatting_default) ---
  # Choose logo image URL and filename
  chosen_logo_url = _normalize_data_url_to_png(gray_logo_url) if isinstance(gray_logo_url, str) and gray_logo_url.strip() else \
                    '/personal/old/img/footer/logo.svg'

  # No mapping here; MainPageCreator injects socials.json at render time
  structured_social_links = []

  structured_payload = {
    'Content': {
      'businessInfo': {
        'name': business_name,
        'address': address,
      	'phone': phone,
        'email': email
      },
      'bbbInfo': {
        'accredited': bool(bbb.get('accredited')) if isinstance(bbb, dict) else False,
        'logo_url': chosen_logo_url,
        'website': (bbb.get('website') or '') if isinstance(bbb, dict) else '',
        'telephone': phone,
        'email': email,
        'business_name': business_name,
        'address': address
      },
      'quickLinks': [
        { 'label': 'About', 'href': '/about' },
        { 'label': 'Services', 'href': '/services' },
        { 'label': 'Contact', 'href': '/contact' }
      ],
      'socialLinks': structured_social_links,
      'copyright': business_name
    },
    'Design_default': {
      'Text-businessName': {
        'Font': 'Inter',
        'Color': '#FFFFFF',
        'Mobile': { 'Size': 16, 'Height': 1.3, 'Weight': 700, 'Spacing': 0.4 },
        'Desktop': { 'Size': 24, 'Height': 1.2, 'Weight': 700, 'Spacing': 0.5 }
      },
      'Text-contactInfo': {
        'Font': 'Inter',
        'Color': '#FFFFFF',
        'Mobile': { 'Size': 12, 'Height': 1.4, 'Weight': 400, 'Spacing': 0.2 },
        'Desktop': { 'Size': 14, 'Height': 1.5, 'Weight': 400, 'Spacing': 0.3 }
      },
      'Text-links': {
        'Font': 'Inter',
        'Color': '#E5E7EB',
        'Mobile': { 'Size': 14, 'Height': 1.4, 'Weight': 400, 'Spacing': 0.2 },
        'Desktop': { 'Size': 16, 'Height': 1.5, 'Weight': 400, 'Spacing': 0.3 }
      },
      'Text-copyright': {
        'Font': 'Inter',
        'Color': '#9CA3AF',
        'Mobile': { 'Size': 12, 'Height': 1.4, 'Weight': 400, 'Spacing': 0.2 },
        'Desktop': { 'Size': 14, 'Height': 1.5, 'Weight': 400, 'Spacing': 0.3 }
      },
      'Bg': {
        'gradientConfig': { 'direction': 'to right', 'startColor': '#1e293b', 'endColor': '#1e293b' }
      },
      'Colors': {
        'backgroundColor': '#1e293b',
        'textColor': '#FFFFFF',
        'linkColor': '#E5E7EB',
        'linkHoverColor': '#FFFFFF',
        'borderColor': '#374151',
        'socialIconColor': '#E5E7EB'
      }
    },
    'Formatting_default': {
      'Height': {
        'Mobile': 24,
        'Desktop': 20
      },
      'Padding': {
        'Mobile': { 'top': 2, 'bottom': 2 },
        'Desktop': { 'top': 4, 'bottom': 4 }
      }
    }
  }

  return structured_payload


def main():
  try:
    # Load optional memory-only payload from STDIN
    stdin_payload = {}
    try:
      raw = sys.stdin.read()
      if raw and raw.strip():
        stdin_payload = json.loads(raw)
        logger.info('[Footer] Loaded input from STDIN')
    except Exception as e:
      logger.warning(f'[Footer] Failed to read STDIN payload: {e}')

    payload = build_footer_payload(stdin_payload)

    # Write to deterministic raw_data output
    # memory-only: do not write to disk, emit via stdout only

    # Emit to stdout with markers for backend parsing
    print('FOOTER_JSON_START')
    print(json.dumps(payload, ensure_ascii=False))
    print('FOOTER_JSON_END')

  except Exception as e:
    logger.error(f"Footer generation failed: {e}")
    raise


if __name__ == '__main__':
  main()


