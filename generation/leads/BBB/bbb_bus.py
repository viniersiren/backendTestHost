import logging
import time
import random
import json
import pandas as pd
import urllib.parse
import os

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

##############################################################################
# 1) WEB DRIVER INIT
##############################################################################
def web_driver(headless=True):
    """
    Initializes and returns a Selenium WebDriver with specified options.
    """
    options = Options()
    
    if headless:
        options.add_argument("--headless=new")  # Run headless if desired
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-infobars")
    options.add_argument("--incognito")  # Private mode
    options.add_argument("--no-sandbox")
    
    # Optionally disable images:
    prefs = {"profile.managed_default_content_settings.images": 2}
    options.add_experimental_option("prefs", prefs)
    
    # Set a common user agent
    user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/113.0.5672.63 Safari/537.36"
    )
    options.add_argument(f"user-agent={user_agent}")
    
    # Stealth
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )
    # Additional stealth measure
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    
    # Optional: Maximize window for better scrolling
    driver.maximize_window()
    
    return driver

##############################################################################
# 2) SCROLLING FUNCTION
##############################################################################
def scroll_to_load(driver, max_scroll_attempts=10, scroll_pause_time=1):
    """
    Scrolls to the bottom of the page up to 'max_scroll_attempts' times,
    waiting 'scroll_pause_time' seconds in between. Stops if no new content
    loads. Logs every scroll attempt.
    """
    last_height = driver.execute_script("return document.body.scrollHeight")
    scroll_attempts = 0

    while scroll_attempts < max_scroll_attempts:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        logging.info(f"Scrolled to bottom. Attempt {scroll_attempts + 1} of {max_scroll_attempts}.")
        time.sleep(scroll_pause_time)

        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            logging.info("No more content to load or page height hasn't changed.")
            break
        last_height = new_height
        scroll_attempts += 1

    if scroll_attempts == max_scroll_attempts:
        logging.warning("Reached maximum scroll attempts without loading all content.")

##############################################################################
# 3) SCRAPE BBB LISTINGS (Pulling only FIRST non‐ad .card.result-card)
##############################################################################
def scrape_bbb_listings(
    driver,
    business_name="",
    near_location="",
    max_listings=3
):
    """
    - Constructs a BBB search URL with given business name and location.
    - Navigates directly to that search URL (no need to type into search fields).
    - Waits for 'main.page-content' and then 'div.not-sidebar.stack' container.
    - Scrolls to load more results.
    - Locates 'div.stack.stack-space-20', then picks only the FIRST child 
      '.card.result-card' that does NOT reside in an '.ad-slot'.
    - Returns that single listing's data in a dictionary.
    """
    collected_data = {
        "BBB_bus": [],
        "BBB_url": [],
        "BBB_phone": [],
        "BBB_address": []
    }
    # Base URL for BBB search
    base_url = "https://www.bbb.org/search"
    
    # Construct search parameters
    params = {
        "find_country": "USA",
        "find_text": business_name,
        "find_loc": near_location,
        "page": "1"
    }
    # Encode parameters
    query_string = urllib.parse.urlencode(params)
    search_url = f"{base_url}?{query_string}"
    
    ########################################################################
    # STEP 1: NAVIGATE TO SEARCH URL
    ########################################################################
    logging.info(f"[STEP 1] Navigating to search URL: {search_url}")
    driver.get(search_url)
    
    ########################################################################
    # STEP 2: WAIT FOR <body> / PAGE CONTENT
    ########################################################################
    logging.info("[STEP 2] Waiting for <body> to load.")
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        logging.info("<body> loaded successfully.")
    except Exception as e:
        logging.error(f"<body> did not load properly within 10 seconds: {e}")
        return collected_data
    
    ########################################################################
    # STEP 3: WAIT FOR SEARCH RESULTS IN 'main.page-content'
    ########################################################################
    logging.info("[STEP 3] Waiting for main.page-content to be present.")
    try:
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "main.page-content"))
        )
        logging.info("Found main.page-content container.")
    except Exception as e:
        logging.error(f"Search results not found or timed out after 5 seconds: {e}")
        raise Exception("TIMEOUT_OR_NOT_FOUND_ERROR")
    
    ########################################################################
    # STEP 4: WAIT FOR AND FIND 'div.not-sidebar.stack' (the container)
    ########################################################################
    logging.info("[STEP 4] Locating the 'div.not-sidebar.stack' container.")
    try:
        container = WebDriverWait(driver, 7).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.not-sidebar.stack"))
        )
        logging.info("Successfully found 'div.not-sidebar.stack' container for results.")
    except Exception as e:
        # This often indicates "no match" for the business
        logging.error(f"Could not locate 'div.not-sidebar.stack' container: {e}")
        return collected_data
    
    ########################################################################
    # STEP 5: SCROLL TO LOAD MORE RESULTS IF NEEDED
    ########################################################################
    logging.info("[STEP 5] Attempting to scroll the entire window to load more results if necessary.")
    try:
        scroll_to_load(driver, max_scroll_attempts=10, scroll_pause_time=2)
    except Exception as e:
        logging.warning(f"Scrolling encountered an issue or is not necessary: {e}")
    
    ########################################################################
    # STEP 6: EXTRACT ONLY THE FIRST NON-AD 'div.card.result-card'
    #         INSIDE "div.stack.stack-space-20" (skipping 'ad-slot').
    ########################################################################
    logging.info("[STEP 6] Searching for the first non-ad card inside 'div.stack.stack-space-20'.")

    # 1) Locate the parent container with class "stack stack-space-20"
    try:
        stack_space_20 = container.find_element(By.CSS_SELECTOR, "div.stack.stack-space-20")
    except Exception as e:
        logging.error(f"Could not locate div.stack.stack-space-20: {e}")
        return collected_data

    # 2) Within that container, locate only direct <div> children
    #    that have class 'card result-card' and are NOT in 'ad-slot'.
    #    We'll use an XPath that excludes "ad-slot" and includes only "card result-card":
    non_ad_cards = stack_space_20.find_elements(
        By.XPATH,
        "./div[not(contains(@class,'ad-slot')) and contains(@class,'card') and contains(@class,'result-card')]"
    )

    logging.info(f"Found {len(non_ad_cards)} non-ad .card.result-card elements under 'stack stack-space-20'.")

    # If there's at least one non‐ad card, scrape only the FIRST one:
    if len(non_ad_cards) > 0:
        card = non_ad_cards[0]  # The first non-ad result
        logging.info("Extracting data from the FIRST non-ad card.")

        try:
            # Extract Business Name
            h3_name = card.find_element(By.CLASS_NAME, "result-business-name")
            b_name_element = h3_name.find_element(By.TAG_NAME, "a")
            b_name = b_name_element.text.strip()
            
            # Extract BBB URL
            b_url = b_name_element.get_attribute("href").strip()
            
            # Extract Phone Number
            try:
                phone_link = card.find_element(By.CSS_SELECTOR, "a[href^='tel:']")
                b_phone = phone_link.text.strip()
            except Exception:
                b_phone = "N/A"
            
            # Extract Address
            try:
                addr_tag = card.find_element(By.CSS_SELECTOR, "p.bds-body.text-size-5.text-gray-70")
                full_address = addr_tag.text.strip()
            except Exception:
                full_address = "N/A"

            # Store in our dictionary
            collected_data["BBB_bus"].append(b_name)
            collected_data["BBB_url"].append(b_url)
            collected_data["BBB_phone"].append(b_phone)
            collected_data["BBB_address"].append(full_address)

            logging.info(f"  Business Name: {b_name}")
            logging.info(f"  BBB URL: {b_url}")
            logging.info(f"  Phone: {b_phone}")
            logging.info(f"  Address: {full_address}")

        except Exception as e:
            logging.error(f"Error extracting data from the first non-ad card: {e}")
    else:
        logging.info("No non-ad result-card found to extract.")
    
    return collected_data

##############################################################################
# 4) MAIN EXECUTION
##############################################################################
if __name__ == "__main__":
    # -----------------------------------------------------------------------
    # LOGGING SETUP
    # -----------------------------------------------------------------------
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    # Define paths
    input_json_path = 'public/data/output/leads/raw/google_filter.json'
    output_dir = 'public/data/output/leads/raw'
    output_json_path = os.path.join(output_dir, 'bbb_match.json')
    
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    
    # -----------------------------------------------------------------------
    # INITIALIZE WEBDRIVER
    # -----------------------------------------------------------------------
    driver = web_driver(headless=False)

    try:
        # -------------------------------------------------------------------
        # SCRAPE FROM google_filter.json
        # -------------------------------------------------------------------
        
        logging.info(f"Reading input JSON: {input_json_path}")
        try:
            with open(input_json_path, 'r', encoding='utf-8') as f:
                input_data = json.load(f)
        except FileNotFoundError:
            logging.error(f"The file {input_json_path} does not exist.")
            input_data = []
        
        all_scraped_data = []
        
        # Iterate over each entry in the input JSON
        for entry in input_data:
            business_to_find = str(entry.get("BusinessName", "")).strip()
            search_term = str(entry.get("Location", "")).strip()
            
            if not business_to_find or not search_term:
                logging.warning(f"Entry is missing 'BusinessName' or 'Location'. Skipping: {entry}")
                continue
            
            logging.info(f"=== Searching BBB for '{business_to_find}' near '{search_term}' ===")
            
            try:
                results = scrape_bbb_listings(
                    driver,
                    business_name=business_to_find,
                    near_location=search_term,
                    max_listings=1
                )
            except Exception as e:
                if "TIMEOUT_OR_NOT_FOUND_ERROR" in str(e):
                    logging.info("Encountered TIMEOUT_OR_NOT_FOUND_ERROR. Reopening browser.")
                    driver.quit()
                    driver = web_driver(headless=False)

                    entry["BBB_bus"] = "N/A"
                    entry["BBB_url"] = "N/A"
                    entry["BBB_phone"] = "N/A"
                    entry["BBB_address"] = "N/A"

                    all_scraped_data.append(entry)
                    continue
                else:
                    logging.error(f"Unexpected error for entry {entry}: {e}")
                    continue
            
            if results["BBB_bus"]:
                entry["BBB_bus"] = "; ".join(results["BBB_bus"])
                entry["BBB_url"] = "; ".join(results["BBB_url"])
                entry["BBB_phone"] = "; ".join(results["BBB_phone"])
                entry["BBB_address"] = "; ".join(results["BBB_address"])
            else:
                entry["BBB_bus"] = "N/A"
                entry["BBB_url"] = "N/A"
                entry["BBB_phone"] = "N/A"
                entry["BBB_address"] = "N/A"

            all_scraped_data.append(entry)
            
            delay = random.uniform(2, 4)
            logging.info(f"Sleeping for {delay:.2f} seconds before next search.")
            time.sleep(delay)
        
    except (Exception, KeyboardInterrupt) as exc:
        logging.error(f"Error or interruption in main execution: {exc}")
    
    finally:
        # Quit the driver if it exists
        if 'driver' in locals() and driver:
            driver.quit()
            logging.info("Browser closed.")

        # Save any collected data
        if all_scraped_data:
            with open(output_json_path, 'w', encoding='utf-8') as json_file:
                json.dump(all_scraped_data, json_file, indent=2)
            logging.info(f"Saved all scraped data to {output_json_path}.")

            print("\nFINAL SCRAPED RESULTS:")
            print(json.dumps(all_scraped_data, indent=2))
        else:
            logging.info("No data was collected to save.")
        
        logging.info("Script finished.")
