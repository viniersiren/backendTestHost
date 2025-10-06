#!/usr/bin/env python3
"""
Generate About Page images (memory-only) using prompts from about_page.json ImageProps.

Inputs: STDIN JSON (optional) { "aboutPage": { ...about_page.json... } }
If not provided on STDIN, reads raw_data/step_3/about_page.json.

Outputs to STDOUT markers:
ABOUT_IMAGES_START
{ "items": [ { "path": "/generation/img/about_page/Hero/1.jpg", "oldPath": "/personal/old/img/about_page/Hero/1.jpg", "prompt": "...", "output": "data:image/..." }, ... ] }
ABOUT_IMAGES_END

Quality: medium for hero; medium for team photos. Uses generate_images_with_ai API conventions.
"""
import os, sys, json
from pathlib import Path
import dotenv
import openai
import requests

ROOT = Path(__file__).resolve().parents[5]
RAW_DIR = ROOT / 'public' / 'data' / 'generation' / 'webgen' / 'raw_data' / 'step_3'
ABOUT_JSON_PATH = RAW_DIR / 'about_page.json'

def load_env():
    try:
        dotenv.load_dotenv(Path(__file__).resolve().parents[2] / '.env')
    except Exception:
        pass

def get_api_key():
    return os.environ.get('OPENAI_API_KEY')

def read_stdin_about():
    try:
        raw = sys.stdin.read()
        if raw and raw.strip():
            payload = json.loads(raw)
            ap = payload.get('aboutPage') or payload
            if isinstance(ap, dict) and ap.get('title'):
                return ap
    except Exception:
        pass
    return None

def load_about_fallback():
    try:
        if ABOUT_JSON_PATH.exists():
            with open(ABOUT_JSON_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return None

def generate_image_data_url(api_key: str, prompt: str, size: str = '1536x1024', quality: str = 'medium') -> str | None:
    try:
        client = openai.OpenAI(api_key=api_key)
        resp = client.images.generate(model='gpt-image-1', prompt=prompt, size=size, quality=quality, n=1)
        data = resp.data[0]
        b64 = getattr(data, 'b64_json', None)
        if b64:
            return f"data:image/png;base64,{b64}"
        url = getattr(data, 'url', None)
        if url:
            r = requests.get(url, timeout=120)
            r.raise_for_status()
            import base64
            return 'data:image/png;base64,' + base64.b64encode(r.content).decode('utf-8')
    except Exception as e:
        print(f"[AboutImages] generate failed: {e}")
    return None

def main():
    load_env()
    api_key = get_api_key()
    if not api_key:
        print('[AboutImages] Missing OPENAI_API_KEY')
        sys.exit(1)

    about = read_stdin_about() or load_about_fallback()
    if not isinstance(about, dict):
        print('[AboutImages] No about_page data available')
        sys.exit(1)

    items = []
    # Hero
    hero_old = about.get('heroImage') or '/personal/old/img/about_page/Hero/1.jpg'
    hero_new = hero_old.replace('/personal/old/', '/generation/')
    hero_prompt = (about.get('ImageProps') or {}).get('hero', {}).get('v1') or 'Photorealistic roofing hero image, copy-safe, 16:9'
    hero_du = generate_image_data_url(api_key, hero_prompt, size='1536x1024', quality='medium')
    if hero_du:
        items.append({ 'path': hero_new, 'oldPath': hero_old, 'prompt': hero_prompt, 'output': hero_du })

    # Team
    team = about.get('team') or []
    team_prompts = (about.get('ImageProps') or {}).get('team') or {}
    variants = [team_prompts.get(k) for k in sorted(team_prompts.keys()) if isinstance(team_prompts.get(k), str)] or []
    for idx, member in enumerate(team):
        oldp = member.get('photo') or f"/personal/old/img/about_page/team/{idx+1}.jpg"
        newp = oldp.replace('/personal/old/', '/generation/')
        prompt = variants[idx % len(variants)] if variants else 'Professional headshot on neutral backdrop, soft key light, shallow depth'
        du = generate_image_data_url(api_key, prompt, size='1024x1024', quality='medium')
        if du:
            items.append({ 'path': newp, 'oldPath': oldp, 'prompt': prompt, 'output': du })

    print('ABOUT_IMAGES_START')
    print(json.dumps({ 'items': items }, ensure_ascii=False))
    print('ABOUT_IMAGES_END')

if __name__ == '__main__':
    main()


