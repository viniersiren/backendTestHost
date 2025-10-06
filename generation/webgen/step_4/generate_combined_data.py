#!/usr/bin/env python3

import os
import sys
import json
import logging
import time
import random
import re
from typing import Dict, Any, List, Optional, Tuple
from dotenv import load_dotenv
from pathlib import Path
import os
import json as _json
import requests
from urllib.parse import urlparse
import shutil

def call_openai_chat(prompt: str) -> str:
    api_key = os.getenv('OPENAI_API_KEY')
    try:
        from datetime import datetime as _dt
        print(f"[Combined][LLM] {str(_dt.now())}: prompt_len={len(prompt or '')}, key_present={bool(api_key)}")
    except Exception:
        pass
    if not api_key:
        raise RuntimeError('OPENAI_API_KEY missing')
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    data = {
        'model': 'gpt-4o-mini',
        'messages': [{ 'role': 'user', 'content': prompt }],
        'temperature': 0.7,
        'max_tokens': 4000
    }
    resp = requests.post('https://api.openai.com/v1/chat/completions', headers=headers, json=data, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f'OpenAI error: {resp.status_code} {resp.text}')
    return resp.json()['choices'][0]['message']['content']

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables from shared .env (same convention as step_2/research_services.py)
env_path = Path(__file__).parent.parent.parent / ".env"
try:
    load_dotenv(env_path)
    print(f"[Combined] Loaded .env from {env_path} (exists={os.path.exists(env_path)})")
    print(f"[Combined] OPENAI key present: {bool(os.getenv('OPENAI_API_KEY'))}")
except Exception as _e:
    print(f"[Combined] Failed to load .env: {_e}")

class CombinedDataGenerator:
    """
    Class to generate comprehensive combined_data.json that powers the roofing website.
    Uses BBB profile data, sentiment reviews, and OpenAI to create comprehensive content.
    Uses a template approach where placeholder variables are replaced with actual data.
    """
    
    def __init__(self, bbb_profile_path: str, reviews_path: str, insights_path: str = None, yelp_path: str = None, template_path: str = None, stdin_payload: Dict[str, Any] = None):
        """Initialize with paths to various data sources."""
        logger.info("Initializing CombinedDataGenerator")
        
        # OpenAI API key is loaded via load_dotenv; individual calls validate presence as needed
        
        # Memory-only: prefer STDIN payload if provided
        self._stdin = stdin_payload or {}
        try:
            if isinstance(stdin_payload, dict):
                logger.info(f"[Combined] STDIN payload keys: {list(stdin_payload.keys())}")
            else:
                logger.info("[Combined] No STDIN payload or not a dict")
        except Exception:
            pass
        self.bbb_profile = {}
        if isinstance(self._stdin, dict):
            if isinstance(self._stdin.get('bbbProfile'), dict):
                self.bbb_profile = self._stdin.get('bbbProfile') or {}
            elif isinstance(self._stdin.get('profileData'), dict):
                self.bbb_profile = self._stdin.get('profileData') or {}
        if not self.bbb_profile:
            logger.info(f"Loading BBB profile from: {bbb_profile_path}")
            self.bbb_profile = self._load_json(bbb_profile_path)
        if not self.bbb_profile:
            logger.warning("BBB profile data is empty or failed to load")
        
        self.reviews = None
        if isinstance(self._stdin, dict) and self._stdin.get('reviewsData'):
            self.reviews = self._stdin.get('reviewsData')
        if self.reviews is None:
            logger.info(f"Loading reviews from: {reviews_path}")
            self.reviews = self._load_json(reviews_path)
        if not self.reviews:
            logger.warning("Reviews data is empty or failed to load")
        
        # Optional Yelp data for service hours/contact
        self.yelp_data = {}
        if isinstance(self._stdin, dict) and self._stdin.get('yelpData'):
            self.yelp_data = self._stdin.get('yelpData') or {}
        elif yelp_path:
            logger.info(f"Loading Yelp data from: {yelp_path}")
            self.yelp_data = self._load_json(yelp_path)
            if not self.yelp_data:
                logger.warning("Yelp data is empty or failed to load")
        
        if isinstance(self._stdin, dict) and self._stdin.get('insights'):
            self.insights = self._stdin.get('insights') or {}
        elif insights_path:
            logger.info(f"Loading research insights from: {insights_path}")
            self.insights = self._load_json(insights_path)
            if not self.insights:
                logger.warning("Research insights data is empty or failed to load")
        else:
            logger.info("No insights path provided, skipping insights loading")
            self.insights = {}
        
        # Load services from the shared roofing_services.json
        self.services = self._load_services()
        try:
            logger.info(f"[Combined] Services counts → res={len(self.services.get('residential', []))}, com={len(self.services.get('commercial', []))}")
        except Exception:
            pass
        # Social links from STDIN memory (deterministic, optional)
        self.social_links = {}
        if isinstance(self._stdin, dict):
            sd = self._stdin.get('socialData') or {}
            if isinstance(sd, dict):
                # Normalize to simple map of network -> url
                self.social_links = { k: (v or '').strip() for k, v in sd.items() if isinstance(v, str) and v.strip() }
        # Image selections and gray logo
        self.image_selections = {}
        self.gray_logo_url = None
        if isinstance(self._stdin, dict):
            if isinstance(self._stdin.get('imageSelections'), dict):
                self.image_selections = self._stdin.get('imageSelections') or {}
            if isinstance(self._stdin.get('grayLogoUrl'), str):
                self.gray_logo_url = (self._stdin.get('grayLogoUrl') or '').strip() or None
            # In-memory testimonial selection from admin controls
            self.testimonial_config = self._stdin.get('testimonialConfig') or {}
        
        # Load template file (use dedicated combined_template.json); do NOT overwrite template
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.template_file = template_path if (template_path and os.path.exists(template_path)) else os.path.join(script_dir, "combined_template.json")
        try:
            logger.info(f"[Combined] Using template: {self.template_file} (exists={os.path.exists(self.template_file)})")
        except Exception:
            pass
        
        # Memory-only: do not persist to disk by default
        data_dir = None
        self.output_file = None

        # Prepare generation image base dir
        # Memory-only: disable image persistence locations
        self.repo_root = None
        self.generation_img_dir = None
        self.main_page_img_dir = Path('/dev/null')

    def _download_or_copy_image(self, url: str, dest_path: Path) -> bool:
        try:
            # memory-only: skip persistence
            return False
            # Support data URLs or http(s)
            if isinstance(url, str) and url.startswith('data:image/'):
                # data URL; find mime
                import base64
                header, b64 = url.split(',', 1)
                # Respect extension from dest_path
                with open(dest_path, 'wb') as f:
                    f.write(base64.b64decode(b64))
                return True
            parsed = urlparse(url)
            if parsed.scheme in ('http', 'https'):
                r = requests.get(url, timeout=30)
                if r.status_code == 200:
                    with open(dest_path, 'wb') as f:
                        f.write(r.content)
                    return True
                return False
            # If it's a local absolute path
            if os.path.exists(url):
                shutil.copyfile(url, str(dest_path))
                return True
        except Exception as e:
            logger.warning(f"Failed to persist image {url} -> {dest_path}: {e}")
        return False

    def _ext_from_url_or_default(self, url: str, default_ext: str = '.jpg') -> str:
        if not isinstance(url, str):
            return default_ext
        path = urlparse(url).path if '://' in url else url
        _, ext = os.path.splitext(path)
        return ext if ext else default_ext

    def _normalize_employee_name(self, name: str) -> str:
        """Return a canonical form of a person's name for duplicate detection.
        - Trim whitespace
        - If a role is appended after a comma, drop it
        - Collapse internal whitespace and lowercase
        """
        try:
            if not isinstance(name, str):
                return ''
            cleaned = name.strip()
            if ',' in cleaned:
                cleaned = cleaned.split(',', 1)[0].strip()
            cleaned = re.sub(r'\s+', ' ', cleaned)
            return cleaned.lower()
        except Exception:
            return ''

    def _dedupe_name_strings(self, names: List[str]) -> List[str]:
        """Dedupe a list of name strings by normalized name, preserving order."""
        seen = set()
        unique: List[str] = []
        for raw in names or []:
            norm = self._normalize_employee_name(raw)
            if norm and norm not in seen:
                seen.add(norm)
                unique.append((raw or '').strip())
        return unique

    def _dedupe_name_role_pairs(self, pairs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Dedupe a list of {name, role} pairs by normalized name, preserving order."""
        seen = set()
        unique: List[Dict[str, Any]] = []
        for p in pairs or []:
            norm = self._normalize_employee_name(p.get('name'))
            if norm and norm not in seen:
                seen.add(norm)
                unique.append(p)
        return unique

    def _old_to_generation(self, path: str) -> str:
        try:
            if isinstance(path, str) and path.startswith('/personal/old/'):
                return '/generation/' + path[len('/personal/old/'):]
            return path
        except Exception:
            return path
    
    def _load_services(self) -> Dict[str, List[Dict[str, Any]]]:
        """Load services from the shared roofing_services.json file."""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.dirname(script_dir)
        services_path = os.path.join(data_dir, "roofing_services.json")
        
        # Default services in case the file doesn't exist
        default_services = {
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
        
        try:
            if os.path.exists(services_path):
                with open(services_path, 'r', encoding='utf-8') as f:
                    services = json.load(f)
                logger.info(f"Successfully loaded services from {services_path}")
                return services
            else:
                logger.warning(f"Services file not found at {services_path}, using default services")
                return default_services
        except Exception as e:
            logger.error(f"Error loading services file: {e}")
            return default_services
    
    def _load_json(self, filepath: str) -> Dict[str, Any]:
        """Load and return JSON data from file."""
        logger.debug(f"Attempting to load JSON from: {filepath}")
        try:
            if not os.path.exists(filepath):
                logger.error(f"File does not exist: {filepath}")
                return {}
                
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.debug(f"Successfully loaded JSON data from {filepath}")
                return data
        except FileNotFoundError:
            logger.error(f"File not found: {filepath}")
            return {}
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in file {filepath}: {str(e)}")
            return {}
        except Exception as e:
            logger.error(f"Unexpected error loading {filepath}: {str(e)}")
            return {}
    
    def _save_combined_data(self, data: Dict[str, Any]):
        """Save combined data to JSON file."""
        # memory-only: no file write
        logger.info("Combined data prepared (memory-only)")
    
    def _extract_business_name(self) -> Tuple[str, str]:
        """
        Extract business name and intelligently split it into main title and subtitle based on LLM analysis.
        If the name is short, don't use a subtitle.
        """
        if not self.bbb_profile:
            return "ROOFING COMPANY", ""
            
        business_name = self.bbb_profile.get('business_name', 'Roofing Company')
        
        
        # Ask OpenAI if/how the name should be split
        prompt = f"""
        I have a roofing business name: "{business_name}"
        
        Should this name be split into a main title and subtitle for a website header? If yes, how would you split it?
        
        Some guidelines:
        1. If the name is very short (1-2 words), don't split it and just leave the subtitle empty
        2. If the name contains words like "Construction", "Roofing", "Contractors", "Company", etc., these are good candidates for the subtitle
        3. If the name has a clear brand name followed by a descriptor, split between those
        
        Return your answer as a JSON with two keys:
        - "shouldSplit": boolean (true or false)
        - "mainTitle": string (the main title portion or the entire name if not splitting)
        - "subTitle": string (the subtitle portion, or empty string if not splitting)
        """
        
        # Hard-require OpenAI for name split
        response = call_openai_chat(prompt)
        
        try:
            # Extract JSON from response
            if '{' in response and '}' in response:
                json_str = response[response.find('{'):response.rfind('}')+1]
                result = json.loads(json_str)
                
                should_split = result.get('shouldSplit', False)
                main_title = result.get('mainTitle', business_name)
                sub_title = result.get('subTitle', "")
                
                if should_split:
                    return main_title, sub_title
                else:
                    return business_name, ""
            else:
                # No parsable JSON
                raise RuntimeError("Failed to parse OpenAI response for business name split")
        except Exception as e:
            raise RuntimeError(f"Business name split failed: {e}")
            
    def _simple_business_name_split(self, business_name: str) -> Tuple[str, str]:
        """Simple fallback method to split business name."""
        parts = business_name.split()
        if len(parts) <= 2:
            return business_name, ""
        
        # Look for common business suffixes to determine where to split
        suffixes = ["Construction", "Roofing", "Contractors", "Company", "Services", "Inc", "LLC"]
        for i, word in enumerate(parts):
            if any(suffix.lower() in word.lower() for suffix in suffixes) and i > 0:
                return " ".join(parts[:i]), " ".join(parts[i:])
        
        # Default split halfway if no better option is found
        midpoint = len(parts) // 2
        return " ".join(parts[:midpoint]), " ".join(parts[midpoint:])
    
    def _extract_best_reviews(self, count: int = 6) -> List[Dict[str, Any]]:
        """Extract the best reviews based on sentiment and rating."""
        if not self.reviews:
            return []
        
        # Support multiple formats: { reviews: [...] } or a list [...]
        raw_reviews = []
        if isinstance(self.reviews, dict) and isinstance(self.reviews.get('reviews'), list):
            raw_reviews = self.reviews.get('reviews', [])
        elif isinstance(self.reviews, list):
            raw_reviews = self.reviews
        else:
            # Unknown format
            return []
        
        def to_float(value, default=0.0):
            try:
                return float(value)
            except Exception:
                return default
        
        # Sort by rating and optional polarity if present
        sorted_reviews = sorted(
            raw_reviews,
            key=lambda x: (
                to_float(x.get('rating') or x.get('stars') or 0),
                to_float(x.get('polarity') or 0)
            ),
            reverse=True
        )
        
        formatted_reviews = []
        for review in sorted_reviews[:count]:
            # Normalize fields
            name = review.get('name') or review.get('author') or 'Customer'
            rating_val = review.get('rating') or review.get('stars') or 5
            date_val = review.get('date') or review.get('time') or ''
            text_val = review.get('review_text') or review.get('text') or ''
            try:
                stars = int(round(float(rating_val)))
            except Exception:
                stars = 5
            
            formatted_reviews.append({
                "name": name,
                "stars": stars,
                "date": date_val,
                "text": text_val,
                "logo": "/assets/images/hero/googleimage.png",
                "link": "https://www.google.com/maps"
            })
        
        return formatted_reviews

    def _map_yelp_hours_to_service_hours(self, yelp_hours: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Map Yelp hours dictionary to serviceHours list with ids and abbreviations."""
        if not isinstance(yelp_hours, dict) or not yelp_hours:
            return []
        day_order = [
            ("Mon", "Monday"), ("Tue", "Tuesday"), ("Wed", "Wednesday"), ("Thu", "Thursday"),
            ("Fri", "Friday"), ("Sat", "Saturday"), ("Sun", "Sunday")
        ]
        mapped = []
        for idx, (abbr, full) in enumerate(day_order):
            entry = yelp_hours.get(full) or yelp_hours.get(abbr) or {}
            hours_text = entry.get('hours') or entry.get('time') or entry.get('value') or 'CLOSED'
            mapped.append({
                "id": f"sh_{abbr.lower()}",
                "day": abbr,
                "time": hours_text
            })
        return mapped
    
    def _generate_rich_text_hero(self, business_name: str) -> str:
        """Generate hero text for rich text section."""
        templates = [
            f"Expert Roofs, Trusted Craftsmanship",
            f"Quality Roofing Solutions by {business_name}",
            f"Protecting Your Home with Excellence",
            f"Reliable Roofing for Every Season"
        ]
        return random.choice(templates)

    def _generate_rich_text_cards_llm(self, business_name: str, years: int, services_data: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """Use OpenAI to generate 3-4 benefit cards for RichTextBlock.Content.cards.
        Returns a list of {id, title, desc, icon, iconPack} objects.
        """
        # Flatten service names for context
        residential_names = [s.get('name') for s in services_data.get('residential', []) if s.get('name')]
        commercial_names = [s.get('name') for s in services_data.get('commercial', []) if s.get('name')]

        prompt = f"""
            Create concise marketing cards for a roofing company's homepage rich text section.
            Company: {business_name}
            Years in business: {years}
            Residential services: {', '.join(residential_names) or 'N/A'}
            Commercial services: {', '.join(commercial_names) or 'N/A'}

            Requirements:
            - Return STRICT JSON ONLY (no markdown), with a top-level key "cards" mapping to an array of 3-4 items.
            - Each item must be an object with keys: "title" (<= 3 words), "desc" (1 sentence), "icon" (icon name), "iconPack" (one of: "lucide", "fa", "md", "hi2", "ri", "tb"). Prefer lucide; if unsure, choose lucide.
            - Do not include IDs; we'll assign them.
            - Tone: professional, trustworthy, customer-focused, concise.

            Example JSON shape:
            {{"cards":[{{"title":"Expert Craftsmanship","desc":"Skilled crews deliver precise installations and durable repairs.","icon":"Tools","iconPack":"lucide"}}]}}
            """

        response = call_openai_chat(prompt)
        # Extract pure JSON in case the model wrapped anything
        json_str = None
        if '{' in response and '}' in response:
            json_str = response[response.find('{'):response.rfind('}')+1]
        parsed = json.loads(json_str) if json_str else {}
        cards = parsed.get('cards', []) if isinstance(parsed, dict) else []

        result = []
        allowed_packs = {"lucide", "fa", "md", "hi2", "ri", "tb"}
        for idx, c in enumerate(cards[:4]):
            title = str(c.get('title') or '').strip() or f"Benefit {idx+1}"
            desc = str(c.get('desc') or '').strip() or "Professional service from inspection to final cleanup."
            icon = str(c.get('icon') or 'Star').strip()
            icon_pack_raw = str(c.get('iconPack') or '').strip().lower()
            icon_pack = icon_pack_raw if icon_pack_raw in allowed_packs else 'lucide'
            result.append({
                "id": f"card-{idx+1}",
                "title": title,
                "desc": desc,
                "icon": icon,
                "iconPack": icon_pack
            })

        if not result:
            raise RuntimeError("LLM returned no cards")
        return result
    
    def _get_geocoordinates_from_address(self, address: str) -> Tuple[float, float]:
        """
        Get geocoordinates (latitude, longitude) from address using OpenAI.
        
        Since we don't have direct access to mapping APIs, we'll use the LLM to
        estimate the coordinates based on the address.
        """
        prompt = f"""
        Please provide latitude and longitude coordinates for this address: {address}
        
        Return only the coordinates as a JSON with 'lat' and 'lng' keys.
        Example: {{"lat": 33.7490, "lng": -84.3880}}
        
        Do not include any additional information or explanation, just the JSON.
        """
        
        response = call_openai_chat(prompt)
        
        try:
            # Extract JSON from response
            if '{' in response and '}' in response:
                json_str = response[response.find('{'):response.rfind('}')+1]
                result = json.loads(json_str)
                
                lat = float(result['lat'])
                lng = float(result['lng'])
                
                return lat, lng
            else:
                raise RuntimeError("No JSON coordinates in OpenAI response")
        except Exception as e:
            raise RuntimeError(f"Geocoordinates derivation failed: {e}")
    
    def _extract_city_from_address(self, address: str) -> str:
        """Extract city from address string."""
        # Try simple pattern matching for city extraction
        city_pattern = r'(?:,\s*|\s+)([A-Za-z\s]+)(?:,\s*[A-Z]{2}|$)'
        match = re.search(city_pattern, address)
        if match:
            city = match.group(1).strip()
            if city and len(city) > 2:  # Ensure we have a reasonable city name
                return city
        
        # Default city if extraction fails
        return "Atlanta"
    
    def _format_employee_data(self) -> List[Dict[str, Any]]:
        """Format employee data from BBB profile."""
        formatted_employees: List[Dict[str, Any]] = []

        # Extract employee names from BBB profile (allow 1-9, dedup by name)
        employee_names: List[str] = []
        if 'employee_names' in self.bbb_profile and isinstance(self.bbb_profile['employee_names'], list):
            employee_names = self.bbb_profile['employee_names']
        names_unique = self._dedupe_name_strings(employee_names)[:9]

        # Default photos to use
        photos = [
            "/assets/images/team/roofer.png",
            "/assets/images/team/foreman.png",
            "/assets/images/team/estimator.png",
            "/assets/images/team/salesrep.png",
            "/assets/images/team/manager.png",
            "/assets/images/team/inspector.png"
        ]

        # Default positions if not included in the employee name
        positions = ["Owner", "Manager", "Estimator", "Sales Rep", "Inspector", "Foreman"]

        # Format each employee (cap 9, dedup already applied)
        for i, raw_name in enumerate(names_unique[:9]):
            position = positions[i % len(positions)]
            employee_name = raw_name
            if ',' in raw_name:
                name_parts = raw_name.split(',', 1)
                employee_name = name_parts[0].strip()
                if len(name_parts) > 1 and name_parts[1].strip():
                    position = name_parts[1].strip()

            formatted_employees.append({
                "name": employee_name,
                "role": position,
                "image": photos[i % len(photos)]
            })

        # If no employees found, add a single placeholder (do not force two)
        if not formatted_employees:
            formatted_employees = [{
                "name": "John Smith",
                "role": "Owner",
                "image": "/assets/images/team/roofer.png"
            }]

        return formatted_employees
    
    def _generate_employees_title(self, business_name: str, city: str) -> str:
        """Use LLM to generate a concise 1-2 word employees section title."""
        try:
            prompt = (
                "Generate a concise 1-2 word section title for a roofing company's team section. "
                f"Company: {business_name}. City: {city}. Return STRICT JSON only: {{\"title\": \"OUR TEAM\"}}. "
                "Prefer options like 'OUR TEAM', 'CREW', or 'TEAM MEMBERS'."
            )
            resp = call_openai_chat(prompt)
            if '{' in resp and '}' in resp:
                js = resp[resp.find('{'):resp.rfind('}')+1]
                parsed = json.loads(js)
                title = (parsed.get('title') or '').strip()
                return title or 'OUR TEAM'
        except Exception:
            pass
        return 'OUR TEAM'

    def _generate_before_after_title(self, business_name: str) -> str:
        """Use LLM to generate a concise 1-2 word gallery title for before/after."""
        try:
            prompt = (
                "Generate a concise 1-2 word section title for a roofing before/after gallery. "
                f"Company: {business_name}. Return STRICT JSON only: {{\"title\": \"GALLERY\"}}. "
                "Prefer 'GALLERY', 'SHOWCASE', or 'BEFORE & AFTER'."
            )
            resp = call_openai_chat(prompt)
            if '{' in resp and '}' in resp:
                js = resp[resp.find('{'):resp.rfind('}')+1]
                parsed = json.loads(js)
                title = (parsed.get('title') or '').strip()
                return title or 'GALLERY'
        except Exception:
            pass
        return 'GALLERY'

    def _generate_map_title(self, business_name: str, city: str) -> str:
        """Use LLM to generate a concise 1-2 word contact/map section title."""
        try:
            prompt = (
                "Generate a concise 1-2 word section title for a contact/location map section for a roofing company. "
                f"Company: {business_name}. City: {city}. Return STRICT JSON only: {{\"title\": \"Contact Us\"}}. "
                "Prefer 'Contact Us', 'Visit Us', or 'Find Us'."
            )
            resp = call_openai_chat(prompt)
            if '{' in resp and '}' in resp:
                js = resp[resp.find('{'):resp.rfind('}')+1]
                parsed = json.loads(js)
                title = (parsed.get('title') or '').strip()
                return title or 'Contact Us'
        except Exception:
            pass
        return 'Contact Us'

    def _get_reviews_flat(self) -> List[Dict[str, Any]]:
        """Normalize reviews data to a simple list of dicts."""
        try:
            if not self.reviews:
                return []
            if isinstance(self.reviews, dict) and isinstance(self.reviews.get('reviews'), list):
                return self.reviews.get('reviews', [])
            if isinstance(self.reviews, list):
                return self.reviews
        except Exception:
            return []
        return []

    def _compute_basic_map_stats(self, years: int, employee_count_fallback: int, customers_served_fallback: int) -> List[Dict[str, Any]]:
        """Compose BasicMap stats from BBB/reviews/Yelp with sensible fallbacks.
        Returns up to 4 stat items with id, title, value, icon.
        """
        stats: List[Dict[str, Any]] = []

        # Years of Service (from BBB parsed years)
        try:
            yrs = int(years) if years is not None else 0
        except Exception:
            yrs = 0
        if yrs > 0:
            stats.append({
                "id": "stat_years_service",
                "title": "Years of Service",
                "value": str(yrs),
                "icon": "FaCalendarAlt"
            })

        # Average Rating from reviews (fallback to Yelp if available)
        avg_rating = None
        try:
            rv = self._get_reviews_flat()
            ratings = []
            for r in rv:
                val = r.get('rating') or r.get('stars')
                try:
                    if val is not None:
                        ratings.append(float(val))
                except Exception:
                    continue
            if ratings:
                avg_rating = round(sum(ratings) / len(ratings), 2)
        except Exception:
            avg_rating = None
        # Yelp fallback if no review avg was found
        if avg_rating is None:
            try:
                if isinstance(self.yelp_data, dict):
                    if isinstance(self.yelp_data.get('rating'), (int, float)):
                        avg_rating = float(self.yelp_data.get('rating'))
                    elif isinstance(self.yelp_data.get('business'), dict) and isinstance(self.yelp_data['business'].get('rating'), (int, float)):
                        avg_rating = float(self.yelp_data['business'].get('rating'))
            except Exception:
                pass
        if isinstance(avg_rating, (int, float)) and avg_rating > 0:
            stats.append({
                "id": "stat_avg_rating",
                "title": "Average Rating",
                "value": f"{avg_rating}",
                "icon": "FaStar"
            })

        # Team members from BBB employee list; fallback to provided
        try:
            bbb_count = 0
            if isinstance(self.bbb_profile, dict):
                if isinstance(self.bbb_profile.get('employee_names'), list):
                    bbb_count = len([n for n in self.bbb_profile.get('employee_names') if isinstance(n, str) and n.strip()])
                else:
                    # Count Employee_i_name fields
                    c = 0
                    for i in range(1, 21):
                        v = self.bbb_profile.get(f'Employee_{i}_name')
                        if isinstance(v, str) and v.strip():
                            c += 1
                    bbb_count = c
            team_count = bbb_count or employee_count_fallback or 0
            if team_count > 0:
                stats.append({
                    "id": "stat_team_members",
                    "title": "Team Members",
                    "value": str(team_count),
                    "icon": "FaUsers"
                })
        except Exception:
            pass

        # Customers served fallback (derived earlier)
        try:
            if customers_served_fallback and customers_served_fallback > 0:
                stats.append({
                    "id": "stat_customers",
                    "title": "Customers Served",
                    "value": f"{customers_served_fallback}+",
                    "icon": "FaHandshake"
                })
        except Exception:
            pass

        # Limit to 4 items maximum
        return stats[:4]
    
    def _format_and_add_slugs_to_services(self, services_data: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
        """
        Format services data and add slugs for the hero section and combined page.
        Returns data formatted for both hero section and combined page.
        """
        result = {
            "hero": {
                "residential": [],
                "commercial": []
            },
            "combined": {
                "residential": [],
                "commercial": []
            }
        }
        
        # Icons for combined page
        residential_icons = ["FaHardHat", "FaHome", "FaTools", "FaBroom"]
        commercial_icons = ["FaPaintRoller", "FaBuilding", "FaWarehouse", "FaChimney"]
        
        # Process residential services
        for idx, service in enumerate(services_data.get("residential", [])):
            service_id = service.get("id", idx + 1)
            service_name = service.get("name", f"Service {service_id}")
            
            # Create slug - replace spaces with hyphens and make lowercase
            slug = f"residential-{service_id}-{service_name.lower().replace(' ', '-')}"
            
            # Add to hero format
            result["hero"]["residential"].append({
                "title": service_name,
                "slug": slug
            })
            
            # Add to combined page format with icon
            icon = residential_icons[idx % len(residential_icons)]
            result["combined"]["residential"].append({
                "icon": icon,
                "title": service_name,
                "link": f"/services/{slug}"
            })
        
        # Process commercial services
        for idx, service in enumerate(services_data.get("commercial", [])):
            service_id = service.get("id", idx + 1)
            service_name = service.get("name", f"Service {service_id}")
            
            # Create slug
            slug = f"commercial-{service_id}-{service_name.lower().replace(' ', '-')}"
            
            # Add to hero format
            result["hero"]["commercial"].append({
                "title": service_name,
                "slug": slug
            })
            
            # Add to combined page format with icon
            icon = commercial_icons[idx % len(commercial_icons)]
            result["combined"]["commercial"].append({
                "icon": icon,
                "title": service_name,
                "link": f"/services/{slug}"
            })
        
        return result
    
    def _generate_booking_header(self) -> str:
        """Generate a short, 1-3 word booking header text."""
        options = [
            "Call Us Today!",
            "Contact Us",
            "Get a Quote",
            "Free Estimate",
            "Roof Help?",
            "Need Service?"
        ]
        return random.choice(options)
    
    def _generate_gallery_title(self) -> str:
        """Generate a 1-2 word variation for the gallery section title."""
        options = [
            "GALLERY",
            "PORTFOLIO",
            "SHOWCASE",
            "OUR WORK",
            "PROJECTS"
        ]
        return random.choice(options)
    
    def _generate_team_section_title(self) -> str:
        """Generate a 1-2 word variation for the team members section title."""
        options = [
            "TEAM MEMBERS",
            "OUR TEAM",
            "CREW",
            "EXPERTS",
            "PROFESSIONALS"
        ]
        return random.choice(options)
    
    def generate(self):
        """Generate the combined data by populating the template with actual data."""
        logger.info("Starting generation of combined data")
        
        try:
            # Load template (dedicated combined_template.json as baseline)
            if not os.path.exists(self.template_file):
                logger.error(f"Template file not found: {self.template_file}")
                raise RuntimeError("Template file not found")
            with open(self.template_file, 'r', encoding='utf-8') as f:
                template_data = json.load(f)
            logger.info("Template loaded successfully")
            
            # Extract data from BBB profile and other sources
            business_name = self.bbb_profile.get('business_name', 'Roofing Company')
            main_title, sub_title = self._extract_business_name()
            address = self.bbb_profile.get('address', "123 Main St, Atlanta, GA")
            city = self._extract_city_from_address(address)
            phone = self.bbb_profile.get('telephone', "(404) 227-5000")
            accredited = self.bbb_profile.get('accredited', True)
            
            # Parse years in business
            years_data = self.bbb_profile.get('years_in_business', 10)
            if isinstance(years_data, str) and ":" in years_data:
                try:
                    years = int(years_data.split(":")[-1].strip())
                except ValueError:
                    years = 10
            else:
                try:
                    years = int(years_data)
                except (ValueError, TypeError):
                    years = 10
            
            # Get geocoordinates
            lat, lng = self._get_geocoordinates_from_address(address)
            
            # Calculate stats
            customers_served = round(years * 50, -1)
            roofs_repaired = round(years * 30, -1)
            completed_projects = round(years * 55, -1)
            happy_clients = round(years * 45, -1)
            team_members_count = min(8, 2 + years // 2)  # Scale team size with years
            
            # Format services
            formatted_services = self._format_and_add_slugs_to_services(self.services)
            
            # Extract reviews
            reviews = self._extract_best_reviews()
            
            # Generate rich text content
            rich_text_hero = self._generate_rich_text_hero(business_name)
            rich_text_desc1 = f"{business_name} has been a trusted name in the roofing industry for {years} years, delivering exceptional craftsmanship and reliability. Specializing in residential and commercial roofing, we combine time-tested techniques with modern materials to ensure durability, aesthetic appeal, and long-lasting protection for your property."
            rich_text_desc2 = f"At {business_name}, we pride ourselves on personalized service and unwavering integrity. Our skilled team handles every project with meticulous attention to detail, from initial inspection to final installation. Customer satisfaction is our top priority, and we stand behind our work with industry-leading warranties and transparent communication."
            
            # Format employees for team sections
            employee_data = self._format_employee_data()
            
            # Generate section titles variations
            booking_header = self._generate_booking_header()
            gallery_title = self._generate_gallery_title()
            team_section_title = self._generate_team_section_title()
            
            # Apply replacements ONLY to content areas in block-oriented template
            def find_block(blocks: List[Dict[str, Any]], name: str) -> Optional[Dict[str, Any]]:
                return next((b for b in blocks if b.get('blockName') == name), None)

            main_blocks = template_data.get('mainPageBlocks', [])

            # Generate concise AI titles for sections
            try:
                ai_emp_title = self._generate_employees_title(business_name, city)
            except Exception:
                ai_emp_title = 'OUR TEAM'
            try:
                ai_ba_title = self._generate_before_after_title(business_name)
            except Exception:
                ai_ba_title = 'GALLERY'
            try:
                ai_map_title = self._generate_map_title(business_name, city)
            except Exception:
                ai_map_title = 'Contact Us'

            # Update HeroBlock Content: set businessName from BBB data (preserve images/prompts/variant)
            hero_block = find_block(main_blocks, 'HeroBlock')
            if hero_block and isinstance(hero_block.get('config'), dict):
                hb_content = hero_block['config'].get('Content', {})
                if business_name:
                    hb_content['businessName'] = business_name
                # Also surface split title/subtitle for display components that prefer them
                if main_title:
                    hb_content['mainTitle'] = main_title
                if sub_title:
                    hb_content['subTitle'] = sub_title
                # Inject contact details to HeroBlock for top-of-page visibility
                if phone:
                    hb_content['telephone'] = phone
                if address:
                    hb_content['address'] = address
                hero_block['config']['Content'] = hb_content

            # Update RichTextBlock Content using LLM: heroText, bus_description, cards
            rich_text_block = find_block(main_blocks, 'RichTextBlock')
            if rich_text_block and isinstance(rich_text_block.get('config'), dict):
                rt_content = rich_text_block['config'].get('Content', {})
                # Set hero text and business description
                if rich_text_hero:
                    rt_content['heroText'] = rich_text_hero
                if rich_text_desc1 and rich_text_desc2:
                    # Combine into two-paragraph description
                    rt_content['bus_description'] = f"{rich_text_desc1}\n\n{rich_text_desc2}"
                # Generate cards via OpenAI
                try:
                    llm_cards = self._generate_rich_text_cards_llm(business_name, years, self.services)
                    if isinstance(llm_cards, list) and llm_cards:
                        rt_content['cards'] = llm_cards
                except Exception as e:
                    logger.warning(f"Failed to generate rich text cards via LLM: {e}")
                # Write back
                rich_text_block['config']['Content'] = rt_content

            # Update BasicMapBlock Content: serviceHours, address, telephone (preserve Design/Formatting)
            basic_map_block = find_block(main_blocks, 'BasicMapBlock')
            if basic_map_block and isinstance(basic_map_block.get('config'), dict):
                bm_content = basic_map_block['config'].get('Content', {})
                # AI-generated title
                if ai_map_title:
                    bm_content['title'] = ai_map_title
                # Address/phone from BBB if present
                if address:
                    bm_content['address'] = address
                if phone:
                    bm_content['telephone'] = phone
                # Service hours from Yelp if available
                yelp_hours = {}
                if isinstance(self.yelp_data, dict):
                    yelp_hours = self.yelp_data.get('yelp_hours') or {}
                mapped_hours = self._map_yelp_hours_to_service_hours(yelp_hours)
                if mapped_hours:
                    bm_content['serviceHours'] = mapped_hours
                # Compute stats from BBB/Reviews/Yelp with fallbacks
                try:
                    # Prefer actual employee list length from formatted data when available
                    employee_count = 0
                    try:
                        employee_count = len(self._format_employee_data())
                    except Exception:
                        employee_count = team_members_count
                    stats_list = self._compute_basic_map_stats(years, employee_count, customers_served)
                    if isinstance(stats_list, list) and stats_list:
                        bm_content['stats'] = stats_list
                except Exception as e:
                    logger.warning(f"Failed to compute BasicMap stats: {e}")
                # Write back
                basic_map_block['config']['Content'] = bm_content

            # Update TestimonialBlock Content: googleReviews from analyzed reviews
            testimonial_block = find_block(main_blocks, 'TestimonialBlock')
            if testimonial_block and isinstance(testimonial_block.get('config'), dict):
                tb_content = testimonial_block['config'].get('Content', {})
                # Prefer user-selected testimonials from admin controls when provided
                try:
                    selected = None
                    if isinstance(getattr(self, 'testimonial_config', None), dict):
                        selected = self.testimonial_config.get('Content', {}).get('googleReviews')
                    if isinstance(selected, list) and len(selected) > 0:
                        tb_content['googleReviews'] = selected[:6]
                    else:
                        best_reviews = self._extract_best_reviews(count=6)
                        if best_reviews:
                            tb_content['googleReviews'] = best_reviews
                except Exception:
                    best_reviews = self._extract_best_reviews(count=6)
                    if best_reviews:
                        tb_content['googleReviews'] = best_reviews
                testimonial_block['config']['Content'] = tb_content

            # Rewrite BeforeAfterBlock paths to /generation/ mirror (memory-only mapping)
            ba_block = find_block(main_blocks, 'BeforeAfterBlock')
            if ba_block and isinstance(ba_block.get('config'), dict):
                try:
                    ba_content = ba_block['config'].get('Content', {})
                    # AI-generated title
                    if ai_ba_title:
                        ba_content['sectionTitle'] = ai_ba_title
                    items = ba_content.get('items') if isinstance(ba_content.get('items'), list) else []
                    new_items = []
                    for it in items:
                        if not isinstance(it, dict):
                            new_items.append(it)
                            continue
                        new_it = dict(it)
                        if 'before' in new_it:
                            new_it['before'] = self._old_to_generation(new_it.get('before'))
                        if 'after' in new_it:
                            new_it['after'] = self._old_to_generation(new_it.get('after'))
                        new_items.append(new_it)
                    if new_items:
                        ba_content['items'] = new_items
                        ba_block['config']['Content'] = ba_content
                except Exception as e:
                    logger.warning(f"BeforeAfterBlock generation path mapping failed: {e}")

            # Seed BeforeAfterBlock ImageProps.before_after.selected with RNG picks (validated by LLM)
            try:
                if ba_block and isinstance(ba_block.get('config'), dict):
                    img_props = ba_block['config'].get('ImageProps', {}) or {}
                    pool = img_props.get('before_after', {}) or {}
                    before_map = pool.get('before') or {}
                    after_map = pool.get('after') or {}
                    before_list = [v for v in before_map.values() if isinstance(v, str) and v.strip()]
                    after_list = [v for v in after_map.values() if isinstance(v, str) and v.strip()]
                    if before_list and after_list:
                        # Gather service hints from services for context
                        try:
                            res_names = [s.get('name') for s in self.services.get('residential', []) if s.get('name')]
                            com_names = [s.get('name') for s in self.services.get('commercial', []) if s.get('name')]
                            hints = [*res_names, *com_names]
                        except Exception:
                            hints = []
                        # Sample 6 pairs
                        picks = []
                        tries = 0
                        import random as _rnd
                        while len(picks) < 6 and tries < 64:
                            tries += 1
                            b = _rnd.choice(before_list)
                            a = _rnd.choice(after_list)
                            hint = _rnd.choice(hints) if hints else 'Roofing Service'
                            picks.append({
                                'serviceHint': hint,
                                'before': f"BEFORE — Roofing service context: {hint}. Photorealistic, clean composition, no watermark, natural lighting, realistic materials. {b}",
                                'after': f"AFTER — Roofing service context: {hint}. Photorealistic, clean composition, no watermark, natural lighting, realistic materials. {a}"
                            })
                        # Validate via LLM (best-effort)
                        try:
                            prompt = (
                                "You are a roofing content QA assistant. Given 6 before/after prompt pairs, "
                                "edit any pairs that do not align with common roofing services. Keep concise. "
                                "Return ONLY JSON with key 'pairs' as an array of 6 objects like: "
                                "{\"serviceHint\": string, \"before\": string, \"after\": string}."
                            )
                            payload = { 'pairs': picks }
                            resp = call_openai_chat(prompt + "\n\n" + json.dumps(payload))
                            if '{' in resp and '}' in resp:
                                js = resp[resp.find('{'):resp.rfind('}')+1]
                                parsed = json.loads(js)
                                pairs = parsed.get('pairs')
                                if isinstance(pairs, list) and len(pairs) == 6:
                                    picks = pairs
                        except Exception:
                            pass
                        # Write back to ImageProps
                        img_props.setdefault('before_after', {})['selected'] = picks
                        ba_block['config']['ImageProps'] = img_props
            except Exception as e:
                logger.warning(f"Failed to seed BeforeAfterBlock selected variants: {e}")

            # Update BookingBlock Content: include select social links (website, facebook, instagram, yelp, google)
            booking_block = find_block(main_blocks, 'BookingBlock')
            if booking_block and isinstance(booking_block.get('config'), dict):
                bk_content = booking_block['config'].get('Content', {})
                # Preserve contactEmail if provided via STDIN/template; do not auto-generate
                try:
                    if isinstance(self._stdin, dict):
                        incoming_email = (
                            (self._stdin.get('booking') or {}).get('Content', {}).get('contactEmail')
                            if isinstance(self._stdin.get('booking'), dict) else None
                        )
                        if isinstance(incoming_email, str):
                            bk_content['contactEmail'] = incoming_email.strip()
                except Exception:
                    pass
                # Set logo to enhanced grayscale if provided (memory-only usage is allowed)
                try:
                    if self.gray_logo_url:
                        bk_content['logo'] = self.gray_logo_url
                except Exception:
                    pass
                socials_out = []
                # preserve order: website, google, yelp, facebook, instagram, linkedin, youtube, tiktok
                order = ['website','google','yelp','facebook','instagram','linkedin','youtube','tiktok']
                for key in order:
                    url = self.social_links.get(key)
                    if url:
                        socials_out.append({ 'network': key, 'url': url })
                if socials_out:
                    bk_content['socialLinks'] = socials_out
                booking_block['config']['Content'] = bk_content

                # Apply image selections mapping to template paths
                try:
                    selections = self.image_selections or {}
                    # Map → BasicMapBlock: 1 image max, use as statsBackgroundImage if provided. Use gray logo for markerIcon if provided
                    bm_block = find_block(main_blocks, 'BasicMapBlock')
                    if bm_block and isinstance(bm_block.get('config'), dict):
                        bm_design = bm_block['config'].get('Design', {})
                        # markerIcon from gray logo if present (memory-first: set data URL or direct URL)
                        if self.gray_logo_url:
                            try:
                                # Attempt persistence only if download/copy succeeds; otherwise fall back to direct URL
                                marker_ext = self._ext_from_url_or_default(self.gray_logo_url, '.png')
                                marker_rel = self.main_page_img_dir / 'BasicMapBlock' / f'logo_gray{marker_ext}'
                                persisted = self._download_or_copy_image(self.gray_logo_url, marker_rel)
                                if persisted:
                                    bm_design.setdefault('Map', {})['markerIcon'] = f"/data/generation/webgen/img/main_page_images/BasicMapBlock/{marker_rel.name}"
                                else:
                                    bm_design.setdefault('Map', {})['markerIcon'] = self.gray_logo_url
                            except Exception:
                                bm_design.setdefault('Map', {})['markerIcon'] = self.gray_logo_url
                        # stats background from selection
                        sel_map = selections.get('map') if isinstance(selections.get('map'), list) else []
                        if sel_map:
                            src = sel_map[0]
                            ext = self._ext_from_url_or_default(src, '.jpg')
                            dest = self.main_page_img_dir / 'BasicMapBlock' / f'stats_background{ext}'
                            if self._download_or_copy_image(src, dest):
                                bm_design.setdefault('Map', {})['statsBackgroundImage'] = f"/data/generation/webgen/img/main_page_images/BasicMapBlock/{dest.name}"
                        bm_block['config']['Design'] = bm_design
                    # RichTextBlock → showcase: use up to 3 from richText selection; do not overwrite cardImages
                    rt_block = find_block(main_blocks, 'RichTextBlock')
                    if rt_block and isinstance(rt_block.get('config'), dict):
                        rt_content = rt_block['config'].get('Content', {})
                        sel_rt = selections.get('richText') if isinstance(selections.get('richText'), list) else []
                        if sel_rt:
                            # cap at 5 but use first 3 for showcase
                            chosen = sel_rt[:5]
                            showcase = chosen[:3]
                            persisted = []
                            for idx, url in enumerate(showcase):
                                ext = self._ext_from_url_or_default(url, '.jpg')
                                dest = self.main_page_img_dir / 'RichTextBlock' / 'showcase' / f'{idx+1}{ext}'
                                if self._download_or_copy_image(url, dest):
                                    persisted.append(f"/data/generation/webgen/img/main_page_images/RichTextBlock/showcase/{dest.name}")
                            if persisted:
                                rt_content['images'] = persisted
                        rt_block['config']['Content'] = rt_content
                    # ButtonBlock → first up to 13 images sequentially
                    btn_block = find_block(main_blocks, 'ButtonBlock')
                    if btn_block and isinstance(btn_block.get('config'), dict):
                        btn_content = btn_block['config'].get('Content', {})
                        sel_btn = selections.get('buttonBlock') if isinstance(selections.get('buttonBlock'), list) else []
                        if sel_btn:
                            persisted = []
                            for idx, url in enumerate(sel_btn[:13]):
                                ext = self._ext_from_url_or_default(url, '.jpg')
                                dest = self.main_page_img_dir / 'ButtonBlock' / f'i{idx+1}{ext}'
                                if self._download_or_copy_image(url, dest):
                                    persisted.append(f"/data/generation/webgen/img/main_page_images/ButtonBlock/{dest.name}")
                            if persisted:
                                btn_content['images'] = persisted
                        btn_block['config']['Content'] = btn_content
                    # EmployeesBlock → update names/roles from BBB (preserve images), then optionally map images from selections
                    emp_block = find_block(main_blocks, 'EmployeesBlock')
                    if emp_block and isinstance(emp_block.get('config'), dict):
                        emp_content = emp_block['config'].get('Content', {})
                        # AI-generated title
                        try:
                            if ai_emp_title:
                                emp_content['sectionTitle'] = ai_emp_title
                        except Exception:
                            pass
                        try:
                            employees = emp_content.get('employees') if isinstance(emp_content.get('employees'), list) else []
                            bbb_names_roles = []
                            if isinstance(self.bbb_profile, dict):
                                for i in range(1, 11):
                                    n = self.bbb_profile.get(f'Employee_{i}_name')
                                    r = self.bbb_profile.get(f'Employee_{i}_role')
                                    if n and isinstance(n, str) and n.strip():
                                        bbb_names_roles.append({ 'name': n.strip(), 'role': (r or '').strip() })
                            if not bbb_names_roles and isinstance(self.bbb_profile.get('employee_names'), list):
                                # If no existing employees, still allow reading up to 10 from list
                                fallback_count = 10 if not isinstance(employees, list) or len(employees) == 0 else len(employees)
                                # Dedupe raw names before mapping
                                deduped_names = self._dedupe_name_strings(self.bbb_profile['employee_names'])[:fallback_count]
                                for entry in deduped_names:
                                    if isinstance(entry, str) and entry.strip():
                                        parts = entry.split(',', 1)
                                        bbb_names_roles.append({ 'name': parts[0].strip(), 'role': (parts[1].strip() if len(parts) > 1 else '') })
                            # Dedupe final name/role pairs and cap at 9
                            bbb_names_roles = self._dedupe_name_role_pairs(bbb_names_roles)[:9]
                            if bbb_names_roles:
                                count = min(len(bbb_names_roles), 9)
                                updated = []
                                for idx in range(count):
                                    existing = employees[idx] if idx < len(employees) and isinstance(employees[idx], dict) else {}
                                    from_bbb = bbb_names_roles[idx]
                                    img_path = existing.get('image') or f"/personal/old/img/main_page_images/EmployeesBlock/{idx+1}.jpg"
                                    updated.append({
                                        'name': from_bbb.get('name') or existing.get('name') or '',
                                        'role': from_bbb.get('role') or existing.get('role') or '',
                                        'image': img_path
                                    })
                                emp_content['employees'] = updated
                        except Exception as e:
                            logger.warning(f"Employees mapping failed: {e}")
                        sel_emp = selections.get('employees') if isinstance(selections.get('employees'), list) else []
                        if sel_emp:
                            employees = emp_content.get('employees') if isinstance(emp_content.get('employees'), list) else []
                            for idx, url in enumerate(sel_emp[:10]):
                                ext = self._ext_from_url_or_default(url, '.png')
                                dest = self.main_page_img_dir / 'EmployeesBlock' / f'person_{idx+1}{ext}'
                                if self._download_or_copy_image(url, dest):
                                    rel = f"/data/generation/webgen/img/main_page_images/EmployeesBlock/{dest.name}"
                                    if idx < len(employees) and isinstance(employees[idx], dict):
                                        employees[idx]['image'] = rel
                            emp_content['employees'] = employees
                        emp_block['config']['Content'] = emp_content
                except Exception as e:
                    logger.warning(f"Image selections application failed: {e}")

            # Memory-only: do not save to disk; return data for stdout emission by caller
            logger.info("Combined data generation completed successfully (content-only updates)")
            return template_data
            
        except Exception as e:
            logger.error(f"Error generating combined data: {e}")
            raise

def main():
    """Main entry point for the script."""
    # Set up paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.dirname(script_dir)
    raw_data_dir = os.path.join(data_dir, "raw_data")
    
    # Input files from previous steps
    bbb_profile_path = os.path.join(raw_data_dir, "step_1", "bbb_profile_data.json")
    reviews_path = os.path.join(raw_data_dir, "step_2", "sentiment_reviews.json")
    insights_path = os.path.join(raw_data_dir, "step_2", "roofing_business_insights.json")
    
    # Ensure output directory exists
    output_dir = os.path.join(raw_data_dir, "step_4")
    os.makedirs(output_dir, exist_ok=True)
    
    # Read clipped logo from step_3
    clipped_logo_path = os.path.join(raw_data_dir, "step_3", "clipped.png")
    if not os.path.exists(clipped_logo_path):
        # Try the root raw_data directory as fallback
        clipped_logo_path = os.path.join(raw_data_dir, "clipped.png")
        
    logger.info(f"Using bbb_profile_path: {bbb_profile_path}")
    logger.info(f"Using reviews_path: {reviews_path}")
    logger.info(f"Using insights_path: {insights_path}")
    logger.info(f"Using clipped_logo_path: {clipped_logo_path}")
    
    # Yelp scrape file from step_2 (individual pipeline) — optional
    # Prefer the individual output if present
    yelp_path_candidate_1 = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))),
        "data",
        "output",
        "individual",
        "step_2",
        "yelp_scrape.json",
    )
    # Alternate location (repo-wide step_2)
    yelp_path_candidate_2 = os.path.join(raw_data_dir, "step_2", "yelp_scrape.json")
    yelp_path = None
    if os.path.exists(yelp_path_candidate_1):
        yelp_path = yelp_path_candidate_1
    elif os.path.exists(yelp_path_candidate_2):
        yelp_path = yelp_path_candidate_2

    # Template path: use dedicated combined_template.json under public/personal/old/jsons
    public_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(script_dir))))
    template_path = os.path.join(public_dir, "personal", "old", "jsons", "combined_template.json")

    # Read optional memory-only payload from STDIN
    stdin_payload: Dict[str, Any] = {}
    try:
        raw = sys.stdin.read()
        if raw and raw.strip():
            stdin_payload = json.loads(raw)
            logger.info('[Combined] Loaded input from STDIN')
    except Exception as e:
        logger.warning(f'[Combined] Failed to read STDIN payload: {e}')

    # Initialize and run the generator (prefer memory payloads when provided)
    generator = CombinedDataGenerator(
        bbb_profile_path=bbb_profile_path,
        reviews_path=reviews_path,
        insights_path=insights_path,
        yelp_path=yelp_path,
        template_path=template_path,
        stdin_payload=stdin_payload
    )
    
    # Set the output file to be in the step_4 directory
    generator.output_file = os.path.join(output_dir, "combined_data.json")
    
    # Run the generation process
    try:
        logger.info(f"[Combined] OpenAI key present: {bool(os.getenv('OPENAI_API_KEY'))}")
    except Exception:
        pass
    result = generator.generate()
    # Emit markers for backend parser
    try:
        print('COMBINED_JSON_START')
        print(_json.dumps(result, ensure_ascii=False))
        print('COMBINED_JSON_END')
    except Exception as e:
        logger.error(f"Failed to emit combined JSON markers: {e}")
    
if __name__ == "__main__":
    main()