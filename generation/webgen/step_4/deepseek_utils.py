#!/usr/bin/env python3

import os
import requests
import json
import logging
import time
import random
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment variables from .env.deepseek file
env_path = Path(__file__).parent.parent / ".env.deepseek"
load_dotenv(env_path)

# Fallback text for testing when API key is not available
FALLBACK_TEXTS = [
    """{"description1": "Cowboys-Vaqueros Construction has earned a stellar reputation for high-quality roofing solutions throughout Georgia. With over 11 years of industry experience, our team of licensed professionals specializes in both residential and commercial projects, delivering exceptional results every time.", "description2": "What sets us apart is our unwavering commitment to customer satisfaction and attention to detail. We use only premium materials backed by comprehensive warranties, ensuring your roof not only looks great but provides lasting protection for your home or business.", "cards": [{"title": "Expert Craftsmanship", "desc": "Our skilled team brings years of specialized training to every project, ensuring precision installation and repairs that stand the test of time.", "icon": "Tools"}, {"title": "Quality Materials", "desc": "We partner with top manufacturers to provide superior roofing products backed by industry-leading warranties for your peace of mind.", "icon": "Shield"}, {"title": "Customer Service", "desc": "From initial consultation to project completion, we prioritize clear communication and exceptional service at every step.", "icon": "HeartHandshake"}, {"title": "BBB Accredited", "desc": "Our A+ Better Business Bureau rating reflects our commitment to ethical practices and outstanding customer satisfaction.", "icon": "Certificate"}]}""",
    """{"description1": "At Cowboys-Vaqueros Construction, we bring over a decade of roofing expertise to homes and businesses across Georgia. Our skilled team specializes in comprehensive roofing solutions, from minor repairs to complete installations, all delivered with exceptional craftsmanship and attention to detail.", "description2": "We understand that your roof is one of your property's most critical components. That's why we use only premium materials and proven techniques, backed by extensive warranties and our personal guarantee of satisfaction on every project we complete.", "cards": [{"title": "Certified Team", "desc": "Our technicians undergo rigorous training and certification, ensuring they stay current with the latest roofing technologies and safety protocols.", "icon": "GraduationCap"}, {"title": "Fast Response", "desc": "We provide prompt service for both scheduled maintenance and emergency situations, minimizing disruption to your home or business.", "icon": "Clock"}, {"title": "BBB Accredited", "desc": "Our accreditation with the Better Business Bureau demonstrates our commitment to resolving customer concerns and maintaining high standards.", "icon": "Certificate"}, {"title": "Comprehensive Service", "desc": "From initial inspection to final installation, we handle every aspect of your roofing project with professional care and expertise.", "icon": "Tools"}]}"""
]

def query_deepseek_api(prompt: str) -> str:
    """
    Query the DeepSeek API with a prompt.
    
    Args:
        prompt (str): The prompt to send to the API.
        
    Returns:
        str: The API response text or a fallback text if API call fails.
    """
    api_key = os.getenv('DEEPSEEK_API_KEY')
    if not api_key:
        logger.warning("No DeepSeek API key found. Using fallback text.")
        return _get_fallback_response(prompt)
        
    api_url = "https://api.deepseek.com/v1/chat/completions"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    data = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 1000
    }
    
    try:
        logger.info("Sending request to DeepSeek API")
        response = requests.post(api_url, headers=headers, json=data)
        response.raise_for_status()
        
        result = response.json()
        if "choices" in result and len(result["choices"]) > 0:
            logger.info("Received successful response from DeepSeek API")
            return result["choices"][0]["message"]["content"]
        else:
            logger.error(f"Unexpected API response format: {result}")
            return _get_fallback_response(prompt)
            
    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {str(e)}")
        return _get_fallback_response(prompt)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse API response: {str(e)}")
        return _get_fallback_response(prompt)
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return _get_fallback_response(prompt)

def _get_fallback_response(prompt: str) -> str:
    """Generate a fallback response when the API is unavailable."""
    # Business description fallbacks
    if "roofing business name" in prompt.lower() and "split" in prompt.lower():
        return """{"shouldSplit": true, "mainTitle": "COWBOYS-VAQUEROS", "subTitle": "CONSTRUCTION"}"""
    
    # Rich text fallbacks
    if "create rich text content" in prompt.lower():
        return """{"description1": "Cowboys-Vaqueros Construction has earned a stellar reputation for high-quality roofing solutions throughout Georgia. With over 11 years of industry experience, our team of licensed professionals specializes in both residential and commercial projects, delivering exceptional results every time.", "description2": "What sets us apart is our unwavering commitment to customer satisfaction and attention to detail. We use only premium materials backed by comprehensive warranties, ensuring your roof not only looks great but provides lasting protection for your home or business.", "cards": [{"title": "Expert Craftsmanship", "desc": "Our skilled team brings years of specialized training to every project, ensuring precision installation and repairs that stand the test of time.", "icon": "Tools"}, {"title": "Quality Materials", "desc": "We partner with top manufacturers to provide superior roofing products backed by industry-leading warranties for your peace of mind.", "icon": "Shield"}, {"title": "Customer Service", "desc": "From initial consultation to project completion, we prioritize clear communication and exceptional service at every step.", "icon": "HeartHandshake"}, {"title": "BBB Accredited", "desc": "Our A+ Better Business Bureau rating reflects our commitment to ethical practices and outstanding customer satisfaction.", "icon": "Certificate"}]}"""
    
    # Service categorization fallbacks
    if "categorize these into residential and commercial services" in prompt.lower():
        return """{"residential": ["Roof Repair", "Shingling", "Ventilation", "Siding"], "commercial": ["Metal Roof", "Coating", "Single Ply", "Built Up"]}"""
    
    # Card replacement fallbacks
    if "which card (by number) should be replaced" in prompt.lower():
        return "3"
    
    # Geocoordinates fallbacks
    if "latitude and longitude coordinates" in prompt.lower():
        return """{"lat": 33.3365, "lng": -84.6472}"""
    
    # Generic fallback for other prompts
    return """{"response": "This is a fallback response as the DeepSeek API is currently unavailable."}""" 