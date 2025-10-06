#!/usr/bin/env python3
import sys
import json
import os
from pathlib import Path
from datetime import datetime
import logging
import dotenv
from openai import OpenAI

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load API key (optional): may be used if you want to generate via OpenAI images API here
env_path = Path(__file__).parent.parent.parent / ".env"
dotenv.load_dotenv(env_path)

OUTPUT_ROOT = "/Users/rhettburnham/Desktop/projects/roofing-co/public/data/generation/webgen/img/services"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

def ensure_parent_dir(path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)

def read_jobs_from_stdin():
    raw = sys.stdin.read()
    if not raw.strip():
        raise RuntimeError("No jobs JSON received on STDIN")
    data = json.loads(raw)
    jobs = data.get('jobs', [])
    return jobs

def map_old_to_generation(abs_old: str) -> str:
    return abs_old.replace(
        "/Users/rhettburnham/Desktop/projects/roofing-co/public/personal/old/img/services",
        OUTPUT_ROOT
    )

def write_placeholder_png(path: str):
    ensure_parent_dir(path)
    with open(path, 'wb') as f:
        f.write(b"\x89PNG\r\n\x1a\n")

def generate_image_to_path(prompt: str, path: str) -> bool:
    try:
        if not OPENAI_API_KEY:
            write_placeholder_png(path)
            return False
        client = OpenAI(api_key=OPENAI_API_KEY)
        # gpt-image-1 returns base64 data
        resp = client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size="1024x1024",
            n=1
        )
        b64 = resp.data[0].b64_json if hasattr(resp.data[0], 'b64_json') else None
        url = getattr(resp.data[0], 'url', None)
        ensure_parent_dir(path)
        if b64:
            import base64
            with open(path, 'wb') as f:
                f.write(base64.b64decode(b64))
            return True
        elif url:
            import requests
            r = requests.get(url)
            r.raise_for_status()
            with open(path, 'wb') as f:
                f.write(r.content)
            return True
        else:
            write_placeholder_png(path)
            return False
    except Exception as e:
        logger.error(f"image generation failed: {e}")
        write_placeholder_png(path)
        return False

def main():
    try:
        jobs = read_jobs_from_stdin()
        logger.info(f"Received {len(jobs)} image jobs")
        results = []
        for job in jobs:
            old_path = job.get('oldPath')
            new_path = job.get('path') or map_old_to_generation(old_path or '')
            prompt = job.get('prompt') or 'Service block image'
            if not new_path:
                continue
            ok = generate_image_to_path(prompt, new_path)
            results.append({
                'ok': ok,
                'oldPath': old_path,
                'newPath': new_path,
                'prompt': prompt
            })
        print(json.dumps({
            'success': True,
            'generatedAt': datetime.now().isoformat(),
            'results': results
        }, indent=2))
    except Exception as e:
        print(json.dumps({'success': False, 'error': str(e)}))
        sys.exit(1)

if __name__ == "__main__":
    main()


