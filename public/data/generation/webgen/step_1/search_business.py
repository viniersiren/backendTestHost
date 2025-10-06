import os
import json
import requests
from dotenv import load_dotenv
import logging
import argparse

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_google_search_results(api_key: str, search_engine_id: str, query: str):
    """
    Performs a Google search using the Custom Search JSON API.

    Args:
        api_key: Your Google API key.
        search_engine_id: Your Programmable Search Engine ID.
        query: The search query string.

    Returns:
        A dictionary containing the search results, or None if an error occurs.
    """
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        'key': api_key,
        'cx': search_engine_id,
        'q': query
    }

    try:
        logging.info(f"Performing search for query: '{query}'")
        response = requests.get(url, params=params)
        response.raise_for_status()  # Raise an exception for bad status codes
        return response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"An error occurred during the search request: {e}")
        if 'response' in locals() and 'error' in response.json():
            logging.error(f"API Error: {response.json()['error']['message']}")
        return None

def main():
    """
    Main function to load data, perform search, and save results.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('--business-name', dest='business_name', default=None)
    parser.add_argument('--business-address', dest='business_address', default=None)
    args = parser.parse_args()
    # --- Configuration ---
    # Define paths relative to the script's location
    script_dir = os.path.dirname(os.path.abspath(__file__))
    webgen_dir = os.path.dirname(script_dir)
    
    # Path to the .env file with API keys
    env_path = os.path.join(script_dir, 'google_api.env')
    
    # Path to the BBB profile data
    bbb_profile_path = os.path.join(webgen_dir, '../../output/individual/step_1/raw/bbb_profile_data.json')

    # Path for the output file
    output_dir = os.path.join(webgen_dir, '../../output/individual/step_1/raw/')
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, 'google_api_search.json')
    
    # --- Load API Keys and Business Data ---
    load_dotenv(dotenv_path=env_path)
    
    google_api_key = os.getenv("GOOGLE_SEARCH_API_KEY")
    search_engine_id = os.getenv("GOOGLE_SEARCH_ENGINE_ID")

    if not google_api_key:
        logging.error("Google API key not found in environment variables.")
        return

    if not search_engine_id:
        logging.error("Google Search Engine ID (cx) not found in environment variables.")
        logging.error("Please create a Programmable Search Engine at https://programmablesearchengine.google.com/ and add the ID to your .env file as GOOGLE_SEARCH_ENGINE_ID.")
        return

    business_data = {}
    if not args.business_name:
        try:
            with open(bbb_profile_path, 'r') as f:
                business_data = json.load(f)
        except FileNotFoundError:
            logging.warning(f"Business profile data not found at: {bbb_profile_path} (falling back to args)")
        except json.JSONDecodeError:
            logging.warning(f"Error decoding JSON from: {bbb_profile_path} (falling back to args)")

    business_name = args.business_name or business_data.get("business_name")
    business_address = args.business_address or business_data.get("address")

    if not business_name:
        logging.error("Business name not found in bbb_profile_data.json.")
        return

    # --- Perform Searches ---
    all_results = {"base_search": None, "social_media_search": {}}

    # 1. Original broad search for verification
    if business_address:
        logging.info("--- Performing Base Search ---")
        base_query = f'"{business_name}" {business_address}'
        base_search_results = get_google_search_results(google_api_key, search_engine_id, base_query)
        if base_search_results:
            all_results["base_search"] = base_search_results
    else:
        logging.warning("Business address not found, skipping base search.")

    # 2. Targeted search for social media profiles
    logging.info("\n--- Performing Social Media Search ---")
    social_media_sites = [
        "facebook.com",
        "instagram.com",
        "twitter.com",
        "linkedin.com",
        "yelp.com",
        "nextdoor.com",
        "homeadvisor.com",
        "angi.com",
        "yelp.com"
    ]
    
    social_media_results = {}
    for site in social_media_sites:
        search_query = f'"{business_name}" site:{site}'
        results = get_google_search_results(google_api_key, search_engine_id, search_query)
        # Only store results if items are found
        if results and results.get("items"):
            logging.info(f"Found results for {site}")
            social_media_results[site] = results
        else:
            logging.info(f"No results for {site}")

    all_results["social_media_search"] = social_media_results

    # --- Output (memory-only supported) ---
    memory_only = os.environ.get('MEMORY_ONLY', '0') == '1'
    if memory_only:
        print("WEBSEARCH_RESULTS_START")
        print(json.dumps(all_results))
        print("WEBSEARCH_RESULTS_END")
    else:
        if all_results["base_search"] or all_results["social_media_search"]:
            try:
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(all_results, f, ensure_ascii=False, indent=4)
                logging.info(f"All search results successfully saved to {output_path}")
            except IOError as e:
                logging.error(f"Error saving search results to file: {e}")

if __name__ == "__main__":
    main() 