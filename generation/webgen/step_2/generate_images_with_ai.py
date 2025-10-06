#!/usr/bin/env python3
# public/data/generation/webgen/step_2/generate_images_with_ai.py

import os
import json
import openai
import logging
import sys
import urllib.parse
import base64
from pathlib import Path
from datetime import datetime
import argparse
import dotenv

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
BBB_PROFILE_PATH = os.path.join(INPUT_DIR, 'bbb_profile_data.json')
IMAGES_OUTPUT_DIR = os.path.join(OUTPUT_DIR, 'generated_images')
IMAGES_JSON_PATH = os.path.join(OUTPUT_DIR, 'generated_images.json')
COMBINED_DATA_PATH = "/Users/rhettburnham/Desktop/projects/roofing-co/public/personal/old/jsons/combined_data.json"

# Ensure output directories exist
os.makedirs(IMAGES_OUTPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

def get_api_key():
    """Get OpenAI API key from environment variable."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("WARNING: The OPENAI_API_KEY environment variable is not set.")
        print(f"Looking for .env at: {env_path}")
        return None
    return api_key

def generate_logo_prompt(business_data):
    """
    Creates a prompt for generating a business logo based on BBB profile data.
    """
    business_name = business_data.get('business_name', 'a roofing company')
    services = business_data.get('services', [])
    
    # Create a description based on services
    service_description = ""
    if services:
        service_description = f" specializing in {', '.join(services)}"
    else:
        service_description = " specializing in roofing and construction services"
    
    prompt = f"""
Create a professional, minimalist logo for {business_name}, a construction company{service_description}.

The logo should be:
- Simple, clean, and professional design
- No text or letters - purely visual/iconic
- Suitable for a construction/roofing company
- Modern, trustworthy, and professional appearance
- Single color or simple color scheme
- Works well at small sizes
- Clean, minimalist background
- High resolution suitable for business use
- No text, watermarks, or branding overlays
- Perfect for use on business cards, websites, and marketing materials

The design should convey: professionalism, reliability, quality, and construction expertise.
"""
    return prompt.strip()

def load_combined_data(path: str = COMBINED_DATA_PATH, stdin_payload: dict | None = None):
    """Load combined_data.json for pulling example ImageProps prompts.
    Prefer memory-provided combinedData if present in stdin payload.
    """
    try:
        if isinstance(stdin_payload, dict) and stdin_payload.get('combinedData'):
            return stdin_payload['combinedData']
        if not os.path.exists(path):
            logger.warning(f"combined_data.json not found at {path}")
            return None
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except Exception as e:
        logger.error(f"Failed to read combined_data.json: {e}")
        return None

def extract_image_prompt_from_combined_data(
    combined_data,
    block_name: str = "HeroBlock",
    group_key: str = "imag_gen1",
    variant_key: str = "v1"
):
    """
    Extract a single prompt from ImageProps within combined_data.json.

    Returns (prompt_text, image_name) or (None, None) if not found.
    """
    try:
        blocks = combined_data.get("mainPageBlocks", []) if isinstance(combined_data, dict) else []
        target_block = next((b for b in blocks if b.get("blockName") == block_name), None)
        if not target_block:
            logger.warning(f"Block '{block_name}' not found in combined_data.json")
            return None, None

        image_props = (
            target_block.get("config", {}).get("ImageProps")
            if isinstance(target_block.get("config"), dict)
            else None
        )
        if not image_props:
            logger.warning(f"No ImageProps found for block '{block_name}'")
            return None, None

        group = image_props.get(group_key)
        if not group:
            logger.warning(f"ImageProps group '{group_key}' not found under '{block_name}'")
            return None, None

        prompt = group.get(variant_key)
        if not prompt:
            logger.warning(f"Variant '{variant_key}' not found in group '{group_key}' under '{block_name}'")
            return None, None

        image_name = f"combined_{block_name}_{group_key}_{variant_key}"
        return prompt, image_name
    except Exception as e:
        logger.error(f"Error extracting prompt from combined_data.json: {e}")
        return None, None

def generate_shingle_prompts():
    """
    Creates a list of prompts for generating professional shingle images.
    """
    prompts = [
        {
            "name": "premium_asphalt_shingle",
            "prompt": """
Create a professional, high-quality product photography image of a premium asphalt shingle. 
The image should be:
- Full-on view of the shingle showing its texture and color
- Professional lighting with subtle shadows to highlight depth
- Clean, minimalist background (white or light gray)
- High resolution suitable for online advertising
- Shows the shingle's dimensional texture and realistic appearance
- No text, watermarks, or branding overlays
- Perfect for use in roofing company marketing materials
""",
            "size": "1024x1024"
        },
        {
            "name": "shingle_texture_closeup",
            "prompt": """
Create a close-up, detailed photograph of asphalt shingle texture and surface details.
The image should be:
- Extreme close-up showing the granular texture and surface patterns
- Professional macro photography style
- Natural lighting that highlights the texture variations
- Clean background that doesn't distract from the shingle
- High resolution suitable for product detail pages
- Shows the realistic appearance of weathered shingle surface
- No text, watermarks, or branding overlays
""",
            "size": "1024x1024"
        },
        {
            "name": "shingle_installation_view",
            "prompt": """
Create a professional photograph showing a partially installed asphalt shingle roof.
The image should be:
- Side view showing shingles being installed on a roof
- Professional construction photography style
- Good lighting that shows the installation process
- Clean, professional appearance suitable for marketing
- Shows the quality and precision of the installation
- No text, watermarks, or branding overlays
- Perfect for demonstrating roofing expertise
""",
            "size": "1792x1024"
        },
        {
            "name": "shingle_color_variety",
            "prompt": """
Create a professional product photography image showing multiple asphalt shingle colors and styles.
The image should be:
- Multiple shingle samples arranged professionally
- Various colors and textures displayed together
- Professional lighting that shows color differences
- Clean, minimalist background (white or light gray)
- High resolution suitable for product selection pages
- Shows the variety of available shingle options
- No text, watermarks, or branding overlays
""",
            "size": "1792x1024"
        }
    ]
    return prompts

def generate_image_with_ai(api_key, prompt, size="1024x1024", model="image-generate-1", quality="medium"):
    """
    Calls the OpenAI API to generate an image.
    """
    try:
        client = openai.OpenAI(api_key=api_key)
        logger.info("Sending image generation request to OpenAI API...")

        # Normalize model alias (align with hero script env defaults)
        def normalize_model(selected_model: str) -> str:
            m = (selected_model or "").strip()
            if m.lower() == "image-generate-1":
                return "gpt-image-1"
            return m or "gpt-image-1"

        # Normalize quality based on model
        def normalize_quality(selected_model: str, selected_quality: str) -> str:
            m = (selected_model or "").lower()
            q = (selected_quality or "").lower()
            if m.startswith("gpt-image") or m == "gpt-image-1" or m == "image-generate-1":
                # Supported: low, medium, high, auto
                if q in {"low", "medium", "high", "auto"}:
                    return q
                if q == "standard":
                    return "medium"
                if q == "hd":
                    return "high"
                return "medium"
            # dall-e-3 branch
            if q in {"standard", "hd"}:
                return q
            if q in {"low", "medium"}:
                return "standard"
            if q in {"high", "auto"}:
                return "hd"
            return "standard"

        # Normalize size based on model
        def normalize_size(selected_model: str, requested_size: str) -> str:
            m = (selected_model or "").lower()
            s = (requested_size or "").lower()
            if m.startswith("gpt-image") or m == "gpt-image-1" or m == "image-generate-1":
                # Allowed: 1024x1024, 1024x1536, 1536x1024, auto
                allowed = {"1024x1024", "1024x1536", "1536x1024", "auto"}
                if s in allowed:
                    return s
                if s == "1792x1024":
                    return "1536x1024"
                if s == "1024x1792":
                    return "1024x1536"
                return "1024x1024"
            # dall-e-3 branch: allow 1024x1024 and 1792 variants
            if s in {"1792x1024", "1024x1792", "1024x1024"}:
                return s
            if s == "auto":
                return "1024x1024"
            return "1024x1024"

        model = normalize_model(model)
        normalized_quality = normalize_quality(model, quality)
        size = normalize_size(model, size)

        response = client.images.generate(
            model=model,
            prompt=prompt,
            size=size,
            quality=normalized_quality,
            n=1
        )

        image_url = response.data[0].url
        logger.info("Successfully generated image.")
        return image_url

    except Exception as e:
        logger.error(f"An error occurred while generating image: {e}")
        return None

def download_image(image_url, filename):
    """
    Downloads an image from URL and saves it locally.
    """
    try:
        import requests
        
        response = requests.get(image_url)
        response.raise_for_status()
        
        filepath = os.path.join(IMAGES_OUTPUT_DIR, filename)
        with open(filepath, 'wb') as f:
            f.write(response.content)
        
        logger.info(f"Image saved to {filepath}")
        return filepath
        
    except Exception as e:
        logger.error(f"Error downloading image: {e}")
        return None

def update_images_json(filename, prompt, size, timestamp, image_name, model, quality):
    """Update the generated_images.json file with new image info"""
    try:
        # Load existing data or create new
        if os.path.exists(IMAGES_JSON_PATH):
            with open(IMAGES_JSON_PATH, 'r', encoding='utf-8') as f:
                images_data = json.load(f)
        else:
            images_data = {
                'generated_images': [],
                'metadata': {
                    'total_images': 0,
                    'last_updated': datetime.now().isoformat()
                }
            }
        
        # Add new image info
        new_image = {
            'filename': filename,
            'filepath': os.path.join('generated_images', filename),
            'name': image_name,
            'prompt': prompt,
            'size': size,
            'generated_at': timestamp,
            'model': model,
            'quality': quality
        }
        
        images_data['generated_images'].append(new_image)
        images_data['metadata']['total_images'] = len(images_data['generated_images'])
        images_data['metadata']['last_updated'] = datetime.now().isoformat()
        
        # Save updated data
        with open(IMAGES_JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(images_data, f, indent=2)
            
        logger.info(f"Updated {IMAGES_JSON_PATH} with new image info")
        
    except Exception as e:
        logger.error(f"Error updating images JSON: {e}")

def generate_test_image_from_combined_data(api_key, block_name="HeroBlock", group_key="imag_gen1", variant_key="v1", size="1536x1024", model="gpt-image-1", quality="high", stdin_payload: dict | None = None):
    """Generate one test image using a prompt pulled from combined_data.json ImageProps.

    Parameters:
        block_name (str): Which block to read from (e.g., 'HeroBlock').
        group_key (str): Which ImageProps group (e.g., 'imag_gen1').
        variant_key (str): Which variant inside the group (e.g., 'v1').
        size (str): Image size to request from the API.
    """
    logger.info("--- Generating Test Image from combined_data.json ImageProps ---")

    combined = load_combined_data(stdin_payload=stdin_payload)
    if not combined:
        logger.warning("Skipping test image generation: combined_data.json not available")
        return False

    prompt, image_name = extract_image_prompt_from_combined_data(
        combined_data=combined,
        block_name=block_name,
        group_key=group_key,
        variant_key=variant_key
    )

    if not prompt:
        logger.warning("Could not extract ImageProps prompt; skipping test image generation")
        return False

    try:
        image_url = generate_image_with_ai(api_key, prompt, size, model=model, quality=quality)
        if not image_url:
            logger.error("Failed to generate test image from combined_data.json prompt")
            return False

        timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{image_name}_{timestamp_str}.png"

        filepath = download_image(image_url, filename)
        if not filepath:
            logger.error("Failed to download test image from combined_data.json prompt")
            return False

        update_images_json(filename, prompt, size, datetime.now().isoformat(), image_name, model, quality)
        logger.info(f"✓ Successfully generated test image from combined_data.json: {filename}")
        return True
    except Exception as e:
        logger.error(f"Error during test image generation from combined_data.json: {e}")
        return False

def generate_logo_for_business(business_data, api_key, model="gpt-image-1", quality="standard"):
    """
    Generate a logo for the business using AI.
    """
    logger.info("--- Generating Business Logo ---")
    
    try:
        # Generate logo prompt
        logo_prompt = generate_logo_prompt(business_data)
        logger.info("Generated logo prompt based on business profile")
        
        # Generate logo image
        logger.info("Generating logo with image model...")
        image_url = generate_image_with_ai(api_key, logo_prompt, "1024x1024", model=model, quality=quality)
        
        if image_url:
            # Create filename
            timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"business_logo_{timestamp_str}.png"
            
            # Download and save image
            filepath = download_image(image_url, filename)
            
            if filepath:
                # Update generated_images.json
                update_images_json(filename, logo_prompt, "1024x1024", 
                                 datetime.now().isoformat(), "business_logo", model, quality)
                
                # Also save as logo.png in the raw directory for color extraction
                logo_raw_path = os.path.join(INPUT_DIR, 'logo.png')
                import shutil
                shutil.copy2(filepath, logo_raw_path)
                logger.info(f"✓ Logo saved to raw directory: {logo_raw_path}")
                
                logger.info(f"✓ Successfully generated business logo: {filename}")
                return True
            else:
                logger.error("✗ Failed to download logo image")
                return False
        else:
            logger.error("✗ Failed to generate logo image")
            return False
            
    except Exception as e:
        logger.error(f"✗ Error generating logo: {e}")
        return False

def generate_images_for_webgen(model="gpt-image-1", quality="standard"):
    """
    Generate a set of professional shingle images for the webgen pipeline.
    """
    logger.info("--- Starting AI Image Generation for WebGen Pipeline ---")

    # Check if the BBB profile data exists
    if not os.path.exists(BBB_PROFILE_PATH):
        logger.warning(f"Business profile data not found at {BBB_PROFILE_PATH}. Skipping logo generation.")
        business_data = None
    else:
        # Load business data for context
        try:
            with open(BBB_PROFILE_PATH, 'r', encoding='utf-8') as f:
                business_data = json.load(f)
            logger.info(f"Successfully loaded business profile data for: {business_data.get('business_name', 'Unknown')}")
        except Exception as e:
            logger.error(f"Failed to read or parse {BBB_PROFILE_PATH}: {e}")
            business_data = None

    # Check API key
    api_key = get_api_key()
    if not api_key:
        print("ERROR: OpenAI API key not found. Please set the OPENAI_API_KEY environment variable.")
        print("Skipping image generation and continuing with pipeline...")
        return True

    # First, generate business logo (if business data exists)
    if business_data is not None:
        logo_success = generate_logo_for_business(business_data, api_key, model=model, quality=quality)
        if logo_success:
            print("✅ Business logo generated successfully!")
        else:
            print("⚠️  Business logo generation failed, continuing with other images...")

    # Then, generate one test image from combined_data.json ImageProps
    test_success = generate_test_image_from_combined_data(api_key, model=model, quality=quality)
    if test_success:
        print("✅ Test image from combined_data.json generated successfully!")
    else:
        print("⚠️  Test image from combined_data.json was skipped or failed.")

    # Get prompts for different shingle images
    prompts = generate_shingle_prompts()
    
    logger.info(f"Generating {len(prompts)} professional shingle images...")
    
    successful_generations = 0
    
    for i, prompt_data in enumerate(prompts, 1):
        logger.info(f"Generating image {i}/{len(prompts)}: {prompt_data['name']}")
        
        try:
            # Generate image
            image_url = generate_image_with_ai(api_key, prompt_data['prompt'], prompt_data['size'], model=model, quality=quality)
            
            if image_url:
                # Create filename
                timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"{prompt_data['name']}_{timestamp_str}.png"
                
                # Download and save image
                filepath = download_image(image_url, filename)
                
                if filepath:
                    # Update generated_images.json
                    update_images_json(filename, prompt_data['prompt'], prompt_data['size'], 
                                     datetime.now().isoformat(), prompt_data['name'], model, quality)
                    
                    successful_generations += 1
                    logger.info(f"✓ Successfully generated: {filename}")
                else:
                    logger.error(f"✗ Failed to download image: {prompt_data['name']}")
            else:
                logger.error(f"✗ Failed to generate image: {prompt_data['name']}")
                
        except Exception as e:
            logger.error(f"✗ Error generating {prompt_data['name']}: {e}")
    
    logger.info(f"Image generation complete: {successful_generations}/{len(prompts)} images generated successfully")
    
    if successful_generations > 0:
        print(f"\n✅ Successfully generated {successful_generations} professional shingle images")
        print(f"📁 Images saved to: {IMAGES_OUTPUT_DIR}")
        print(f"📄 Metadata saved to: {IMAGES_JSON_PATH}")
    else:
        print("\n⚠️  No images were generated successfully")
    
    return successful_generations > 0

def main():
    """
    Main function to run image generation as part of the webgen pipeline.
    """
    parser = argparse.ArgumentParser(description="Generate AI images for roofing website assets.")
    parser.add_argument("--prompt", type=str, default=None, help="Direct prompt text to generate a single image.")
    parser.add_argument("--size", type=str, default="1024x1024", help="Image size, e.g., 1024x1024 or 1792x1024.")
    parser.add_argument("--from-combined", action="store_true", help="Use a prompt from combined_data.json ImageProps.")
    parser.add_argument("--block", type=str, default="HeroBlock", help="Block name in combined_data.json.")
    parser.add_argument("--group", type=str, default="imag_gen1", help="ImageProps group key, e.g., imag_gen1.")
    parser.add_argument("--variant", type=str, default="v1", help="Variant key within the group, e.g., v1.")
    # Defaults align with hero script env names, with alias mapping handled in generate_image_with_ai
    env_model_default = os.environ.get("HERO_IMAGE_MODEL", "image-generate-1")
    env_quality_default = os.environ.get("HERO_IMAGE_QUALITY", "medium")
    env_size_default = os.environ.get("HERO_IMAGE_SIZE")
    if env_size_default:
        # Override CLI default if set via env to keep parity with hero script
        parser.set_defaults(size=env_size_default)

    parser.add_argument("--model", type=str, default=env_model_default, help="Image model to use (e.g., gpt-image-1, image-generate-1, dall-e-3).")
    parser.add_argument("--quality", type=str, default=env_quality_default, choices=["standard", "hd", "low", "medium", "high", "auto"], help="Image quality tier.")
    args = parser.parse_args()

    # Attempt to parse optional stdin payload for memory-only runs
    stdin_payload = None
    try:
        raw = sys.stdin.read()
        if raw:
            stdin_payload = json.loads(raw)
    except Exception:
        stdin_payload = None

    # Check API key
    api_key = get_api_key()
    if not api_key:
        print("ERROR: OpenAI API key not found. Please set the OPENAI_API_KEY environment variable in public/data/generation/.env or your shell.")
        return False

    # Mode 1: Direct prompt
    if args.prompt is not None:
        logger.info("--- Generating single image from direct --prompt ---")
        image_url = generate_image_with_ai(api_key, args.prompt, args.size, model=args.model, quality=args.quality)
        if not image_url:
            print("✗ Failed to generate image from provided prompt")
            return False
        timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"direct_prompt_{timestamp_str}.png"
        filepath = download_image(image_url, filename)
        if not filepath:
            print("✗ Failed to download image")
            return False
        update_images_json(filename, args.prompt, args.size, datetime.now().isoformat(), "direct_prompt", args.model, args.quality)
        print(f"✅ Generated image from --prompt and saved to {filepath}")
        return True

    # Mode 2: Prompt from combined_data.json
    if args["from_combined"] if isinstance(args, dict) else args.from_combined:
        ok = generate_test_image_from_combined_data(
            api_key,
            block_name=args.block,
            group_key=args.group,
            variant_key=args.variant,
            size=args.size,
            model=args.model,
            quality=args.quality,
            stdin_payload=stdin_payload,
        )
        if ok:
            print("\n🎉 Combined-data image generation completed successfully!")
            return True
        print("\n⚠️  Combined-data image generation failed")
        return False

    # Mode 3: Full pipeline
    success = generate_images_for_webgen(model=args.model, quality=args.quality)
    if success:
        print("\n🎉 AI Image Generation completed successfully!")
        return True
    else:
        print("\n⚠️  AI Image Generation completed with warnings (continuing pipeline)")
        return True  # Return True to continue pipeline even if no images generated

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
