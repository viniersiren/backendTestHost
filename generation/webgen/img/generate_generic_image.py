#!/usr/bin/env python3
"""
Generate a single image (memory-only) from a provided prompt/size/quality.
STDIN JSON: { "prompt": str, "size": "1024x1024", "quality": "medium", "model": "gpt-image-1" }
STDOUT markers:
GENERIC_IMAGE_START
{ "output": "data:image/..." }
GENERIC_IMAGE_END
"""
import os, sys, json, base64
import dotenv
import requests
import openai

def get_api_key():
    return os.environ.get('OPENAI_API_KEY')

def read_payload():
    try:
        raw = sys.stdin.read() or ''
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}

def generate_image(api_key, prompt, size, quality, model):
    client = openai.OpenAI(api_key=api_key)
    # normalize
    model = model or 'gpt-image-1'
    # Map quality to allowed values for current API
    q_in = (quality or 'medium').lower()
    q = 'low' if q_in in ('low','standard') else ('high' if q_in in ('high','hd') else 'medium')
    s = size or '1024x1024'
    try:
        resp = client.images.generate(
            model=model,
            prompt=prompt,
            size=s,
            quality=q,
            n=1,
        )
        result = resp.data[0]
        b64 = getattr(result, 'b64_json', None)
        if b64:
            return f"data:image/png;base64,{base64.b64encode(base64.b64decode(b64)).decode('utf-8')}"
        url = getattr(result, 'url', None)
        if url:
            r = requests.get(url, timeout=120)
            r.raise_for_status()
            return f"data:image/png;base64,{base64.b64encode(r.content).decode('utf-8')}"
    except Exception as e:
        print(str(e), file=sys.stderr)
        return None

def main():
    try:
        dotenv.load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))
    except Exception:
        pass
    api_key = get_api_key()
    if not api_key:
        print('No OPENAI_API_KEY', file=sys.stderr)
        return 1
    payload = read_payload()
    prompt = payload.get('prompt')
    if not prompt:
        print('Missing prompt', file=sys.stderr)
        return 1
    size = payload.get('size') or '1024x1024'
    quality = payload.get('quality') or 'medium'
    model = payload.get('model') or 'gpt-image-1'
    out = generate_image(api_key, prompt, size, quality, model)
    if not out:
        print('Generation failed', file=sys.stderr)
        return 1
    print('GENERIC_IMAGE_START')
    print(json.dumps({ 'output': out }))
    print('GENERIC_IMAGE_END')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())


