#!/usr/bin/env python3
import json
import os
import requests
from datetime import datetime
import random
import logging
from pathlib import Path
import dotenv

"""
Generate About Page Script

This script creates a separate about_page.json file for the about page content.
It generates professional content for a roofing company's about page, complete with
company history, mission statement, core values, and team member information.

The generated content is designed to showcase the company's expertise, values, and team
in a professional and engaging way.
"""

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables from shared .env (same convention as step_2/research_services.py)
env_path = Path(__file__).parent.parent.parent / ".env"
try:
    dotenv.load_dotenv(env_path)
except Exception:
    pass

# Align key usage with research_services.py
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
API_ENDPOINT = "https://api.openai.com/v1/chat/completions"

def call_openai_chat(prompt: str) -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError('OPENAI_API_KEY missing for about page generation')
    headers = { 'Authorization': f'Bearer {OPENAI_API_KEY}', 'Content-Type': 'application/json' }
    data = {
        'model': 'gpt-4o-mini',
        'messages': [{ 'role': 'user', 'content': prompt }],
        'temperature': 0.7,
        'max_tokens': 3000
    }
    resp = requests.post(API_ENDPOINT, headers=headers, json=data, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f'OpenAI error: {resp.status_code} {resp.text}')
    return resp.json()['choices'][0]['message']['content']

def main():
    logger.info("Starting About Page Generation...")
    
    try:
        # Set paths
        script_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.dirname(script_dir)
        raw_data_dir = os.path.join(data_dir, "raw_data")
        output_dir = os.path.join(raw_data_dir, "step_3")
        
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Set output file path for about page data
        about_page_output = os.path.join(output_dir, "about_page.json")
        
        # Check if combined_data.json exists to extract company data
        #combined_data_path = os.path.join(raw_data_dir, "step_4", "combined_data.json")
        bbb_profile_path = os.path.join(raw_data_dir, "step_1", "bbb_profile_data.json")
        
        # Variables to populate
        company_name = "Roofing Company"
        year_established = datetime.now().year - 10  # Default 10 years ago
        years_in_business = 10
        city = "Atlanta"
        
        # Try to load data from combined_data.json if it exists
        # if os.path.exists(combined_data_path):
        #     logger.info(f"Loading data from {combined_data_path}")
        #     with open(combined_data_path, 'r') as file:
        #         combined_data = json.load(file)
            
        #     # Extract company name
        #     if 'hero' in combined_data and 'mainTitle' in combined_data['hero']:
        #         company_name = combined_data['hero']['mainTitle']
        #         if 'subTitle' in combined_data['hero'] and combined_data['hero']['subTitle']:
        #             company_name += " " + combined_data['hero']['subTitle']
            
        #     # Extract years in business
        #     if 'richText' in combined_data and 'years_in_business' in combined_data['richText']:
        #         years_text = combined_data['richText']['years_in_business']
        #         try:
        #             years_in_business = int(years_text.split()[0])
        #             year_established = datetime.now().year - years_in_business
        #         except:
        #             logger.warning(f"Could not parse years from '{years_text}', using default")
            
        #     # Extract city
        #     if 'map' in combined_data and 'address' in combined_data['map']:
        #         address = combined_data['map']['address']
        #         # Simple city extraction - find text between commas
        #         parts = address.split(',')
        #         if len(parts) >= 2:
        #             city = parts[-2].strip()
        
        # Try to load data from BBB profile if combined_data.json doesn't exist or is missing info
        if os.path.exists(bbb_profile_path):
            logger.info(f"Loading data from {bbb_profile_path}")
            with open(bbb_profile_path, 'r') as file:
                bbb_data = json.load(file)
            
            # Extract company name
            if 'business_name' in bbb_data:
                company_name = bbb_data['business_name']
            
            # Extract years in business
            if 'years_in_business' in bbb_data:
                try:
                    years_text = bbb_data['years_in_business']
                    if isinstance(years_text, str) and ":" in years_text:
                        years_in_business = int(years_text.split(":")[-1].strip())
                    else:
                        years_in_business = int(years_text)
                    year_established = datetime.now().year - years_in_business
                except:
                    logger.warning(f"Could not parse years from BBB data, using default")
            
            # Extract city
            if 'city' in bbb_data:
                city = bbb_data['city']
            elif 'address' in bbb_data:
                address = bbb_data['address']
                parts = address.split(',')
                if len(parts) >= 2:
                    city = parts[-2].strip()
        
        # Hard-require AI generation; if key missing or call fails, exit with error
        logger.info(f"[About] OpenAI key present: {bool(OPENAI_API_KEY)}")
        logger.info(f"Generating about page for {company_name}, established {year_established} in {city}")
        prompt = f"""
        Create a concise about_page JSON for a roofing company. Return JSON only with keys:
        title, subtitle, history, mission, values (array of objects with title, description), team (array of objects name, position, photo), stats (array of objects title, value, icon), heroImage.
        Context:
        - company_name: {company_name}
        - city: {city}
        - years_in_business: {years_in_business}
        - year_established: {year_established}
        Constraints:
        - Keep language professional and realistic.
        - Do not include any image generation prompts; just content fields. For images, any 'photo' or 'heroImage' values you return will be ignored and replaced.
        - Keep arrays small (2-4 entries each).
        """
        content = call_openai_chat(prompt)
        start = content.find('{'); end = content.rfind('}') + 1
        if start < 0 or end <= start:
            raise RuntimeError('About JSON not found in OpenAI response')
        about_page = json.loads(content[start:end])

        # Align team names with BBB data (match combined generator behavior)
        try:
            bbb_names_roles = []
            if isinstance(bbb_data, dict):
                # Prefer explicit list of names
                if isinstance(bbb_data.get('employee_names'), list):
                    for entry in bbb_data['employee_names']:
                        if isinstance(entry, str) and entry.strip():
                            parts = entry.split(',', 1)
                            name = parts[0].strip()
                            role = parts[1].strip() if len(parts) > 1 else ''
                            bbb_names_roles.append({ 'name': name, 'position': role })
                # Also check numbered Employee_i_name / Employee_i_role pairs
                if not bbb_names_roles:
                    for i in range(1, 21):
                        n = bbb_data.get(f'Employee_{i}_name')
                        r = bbb_data.get(f'Employee_{i}_role')
                        if isinstance(n, str) and n.strip():
                            bbb_names_roles.append({ 'name': n.strip(), 'position': (r or '').strip() })

            # If we found BBB employees, use up to 4 to match About page compact layout
            if bbb_names_roles:
                limited = bbb_names_roles[:4]
                about_page['team'] = [
                    { 'name': it.get('name') or '', 'position': it.get('position') or '' }
                    for it in limited
                ]
        except Exception:
            # Keep AI-generated team on failure
            pass

        # Deterministic image paths (template-style) and ImageProps prompts
        # Paths under /personal/old/ so the preview can mirror to /generation/
        # - Hero image
        about_page['heroImage'] = "/personal/old/img/about_page/Hero/1.jpg"

        # - Team photos numbered deterministically (keep indices aligned with team array)
        team_list = about_page.get('team') if isinstance(about_page, dict) else None
        if isinstance(team_list, list) and team_list:
            for idx, member in enumerate(team_list):
                if isinstance(member, dict):
                    member['photo'] = f"/personal/old/img/about_page/team/{idx+1}.jpg"

        # - ImageProps with prompts for hero and team
        image_props = {
            "hero": {
                "v1": f"Photorealistic wide hero image of a trusted {city} roofing company crew with branded truck in background, clean curb appeal house, warm natural light, copy-safe right third, 16:9"
            },
            "team": {
                "v1": "Professional headshot on neutral backdrop, friendly confident expression, soft key light, shallow depth of field",
                "v2": "Team portrait outdoors in front of a home, branded shirts, natural light, balanced composition",
                "v3": "On-site candid: technician with tools on roof edge, safe and professional, shallow depth",
                "v4": "Crew lineup with ladder and tool belts, smiling, brand-neutral background",
                "v5": "Workshop scene with materials neatly arranged, technician at work, warm tone"
            }
        }
        about_page['ImageProps'] = image_props
        
        # Add 'steps' section which wasn't in the original about_page generation
        about_page["steps"] = [
            {
                "title": "Book",
                "videoSrc": "/assets/videos/our_process_videos/booking.mp4",
                "href": "/#booking",
                "scale": 0.8
            },
            {
                "title": "Inspection",
                "videoSrc": "/assets/videos/our_process_videos/magnify.mp4",
                "href": "/inspection",
                "scale": 1.25
            },
            {
                "title": "Service",
                "videoSrc": "/assets/videos/our_process_videos/repair.mp4",
                "href": "/#packages",
                "scale": 1.1
            },
            {
                "title": "Review",
                "videoSrc": "/assets/videos/our_process_videos/approval.mp4",
                "href": "/#testimonials",
                "scale": 0.9
            }
        ]
        
        # Save about page to separate JSON file
        with open(about_page_output, 'w') as file:
            json.dump(about_page, file, indent=2)
        
        logger.info("About page generation completed successfully!")
        logger.info(f"Content saved to: {about_page_output}")
    
    except Exception as e:
        logger.error(f"Error generating about page: {str(e)}")
        return 1
    
    # Emit markers for backend
    try:
        print('ABOUT_JSON_START')
        print(json.dumps(about_page, ensure_ascii=False))
        print('ABOUT_JSON_END')
    except Exception:
        pass
    return 0

def generate_about_page(company_name, year_established, years_in_business, city):
    """
    Generate the about page content with realistic and professional information.
    
    Args:
        company_name: Name of the company
        year_established: Year the company was established
        years_in_business: Number of years in business
        city: City where the company operates
    
    Returns:
        Dictionary containing the about page data
    """
    # Core content generation
    history = generate_history_content(company_name, year_established, years_in_business, city)
    mission = generate_mission_content(company_name)
    values = generate_values_content(city)
    team = generate_team_content()
    stats = generate_stats_content(years_in_business)
    
    # Create about page data structure
    about_page = {
        "title": f"{company_name}: {city}'s Trusted Roofing Experts",
        "subtitle": f"Building Strong Roofs, Stronger Relationships",
        "history": history,
        "mission": mission,
        "values": values,
        "team": team,
        "stats": stats,
        "heroImage": "/assets/images/about/about-hero.jpg"
    }
    
    return about_page

def generate_history_content(company_name, year_established, years_in_business, city):
    """Generate professional company history content."""
    history_templates = [
        f"Founded in {year_established}, {company_name} has been serving the {city} community with top-tier roofing solutions for nearly a decade. What started as a small, family-owned business has grown into a trusted name in the industry, known for quality craftsmanship and exceptional customer service. Over the years, we've tackled everything from minor repairs to full roof replacements, earning a reputation for reliability and attention to detail. Our deep roots in {city} drive our commitment to protecting homes and businesses with durable, weather-resistant roofing systems tailored to the region's unique climate.",
        f"Since our establishment in {year_established}, {company_name} has been dedicated to providing top-quality roofing solutions to our {city} community. What began as a small operation has now expanded into a full-service roofing company with a team of skilled professionals and a portfolio of successful projects across the region. As a locally owned business, we understand the specific challenges that {city} weather presents to roofing systems, and we've developed specialized techniques to ensure lasting protection.",
        f"{company_name} was founded in {year_established} with a simple mission: to provide honest, reliable roofing services at fair prices to the {city} area. Over the past {years_in_business} years, we've stayed true to that mission while growing our expertise, team, and service offerings to better serve our customers. We've built our reputation one roof at a time, with attention to detail and commitment to quality that has made us one of the most trusted names in {city} roofing."
    ]
    
    return random.choice(history_templates)

def generate_mission_content(company_name):
    """Generate professional mission statement content."""
    mission_templates = [
        "Our mission is to deliver superior roofing solutions with integrity, precision, and care. We strive to exceed expectations by combining expert craftsmanship with personalized service, ensuring every project—big or small—is built to last and backed by our unwavering commitment to quality.",
        f"At {company_name}, our mission is simple: to protect your most valuable asset with quality roofing solutions that stand the test of time. We're committed to using premium materials, employing skilled craftsmen, and providing transparent communication throughout every project. Our success is measured not just by the roofs we install, but by the relationships we build with our clients.",
        f"{company_name} is dedicated to exceeding customer expectations through superior workmanship, professional service, and attention to detail. We aim to be the most trusted name in roofing by treating every home or business as if it were our own. Through integrity, expertise, and continuous improvement, we deliver roofing solutions that provide lasting peace of mind."
    ]
    
    return random.choice(mission_templates)

def generate_values_content(city):
    """Generate professional company values with city reference."""
    all_values = [
        {
            "title": "Quality Craftsmanship",
            "description": "We take pride in every detail, using premium materials and proven techniques to ensure roofs that stand the test of time."
        },
        {
            "title": "Customer Trust",
            "description": "Honesty and transparency guide every interaction, fostering long-term relationships built on reliability and respect."
        },
        {
            "title": "Community Focus",
            "description": f"As {city} locals, we're invested in the safety and beauty of our neighborhoods, offering solutions that enhance homes and businesses alike."
        },
        {
            "title": "Innovation",
            "description": "We stay ahead of industry trends and technologies to provide efficient, sustainable, and cutting-edge roofing options."
        },
        {
            "title": "Safety",
            "description": "Safety is our top priority on every job site, protecting both our team members and your property throughout the project."
        },
        {
            "title": "Environmental Responsibility",
            "description": "We're committed to eco-friendly practices and materials that minimize environmental impact while maximizing energy efficiency."
        },
        {
            "title": "Excellence",
            "description": "We pursue excellence in everything we do, from our initial consultation to the final inspection and follow-up."
        }
    ]
    
    # Select 4 random values but always include "Community Focus" with the city reference
    community_value = next((v for v in all_values if v["title"] == "Community Focus"), None)
    other_values = [v for v in all_values if v["title"] != "Community Focus"]
    selected_values = random.sample(other_values, 3)
    
    if community_value:
        selected_values.append(community_value)
    
    return selected_values

def generate_team_content():
    """Generate sample team members."""
    # These would typically be replaced with actual team information
    team = [
        {
            "name": "Luis Aguilar-Lopez",
            "position": "Owner",
            "photo": "/assets/images/team/roofer.png"
        },
        {
            "name": "Erika Salinas",
            "position": "Manager",
            "photo": "/assets/images/team/foreman.png"
        }
    ]
    
    # Additional sample team members that could be randomly added
    additional_members = [
        {
            "name": "Michael Rodriguez",
            "position": "Lead Technician",
            "photo": "/assets/images/team/manager.png"
        },
        {
            "name": "Sarah Johnson",
            "position": "Customer Relations",
            "photo": "/assets/images/team/salesrep.png"
        },
        {
            "name": "Robert Garcia",
            "position": "Project Manager",
            "photo": "/assets/images/team/estimator.png"
        }
    ]
    
    # Randomly add 0-2 additional team members
    num_additional = random.randint(0, 2)
    if num_additional > 0:
        selected_additional = random.sample(additional_members, num_additional)
        team.extend(selected_additional)
    
    return team

def generate_stats_content(years_in_business):
    """Generate company statistics for the about page."""
    stats = [
        {
            "title": "Years in Business",
            "value": years_in_business,
            "icon": "FaHistory"
        },
        {
            "title": "Completed Projects",
            "value": random.randint(years_in_business * 30, years_in_business * 60),
            "icon": "FaAward"
        },
        {
            "title": "Happy Clients",
            "value": random.randint(years_in_business * 25, years_in_business * 50),
            "icon": "FaUsers"
        },
        {
            "title": "Team Members",
            "value": random.randint(5, 15),
            "icon": "FaHandshake"
        }
    ]
    
    return stats

if __name__ == "__main__":
    exit(main()) 