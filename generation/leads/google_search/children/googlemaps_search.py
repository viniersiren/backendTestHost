import argparse
import logging
import time
import random
import json
import os
import sys

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException

##############################################################################
# 1) WEB DRIVER INIT (User's preferred version)
##############################################################################
def web_driver(headless=False):
    """
    Initializes and returns a Selenium WebDriver with specified options.
    """
    options = Options()
    # options.binary_location = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-infobars")
    options.add_argument("--incognito")
    options.add_argument("--no-sandbox")
    
    prefs = {"profile.managed_default_content_settings.images": 2}
    options.add_experimental_option("prefs", prefs)
    
    user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/113.0.5672.63 Safari/537.36"
    )
    options.add_argument(f"user-agent={user_agent}")
    
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    return driver

##############################################################################
# 2) SCRAPE GOOGLE MAPS LISTINGS (User's preferred version)
##############################################################################
def scrape_google_maps_listings(driver, search_term="", max_listings=50, scraped_business_names=None):
    """
    Performs a search in the already-open Google Maps tab and scrapes listings.
    Ensures no listing is skipped, even if some fields are missing.
    """
    businesses_data = []
    if scraped_business_names is None:
        scraped_business_names = set()

    # 1) WAIT FOR PAGE BODY (important for single-page app navigation)
    try:
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "body.LoJzbe"))
        )
    except TimeoutException:
        logging.error("Main page body did not load or class changed. Trying to refresh.")
        driver.refresh()
        time.sleep(5)

    ########################################################################
    # 2) USE STICKY SEARCH BAR & ENTER SEARCH TERM
    ########################################################################
    try:
        logging.info(f"Attempting to find the search bar and enter: '{search_term}'")
        search_input = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "input.searchboxinput.xiQnY"))
        )
        search_input.clear()
        search_input.send_keys(search_term)
        
        search_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button#searchbox-searchbutton"))
        )
        search_button.click()
        logging.info(f"Clicked search for '{search_term}'.")
        
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, '//div[@role="feed"]'))
        )
        logging.info("Search results feed loaded.")
        time.sleep(5) 
    except Exception as e:
        logging.error(f"Could not locate the sticky search bar or button for term '{search_term}'. Error: {e}")
        return businesses_data

    ########################################################################
    # 3) LOCATE THE LISTINGS CONTAINER AND SCROLL
    ########################################################################
    try:
        listings_container = driver.find_element(By.XPATH, '//div[@role="feed"]')
        logging.info("Starting to scroll through the listings container...")
        
        # Force-to-bottom continuous scroll until explicit end-of-list banner appears
        last_height = driver.execute_script("return arguments[0].scrollHeight;", listings_container)
        started_at = time.time()

        while True:
            driver.execute_script("arguments[0].scrollTo(0, arguments[0].scrollHeight);", listings_container)
            time.sleep(1.0)
            
            # Re-acquire the feed container in case of re-render
            try:
                listings_container = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.XPATH, '//div[@role="feed"]'))
                )
            except Exception:
                try:
                    listings_container = driver.find_element(By.XPATH, '//div[@role="feed"]')
                except Exception:
                    logging.info("Feed container not found after scroll; stopping.")
                    break

            # Stop only when Google Maps shows the explicit end-of-list banner
            try:
                if driver.find_element(By.XPATH, "//*[contains(text(), \"You've reached the end of the list.\")]" ).is_displayed():
                    logging.info("Reached the explicit 'end of the list' marker.")
                    break
            except Exception:
                pass

            # Track height change for visibility/logging (no longer used to stop)
            new_height = driver.execute_script("return arguments[0].scrollHeight;", listings_container)
            if new_height > last_height:
                last_height = new_height

            # Safety cap to avoid infinite loops (e.g., UI glitches)
            if time.time() - started_at > 180:
                logging.info("Scroll loop timed out after 180s; moving on.")
                break
    except Exception as e:
        logging.error(f"Error occurred during scrolling: {e}")
        return businesses_data

    ########################################################################
    # 4) GET FINAL PAGE SOURCE AND PARSE
    ########################################################################
    logging.info("Parsing final HTML after scroll.")
    page_source = driver.page_source
    soup = BeautifulSoup(page_source, "html.parser")
    
    div_feed = soup.find('div', role='feed')
    if not div_feed:
        logging.error("Could not find the main 'feed' div after scrolling.")
        return businesses_data

    child_divs = div_feed.find_all("div", recursive=False)
    logging.info(f"Found {len(child_divs)} direct child divs in the listing container.")

    for idx, listing_div in enumerate(child_divs, start=1):
        if len(businesses_data) >= max_listings:
            logging.info(f"Reached max desired listings: {max_listings}")
            break

        data = {
            "BusinessName": "N/A", "Rating": "N/A", "NumberOfReviews": "N/A", "Category": "N/A", 
            "Address": "N/A", "Phone": "N/A", "Close": "N/A", "Website": "N/A", "GoogleReviewsLink": "N/A"
        }

        try:
            business_name_tag = listing_div.find("div", class_="qBF1Pd fontHeadlineSmall")
            if business_name_tag:
                business_name = business_name_tag.get_text(strip=True)
                if business_name in scraped_business_names:
                    logging.info(f"Skipping already scraped business: {business_name}")
                    continue
                data["BusinessName"] = business_name

            rating_span = listing_div.find("span", class_="MW4etd")
            if rating_span: data["Rating"] = rating_span.get_text(strip=True)

            reviews_span = listing_div.find("span", class_="UY7F9")
            if reviews_span: data["NumberOfReviews"] = reviews_span.get_text(strip=True)
            
            website_link = listing_div.find("a", {"data-value": "Website"})
            if website_link and website_link.has_attr("href"):
                data["Website"] = website_link["href"]

            reviews_link_tag = listing_div.find("a", class_="hfpxzc")
            if reviews_link_tag and reviews_link_tag.has_attr("href"):
                data["GoogleReviewsLink"] = reviews_link_tag["href"]

            # General info parsing using the user's more specific logic - REVISED AND MORE ROBUST
            uaQhfb_div = listing_div.find("div", class_="UaQhfb fontBodyMedium")
            if uaQhfb_div:
                w4efsd_blocks = uaQhfb_div.find_all("div", class_="W4Efsd", recursive=False)
                
                if len(w4efsd_blocks) > 1:
                    info_block = w4efsd_blocks[1]
                    nested_info_divs = info_block.find_all("div", class_="W4Efsd", recursive=False)

                    # Category & Address Block
                    if len(nested_info_divs) > 0:
                        cat_addr_block = nested_info_divs[0]
                        # Get all text parts, separated by the '·' character
                        cat_addr_parts = cat_addr_block.get_text(separator='|').split('|')
                        
                        # Filter out empty strings that may result from splitting
                        cleaned_parts = [part.strip() for part in cat_addr_parts if part.strip() and part.strip() != '·']
                        
                        if cleaned_parts:
                            # Category is the first clean part
                            data["Category"] = cleaned_parts[0]
                            # Address is the last clean part
                            if len(cleaned_parts) > 1:
                                data["Address"] = cleaned_parts[-1]

                    # Phone & Close status Block
                    if len(nested_info_divs) > 1:
                        phone_close_block = nested_info_divs[1]
                        phone_close_parts = [s.get_text(strip=True) for s in phone_close_block.find_all("span") if s.get_text(strip=True) and s.get_text(strip=True) != '·']

                        for part in phone_close_parts:
                            if '(' in part and ')' in part:
                                data["Phone"] = part
                            elif 'Closed' in part or 'Open' in part:
                                data["Close"] = part

            if data["BusinessName"] != "N/A":
                businesses_data.append(data)
                scraped_business_names.add(data["BusinessName"])
                logging.info(f"Added listing {idx}: {data['BusinessName']}")
        
        except Exception as e:
            logging.error(f"Error processing listing index {idx}. Error: {e}")

    return businesses_data

def get_all_business_names(file_path):
    """Reads a JSON file and returns a set of business names to avoid duplicates."""
    if not os.path.exists(file_path):
        return set()
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, list):
            return {item['BusinessName'] for item in data if 'BusinessName' in item}
        return set()
    except (json.JSONDecodeError, FileNotFoundError):
        return set()

def get_all_business_names_from_by_zip(directory_path):
    """Aggregates BusinessName values from all {ZIP}.json files in by-zip directory."""
    names = set()
    if not directory_path or not os.path.isdir(directory_path):
        return names
    try:
        for name in os.listdir(directory_path):
            if not name.endswith('.json'):
                continue
            path = os.path.join(directory_path, name)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        bn = item.get('BusinessName') if isinstance(item, dict) else None
                        if bn:
                            names.add(bn)
            except Exception:
                continue
    except Exception:
        return names
    return names

def get_valid_zip_ranges_for_state(state_abbr):
    """Return a list of (start, end) tuples for valid ZIP ranges by state. None means no restriction."""
    st = (state_abbr or "").upper()
    if st == 'GA':
        return [(30000, 31999), (39800, 39999)]
    return None

def main(state_abbr, start_zip, end_zip):
    # ==========================================================================
    # LOGGING SETUP
    # ==========================================================================
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )

    # ==========================================================================
    # STATE MANAGEMENT SETUP
    # ==========================================================================
    tracker_file = os.path.join("public", "data", "output", "leads", "final", "scrapped_zips.json")
    output_dir = os.path.join("public", "data", "output", "leads", "raw")
    os.makedirs(output_dir, exist_ok=True)

    # Allow env override for per-worker output path
    output_json = os.environ.get("GGL_OUTPUT_JSON", os.path.join(output_dir, "google_search.json"))
    # Central by-zip output directory (preferred for parallel runs)
    output_by_zip_dir = os.environ.get("GGL_OUTPUT_BY_ZIP_DIR")
    if output_by_zip_dir:
        os.makedirs(output_by_zip_dir, exist_ok=True)
    
    # Optional: bypass tracker in parallel mode to avoid contention
    bypass_tracker = os.environ.get("GGL_TRACKER_BYPASS", "0") == "1"

    tracker_data = None
    state_info = None
    if not bypass_tracker:
        try:
            with open(tracker_file, 'r') as f:
                tracker_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            logging.error(f"Tracker file not found or corrupted at {tracker_file}. Exiting.")
            return
        
        state_info = next((item for item in tracker_data if item["abbreviation"] == state_abbr), None)
        if not state_info:
            logging.error(f"State abbreviation '{state_abbr}' not found in tracker file. Exiting.")
            return

    # Determine the actual start ZIP based on what's already been scraped
    actual_start_zip = start_zip
    if not bypass_tracker:
        last_scraped_zip = state_info.get("last_zip_scraped")
        if last_scraped_zip and last_scraped_zip != "N/A":
            last_scraped_num = int(last_scraped_zip)
            if last_scraped_num >= start_zip:
                actual_start_zip = last_scraped_num + 1
                logging.info(f"Last scraped ZIP was {last_scraped_num}, starting from {actual_start_zip}")
            else:
                logging.info(f"Last scraped ZIP was {last_scraped_num}, but requested start is {start_zip}, using requested start")
        else:
            logging.info(f"No previous scraping for {state_abbr}, starting from {actual_start_zip}")
    
    # Check if we're already past the end ZIP
    if actual_start_zip > end_zip:
        logging.info(f"All ZIPs in range {start_zip}-{end_zip} have already been scraped. Exiting.")
        return
    
    if state_info and not bypass_tracker:
        logging.info(f"Starting scrape for {state_info['name']} from ZIP {actual_start_zip} to {end_zip}.")
    else:
        logging.info(f"Starting scrape (tracker bypass={bypass_tracker}) for state {state_abbr} from ZIP {actual_start_zip} to {end_zip}.")

    # ==========================================================================
    # SINGLE BROWSER SESSION & SCRAPING LOOP
    # ==========================================================================
    driver = web_driver(headless=False)
    # Build a cross-run dedupe set sourced from existing outputs
    if output_by_zip_dir:
        scraped_business_names = get_all_business_names_from_by_zip(output_by_zip_dir)
        logging.info(f"By-zip output mode: loaded {len(scraped_business_names)} existing business names from {output_by_zip_dir}.")
    else:
        scraped_business_names = get_all_business_names(output_json)
        logging.info(f"Loaded {len(scraped_business_names)} existing business names from {output_json}.")

    # Track the highest ZIP we actually process
    highest_processed_zip = actual_start_zip - 1

    try:
        base_maps_url = "https://www.google.com/maps/place/Georgia/@32.6537678,-85.6926567,8z/data=!3m1!4b1!4m6!3m5!1s0x88f136c51d5f8157:0x6684bc10ec4f10e7!8m2!3d32.1574351!4d-82.907123!16zL20vMGQweDg?entry=ttu&g_ep=EgoyMDI1MDkxMC4wIKXMDSoASAFQAw%3D%3D"
        logging.info(f"Navigating to Google Maps once: {base_maps_url}")
        driver.get(base_maps_url)

        # Optional: allow explicit ZIP list for parallel partitioning
        zip_list_env = os.environ.get("GGL_ZIP_LIST")
        explicit_zips = None
        if zip_list_env:
            try:
                parsed = json.loads(zip_list_env)
                if isinstance(parsed, list):
                    explicit_zips = [int(z) for z in parsed]
            except Exception:
                try:
                    explicit_zips = [int(z.strip()) for z in zip_list_env.split(',') if z.strip()]
                except Exception:
                    explicit_zips = None

        valid_ranges = get_valid_zip_ranges_for_state(state_abbr)
        iterable_zips = explicit_zips if explicit_zips is not None else list(range(actual_start_zip, end_zip + 1))
        for zip_code in iterable_zips:
            # Skip ZIPs outside state-valid ranges (e.g., GA excludes 32000–39799)
            if valid_ranges and not any(rs <= zip_code <= re for (rs, re) in valid_ranges):
                continue
            term = f"Roofing {zip_code}, {state_abbr}"
            logging.info(f"\n{'='*20}\n=== Searching for: {term} ===\n{'='*20}")

            listings = scrape_google_maps_listings(
                driver=driver,
                search_term=term,
                max_listings=100,
                scraped_business_names=scraped_business_names
            )
            
            if listings:
                # Tag each listing with the industry and location before saving
                for biz in listings:
                    biz["Industry"] = "Roofing"
                    biz["Location"] = str(zip_code)

                if output_by_zip_dir:
                    # Merge with central per-zip file and dedupe by BusinessName
                    per_zip_path = os.path.join(output_by_zip_dir, f"{zip_code}.json")
                    existing = []
                    try:
                        if os.path.exists(per_zip_path):
                            with open(per_zip_path, 'r', encoding='utf-8') as f:
                                existing = json.load(f)
                    except json.JSONDecodeError:
                        logging.warning(f"Could not decode JSON from {per_zip_path}. Starting fresh for this ZIP.")
                        existing = []

                    names_seen = {item.get('BusinessName') for item in existing if isinstance(item, dict)}
                    new_items = [item for item in listings if item.get('BusinessName') not in names_seen]
                    if new_items:
                        existing.extend(new_items)
                        with open(per_zip_path, 'w', encoding='utf-8') as f:
                            json.dump(existing, f, ensure_ascii=False, indent=4)
                        logging.info(f"ZIP {zip_code}: saved {len(existing)} total listings to {per_zip_path} (added {len(new_items)}).")
                    else:
                        logging.info(f"ZIP {zip_code}: no new unique listings to add.")
                else:
                    # Legacy single-file mode
                    all_results = []
                    if os.path.exists(output_json):
                        with open(output_json, 'r', encoding='utf-8') as f:
                            try:
                                all_results = json.load(f)
                            except json.JSONDecodeError:
                                logging.warning(f"Could not decode JSON from {output_json}. Starting with a fresh list.")
                                all_results = []
                    
                    # Add new listings to the existing data
                    all_results.extend(listings)

                    # Write the combined data back to the JSON file
                    with open(output_json, 'w', encoding='utf-8') as f:
                        json.dump(all_results, f, ensure_ascii=False, indent=4)
                    
                    logging.info(f"Saved {len(all_results)} total listings to {output_json}")
            else:
                logging.info(f"No new listings found for {term}.")

            # Update the highest processed ZIP
            highest_processed_zip = zip_code
            
            time.sleep(random.uniform(2, 5))

    except (Exception, KeyboardInterrupt) as e:
        logging.error(f"An error or interruption occurred during scraping: {e}", exc_info=True)
        # Don't update the tracker file on error/interruption
        logging.info(f"Script interrupted. Last processed ZIP was {highest_processed_zip}")
    finally:
        if 'driver' in locals() and driver:
            driver.quit()
            logging.info("Closed the browser.")
        
        # Only update the tracker file if we successfully processed at least one ZIP
        if not bypass_tracker:
            if highest_processed_zip >= actual_start_zip:
                # Update the tracker file with the highest ZIP we actually processed
                state_info["last_zip_scraped"] = highest_processed_zip
                
                # Update first_zip_scraped if this is the first time scraping this state
                if state_info.get("first_zip_scraped") == "N/A" or not state_info.get("first_zip_scraped"):
                    state_info["first_zip_scraped"] = actual_start_zip
                
                try:
                    with open(tracker_file, 'w') as f:
                        json.dump(tracker_data, f, indent=4)
                    logging.info(f"Updated tracker file: {state_abbr} last_zip_scraped = {highest_processed_zip}")
                except Exception as e:
                    logging.error(f"Failed to update tracker file: {e}")
            else:
                logging.info("No ZIPs were processed, not updating tracker file.")
        
        logging.info("Scraping session finished.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape Google Maps for roofing companies by state and zip range.")
    parser.add_argument("state_abbr", type=str, help="The two-letter abbreviation for the state (e.g., GA).")
    parser.add_argument("start_zip", type=int, help="The starting zip code for the search range.")
    parser.add_argument("end_zip", type=int, help="The ending zip code for the search range.")
    args = parser.parse_args()

    main(args.state_abbr.upper(), args.start_zip, args.end_zip)
