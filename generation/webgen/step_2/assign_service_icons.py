#!/usr/bin/env python3
"""
assign_service_icons.py

Memory-only script to assign category/service icons and labels for service_names.
Input (STDIN JSON):
  {
    "serviceNames": { ... },
    "locationInfo": { ... }   # optional
  }

Behavior:
  - Uses OpenAI (same model as generate_service_jsons.py) to select icons from lucide icon set
  - Preserves existing categories if provided; defaults to residential/commercial
  - Returns updated serviceNames JSON with icons filled for categories and services

Output (STDOUT):
  SERVICE_ICONS_START
  { "serviceNames": { ... with icons ... } }
  SERVICE_ICONS_END

No disk writes; caller decides persistence.
"""

import os
import sys
import json
from pathlib import Path
from typing import Any, Dict

try:
    import dotenv
except Exception:
    dotenv = None

import requests


ROOT = Path(__file__).resolve().parents[5]
if dotenv is not None:
    try:
        dotenv.load_dotenv(ROOT / 'public' / 'data' / 'generation' / '.env')
    except Exception:
        pass

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
OPENAI_ENDPOINT = 'https://api.openai.com/v1/chat/completions'

MODEL = 'gpt-4o-mini'


def read_stdin_payload() -> Dict[str, Any]:
    raw = sys.stdin.read()
    if not raw or not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def call_openai(prompt: str) -> str:
    headers = {
        'Authorization': f'Bearer {OPENAI_API_KEY}',
        'Content-Type': 'application/json',
    }
    data = {
        'model': MODEL,
        'messages': [{ 'role': 'user', 'content': prompt }],
        'temperature': 0.5,
        'max_tokens': 2000,
    }
    resp = requests.post(OPENAI_ENDPOINT, headers=headers, json=data, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"OpenAI error: {resp.status_code} {resp.text}")
    return resp.json()['choices'][0]['message']['content']


LUCIDE_ICON_HINT = (
    "Select icons from the lucide icon set. Return icon names like 'Home', 'Building2', "
    "'ShieldCheck', 'Droplets', 'Wrench', 'Layers', 'Fan', 'FileText'."
)


def load_template_service_names() -> Dict[str, Any]:
    tpl = ROOT / 'public' / 'data' / 'generation' / 'webgen' / 'templates' / 'service_names.template.json'
    try:
        if tpl.exists():
            with open(tpl, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def ensure_default_categories(sn: Dict[str, Any]) -> Dict[str, Any]:
    # Promote to categories[] if only legacy shape present
    if not isinstance(sn, dict):
        return {
            'meta': { 'version': 2, 'maxCategories': 5 },
            'categories': [
                { 'key': 'residential', 'label': 'Residential', 'icon': 'Home', 'iconPack': 'lucide', 'order': 0, 'services': [] },
                { 'key': 'commercial', 'label': 'Commercial', 'icon': 'Building2', 'iconPack': 'lucide', 'order': 1, 'services': [] },
            ]
        }

    categories = sn.get('categories')
    if isinstance(categories, list) and categories:
        # Categories already exist - return as-is to prevent duplication
        return sn

    # Build from legacy keys if available
    out = {
        'meta': { 'version': 2, 'maxCategories': 5 },
        'categories': []
    }
    res = (sn.get('residential') or {}).get('services') or []
    com = (sn.get('commercial') or {}).get('services') or []
    out['categories'].append({ 'key': 'residential', 'label': 'Residential', 'icon': 'Home', 'iconPack': 'lucide', 'order': 0, 'services': res })
    out['categories'].append({ 'key': 'commercial', 'label': 'Commercial', 'icon': 'Building2', 'iconPack': 'lucide', 'order': 1, 'services': com })
    return out


def build_prompt(sn: Dict[str, Any], location: Dict[str, Any]) -> str:
    cats = sn.get('categories') or []
    def fmt_services(svcs):
        return [ (s.get('title') or s.get('name') or '').strip() for s in (svcs or []) ]
    lines = [
        "You are assigning icons to website service categories and their services.",
        LUCIDE_ICON_HINT,
        f"Business: {(location or {}).get('business_name') or 'Roofing Company'}",
        "Categories and services:"
    ]
    for c in cats:
        lines.append(f"- {c.get('label') or c.get('key')}: {fmt_services(c.get('services'))}")
    lines.append(
        "Return ONLY JSON with shape: {\n"
        "  \"categories\": [ { \"key\": string, \"label\": string, \"icon\": string, \"iconPack\": \"lucide\", \"order\": number, \"services\": [ { \"id\": string|number, \"title\": string, \"name\": string, \"icon\": string, \"iconPack\": \"lucide\" } ] } ]\n"
        "}. Keep existing ids/titles. Do not invent categories or services."
    )
    return "\n".join(lines)


def main() -> int:
    try:
        payload = read_stdin_payload()
        sn_in = payload.get('serviceNames') or {}
        location = payload.get('locationInfo') or {}
        # If serviceNames not provided or empty, load template
        if not isinstance(sn_in, dict) or (not sn_in.get('categories') and not sn_in.get('residential') and not sn_in.get('commercial')):
            tpl = load_template_service_names()
            if tpl:
                sn_in = tpl
        if not OPENAI_API_KEY:
            # Without API key, just ensure categories present and fill default icons
            sn = ensure_default_categories(sn_in)
            for i, c in enumerate(sn.get('categories') or []):
                c.setdefault('iconPack', 'lucide')
                c.setdefault('icon', 'Home' if (c.get('key') == 'residential') else 'Building2')
                for s in (c.get('services') or []):
                    s.setdefault('iconPack', 'lucide')
                    title = (s.get('title') or s.get('name') or '').lower()
                    s.setdefault('icon', 'ShieldCheck' if 'shingle' in title else 'Wrench' if 'repair' in title else 'Layers' if 'coat' in title else 'FileText')
            print('SERVICE_ICONS_START')
            print(json.dumps({ 'serviceNames': sn }, ensure_ascii=False))
            print('SERVICE_ICONS_END')
            return 0

        sn = ensure_default_categories(sn_in)
        prompt = build_prompt(sn, location)
        content = call_openai(prompt)
        s = content.find('{'); e = content.rfind('}') + 1
        if s < 0 or e <= s:
            raise RuntimeError('No JSON in OpenAI response')
        parsed = json.loads(content[s:e])
        # Merge icons back into original structure to preserve extra fields
        cats_by_key = { (c.get('key') or c.get('label')): c for c in (sn.get('categories') or []) }
        for c in (parsed.get('categories') or []):
            key = c.get('key') or c.get('label')
            if not key or key not in cats_by_key:
                continue
            target = cats_by_key[key]
            # Update category icon
            if c.get('icon'): target['icon'] = c.get('icon')
            target['iconPack'] = 'lucide'
            # Index services by id|title
            idx = {}
            for s in (target.get('services') or []):
                sid = str(s.get('id') or '').strip()
                nm = (s.get('title') or s.get('name') or '').strip().lower()
                if sid: idx[f'id:{sid}'] = s
                if nm: idx[f'name:{nm}'] = s
            for s in (c.get('services') or []):
                sid = str(s.get('id') or '').strip()
                nm = (s.get('title') or s.get('name') or '').strip().lower()
                key1 = f'id:{sid}' if sid else None
                key2 = f'name:{nm}' if nm else None
                tgt = idx.get(key1) or idx.get(key2)
                if tgt is None:
                    continue
                if s.get('icon'): tgt['icon'] = s['icon']
                tgt['iconPack'] = 'lucide'

        print('SERVICE_ICONS_START')
        print(json.dumps({ 'serviceNames': sn }, ensure_ascii=False))
        print('SERVICE_ICONS_END')
        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


if __name__ == '__main__':
    raise SystemExit(main())


