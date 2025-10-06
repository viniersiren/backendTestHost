#!/usr/bin/env python3
# public/data/generation/webgen/step_2/logogen.py

import os
import json
import openai
import logging
import sys
import urllib.parse
import base64
from pathlib import Path
from datetime import datetime
import dotenv
import requests
import shutil

# --- Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# --- Load API Key from .env file ---
env_path = Path(__file__).parent.parent.parent / ".env"
dotenv.load_dotenv(env_path)

# --- File Paths ---
INPUT_DIR = "/Users/rhettburnham/Desktop/projects/roofing-co/public/data/output/individual/step_1/raw"
OUTPUT_DIR = "/Users/rhettburnham/Desktop/projects/roofing-co/public/data/output/individual/step_2"
LEADS_FINAL_DIR = "/Users/rhettburnham/Desktop/projects/roofing-co/public/data/output/leads/final"
LOGO_FINAL_DIR = os.path.join(LEADS_FINAL_DIR, 'logo')
BBB_PROFILE_PATH = os.path.join(INPUT_DIR, 'bbb_profile_data.json')
LOGO_OUTPUT_DIR = os.path.join(OUTPUT_DIR, 'generated_logos')
LOGO_RAW_PATH = os.path.join(LOGO_FINAL_DIR, 'logo.png')

# MEMORY_ONLY: Avoid creating output directories when running in memory-only mode
MEMORY_ONLY = os.environ.get('MEMORY_ONLY', '0') == '1'
if not MEMORY_ONLY:
    os.makedirs(LOGO_OUTPUT_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(LEADS_FINAL_DIR, exist_ok=True)
    os.makedirs(LOGO_FINAL_DIR, exist_ok=True)

def get_api_key():
    """Get OpenAI API key from environment variable."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("WARNING: The OPENAI_API_KEY environment variable is not set.")
        print(f"Looking for .env at: {env_path}")
        return None
    return api_key

def generate_logo_prompt(business_data, variation=1):
    """
    Creates a prompt for generating a business logo based on BBB profile data.
    """
    business_name = business_data.get('business_name', 'a roofing company')
    services = business_data.get('services', [])
    address = business_data.get('address', '')
    
    # Create a description based on services
    service_description = ""
    if services:
        service_description = f" specializing in {', '.join(services)}"
    else:
        service_description = " specializing in roofing and construction services"
    
    # Extract location info
    location_info = ""
    if address:
        if "GA" in address or "Georgia" in address:
            location_info = " based in Georgia"
        elif "Atlanta" in address:
            location_info = " based in Atlanta, Georgia"
    
    # Different style variations for each logo (favor ultra-minimal outcomes)
    style_variations = {
        1: "ultra-minimal monoline flat icon with thick strokes",
        2: "single-color solid silhouette using one basic geometric shape", 
        3: "simple negative-space pictogram with clear contrast",
        4: "rounded flat icon with at most two shapes",
        5: "abstract geometric mark using a single motif"
    }
    
    style = style_variations.get(variation, "simple and professional")
    
    prompt = f"""
Create a professional, ULTRA-MINIMAL logo for {business_name}, a construction company{service_description}{location_info}.

Hard requirements:
- EXTREMELY SIMPLE, flat, iconic design. Avoid any complexity.
- NO TEXT OR LETTERS. Icon only.
- {style} style.
- Use a SINGLE SOLID COLOR or at most two harmonious tones (prefer one color).
- FLAT design only: no gradients, no shadows, no 3D, no bevel, no textures.
- Use 1–2 simple shapes maximum. Favor large, bold forms.
- THICK strokes if outlines are used; avoid thin lines and fine details.
- Centered composition with generous whitespace. No background patterns.
- Works clearly at small sizes (favicon, business card).
- Suitable for roofing/construction: simple roofline, house, or geometric construction motif.

Include exactly one motif:
- A single roof shape or house outline; OR
- One geometric construction element (triangle/chevron/beam) with clear silhouette.

Strictly avoid:
- Any text, letters, numbers, monograms, or words.
- Photorealism, complex illustrations, detailed scenes.
- Thin strokes, intricate linework, fine textures, hatching.
- Gradients, drop shadows, glows, 3D perspective, reflections.
- Busy compositions or multiple overlapping elements.

Keep it extremely simple and clean. Prioritize clarity and minimal shapes.
"""
    return prompt.strip()

def generate_image_with_ai(api_key, prompt, size=None):
    """
    Calls the OpenAI API to generate an image.
    """
    try:
        client = openai.OpenAI(api_key=api_key)
        logger.info("Sending logo generation request to OpenAI API...")

        if size is None:
            size = os.environ.get('LOGO_PREVIEW_SIZE', '1024x1024')

        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size=size,
            quality="standard",
            n=1
        )

        image_url = response.data[0].url
        logger.info("Successfully generated logo image.")
        return image_url

    except Exception as e:
        logger.error(f"An error occurred while generating logo: {e}")
        return None

def download_image(image_url, filename):
    """
    Downloads an image from URL and saves it locally.
    """
    try:
        response = requests.get(image_url)
        response.raise_for_status()
        
        if MEMORY_ONLY:
            # Return base64 content directly (do not write to disk)
            b64 = base64.b64encode(response.content).decode('utf-8')
            return f"data:image/png;base64,{b64}"
        else:
            filepath = os.path.join(LOGO_OUTPUT_DIR, filename)
            with open(filepath, 'wb') as f:
                f.write(response.content)
            logger.info(f"Logo saved to {filepath}")
            return filepath
        
    except Exception as e:
        logger.error(f"Error downloading logo: {e}")
        return None

def update_logo_json(filename, prompt, size, timestamp, business_name):
    """Update the generated_logos.json file with new logo info"""
    logo_json_path = os.path.join(OUTPUT_DIR, 'generated_logos.json')
    
    try:
        # Load existing data or create new
        if os.path.exists(logo_json_path):
            with open(logo_json_path, 'r', encoding='utf-8') as f:
                logos_data = json.load(f)
        else:
            logos_data = {
                'generated_logos': [],
                'metadata': {
                    'total_logos': 0,
                    'last_updated': datetime.now().isoformat()
                }
            }
        
        # Add new logo info
        new_logo = {
            'filename': filename,
            'filepath': os.path.join('generated_logos', filename),
            'business_name': business_name,
            'prompt': prompt,
            'size': size,
            'generated_at': timestamp,
            'model': 'dall-e-3',
            'quality': 'standard'
        }
        
        logos_data['generated_logos'].append(new_logo)
        logos_data['metadata']['total_logos'] = len(logos_data['generated_logos'])
        logos_data['metadata']['last_updated'] = datetime.now().isoformat()
        
        if not MEMORY_ONLY:
            with open(logo_json_path, 'w', encoding='utf-8') as f:
                json.dump(logos_data, f, indent=2)
            logger.info(f"Updated {logo_json_path} with new logo info")
        
    except Exception as e:
        logger.error(f"Error updating logos JSON: {e}")

def generate_logo_for_business():
    """
    Generate 5 logo variations for the business using AI based on BBB profile data.
    """
    logger.info("--- Starting AI Logo Generation (5 variations) ---")

    # Check if the BBB profile data exists
    if not os.path.exists(BBB_PROFILE_PATH) and not MEMORY_ONLY:
        logger.error(f"Business profile data not found at {BBB_PROFILE_PATH}.")
        print(f"ERROR: Cannot find 'bbb_profile_data.json'. Please run the scraping script first.")
        sys.exit(1)

    # Load business data
    business_data = {}
    if os.path.exists(BBB_PROFILE_PATH):
        try:
            with open(BBB_PROFILE_PATH, 'r', encoding='utf-8') as f:
                business_data = json.load(f)
            logger.info(f"Successfully loaded business profile data for: {business_data.get('business_name', 'Unknown')}")
        except Exception as e:
            logger.error(f"Failed to read or parse {BBB_PROFILE_PATH}: {e}")
            business_data = {}

    # Check API key
    api_key = get_api_key()
    if not api_key:
        print("ERROR: OpenAI API key not found. Please set the OPENAI_API_KEY environment variable.")
        print("Cannot generate logo without API key.")
        sys.exit(1)

    business_name = business_data.get('business_name', 'business')
    safe_name = "".join(c for c in business_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
    safe_name = safe_name.replace(' ', '_')
    timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    successful_generations = 0
    memory_variants = []  # list of data URLs when MEMORY_ONLY
    
    # Generate 5 logo variations
    for variation in range(1, 6):
        logger.info(f"Generating logo variation {variation}/5...")
        
        # Generate logo prompt for this variation
        logo_prompt = generate_logo_prompt(business_data, variation)
        logger.info(f"Generated logo prompt for variation {variation}")
        
        # Generate logo image
        logger.info(f"Generating logo variation {variation} with DALL-E...")
        image_url = generate_image_with_ai(api_key, logo_prompt, "1024x1024")
        
        if image_url:
            # Create filename for this variation
            filename = f"logo_{safe_name}_variation_{variation}_{timestamp_str}.png"
            
            # Download and save image
            filepath = download_image(image_url, filename)
            
            if filepath:
                if MEMORY_ONLY and filepath.startswith('data:image'):
                    memory_variants.append(filepath)
                    successful_generations += 1
                    logger.info(f"✓ Successfully generated logo variation {variation}: (memory)")
                    continue
                # Update generated_logos.json
                update_logo_json(filename, logo_prompt, "1024x1024", 
                               datetime.now().isoformat(), business_name)
                
                # Save to leads/final/logo directory
                final_logo_path = os.path.join(LOGO_FINAL_DIR, f"logo_variation_{variation}.png")
                try:
                    shutil.copy2(filepath, final_logo_path)
                    logger.info(f"✓ Logo variation {variation} saved to: {final_logo_path}")
                except Exception as e:
                    logger.error(f"Error copying logo variation {variation} to final directory: {e}")
                
                successful_generations += 1
                logger.info(f"✓ Successfully generated logo variation {variation}: {filename}")
            else:
                logger.error(f"✗ Failed to download logo variation {variation}")
        else:
            logger.error(f"✗ Failed to generate logo variation {variation}")
    
    if successful_generations > 0:
        if MEMORY_ONLY and memory_variants:
            # Emit base64 list for backend to capture
            print("LOGO_VARIANTS_BASE64_START")
            print(json.dumps(memory_variants))
            print("LOGO_VARIANTS_BASE64_END")
        else:
            print(f"\n✅ Successfully generated {successful_generations}/5 logo variations!")
            print(f"📁 Logos saved to: {LEADS_FINAL_DIR}")
            print(f"📄 Metadata saved to: {os.path.join(OUTPUT_DIR, 'generated_logos.json')}")
        return True
    else:
        print("❌ Failed to generate any logo variations")
        return False

def main():
    """
    Main function to run logo generation.
    """
    success = generate_logo_for_business()
    
    if success:
        print("\n🎉 AI Logo Generation completed successfully!")
        print("The logo is now available for color extraction and website use.")
        return True
    else:
        print("\n❌ AI Logo Generation failed!")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
