import logging
import time
import random
import json
import os
import threading
import queue
import urllib.parse

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

##############################################################################
# WEB DRIVER INIT
##############################################################################
def web_driver(headless=False):
    """
    Initializes and returns a Selenium WebDriver with specified options.
    Each worker thread should create and own its WebDriver instance.
    """
    options = Options()
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
    options.add_experimental_option("useAutomationExtension", False)

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    try:
        driver.maximize_window()
    except Exception:
        pass
    return driver

##############################################################################
# SCROLLING FUNCTION
##############################################################################
def scroll_to_load(driver, max_scroll_attempts=10, scroll_pause_time=1):
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

##############################################################################
# SCRAPE BBB LISTINGS (FIRST non-ad result)
##############################################################################
def scrape_bbb_listings(driver, business_name="", near_location=""):
    collected_data = {
        "BBB_bus": [],
        "BBB_url": [],
        "BBB_phone": [],
        "BBB_address": []
    }

    base_url = "https://www.bbb.org/search"
    params = {
        "find_country": "USA",
        "find_text": business_name,
        "find_loc": near_location,
        "page": "1"
    }
    query_string = urllib.parse.urlencode(params)
    search_url = f"{base_url}?{query_string}"

    logging.info(f"[STEP 1] Navigating to search URL: {search_url}")
    driver.get(search_url)

    logging.info("[STEP 2] Waiting for <body> to load.")
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
    except Exception as e:
        logging.error(f"<body> did not load properly within 10 seconds: {e}")
        return collected_data

    logging.info("[STEP 3] Waiting for main.page-content to be present.")
    try:
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "main.page-content"))
        )
    except Exception as e:
        logging.error(f"Search results not found or timed out after 5 seconds: {e}")
        return collected_data

    logging.info("[STEP 4] Locating the 'div.not-sidebar.stack' container.")
    try:
        container = WebDriverWait(driver, 7).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.not-sidebar.stack"))
        )
    except Exception as e:
        logging.error(f"Could not locate 'div.not-sidebar.stack' container: {e}")
        return collected_data

    logging.info("[STEP 5] Attempting to scroll the entire window to load more results if necessary.")
    try:
        scroll_to_load(driver, max_scroll_attempts=10, scroll_pause_time=2)
    except Exception as e:
        logging.warning(f"Scrolling encountered an issue or is not necessary: {e}")

    logging.info("[STEP 6] Searching for the first non-ad card inside 'div.stack.stack-space-20'.")
    try:
        stack_space_20 = container.find_element(By.CSS_SELECTOR, "div.stack.stack-space-20")
    except Exception as e:
        logging.error(f"Could not locate div.stack.stack-space-20: {e}")
        return collected_data

    non_ad_cards = stack_space_20.find_elements(
        By.XPATH,
        "./div[not(contains(@class,'ad-slot')) and contains(@class,'card') and contains(@class,'result-card')]"
    )
    logging.info(f"Found {len(non_ad_cards)} non-ad .card.result-card elements under 'stack stack-space-20'.")

    if len(non_ad_cards) > 0:
        card = non_ad_cards[0]
        try:
            h3_name = card.find_element(By.CLASS_NAME, "result-business-name")
            b_name_element = h3_name.find_element(By.TAG_NAME, "a")
            b_name = b_name_element.text.strip()
            b_url = b_name_element.get_attribute("href").strip()

            try:
                phone_link = card.find_element(By.CSS_SELECTOR, "a[href^='tel:']")
                b_phone = phone_link.text.strip()
            except Exception:
                b_phone = "N/A"

            try:
                addr_tag = card.find_element(By.CSS_SELECTOR, "p.bds-body.text-size-5.text-gray-70")
                full_address = addr_tag.text.strip()
            except Exception:
                full_address = "N/A"

            collected_data["BBB_bus"].append(b_name)
            collected_data["BBB_url"].append(b_url)
            collected_data["BBB_phone"].append(b_phone)
            collected_data["BBB_address"].append(full_address)
        except Exception as e:
            logging.error(f"Error extracting data from the first non-ad card: {e}")
    else:
        logging.info("No non-ad result-card found to extract.")

    return collected_data

##############################################################################
# UTIL: Load existing final BBB URLs to skip
##############################################################################
def load_existing_final_bbb_urls(final_file_path):
    if not os.path.exists(final_file_path):
        return set()
    try:
        with open(final_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return {item.get('BBB_url') for item in data if item.get('BBB_url') and item.get('BBB_url') != 'N/A'}
    except Exception:
        return set()

def load_existing_business_names(*file_paths):
    names = set()
    for path in file_paths:
        try:
            if path and os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            name = item.get('BusinessName')
                            if name and name != 'N/A':
                                names.add(name.strip())
        except Exception:
            continue
    return names

##############################################################################
# WORKER THREAD FUNCTION
##############################################################################
def worker(task_queue, results_list, results_lock, headless=False):
    driver = None
    try:
        driver = web_driver(headless=headless)
        while True:
            try:
                entry = task_queue.get(timeout=2)
            except queue.Empty:
                break
            if entry is None:
                break

            business_to_find = str(entry.get("BusinessName", "")).strip()
            search_term = str(entry.get("Location", "")).strip()
            if not business_to_find or not search_term:
                task_queue.task_done()
                continue

            try:
                results = scrape_bbb_listings(
                    driver,
                    business_name=business_to_find,
                    near_location=search_term
                )
            except Exception as e:
                # Retry with fresh browser on timeout-like issues
                try:
                    if driver:
                        driver.quit()
                except Exception:
                    pass
                driver = web_driver(headless=headless)
                results = {"BBB_bus": [], "BBB_url": [], "BBB_phone": [], "BBB_address": []}

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

            with results_lock:
                results_list.append(entry)

            delay = random.uniform(1.5, 3.5)
            logging.info(f"[Worker] Sleeping for {delay:.2f}s before next search.")
            time.sleep(delay)

            task_queue.task_done()
    finally:
        try:
            if driver:
                driver.quit()
        except Exception:
            pass

##############################################################################
# MAIN
##############################################################################
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    # Paths
    input_json_path = 'public/data/output/leads/raw/google_filter.json'
    output_dir = 'public/data/output/leads/raw'
    # Write to a separate file to avoid interfering with current pipeline runs
    output_json_path = os.path.join(output_dir, 'bbb_match_parallel.json')
    final_file_path = 'public/data/output/leads/final/final_leads.json'

    os.makedirs(output_dir, exist_ok=True)

    # Load inputs
    try:
        with open(input_json_path, 'r', encoding='utf-8') as f:
            input_data = json.load(f)
    except FileNotFoundError:
        logging.error(f"The file {input_json_path} does not exist.")
        input_data = []
    except json.JSONDecodeError:
        logging.error(f"Could not decode JSON from {input_json_path}.")
        input_data = []

    # Skip entries already present in final leads (by BBB_url later; here by BusinessName as a prefilter)
    existing_bbb_urls = load_existing_final_bbb_urls(final_file_path)
    logging.info(f"Loaded {len(existing_bbb_urls)} existing BBB URLs from final leads for skip logic.")

    # Prepare queue and threading
    task_queue = queue.Queue()
    results = []
    results_lock = threading.Lock()

    # Enqueue tasks with duplicate-by-name skipping using existing raw/final outputs
    existing_raw_bbb_match = os.path.join(output_dir, 'bbb_match.json')
    existing_names = load_existing_business_names(existing_raw_bbb_match, output_json_path, final_file_path)
    enqueued_names = set()
    for entry in input_data:
        name = str(entry.get("BusinessName", "")).strip()
        if not name or name == 'N/A':
            continue
        if name in existing_names or name in enqueued_names:
            continue
        enqueued_names.add(name)
        task_queue.put(entry)

    # Start workers
    num_workers = 10
    threads = []
    for _ in range(num_workers):
        t = threading.Thread(target=worker, args=(task_queue, results, results_lock, False), daemon=True)
        t.start()
        threads.append(t)

    # Wait for all tasks
    task_queue.join()
    for _ in range(num_workers):
        task_queue.put(None)
    for t in threads:
        t.join()

    # Write results
    if results:
        with open(output_json_path, 'w', encoding='utf-8') as json_file:
            json.dump(results, json_file, indent=2)
        logging.info(f"Saved all scraped data to {output_json_path}.")
        print("\nFINAL SCRAPED RESULTS (parallel):")
        print(json.dumps(results, indent=2))
    else:
        logging.info("No data was collected to save.")

    logging.info("Parallel BBB script finished.")


