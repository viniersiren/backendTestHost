#!/usr/bin/env python3
import json
import os
import re
import random
import requests
import time
import dotenv
import sys
from pathlib import Path
from typing import Dict, List, Any

# Load the OpenAI API key from .env file
env_path = Path(__file__).parent.parent.parent / ".env"
try:
    dotenv.load_dotenv(env_path)
except Exception:
    pass

# Get API key from environment variable
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
API_ENDPOINT = "https://api.openai.com/v1/chat/completions"

# Memory-only mode (default): do not write files to disk, emit JSON to stdout for the caller to consume
MEMORY_ONLY = os.environ.get("MEMORY_ONLY", "1") == "1"

if not OPENAI_API_KEY:
    print("WARNING: OpenAI API key not found. Please set it in the .env file in the generation directory.")
    print(f"Looking for .env at: {env_path}")

# Added runtime diagnostics
print(f"[Research] OpenAI key present: {bool(OPENAI_API_KEY)}")
print(f"[Research] MEMORY_ONLY: {MEMORY_ONLY}")

# No disk fallbacks are allowed in memory-only flow

def slugify(text):
    """Convert text to URL-friendly slug"""
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'\s+', '-', text.strip())
    return text


def call_openai_api(prompt: str) -> str:
    """Call the OpenAI API with a given prompt and return the response, with retry logic."""
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
    
    max_retries = 3
    base_delay = 2
    
    for attempt in range(max_retries):
        try:
            response = requests.post(API_ENDPOINT, headers=headers, json=data, timeout=30)
            
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"]
            elif response.status_code in [502, 503, 504]:  # Temporary server errors
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)  # Exponential backoff
                    print(f"API call failed with {response.status_code}, retrying in {delay} seconds... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(delay)
                    continue
                else:
                    print(f"API call failed after {max_retries} attempts: {response.status_code}")
                    print(response.text)
                    return f"Error: {response.status_code} - {response.text}"
            else:
                print(f"API call failed with {response.status_code}: {response.text}")
                return f"Error: {response.status_code} - {response.text}"
                
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                print(f"Request failed: {e}, retrying in {delay} seconds... (attempt {attempt + 1}/{max_retries})")
                time.sleep(delay)
                continue
            else:
                print(f"Request failed after {max_retries} attempts: {e}")
                return f"Error: Request failed - {e}"
    
    return "Error: Maximum retries exceeded"


def generate_research_prompt(service_name: str, service_type: str, location_info: Dict[str, Any]) -> str:
    """Generate a comprehensive research prompt for OpenAI about a roofing service."""
    business_name = location_info.get("business_name") or "Roofing Company"
    address = location_info.get("address") or ""
    years_in_business = location_info.get("years_in_business") or ""
    return f"""
    Research the following roofing service thoroughly: {service_name} ({service_type})
    
    Business context:
    - Business Name: {business_name}
    - Address/Region: {address}
    - Years in Business: {years_in_business}
    
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


def create_block(block_name, config, search_terms="", image_path=None):
    """Create a properly structured block for a service page"""
    block = {
        "blockName": block_name,
        "config": config,
        "searchTerms": search_terms
    }
    
    if image_path:
        block["imagePath"] = image_path
        
    return block


def generate_hero_block(service_name, category, service_id):
    """Generate a HeroBlock configuration"""
    prefix = "r" if category == "residential" else "c"
    return create_block(
        "HeroBlock",
        {
            "title": f"{category.capitalize()} {service_name}",
            "subtitle": f"Expert {service_name.lower()} services for your property",
            "backgroundOpacity": 0.6,
            "buttonText": "Get a Free Estimate",
            "buttonUrl": "#contact"
        },
        f"{service_name.lower()} {category}",
        f"/assets/images/services/{category}/{prefix}{service_id}/block_1.jpg"
    )


def generate_header_banner_block(title, subtitle, service_id, category, block_num):
    """Generate a HeaderBannerBlock configuration"""
    prefix = "r" if category == "residential" else "c"
    return create_block(
        "HeaderBannerBlock",
        {
            "title": title,
            "subtitle": subtitle
        },
        f"{title.lower()}",
        f"/assets/images/services/{category}/{prefix}{service_id}/block_{block_num}.jpg"
    )


def generate_general_list(title, items, service_id, category, block_num):
    """Generate a GeneralList block"""
    prefix = "r" if category == "residential" else "c"
    return create_block(
        "GeneralList",
        {
            "title": title,
            "items": items
        },
        f"{title.lower()} steps process",
        f"/assets/images/services/{category}/{prefix}{service_id}/block_{block_num}.jpg"
    )


def generate_overview_advantages(title, items, service_id, category, block_num):
    """Generate an OverviewAndAdvantagesBlock"""
    prefix = "r" if category == "residential" else "c"
    return create_block(
        "OverviewAndAdvantagesBlock",
        {
            "title": title,
            "advantages": items if isinstance(items[0], str) else [item["title"] for item in items],
            "items": items if not isinstance(items[0], str) else [{"title": item, "description": ""} for item in items]
        },
        f"{title.lower()} benefits advantages",
        f"/assets/images/services/{category}/{prefix}{service_id}/block_{block_num}.jpg"
    )


def extract_construction_steps(construction_text):
    """Extract steps from construction process text"""
    steps = []
    if "**Step-by-Step" in construction_text or "**Installation Process" in construction_text:
        # Try to extract steps by finding numbers followed by text
        step_matches = re.findall(r'\d+\.\s\*\*([^*]+)\*\*\s[–\-]\s([^\n\.]+)', construction_text)
        if step_matches:
            for step_title, step_desc in step_matches:
                steps.append(f"{step_title.strip()} – {step_desc.strip()}")
        
        # Fallback: look for lines with numbers at the beginning
        if not steps:
            step_matches = re.findall(r'\d+\.\s+\*\*([^*]+)\*\*([^\n\.]+)', construction_text)
            if step_matches:
                for step_title, step_desc in step_matches:
                    steps.append(f"{step_title.strip()} {step_desc.strip()}")
    
    # If we couldn't extract structured steps, create some generic ones
    if not steps:
        steps = [
            "Initial Assessment – Professional inspection and planning",
            "Material Selection – High-quality materials suited to your property",
            "Preparation – Proper preparation of the work area",
            "Installation – Expert application by trained technicians",
            "Cleanup & Inspection – Thorough site cleanup and final quality check"
        ]
    
    return steps


def extract_advantages(advantages_text):
    """Extract advantages from advantages text"""
    advantages = []
    if "**Key" in advantages_text or "**Selling" in advantages_text:
        # Try to find advantages with bullet points
        adv_matches = re.findall(r'\*\*([^:*]+):\*\*\s([^\n\.]+)', advantages_text)
        if adv_matches:
            for adv_title, adv_desc in adv_matches:
                advantages.append({
                    "title": adv_title.strip(),
                    "description": adv_desc.strip()
                })
    
    # If no structured advantages found, create some based on the text
    if not advantages:
        # Look for any phrases that might be advantages
        potential_advantages = re.findall(r'\*\*([^*\n]+)\*\*', advantages_text)
        for i, adv in enumerate(potential_advantages[:4]):
            advantages.append({
                "title": adv.strip(),
                "description": f"Professional {adv.lower()} for optimal performance and durability."
            })
    
    # If still no advantages, use generic ones
    if not advantages:
        advantages = [
            {"title": "Long-lasting Protection", "description": "Our services provide durable protection against the elements."},
            {"title": "Energy Efficiency", "description": "Properly installed systems can reduce energy costs."},
            {"title": "Enhanced Property Value", "description": "Quality workmanship improves curb appeal and value."},
            {"title": "Peace of Mind", "description": "Professional installation backed by comprehensive warranties."}
        ]
    
    return advantages


def extract_variants(variants_text):
    """Extract different product/service variants from the text"""
    variants = []
    
    # Try to find tables with options
    table_match = re.search(r'\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|', variants_text)
    if table_match:
        # Try to extract table rows
        rows = re.findall(r'\|\s*\*\*([^*|]+)\*\*\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|', variants_text)
        if rows:
            for name, durability, cost in rows:
                variants.append({
                    "title": name.strip(),
                    "description": f"Durability: {durability.strip()}",
                    "price": cost.strip()
                })
    
    # If no table found, try to extract product types
    if not variants:
        type_sections = re.findall(r'\*\*([^*:]+):\*\*\s+([^\n]+)', variants_text)
        for type_name, type_desc in type_sections:
            if "budget" not in type_name.lower() and "premium" not in type_name.lower():
                variants.append({
                    "title": type_name.strip(),
                    "description": type_desc.strip(),
                    "price": f"${random.randint(5, 15)}/sq. ft."
                })
    
    # If still no variants, create generic ones
    if not variants:
        variants = [
            {"title": "Standard Option", "description": "Good quality, budget-friendly solution", "price": "$8-$12/sq. ft."},
            {"title": "Premium Option", "description": "Enhanced durability and appearance", "price": "$12-$18/sq. ft."},
            {"title": "Professional Grade", "description": "Maximum protection and aesthetic appeal", "price": "$18-$25/sq. ft."}
        ]
    
    return variants


def load_location_info_from_stdin(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Strict memory-only location info loader from STDIN payload."""
    if not isinstance(payload, dict):
        raise RuntimeError('Missing locationInfo on STDIN')
    li = payload.get('locationInfo')
    if not isinstance(li, dict):
        raise RuntimeError('Missing locationInfo on STDIN')
    li.setdefault('business_name', 'Roofing Company')
    li.setdefault('address', '')
    li.setdefault('years_in_business', '')
    if 'services' not in li:
        li['services'] = []
    print(f"Business context (memory): {li.get('business_name')} in {li.get('address')}")
    return li


def research_service(service: Dict[str, Any], category: str, location_info: Dict[str, Any]) -> Dict[str, Any]:
    """Research a specific service using OpenAI with location context; hard-fail on any error."""
    print(f"Researching {service['name']} ({category}) via OpenAI...")
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY missing")
    prompt = generate_research_prompt(service['name'], category, location_info)
    research_results = call_openai_api(prompt)
    if not research_results or (isinstance(research_results, str) and research_results.startswith("Error:")):
        raise RuntimeError(research_results or "Empty response from OpenAI")
    print(f"[Research] OK: {service['name']} ({category})")
    return {
        "construction_process": extract_section(research_results, "construction_process"),
        "variants": extract_section(research_results, "variants"),
        "sales_supply": extract_section(research_results, "sales_supply"),
        "advantages": extract_section(research_results, "advantages"),
        "marketing": extract_section(research_results, "marketing"),
        "warranty_maintenance": extract_section(research_results, "warranty_maintenance"),
    }



def create_placeholder_research(service_name):
    """Create placeholder research data when OpenAI is not available"""
    return {
        "construction_process": f"**  \n\n### **Step-by-Step {service_name} Process**  \n1. **Initial Assessment** – Professional inspection and planning.  \n2. **Material Selection** – High-quality materials suited to your property.  \n3. **Preparation** – Proper preparation of the work area.  \n4. **Installation** – Expert application by trained technicians.  \n5. **Cleanup & Inspection** – Thorough site cleanup and final quality check.\n\n### **Materials & Specifications**  \nIndustry-leading materials with manufacturer warranties.\n\n### **Timeline Estimates**  \nTypical projects completed in 1-3 days depending on scope.",
        "variants": f"**  \n\n### **Types of {service_name} Options**  \n**Standard:** Cost-effective solution for most properties.  \n**Premium:** Enhanced durability and appearance.  \n**Deluxe:** Maximum protection and aesthetic appeal.\n\n### **Durability & Cost Comparison**  \n| Type | Durability | Cost (per sq. ft.) |  \n|------|------------|-------------------|  \n| Standard | 15-20 years | $8-$12 |  \n| Premium | 25-30 years | $12-$18 |  \n| Deluxe | 30+ years | $18-$25 |",
        "sales_supply": f"**  \n\n### **Material Procurement**  \nContractors typically order materials per project from suppliers or distributors.  \n\n### **Pricing & Profit Margins**  \nTypical markup: 30-50% for materials, 50-100% for labor.  \n\n### **Quoting Process**  \nBased on square footage, material quality, and labor complexity.",
        "advantages": f"**  \n\n### **Key Benefits**  \n**Protection:** Shields your property from weather damage.  \n**Energy Efficiency:** Properly installed systems can reduce energy costs.  \n**Property Value:** Enhances curb appeal and resale value.  \n**Durability:** Long-lasting performance with minimal maintenance.",
        "marketing": f"**  \n\n### **Effective Marketing Strategies**  \n**Visual Content:** Before/after photos and project videos.  \n**Customer Testimonials:** Highlighting successful installations.  \n\n### **Common Customer Questions**  \n\"How long will it last?\"  \n\"What maintenance is required?\"",
        "warranty_maintenance": f"**  \n\n### **Warranty Coverage**  \n**Materials:** Manufacturer warranties on all products.  \n**Workmanship:** Our labor warranty covers installation quality.\n\n### **Maintenance Requirements**  \nAnnual inspections recommended for optimal performance.\n\n### **Lifespan**  \nWith proper care, 20+ years of reliable service."
    }


# Removed disk-based service_names.json loader; services must come from STDIN


def load_services_from_stdin() -> Dict[str, Any]:
    """Load edited services from STDIN (preferred when invoked by backend /research-services).

    Expected payload:
      { "serviceNames": { "universal": { "residential": { "services": [{"name": str}, ...] },
                                           "commercial":  { "services": [{"name": str}, ...] } } } }
    Returns composite: { services: {..}, raw: full_payload } or None
    """
    try:
        raw = sys.stdin.read()
        if not raw or not raw.strip():
            return None
        payload = json.loads(raw)
        service_names = payload.get("serviceNames", payload)

        services: Dict[str, List[Dict[str, Any]]] = {"residential": [], "commercial": []}

        for category in ["residential", "commercial"]:
            # Primary path
            universal_cat = service_names.get("universal", {}).get(category, {}) if isinstance(service_names, dict) else {}
            items = universal_cat.get("services", []) if isinstance(universal_cat, dict) else []
            if isinstance(items, list) and items:
                for i, item in enumerate(items):
                    name = item.get("name") if isinstance(item, dict) else str(item)
                    if name:
                        services[category].append({"id": i + 1, "name": name})

            # Fallback: direct list
            if not services[category]:
                direct_items = service_names.get(category) if isinstance(service_names, dict) else []
                if isinstance(direct_items, list) and direct_items:
                    for i, item in enumerate(direct_items):
                        name = item.get("name") if isinstance(item, dict) else str(item)
                        if name:
                            services[category].append({"id": i + 1, "name": name})

            # Fallback: servicePage.{category}
            if not services[category]:
                sp_items = service_names.get("servicePage", {}).get(category, []) if isinstance(service_names, dict) else []
                if isinstance(sp_items, list) and sp_items:
                    for i, item in enumerate(sp_items):
                        name = item.get("name") if isinstance(item, dict) else str(item)
                        if name:
                            services[category].append({"id": i + 1, "name": name})

        if not services["residential"] and not services["commercial"]:
            return None

        print("[Research] Loaded edited service names from STDIN (Gen.jsx)")
        return { "services": services, "raw": payload }
    except Exception as e:
        print(f"[Research] Failed to load services from STDIN: {e}")
        return None


def main():
    """Research the 8 universal services with location context."""
    print("Starting research_services.py script...")
    
    try:
        # Require edited service list + location info from STDIN (no disk fallback)
        loaded = load_services_from_stdin()
        if not loaded:
            raise RuntimeError('Missing serviceNames on STDIN (no fallback allowed)')
        services = loaded["services"]
        location_info = load_location_info_from_stdin(loaded.get("raw", {}))
        # Log the exact 8 services being researched
        try:
            res_names = ", ".join([s["name"] for s in services.get("residential", [])])
            com_names = ", ".join([s["name"] for s in services.get("commercial", [])])
            print(f"[Research] Services to research → Residential: {res_names} | Commercial: {com_names}")
        except Exception:
            pass

        # Research each service with location context
        research_data = {
            "residential": [],
            "commercial": []
        }
        
        for category in ['residential', 'commercial']:
            print(f"\nResearching {category} services:")
            for service in services[category]:
                print(f"  - {service['name']} (considering {location_info['business_name']} location)")
                
                # Get research data with location context
                service_research = research_service(service, category, location_info)
                
                # Map available sections safely to expected keys to avoid KeyError
                mapped = {
                    "installation_process": service_research.get("construction_process", ""),
                    "repair_emergency": service_research.get("marketing", ""),
                    "maintenance_requirements": service_research.get("warranty_maintenance", ""),
                    "material_variants": service_research.get("variants", ""),
                    "cost_pricing": service_research.get("sales_supply", ""),
                    "warranty_guarantee": service_research.get("warranty_maintenance", ""),
                    "regulatory_compliance": service_research.get("construction_process", ""),
                    "customer_education": service_research.get("marketing", ""),
                    "environmental_efficiency": service_research.get("advantages", ""),
                    "troubleshooting": service_research.get("construction_process", ""),
                    "business_process": service_research.get("sales_supply", ""),
                    "specialized_considerations": service_research.get("advantages", "")
                }
                
                # Add to research data
                research_data[category].append({
                    "id": service["id"],
                    "name": service["name"],
                    **mapped
                })
                
                time.sleep(2)  # Rate limiting
        
        # Emit research JSON to stdout with markers for backend parsing
        if MEMORY_ONLY:
            print("RESEARCH_JSON_START")
            print(json.dumps(research_data, ensure_ascii=False))
            print("RESEARCH_JSON_END")
        else:
            # No fallback persistence in non-memory mode for policy clarity
            pass

        # Also emit a summary with location context (stdout in memory mode, otherwise save beside it)
        summary_data = {
            "location_context": location_info,
            "research_date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_services_researched": len(services["residential"]) + len(services["commercial"]),
            "services_researched": {
                "residential": [s["name"] for s in services["residential"]],
                "commercial": [s["name"] for s in services["commercial"]]
            },
            "detailed_research": research_data
        }
        if MEMORY_ONLY:
            # Emit summary to stderr-like log (print), caller mainly needs main JSON
            print("\nRESEARCH_SUMMARY_START")
            print(json.dumps(summary_data, ensure_ascii=False))
            print("RESEARCH_SUMMARY_END")
        else:
            summary_output_path = "/Users/rhettburnham/Desktop/projects/roofing-co/public/personal/generation/jsons/services_research_summary.json"
            with open(summary_output_path, 'w', encoding='utf-8') as f:
                json.dump(summary_data, f, indent=2, ensure_ascii=False)
            print(f"Also saved research summary to {summary_output_path}")
        
        print(f"\nScript completed successfully!")
        print(f"Researched {len(services['residential'])} residential and {len(services['commercial'])} commercial services")
        print(f"All research includes location context for: {location_info['business_name']} in {location_info['address']}")
        
    except Exception as e:
        print(f"Error running script: {e}")
        # Hard fail
        raise

if __name__ == "__main__":
    main()