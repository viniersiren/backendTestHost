#!/usr/bin/env python3
import json
import os
import re
import random
import requests
import time
import dotenv
from pathlib import Path
from typing import Dict, List, Any
import sys

# Memory mode: emit results to stdout and also persist ONLY to the generation folder for preview/zip.
MEMORY_ONLY = True

# OpenAI (preferred) - load from public/data/generation/.env if present as well
try:
    dotenv.load_dotenv(Path(__file__).parent.parent / ".env")
except Exception:
    pass
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"

print(f"[ServicesJSON] OpenAI key present: {bool(OPENAI_API_KEY)}")
print(f"[ServicesJSON] MEMORY_ONLY: {MEMORY_ONLY}")

# ----------------------------- NEW: normalization helpers ---------------------------------

def _first_nonempty(*vals: str) -> str:
    for v in vals:
        if isinstance(v, str) and v.strip():
            return v
    return ""

def normalize_research_fields(service_obj: Dict[str, Any]) -> Dict[str, str]:
    """Normalize research data keys so downstream composition can rely on a stable schema.
    Attempts multiple key locations/names and falls back gracefully to empty strings.
    """
    # Allow nested 'research' object or flat keys
    research = service_obj.get('research', {}) if isinstance(service_obj.get('research'), dict) else {}

    installation = _first_nonempty(
        service_obj.get('installation', ''),
        service_obj.get('construction_process', ''),
        research.get('installation', ''),
        research.get('construction_process', ''),
    )

    maintenance = _first_nonempty(
        service_obj.get('maintenance', ''),
        service_obj.get('warranty_maintenance', ''),
        research.get('maintenance', ''),
        research.get('warranty_maintenance', ''),
    )

    repair = _first_nonempty(
        service_obj.get('repair', ''),
        research.get('repair', ''),
        service_obj.get('advantages', ''),
        research.get('advantages', ''),
    )

    variants = _first_nonempty(
        service_obj.get('variants', ''),
        research.get('variants', ''),
    )

    marketing = _first_nonempty(
        service_obj.get('marketing', ''),
        research.get('marketing', ''),
    )

    return {
        'installation': installation,
        'maintenance': maintenance,
        'repair': repair,
        'variants': variants,
        'marketing': marketing,
    }

# ----------------------------- NEW: template loading & enforcement -------------------------

from copy import deepcopy

def _get_repo_root() -> Path:
    p = Path(__file__).resolve()
    try:
        return p.parents[5]
    except Exception:
        return p

def load_services_template() -> Dict[str, Any]:
    """Load template with canonical blocks/config shape."""
    candidates = [
        _get_repo_root() / 'public' / 'personal' / 'old' / 'jsons' / 'services_template.json',
        Path(__file__).resolve().parents[4] / 'personal' / 'old' / 'jsons' / 'services_template.json',
    ]
    for tp in candidates:
        try:
            if tp.exists():
                with open(tp, 'r') as f:
                    data = json.load(f)
                    print(f"[ServicesJSON] Loaded template from: {tp}")
                    return data
        except Exception as e:
            print(f"[ServicesJSON] Failed loading template at {tp}: {e}")
    print("[ServicesJSON] No services_template.json found - proceeding without template constraints")
    return {}

def _index_template_blocks(template: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    res: Dict[str, Dict[str, Any]] = {}
    for blk in template.get('blocks', []) or []:
        name = blk.get('blockName')
        cfg = blk.get('config')
        if name and isinstance(cfg, dict):
            res[name] = cfg
    return res

def _index_template_image_prefs(template: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Return blockName -> ImageProps dict from template (AI_script, in_images, prompt, preference)."""
    results: Dict[str, Dict[str, Any]] = {}
    for blk in template.get('blocks', []) or []:
        name = blk.get('blockName')
        cfg = blk.get('config') or {}
        img = cfg.get('ImageProps') or {}
        if name and isinstance(img, dict):
            results[name] = img
    return results

def _merge_content_over_template(template_cfg: Dict[str, Any], ai_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Return new config merging AI Content into template, while preserving template image paths.

    Rules:
    - Start from AI Content (texts, items, etc.) if present, else from template Content
    - Overwrite any top-level image path fields from the template when available:
      keys: images, image, imageUrl, heroImage, backgroundImage, backgroundImageUrl
    - If both AI and template provide items arrays, preserve per-item image fields from template
      (image, imageUrl) by index when present.
    - Design/Formatting from template are left untouched by caller.
    """
    result = deepcopy(template_cfg) if isinstance(template_cfg, dict) else {}
    template_content = (template_cfg or {}).get('Content') if isinstance(template_cfg, dict) else None
    ai_content = (ai_cfg or {}).get('Content') if isinstance(ai_cfg, dict) else None

    # Start from AI Content if provided; otherwise keep template Content
    merged_content: Dict[str, Any] = {}
    if isinstance(ai_content, dict):
        merged_content = deepcopy(ai_content)
    elif isinstance(template_content, dict):
        merged_content = deepcopy(template_content)

    # Helper to set if template has
    def _preserve_from_template(key: str):
        try:
            if isinstance(template_content, dict) and key in template_content:
                merged_content[key] = deepcopy(template_content[key])
        except Exception:
            pass

    # Preserve common image keys at top-level Content
    for k in ['images', 'image', 'imageUrl', 'heroImage', 'backgroundImage', 'backgroundImageUrl']:
        _preserve_from_template(k)

    # Preserve per-item image fields by index when both sides have items arrays
    try:
        if isinstance(template_content, dict) and isinstance(template_content.get('items'), list) \
           and isinstance(merged_content.get('items'), list):
            t_items = template_content.get('items')
            m_items = merged_content.get('items')
            for i in range(min(len(t_items), len(m_items))):
                ti = t_items[i] if isinstance(t_items[i], dict) else None
                mi = m_items[i] if isinstance(m_items[i], dict) else None
                if isinstance(ti, dict) and isinstance(mi, dict):
                    for key in ['image', 'imageUrl']:
                        if key in ti:
                            mi[key] = deepcopy(ti[key])
    except Exception:
        pass

    # Write back merged Content
    if merged_content:
        result['Content'] = merged_content
    return result

def enforce_template_on_blocks(ai_blocks: List[Dict[str, Any]], template: Dict[str, Any]) -> List[Dict[str, Any]]:
    tmpl_index = _index_template_blocks(template)
    if not tmpl_index:
        return ai_blocks
    ai_by_name: Dict[str, Dict[str, Any]] = {}
    for b in ai_blocks or []:
        name = b.get('blockName')
        if name in tmpl_index and isinstance(b.get('config'), dict):
            ai_by_name[name] = b
    enforced: List[Dict[str, Any]] = []
    for tmpl_blk in template.get('blocks', []) or []:
        name = tmpl_blk.get('blockName')
        tmpl_cfg = tmpl_blk.get('config') or {}
        ai_cfg = (ai_by_name.get(name) or {}).get('config') or {}
        merged_cfg = _merge_content_over_template(tmpl_cfg, ai_cfg)
        enforced.append({'blockName': name, 'config': merged_cfg})
    return enforced

def build_preference_hints(template: Dict[str, Any]) -> str:
    """Concise mapping of blockName -> preference text (if present) to guide the AI composer."""
    lines: List[str] = []
    for blk in template.get('blocks', []) or []:
        name = blk.get('blockName')
        pref = (blk.get('config') or {}).get('ImageProps', {}) if isinstance(blk.get('config'), dict) else {}
        pref_text = pref.get('preference')
        if name and isinstance(pref_text, str) and pref_text.strip():
            lines.append(f"- {name}: {pref_text.strip()}")
    return "\n".join(lines)

def _parse_in_images(value: Any) -> int:
    """Convert an in_images value like '3-6' or '2-4' or '0' into an integer image count.
    Special rule: for '2-4', choose either 2 or 4 (never 3).
    """
    try:
        if isinstance(value, int):
            return max(0, value)
        s = str(value).strip()
        if not s:
            return 0
        if '-' in s:
            parts = s.split('-')
            lo = int(parts[0].strip())
            hi = int(parts[1].strip())
            if lo == 2 and hi == 4:
                return random.choice([2, 4])
            if hi < lo:
                lo, hi = hi, lo
            return random.randint(lo, hi)
        return max(0, int(s))
    except Exception:
        return 0

def _format_prompt_for_script(base_prompt: str, script: str, service_name: str, block_name: str, idx: int) -> str:
    """Format a single prompt string appropriate to the target generator script.
    - AI: pass through with light context.
    - swatch: emphasize top‑down material sample characteristics.
    """
    base = (base_prompt or "").strip()
    if script == 'swatch':
        return (
            f"{service_name} — {block_name} — MATERIAL SWATCH (square, orthographic top‑down, uniform repeating layout). "
            f"{base}"
        ).strip()
    return (
        f"{service_name} — {block_name} — {base}"
    ).strip()

def attach_image_prompts_from_template(blocks: List[Dict[str, Any]], template: Dict[str, Any], service_name: str) -> List[Dict[str, Any]]:
    """For each block, read ImageProps from the template and emit prompt_1..prompt_N into config.ImageProps
    based on in_images (with 2-4 rule). Keeps AI_script and in_images from template. Does not change image paths."""
    tmpl_prefs = _index_template_image_prefs(template)
    for blk in blocks or []:
        name = blk.get('blockName')
        cfg = blk.get('config') or {}
        img_cfg = cfg.get('ImageProps') or {}
        t_img = tmpl_prefs.get(name) or {}

        ai_script = t_img.get('AI_script') or img_cfg.get('AI_script')
        in_images_val = t_img.get('in_images') if t_img.get('in_images') is not None else img_cfg.get('in_images')
        prompt_seed = t_img.get('prompt') if t_img.get('prompt') is not None else img_cfg.get('prompt')
        preference = t_img.get('preference') if t_img.get('preference') is not None else img_cfg.get('preference')

        if ai_script is not None:
            img_cfg['AI_script'] = ai_script
        if in_images_val is not None:
            img_cfg['in_images'] = str(in_images_val)
        if preference is not None:
            img_cfg['preference'] = preference
        if prompt_seed is not None:
            img_cfg['prompt'] = prompt_seed

        # Build prompt_1..N
        try:
            count = _parse_in_images(in_images_val)
            if isinstance(prompt_seed, str) and prompt_seed.strip().lower() == 'false':
                count = 0
            # clear legacy prompts
            if 'promptsByPath' in img_cfg:
                try:
                    del img_cfg['promptsByPath']
                except Exception:
                    pass
            for k in list(img_cfg.keys()):
                if isinstance(k, str) and k.startswith('prompt_'):
                    try:
                        del img_cfg[k]
                    except Exception:
                        pass
            if count > 0 and isinstance(prompt_seed, str) and prompt_seed.strip() and ai_script:
                for i in range(1, count + 1):
                    img_cfg[f'prompt_{i}'] = _format_prompt_for_script(prompt_seed, ai_script, service_name, name or 'Block', i)
        except Exception:
            pass

        cfg['ImageProps'] = img_cfg
        blk['config'] = cfg
    return blocks

def build_template_prompt_hint(template: Dict[str, Any]) -> str:
    names = [b.get('blockName') for b in template.get('blocks', []) or [] if b.get('blockName')]
    lines = []
    if names:
        lines.append("AllowedBlocks: " + ", ".join(names))
        lines.append("ShapeRule: For each block, keep Design and Formatting structure; you only fill Content.* fields (titles, descriptions, items, images, rates, etc.).")
        lines.append("DoNot: invent blocks or keys outside Content; do not modify Design/Formatting.")
    return "\n".join(lines)

# ----------------------------- NEW: AI block composition -----------------------------------

def compose_blocks_with_ai(service_name: str, category: str, legacy_base: str, research_norm: Dict[str, str], template: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Ask OpenAI to compose a blocks array using legacy image path rules and research-derived content.
    Returns parsed blocks or raises on parse failure so caller can fallback.
    """
    tmpl_hint = build_template_prompt_hint(template)
    preference_hints = build_preference_hints(template)
    allowed_names = ", ".join([b.get('blockName') for b in template.get('blocks', []) or [] if b.get('blockName')]) or "HeroBlock, OverviewAndAdvantagesBlock, GeneralListVariant2, NumberedImageTextBlock, PricingGrid, AccordionBlock, OptionSelectorBlock, CallToActionButtonBlock"
    prompt = f"""
    You are composing a website service page using a predefined library of React blocks. The page is for the service: "{service_name}" in the {category} category.

    Use these research notes to inform the content you write:
    - Installation (steps/process):\n{research_norm.get('installation','')}
    - Maintenance (care/warranty):\n{research_norm.get('maintenance','')}
    - Repair notes:\n{research_norm.get('repair','')}
    - Variants/types/options:\n{research_norm.get('variants','')}
    - Marketing highlights:\n{research_norm.get('marketing','')}

    Compose a JSON object with a single key "blocks" (array). Each item must be:
    {{ "blockName": string, "config": object }}

    Use a selection of these allowed block types (do not invent others):
    {allowed_names}

    Rules:
    - Write concise, professional content derived from the research notes.
    - ALWAYS include a "HeroBlock" as the FIRST block in the array. The hero anchors the page.
    - Prefer blocks whose usage/preferences match the following guidance:
      {preference_hints}
    - Do NOT include any image paths in Content (e.g., omit images/imageUrl fields or leave arrays empty). Image paths will be provided by the template.
    - Do not invent additional fields beyond what typical blocks use (title, description, items, features, images, rates, etc.). Keep configs simple and consistent.
    - IMPORTANT TEMPLATE CONSTRAINTS:\n{tmpl_hint}
      Only populate Content.* fields; do not include Design or Formatting in your output.
    - Return ONLY JSON (no backticks, no prose). Example shape:
      {{ "blocks": [ {{ "blockName": "HeroBlock", "config": {{ "Content": {{"mainTitle": "...", "subTitle": "..." }} }} }} ] }}
    """

    ai = call_openai_chat(prompt)
    if not ai or ai.startswith("Error:"):
        raise RuntimeError(f"OpenAI error: {ai}")

    start = ai.find('{')
    end = ai.rfind('}') + 1
    if start < 0 or end <= start:
        raise ValueError("No JSON object found in AI response")

    parsed = json.loads(ai[start:end])
    blocks = parsed.get('blocks')
    if not isinstance(blocks, list):
        raise ValueError("AI output missing 'blocks' list")

    # Minimal validation: ensure required keys
    for b in blocks:
        if not isinstance(b, dict) or 'blockName' not in b or 'config' not in b:
            raise ValueError("Invalid block entry in AI output")

    return blocks

# ----------------------------- existing helpers continue -----------------------------------

def call_openai_chat(prompt: str) -> str:
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 4000
    }
    try:
        resp = requests.post(OPENAI_ENDPOINT, headers=headers, json=data, timeout=60)
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"]
        return f"Error: {resp.status_code} - {resp.text}"
    except Exception as e:
        return f"Error: {e}"

# These are shorter service options matching the combined_data.json format
# Services are 1-3 words max as required
ROOFING_SERVICE_OPTIONS = {
    "residential": [
        "Shingling",
        "Guttering",
        "Chimney",
        "Skylights",
        "Siding",
        "Ventilation",
        "Insulation",
        "Waterproofing",
        "Repairs",
        "Inspection",
        "Metal Roof",
        "Ridge Vents",
        "Attic Fans",
        "Fascia",
        "Flashing",
        "Soffits"
    ],
    "commercial": [
        "Coatings",
        "Built-Up",
        "Metal Roof",
        "Drainage",
        "TPO Systems",
        "EPDM",
        "PVC Membrane",
        "Modified Bitumen",
        "Restoration",
        "Maintenance",
        "Flat Roof",
        "Roof Deck",
        "Green Roof",
        "Solar Panels",
        "Sheet Metal",
        "Ventilation"
    ]
}

# Default services from combined_data.json to use as fallbacks
DEFAULT_SERVICES = {
    "residential": [
        {"id": 1, "name": "Shingling"},
        {"id": 2, "name": "Guttering"},
        {"id": 3, "name": "Chimney"},
        {"id": 4, "name": "Skylights"}
    ],
    "commercial": [
        {"id": 1, "name": "Coatings"},
        {"id": 2, "name": "Built-Up"},
        {"id": 3, "name": "Metal Roof"},
        {"id": 4, "name": "Drainage"}
    ]
}

def export_services_list(services=None):
    """Export the defined services to a shared JSON file.
    
    Args:
        services: The services to export. If None, exports ROOFING_SERVICES.
    """
    services_to_export = services if services is not None else {}
    
    # Save to the raw_data/step_2 directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    raw_data_dir = os.path.join(os.path.dirname(script_dir), "raw_data", "step_2")
    os.makedirs(raw_data_dir, exist_ok=True)
    
    services_path = os.path.join(raw_data_dir, "roofing_services.json")
    with open(services_path, 'w') as f:
        json.dump(services_to_export, f, indent=2)
    print(f"Exported services list to {services_path}")
    
    return services_path

def load_combined_data():
    """Attempt to load combined_data.json to extract current services."""
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.dirname(script_dir)
        
        # Try the step_4 directory first
        combined_data_path = os.path.join(data_dir, "raw_data", "step_4", "combined_data.json")
        if not os.path.exists(combined_data_path):
            # Fallback to root data directory
            combined_data_path = os.path.join(data_dir, "combined_data.json")
        
        if os.path.exists(combined_data_path):
            with open(combined_data_path, 'r') as f:
                data = json.load(f)
                
            # Extract services
            residential_services = []
            commercial_services = []
            
            # Extract from hero section if it exists
            if 'hero' in data:
                if 'residential' in data['hero'] and 'subServices' in data['hero']['residential']:
                    residential_services = [
                        {"id": i+1, "name": service.get('title', f"Service {i+1}")}
                        for i, service in enumerate(data['hero']['residential']['subServices'])
                    ]
                
                if 'commercial' in data['hero'] and 'subServices' in data['hero']['commercial']:
                    commercial_services = [
                        {"id": i+1, "name": service.get('title', f"Service {i+1}")}
                        for i, service in enumerate(data['hero']['commercial']['subServices'])
                    ]
            
            # If we got any services, return them
            if residential_services and commercial_services:
                return {
                    "residential": residential_services,
                    "commercial": commercial_services
                }
    except Exception as e:
        print(f"Error loading combined data: {e}")
    
    # Return default services if loading fails
    return DEFAULT_SERVICES

def get_bbb_services() -> Dict[str, List[Dict[str, Any]]]:
    """Extract services from BBB profile data if available, otherwise use fallbacks."""
    try:
        # Try to load the combined_data.json first to get current services
        current_services = load_combined_data()
        
        # Fix the path to look in raw_data/step_1 for BBB profile data
        bbb_data_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "raw_data", "bbb_profile_data.json")
        
        print(f"Looking for BBB data at: {bbb_data_path}")
        
        # Try to load BBB profile data
        with open(bbb_data_path, "r") as f:
            bbb_data = json.load(f)
        
        if not bbb_data:
            print("BBB data exists but is empty. Using current services.")
            return current_services
        
        # Generate appropriate services using AI if DeepSeek key is available
        if OPENAI_API_KEY:
            print("Using OpenAI to generate services based on BBB profile data...")
            generated_services = generate_services_from_bbb(bbb_data, current_services)
            if generated_services:
                return generated_services
            else:
                print("Failed to generate services with OpenAI. Using current services.")
        else:
            print("OpenAI API key not available. Using current services.")
            
        # If no services generated, use current ones
        return current_services
        
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error loading BBB data: {e}. Using current services.")
        return load_combined_data()

def generate_services_from_bbb(bbb_data: Dict[str, Any], current_services: Dict[str, List[Dict[str, Any]]]) -> Dict[str, List[Dict[str, Any]]]:
    """Generate specific, realistic services based on BBB profile data."""
    business_name = bbb_data.get('business_name', 'Roofing Company')
    additional_services = bbb_data.get('additional_services', [])
    service_hints = ', '.join(additional_services) if additional_services else "Roofing Services, Construction Services"
    
    print(f"Generating services for {business_name} based on: {service_hints}")
    
    # Format the current services for reference in the prompt
    current_residential = ", ".join([s["name"] for s in current_services["residential"]])
    current_commercial = ", ".join([s["name"] for s in current_services["commercial"]])
    
    # Convert the options to JSON string
    residential_options = json.dumps(ROOFING_SERVICE_OPTIONS["residential"])
    commercial_options = json.dumps(ROOFING_SERVICE_OPTIONS["commercial"])
    
    prompt = f"""
    You are a professional roofing consultant. Select 8 specific roofing services for a company named "{business_name}".
    
    Additional info about the company: {service_hints}
    
    Current residential services: {current_residential}
    Current commercial services: {current_commercial}
    
    Here are the available service options:
    
    RESIDENTIAL OPTIONS:
    {residential_options}
    
    COMMERCIAL OPTIONS:
    {commercial_options}
    
    Rules:
    1. Select 4 residential services from the residential options
    2. Select 4 commercial services from the commercial options
    3. Try to keep the current services if they make sense for this company
    4. All service names must be 1-3 words maximum
    5. Choose services that would be realistic for a company named "{business_name}"
    6. Consider the additional company info when making your selection: {service_hints}
    
    Return JSON only in this format with no additional text:
    {{
      "residential": [
        {{"id": 1, "name": "Service 1"}},
        {{"id": 2, "name": "Service 2"}},
        {{"id": 3, "name": "Service 3"}},
        {{"id": 4, "name": "Service 4"}}
      ],
      "commercial": [
        {{"id": 1, "name": "Service 1"}},
        {{"id": 2, "name": "Service 2"}},
        {{"id": 3, "name": "Service 3"}},
        {{"id": 4, "name": "Service 4"}}
      ]
    }}
    
    The service names must be exactly as they appear in the options lists above or match the current services.
    """
    
    try:
        print("Calling OpenAI to select services from predefined options...")
        response = call_openai_chat(prompt)
        
        # Extract JSON from response
        json_start = response.find('{')
        json_end = response.rfind('}') + 1
        
        if response and not response.startswith("Error:") and json_start >= 0 and json_end > json_start:
            json_str = response[json_start:json_end]
            try:
                services = json.loads(json_str)
                
                # Validate the structure 
                if ('residential' in services and 'commercial' in services and
                        len(services['residential']) == 4 and len(services['commercial']) == 4):
                    
                    # Verify all selected residential services are in the options list or current services
                    valid_residential = ROOFING_SERVICE_OPTIONS['residential'] + [s["name"] for s in current_services["residential"]]
                    valid_commercial = ROOFING_SERVICE_OPTIONS['commercial'] + [s["name"] for s in current_services["commercial"]]
                    
                    for service in services['residential']:
                        if service['name'] not in valid_residential:
                            print(f"Warning: '{service['name']}' is not in the valid residential options. Replacing with a current service.")
                            service['name'] = current_services["residential"][service['id'] - 1]["name"]
                    
                    # Verify all selected commercial services are in the options list
                    for service in services['commercial']:
                        if service['name'] not in valid_commercial:
                            print(f"Warning: '{service['name']}' is not in the valid commercial options. Replacing with a current service.")
                            service['name'] = current_services["commercial"][service['id'] - 1]["name"]
                    
                    print("Successfully selected services:")
                    for category, service_list in services.items():
                        print(f"\n{category.upper()} SERVICES:")
                        for service in service_list:
                            print(f"  - {service['name']}")
                    return services
                else:
                    print("Generated services have incorrect structure.")
            except json.JSONDecodeError as e:
                print(f"Failed to parse JSON from OpenAI API response: {e}")
        else:
            print("Could not find valid JSON in OpenAI API response.")
        
        print("Failed to generate services with OpenAI. Using current services.")
        return current_services
    except Exception as e:
        print(f"Error generating services: {e}. Using current services.")
        return current_services

def generate_research_prompt(service_name: str, service_type: str) -> str:
    """Generate a comprehensive research prompt for DeepSeek about a roofing service."""
    return f"""
    Research the following roofing service thoroughly: {service_name} ({service_type})
    
    I need detailed information from the perspective of a professional roofing contractor. Please address these topics:
    
    1. Construction Process:
       - Detailed step-by-step process for installing/implementing this service
       - Materials required and their specifications
       - Safety considerations and building code requirements
       - Timeline estimates for completion
    
    2. Variants:
       - What are the different types/styles/materials available for this service?
       - How do these variants differ in terms of durability, appearance, and cost?
       - What are the premium vs. budget options?
    
    3. Sales and Supply Chain:
       - How do roofers typically procure materials for this service?
       - Do they usually have inventory or order per project?
       - What's the typical markup or profit margin for this service?
       - How are these services typically quoted or estimated?
    
    4. Advantages and Benefits:
       - What are the main selling points for this service?
       - How does it compare to alternative solutions?
       - What long-term benefits should be highlighted to customers?
       - Any energy efficiency or insurance benefits?
    
    5. Marketing Considerations:
       - What aspects of this service do roofers typically emphasize in marketing?
       - What visuals or demonstrations are most effective in selling this service?
       - Do roofers typically show pricing publicly for this service? Why or why not?
       - What customer concerns or questions typically arise?
    
    6. Warranty and Maintenance:
       - What warranties are typically offered?
       - What maintenance requirements exist for this service?
       - What is the expected lifespan of this roof/service?
       - What factors can extend or reduce the lifespan?
    
    Format your response with section markers like this:
    
    ## **1. Construction Process**
    [Your detailed content here]
    
    ## **2. Variants**
    [Your detailed content here]
    
    And so on for each section. Provide comprehensive information a roofing website could use to create authoritative service pages.
    """

def extract_section(text: str, section_name: str) -> str:
    """Extract a section from the research results."""
    try:
        section_markers = {
            "construction_process": ["## **1. Construction Process**", "## **2"],
            "variants": ["## **2. Variants**", "## **3"],
            "sales_supply": ["## **3. Sales and Supply Chain**", "## **4"],
            "advantages": ["## **4. Advantages and Benefits**", "## **5"],
            "marketing": ["## **5. Marketing Considerations**", "## **6"],
            "warranty_maintenance": ["## **6. Warranty and Maintenance**", "##"]
        }
        
        markers = section_markers.get(section_name)
        if not markers:
            return "Section not found"
        
        start_marker, end_marker = markers
        
        start = text.find(start_marker)
        if start == -1:
            return f"**  \n\nSection placeholder for {section_name}"
        
        start += len(start_marker)
        
        end = text.find(end_marker, start)
        if end == -1:
            end = len(text)
        
        content = text[start:end].strip()
        return f"**  \n\n{content}"
    except Exception as e:
        print(f"Error extracting section {section_name}: {e}")
        return f"**  \n\nError extracting {section_name}"

def create_slug(category, service_id, service_name):
    """Create a proper slug for service URLs that works with App.jsx routes."""
    # Clean service name: lowercase, replace spaces with dashes
    cleaned_name = service_name.lower().replace(' ', '-')
    # Format: residential-r1-service-name or commercial-c1-service-name
    prefix = 'r' if category == 'residential' else 'c'
    return f"{category}-{prefix}{service_id}-{cleaned_name}"

def research_service(service: Dict[str, Any], category: str) -> Dict[str, Any]:
    """Research a service and return structured research data using OpenAI."""
    print(f"Researching {service['name']} ({category})...")

    if not OPENAI_API_KEY:
        print("No OpenAI API key found, using placeholder research data")
        return create_placeholder_research(service['name'])

    # Generate the research prompt
    research_prompt = generate_research_prompt(service['name'], category)

    try:
        # Call OpenAI API
        research_results = call_openai_chat(research_prompt)

        # Extract each section from the research results
        research_data = {
            "construction_process": extract_section(research_results, "construction_process"),
            "variants": extract_section(research_results, "variants"),
            "sales_supply": extract_section(research_results, "sales_supply"),
            "advantages": extract_section(research_results, "advantages"),
            "marketing": extract_section(research_results, "marketing"),
            "warranty_maintenance": extract_section(research_results, "warranty_maintenance")
        }

        # Sleep to avoid rate limits
        time.sleep(2)

        return research_data
    except Exception as e:
        print(f"Error researching service {service['name']}: {e}")
        return create_placeholder_research(service['name'])

def create_placeholder_research(service_name):
    """Create placeholder research data when DeepSeek is not available"""
    return {
        "construction_process": f"**  \n\n### **Step-by-Step {service_name} Process**  \n1. **Initial Assessment** – Professional inspection and planning.  \n2. **Material Selection** – High-quality materials suited to your property.  \n3. **Preparation** – Proper preparation of the work area.  \n4. **Installation** – Expert application by trained technicians.  \n5. **Cleanup & Inspection** – Thorough site cleanup and final quality check.\n\n### **Materials & Specifications**  \nIndustry-leading materials with manufacturer warranties.\n\n### **Timeline Estimates**  \nTypical projects completed in 1-3 days depending on scope.",
        "variants": f"**  \n\n### **Types of {service_name} Options**  \n**Standard:** Cost-effective solution for most properties.  \n**Premium:** Enhanced durability and appearance.  \n**Deluxe:** Maximum protection and aesthetic appeal.\n\n### **Durability & Cost Comparison**  \n| Type | Durability | Cost (per sq. ft.) |  \n|------|------------|-------------------|  \n| Standard | 15-20 years | $8-$12 |  \n| Premium | 25-30 years | $12-$18 |  \n| Deluxe | 30+ years | $18-$25 |",
        "sales_supply": f"**  \n\n### **Material Procurement**  \nContractors typically order materials per project from suppliers or distributors.  \n\n### **Pricing & Profit Margins**  \nTypical markup: 30-50% for materials, 50-100% for labor.  \n\n### **Quoting Process**  \nBased on square footage, material quality, and labor complexity.",
        "advantages": f"**  \n\n### **Key Benefits**  \n**Protection:** Shields your property from weather damage.  \n**Energy Efficiency:** Properly installed systems can reduce energy costs.  \n**Property Value:** Enhances curb appeal and resale value.  \n**Durability:** Long-lasting performance with minimal maintenance.",
        "marketing": f"**  \n\n### **Effective Marketing Strategies**  \n**Visual Content:** Before/after photos and project videos.  \n**Customer Testimonials:** Highlighting successful installations.  \n\n### **Common Customer Questions**  \n\"How long will it last?\"  \n\"What maintenance is required?\"",
        "warranty_maintenance": f"**  \n\n### **Warranty Coverage**  \n**Materials:** Manufacturer warranties on all products.  \n**Workmanship:** Our labor warranty covers installation quality.\n\n### **Maintenance Requirements**  \nAnnual inspections recommended for optimal performance.\n\n### **Lifespan**  \nWith proper care, 20+ years of reliable service."
    }

def load_research_data_from_stdin() -> Dict[str, Any]:
    """Load research data exclusively from STDIN (memory-only pipeline).
    Expected STDIN: a JSON object like {"residential": [...], "commercial": [...]}.
    """
    raw = sys.stdin.read()
    if not raw or not raw.strip():
        raise RuntimeError("No research JSON received on STDIN")
    try:
        return json.loads(raw)
    except Exception as e:
        raise RuntimeError(f"Failed to parse research JSON from STDIN: {e}")

def create_block(block_name: str, config: dict, search_terms: str = "", image_path: str = None) -> dict:
    """Create a standardized block structure matching ServicePage.jsx requirements.

    Note: To align with existing services.json, we omit generator-only extras like
    searchTerms/imagePath from the emitted JSON. Prompts for image generation are
    attached under config.ImageProps instead (added later).
    """
    block = {
        "blockName": block_name,
        "config": config,
    }
    # Intentionally ignore search_terms and image_path for parity with current schema
    return block

def generate_service_blocks(service: dict, category: str) -> List[dict]:
    """Generate blocks for a service using available block components"""
    blocks = []
    service_id = service['id']
    service_name = service['name']
    
    # Legacy base path for images (to match existing services.json structure)
    legacy_base = f"/personal/old/img/services/{category}/{service_id}"
    
    # Try to normalize research fields if present for better content
    research_norm = normalize_research_fields(service)

    # 1. HeroBlock - Main service banner (legacy paths typically embedded in Content for legacy blocks)
    blocks.append(create_block(
        "HeroBlock",
        {
            "title": f"{service_name}",
            "subtitle": f"Professional {category.capitalize()} Roofing Services",
            "backgroundOpacity": 0.6,
            "buttonText": "Get Free Quote",
            "buttonUrl": "/contact"
        },
        f"{service_name} hero banner",
        f"{legacy_base}/HeroBlock/primary.jpg"
    ))

    # 2. Overview banner (pull key marketing points if available)
    subtitle = "Expert solutions for your property"
    if research_norm.get('marketing'):
        # Take first sentence or short snippet
        snippet = research_norm['marketing'].split('\n')[0].strip()
        if len(snippet) > 12:
            subtitle = snippet[:160]
    blocks.append(create_block(
        "HeaderBannerBlock",
        {
            "title": "Professional Service",
            "subtitle": subtitle
        },
        f"{service_name} overview",
        f"{legacy_base}/HeaderBannerBlock/primary.jpg"
    ))

    # 3. Installation steps if present
    installation_steps = [s.strip('- ').strip() for s in research_norm.get('installation','').split('\n') if s.strip()]
    if installation_steps:
        blocks.append(create_block(
            "GeneralList",
            {
                "title": "Installation Process",
                "items": installation_steps[:5],
                "listStyle": "numbered"
            },
            f"{service_name} installation steps",
            f"{legacy_base}/GeneralList/primary.jpg"
        ))

    # 4. Maintenance details if present
    maintenance_items = [s.strip('- ').strip() for s in research_norm.get('maintenance','').split('\n') if s.strip()]
    if maintenance_items:
        blocks.append(create_block(
            "ListDropdown",
            {
                "title": "Maintenance Guide",
                "items": [
                    {"title": f"Maintenance Step {i+1}", "content": item}
                    for i, item in enumerate(maintenance_items[:4])
                ]
            },
            f"{service_name} maintenance",
            f"{legacy_base}/ListDropdown/primary.jpg"
        ))

    # 5. Repair summary if present
    repair_points = [s.strip('- ').strip() for s in research_norm.get('repair','').split('\n') if s.strip()]
    if repair_points:
        blocks.append(create_block(
            "GridImageTextBlock",
            {
                "title": "Repair Services",
                "items": [
                    {
                        "title": "Professional Repairs",
                        "content": "\n".join(repair_points[:3]),
                        "imagePath": f"{legacy_base}/GridImageTextBlock/primary.jpg",
                        "imageAlt": f"{service_name} repair work"
                    }
                ]
            },
            f"{service_name} repairs",
            f"{legacy_base}/GridImageTextBlock/primary.jpg"
        ))

    # 6. Variants as pricing options if present
    variants = [v.strip('- ').strip() for v in research_norm.get('variants','').split('\n') if v.strip()]
    if variants:
        blocks.append(create_block(
            "PricingGrid",
            {
                "title": "Service Options",
                "subtitle": "Choose the Right Solution for Your Needs",
                "items": [
                    {
                        "title": variant,
                        "price": "Contact for Quote",
                        "features": ["Professional Installation", "Quality Materials", "Expert Service"],
                        "imagePath": f"{legacy_base}/PricingGrid/primary.jpg",
                        "imageAlt": f"{variant} material option"
                    }
                    for variant in variants[:3]
                ]
            },
            f"{service_name} pricing",
            f"{legacy_base}/PricingGrid/primary.jpg"
        ))

    # 7. CTA
    blocks.append(create_block(
        "ActionButtonBlock",
        {
            "title": "Ready to Get Started?",
            "subtitle": "Contact us for a free consultation",
            "buttonText": "Schedule Now",
            "buttonUrl": "/contact"
        },
        f"{service_name} cta",
        f"{legacy_base}/ActionButtonBlock/primary.jpg"
    ))

    return blocks

def _is_image_path_string(val: Any) -> bool:
    """Return True if val looks like an image file path string."""
    if not isinstance(val, str):
        return False
    return re.search(r"\.(jpg|jpeg|png|webp)(\?.*)?$", val, re.IGNORECASE) is not None


# ----------------------------- NEW: rewrite legacy image paths → generation/ -----------------

def _slugify_service_folder(name: str) -> str:
    try:
        s = (name or "").lower().strip()
        # Keep alnum, space, underscore, dash; drop others
        s = re.sub(r"[^a-z0-9\s_-]", "", s)
        s = re.sub(r"\s+", "_", s)
        return s[:64] or "item"
    except Exception:
        return "item"

def _rewrite_image_string(path: str, category: str, service_slug: str, block_name: str) -> str:
    try:
        # Strip query if present and get basename
        clean = path.split('?', 1)[0]
        base = os.path.basename(clean) or 'image.png'
        # Use block folder when available to mirror explorer/zip tree
        block_folder = (block_name or 'Block')
        return f"/generation/img/services/{category}/{service_slug}/{block_folder}/{base}"
    except Exception:
        return path

def _deep_rewrite(node: Any, category: str, service_slug: str, block_name: str) -> Any:
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            out[k] = _deep_rewrite(v, category, service_slug, block_name)
        return out
    if isinstance(node, list):
        return [_deep_rewrite(v, category, service_slug, block_name) for v in node]
    if isinstance(node, str) and _is_image_path_string(node):
        # Rewrite any legacy/relative path to generation tree
        return _rewrite_image_string(node, category, service_slug, block_name)
    return node

def rewrite_service_block_image_paths(blocks: List[Dict[str, Any]], category: str, service_uid: Any) -> List[Dict[str, Any]]:
    """Rewrite any image path strings within block.config to /generation/img/services/... using
    a stable uid-based slug (no dependency on service name) and the block's name as a subfolder."""
    try:
        # Use a deterministic uid-based slug to avoid reliance on service names
        service_slug = f"svc_{str(service_uid).strip()}"
        rewritten: List[Dict[str, Any]] = []
        for blk in blocks or []:
            name = blk.get('blockName') or 'Block'
            cfg = blk.get('config') or {}
            cfg2 = _deep_rewrite(cfg, category, service_slug, name)
            new_blk = dict(blk)
            new_blk['config'] = cfg2
            rewritten.append(new_blk)
        return rewritten
    except Exception:
        return blocks

def _collect_block_image_prompts(block: Dict[str, Any], category: str, service_id: Any, service_name: str) -> Dict[str, str]:
    """Deprecated: prompts are now emitted via ImageProps.prompt_# using the template's ImageProps.
    Kept for backward compatibility; returns an empty mapping.
    """
    return {}

def normalize_service_blocks_image_paths(blocks: List[Dict[str, Any]], category: str, service_id: Any, service_name: str) -> List[Dict[str, Any]]:
    """No-op: legacy promptsByPath emission removed; returned blocks unchanged."""
    return blocks

def main():
    """Generate services.json for ServicePage.jsx using research data from STDIN only"""
    print("Starting service JSON generation...")
    
    try:
        try:
            print(f"[ServicesJSON] OpenAI key present: {bool(OPENAI_API_KEY)}")
        except Exception:
            pass
        # Load research data from STDIN only (strict memory-only)
        research_data = load_research_data_from_stdin()
        print(f"[ServicesJSON] Loaded research from STDIN: residential={len(research_data.get('residential', []))}, commercial={len(research_data.get('commercial', []))}")
        
        # Transform into services with blocks
        output_services = {
            "residential": [],
            "commercial": []
        }
        template = load_services_template()
        
        for category in ['residential', 'commercial']:
            print(f"\nProcessing {category} services:")
            for service in research_data[category]:
                print(f"  - Generating blocks for {service['name']}")
                
                # Create service entry with blocks
                # ✅ UPDATED: Use kebab-case service ID instead of numeric
                service_name = service.get('name') or service.get('title') or f"Service {service.get('id')}"
                assigned_id = re.sub(r'[^a-z0-9]+', '-', service_name.lower()).strip('-') or 'service'
                legacy_base = f"/personal/old/img/services/{category}/{assigned_id}"

                # NEW: Prefer AI-composed blocks using research
                blocks = None
                if not OPENAI_API_KEY:
                    raise RuntimeError("OPENAI_API_KEY missing for services JSON composition")
                try:
                    norm = normalize_research_fields(service)
                    blocks = compose_blocks_with_ai(service['name'], category, legacy_base, norm, template)
                    if template:
                        blocks = enforce_template_on_blocks(blocks, template)
                        # Attach image prompts based on template ImageProps (AI_script, in_images, prompt)
                        blocks = attach_image_prompts_from_template(blocks, template, service['name'])
                    print(f"    [AI] Composed {len(blocks)} blocks for {service['name']}")
                except Exception as e:
                    # Hard fail: do not fallback to deterministic blocks
                    raise

                # Legacy promptsByPath normalization removed (template-driven prompts already attached)

                # NEW: rewrite any legacy image path strings to generation/ tree for explorer/zip parity
                # Rewrite image paths using uid-based slug (no dependency on service name)
                blocks = rewrite_service_block_image_paths(blocks, category, assigned_id)

                service_entry = {
                    "id": assigned_id,
                    "name": service["name"],
                    "blocks": blocks,
                    # Preserve original id for optional cross-referencing/migration
                    "origId": service.get("id")
                }
                
                output_services[category].append(service_entry)
        
        # Memory-only mode: do NOT write to disk

        # Output result to stdout with clear markers for the backend to parse
        print("SERVICE_JSON_START")
        print(json.dumps(output_services, ensure_ascii=False, indent=2))
        print("SERVICE_JSON_END")
        print("[ServicesJSON] Emitted to STDOUT (memory mode)")
        
    except Exception as e:
        print(f"Error generating services.json: {e}")
        # Hard fail
        raise

if __name__ == "__main__":
    main()
