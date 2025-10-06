import logging
import json
import os
import shutil
import argparse
import sys
import subprocess
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import re
from urllib.parse import urljoin

# MEMORY_ONLY: Disable local output writes. Keep paths only for optional debugging.
RAW_DATA_DIR = "/Users/rhettburnham/Desktop/projects/roofing-co/public/data/output/individual/step_1/raw"
# os.makedirs(RAW_DATA_DIR, exist_ok=True)  # disabled: no local dirs needed for memory-only

def _get_macos_screen_bounds():
    try:
        out = subprocess.check_output([
            'osascript',
            '-e',
            'tell application "Finder" to get bounds of window of desktop'
        ], timeout=1.0)
        text = out.decode('utf-8').strip().replace('{', '').replace('}', '')
        parts = [int(p.strip()) for p in text.split(',')]
        if len(parts) == 4:
            return parts[0], parts[1], parts[2], parts[3]
    except Exception:
        pass
    return 0, 0, 1920, 1080

def _position_window_right_half(driver):
    try:
        left, top, right, bottom = _get_macos_screen_bounds()
        screen_width = max(0, right - left)
        screen_height = max(0, bottom - top)
        half_width = max(400, screen_width // 2)
        pos_x = left + (screen_width - half_width)
        pos_y = top
        driver.set_window_size(half_width, screen_height)
        driver.set_window_position(pos_x, pos_y)
    except Exception:
        pass

def web_driver(headless=False):
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    # Pre-launch size/position for macOS
    if not headless and sys.platform == 'darwin':
        left, top, right, bottom = _get_macos_screen_bounds()
        screen_width = max(0, right - left)
        screen_height = max(0, bottom - top)
        half_width = max(400, screen_width // 2)
        pos_x = left + (screen_width - half_width)
        pos_y = top
        options.add_argument(f"--window-position={pos_x},{pos_y}")
        options.add_argument(f"--window-size={half_width},{screen_height}")
    service = ChromeService()
    driver = webdriver.Chrome(service=service, options=options)
    if not headless and sys.platform == 'darwin':
        _position_window_right_half(driver)
    return driver

def download_image(url, filename):
    # This function needs to be implemented or replaced if not available.
    # For now, this is a placeholder.
    logging.warning("Image download function is not fully implemented.")
    return False

def scrape_bbb_profile(url, headless=True):
    logging.basicConfig(level=logging.INFO)
    driver = web_driver(headless=headless)
    bbb_data = {}

    try:
        logging.info(f"Navigating to URL: {url}")
        driver.get(url)

        # Wait for page to load and check for Cloudflare protection
        time.sleep(3)
        
        # Check if we're on a Cloudflare protection page
        page_source = driver.page_source
        if "Just a moment" in page_source or "Checking your browser" in page_source:
            logging.warning("Detected Cloudflare protection page. Waiting for it to resolve...")
            
            # Wait longer for Cloudflare to resolve
            time.sleep(10)
            
            # Try to scroll to trigger any remaining protection
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(5)
            
            # Get updated page source
            page_source = driver.page_source
            
            # Check again if we're still on protection page
            if "Just a moment" in page_source or "Checking your browser" in page_source:
                logging.error("Still on Cloudflare protection page after waiting. BBB may be blocking automated access.")
                # MEMORY_ONLY: Skip saving debug page to disk
                # debug_file = os.path.join(RAW_DATA_DIR, "cloudflare_debug.html")
                # with open(debug_file, "w", encoding="utf-8") as f:
                #     f.write(page_source)
                # logging.info(f"Saved debug page to: {debug_file}")
        
        # Scroll to the bottom of the page to load all content
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(5)  # Wait for lazy-loaded content

        # Get final page source
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, "html.parser")
        
        # MEMORY_ONLY: Skip saving page source debug to disk
        # debug_file = os.path.join(RAW_DATA_DIR, "bbb_page_debug.html")
        # with open(debug_file, "w", encoding="utf-8") as f:
        #     f.write(page_source)
        # logging.info(f"Saved page source to: {debug_file}")
        
        # Check if we got actual BBB content
        if "business profile" not in page_source.lower() and "bbb" not in page_source.lower():
            logging.error("Page doesn't appear to be a BBB business profile")
            logging.info(f"Page title: {driver.title}")
            logging.info(f"Page URL: {driver.current_url}")
            
            # Return fallback data if we can't access the real page
            logging.warning("Returning fallback data due to access issues")
            return {
                "business_name": "",
                "accredited": None,
                "accreditation_status": "Access Blocked",
                "date_of_accreditation": "",
                "website": "",
                "telephone": "",
                "address": "",
                "years_in_business": "",
                "logo_url": "",
                "logo_filename": "",
                "N_employees": "",
                "services": [],
                "Employee_1_name": "Access Blocked",
                "Employee_1_role": "Unable to scrape",
                "scraping_note": "BBB website blocked automated access. Try manual scraping or different approach."
            }

        # --- Extracting data using multiple selector strategies ---

        # business_name - try multiple selectors
        name_tag = None
        for selector in ["#businessName", "h1", ".business-name", "[data-testid='business-name']", "h1.business-name"]:
            name_tag = soup.select_one(selector)
            if name_tag:
                break
        
        bbb_data["business_name"] = name_tag.text.strip() if name_tag else ""
        logging.info(f"Found business name: {bbb_data['business_name']}")
        
        # accredited - try multiple approaches
        accreditation_text = ""
        for selector in ["#accreditation", ".accreditation", "[data-testid='accreditation']", ".accreditation-status"]:
            accreditation_div = soup.select_one(selector)
            if accreditation_div:
                accreditation_text = accreditation_div.text
                break
        
        # Also search in the entire page for accreditation info
        if not accreditation_text:
            page_text = soup.get_text().lower()
            if "not accredited" in page_text or "not a bbb accredited" in page_text:
                accreditation_text = "Not Accredited"
            elif "bbb accredited" in page_text and "not" not in page_text:
                accreditation_text = "Accredited"
        
        if "not accredited" in accreditation_text.lower():
            bbb_data["accredited"] = False
            bbb_data["accreditation_status"] = "Not Accredited"
        elif "bbb accredited" in accreditation_text.lower():
            bbb_data["accredited"] = True
            bbb_data["accreditation_status"] = "Accredited"
        else:
            bbb_data["accredited"] = None
            bbb_data["accreditation_status"] = "Not Found"
        
        logging.info(f"Accreditation status: {bbb_data['accreditation_status']}")

        # date_of_accreditation - try multiple selectors
        date_tag = None
        for selector in [
            "#content > div.page-vertical-padding.bpr-about-body > div > div.with-sidebar > div.not-sidebar.stack > div.bpr-overview-dates.stack > p:nth-child(1)",
            ".accreditation-date",
            "[data-testid='accreditation-date']",
            "p:contains('BBB Accredited Since')"
        ]:
            date_tag = soup.select_one(selector)
            if date_tag:
                break
        
        bbb_data["date_of_accreditation"] = date_tag.text.replace("BBB Accredited Since:", "").strip() if date_tag else ""
        logging.info(f"Accreditation date: {bbb_data['date_of_accreditation']}")
        
        # website - try multiple selectors
        website_tag = None
        for selector in [
            "#content > div.page-center.bpr-header > div.bpr-logo-contact > div > a:nth-child(1)",
            "a[href*='http']",
            ".website-link",
            "[data-testid='website']"
        ]:
            website_tag = soup.select_one(selector)
            if website_tag and website_tag.has_attr('href') and 'http' in website_tag['href']:
                break
        
        bbb_data["website"] = website_tag['href'] if website_tag and website_tag.has_attr('href') else ""
        logging.info(f"Website: {bbb_data['website']}")
        
        # telephone - try multiple selectors
        tel_tag = None
        for selector in [
            "#content > div.page-center.bpr-header > div.bpr-logo-contact > div > a:nth-child(2)",
            "a[href^='tel:']",
            ".phone-number",
            "[data-testid='phone']"
        ]:
            tel_tag = soup.select_one(selector)
            if tel_tag:
                break
        
        bbb_data["telephone"] = tel_tag.text.strip() if tel_tag else ""
        logging.info(f"Telephone: {bbb_data['telephone']}")

        # address - try multiple selectors
        address_div = None
        for selector in [
            "#content > div.page-vertical-padding.bpr-about-body > div > div.with-sidebar > div.sidebar.stack > div.bpr-overview-card.container > div > div.bpr-overview-address",
            ".address",
            "[data-testid='address']",
            ".business-address"
        ]:
            address_div = soup.select_one(selector)
            if address_div:
                break
        
        if address_div:
            address_parts = [p.text.strip() for p in address_div.find_all("p")]
            bbb_data["address"] = " ".join(address_parts)
        else:
            bbb_data["address"] = ""
        
        logging.info(f"Address: {bbb_data['address']}")

        # years_in_business - try multiple selectors
        years_tag = None
        for selector in [
            "#content > div.page-vertical-padding.bpr-about-body > div > div.with-sidebar > div.not-sidebar.stack > div.bpr-overview-dates.stack > p:nth-child(2)",
            ".years-in-business",
            "[data-testid='years-in-business']",
            "p:contains('Years in Business')"
        ]:
            years_tag = soup.select_one(selector)
            if years_tag:
                break
        
        bbb_data["years_in_business"] = years_tag.text.replace("Years in Business:", "").strip() if years_tag else ""
        logging.info(f"Years in business: {bbb_data['years_in_business']}")

        # logo_url - try multiple selectors
        logo_tag = None
        for selector in [
            "#content > div.page-center.bpr-header > div.bpr-logo-contact > img",
            ".business-logo img",
            "[data-testid='logo'] img",
            "img[alt*='logo']",
            "img[alt*='Logo']"
        ]:
            logo_tag = soup.select_one(selector)
            if logo_tag and logo_tag.has_attr('src'):
                break
        
        bbb_data["logo_url"] = logo_tag['src'] if logo_tag and logo_tag.has_attr('src') else ""
        bbb_data["logo_filename"] = "logo.png" if bbb_data["logo_url"] else ""
        logging.info(f"Logo URL: {bbb_data['logo_url']}")

        # N_employees
        dt_tags = soup.find_all("dt")
        n_employees_val = ""
        for dt in dt_tags:
            if "Number of Employees" in dt.text:
                dd = dt.find_next_sibling("dd")
                if dd:
                    n_employees_val = dd.text.strip()
                    break
        bbb_data["N_employees"] = n_employees_val

        # Generic Services extraction: parse the not-sidebar container text for a comma-separated list
        services_list = []
        try:
            ns = soup.select_one("#content > div.page-vertical-padding.bpr-about-body > div > div.with-sidebar > div.not-sidebar.stack")
            raw_text = ns.get_text("\n", strip=True) if ns else soup.get_text("\n", strip=True)
            # Expose full container text for downstream AI context
            bbb_data["container_text"] = raw_text
            lines = [ln.strip() for ln in (raw_text or "").splitlines() if ln and ln.strip()]
            # Heuristic: first line with 2+ commas likely contains services
            candidate = None
            for ln in lines:
                if ln.count(',') >= 2 and len(ln) <= 300:
                    candidate = ln
                    break
            if candidate:
                items = [s.strip() for s in candidate.split(',')]
                # Basic normalization: keep words with reasonable length
                services_list = [s for s in items if 1 < len(s) <= 60]
        except Exception as e:
            logging.warning(f"Generic services extraction failed: {e}")

        # Employee Details
        employee_details = []
        employee_section = soup.select_one("#content > div.page-vertical-padding.bpr-about-body > div > div.with-sidebar > div.not-sidebar.stack > div.bpr-details > div.bpr-details-section.stack > dl")
        if employee_section:
            contact_divs = employee_section.find_all("div", class_="bpr-details-dl-data")
            for i, contact in enumerate(contact_divs):
                 dt = contact.find("dt")
                 dd = contact.find("dd")
                 if dt and dd and ("Contacts" in dt.text):
                     # Example dd text: "Mr. Luis Aguilar-Lopez, Owner"
                     parts = dd.text.strip().split(',')
                     name = parts[0].strip()
                     role = parts[1].strip() if len(parts) > 1 else ""
                     employee_details.append({
                         "name": name,
                         "role": role
                     })
                     bbb_data[f"Employee_{i+1}_name"] = name
                     bbb_data[f"Employee_{i+1}_role"] = role

        # Expose parsed services only (no extra HTML/text blobs)
        bbb_data["services"] = services_list

        # Media Images (kept in memory only)
        try:
            media_items = soup.select("#content > div.page-vertical-padding.bpr-about-body > div > div.with-sidebar > div.not-sidebar.stack > div.container.stack > ul > li.focused-media-item")
            collected_urls = []
            seen = set()
            for li in media_items or []:
                # Direct <img> tags
                for img in li.find_all("img"):
                    src = img.get("src") or img.get("data-src") or img.get("data-lazy")
                    if src:
                        abs_url = urljoin(url, src)
                        if abs_url not in seen:
                            seen.add(abs_url)
                            collected_urls.append({
                                "url": abs_url,
                                "source": "bbb"
                            })
                # Background-image in style attributes
                style = li.get("style") or ""
                if style:
                    m = re.search(r"background-image:\s*url\((['\"]?)([^)\"']+)\1\)", style, re.IGNORECASE)
                    if m:
                        bg_url = m.group(2)
                        abs_url = urljoin(url, bg_url)
                        if abs_url not in seen:
                            seen.add(abs_url)
                            collected_urls.append({
                                "url": abs_url,
                                "source": "bbb"
                            })
                # Any nested elements with style background-image
                for styled in li.find_all(attrs={"style": re.compile(r"background-image", re.IGNORECASE)}):
                    s = styled.get("style") or ""
                    m2 = re.search(r"background-image:\s*url\((['\"]?)([^)\"']+)\1\)", s, re.IGNORECASE)
                    if m2:
                        bg_url = m2.group(2)
                        abs_url = urljoin(url, bg_url)
                        if abs_url not in seen:
                            seen.add(abs_url)
                            collected_urls.append({
                                "url": abs_url,
                                "source": "bbb"
                            })
            bbb_data["images"] = collected_urls
            logging.info(f"Collected BBB media images: {len(collected_urls)}")
        except Exception as e:
            logging.warning(f"Failed to collect BBB media images: {e}")
            bbb_data["images"] = []

    finally:
        logging.info("Closing the browser.")
        driver.quit()
  
    return bbb_data

def main():
    parser = argparse.ArgumentParser(description='Scrape BBB profile data')
    parser.add_argument('--business-name', required=True, help='Business name to scrape')
    parser.add_argument('--bbb-url', required=True, help='BBB URL to scrape')
    parser.add_argument('--headless', action='store_true', default=False, help='Run browser in headless mode')
    parser.add_argument('--persist', type=int, choices=[0,1], default=0, help='Persist outputs to disk (1) or memory-only (0)')
    
    args = parser.parse_args()
    
    print(f"Processing: {args.business_name}")
    print(f"BBB URL: {args.bbb_url}")
    print(f"Headless mode: {args.headless}")
    
    try:
        scraped_data = scrape_bbb_profile(
            url=args.bbb_url,
            headless=args.headless
        )
        
        # Add business name from arguments for reference
        scraped_data["lead_business_name"] = args.business_name
        
        print(f"Successfully scraped data for {args.business_name}")
        
        # Optional persist-to-disk when requested
        if int(args.persist) == 1:
            try:
                os.makedirs(RAW_DATA_DIR, exist_ok=True)
                safe_name = args.business_name.replace(" ", "_").replace(",", "").replace(".", "")
                output_file = os.path.join(RAW_DATA_DIR, f"bbb_profile_data_{safe_name}.json")
                with open(output_file, "w", encoding="utf-8") as json_file:
                    json.dump(scraped_data, json_file, ensure_ascii=False, indent=2)
                main_output_file = os.path.join(RAW_DATA_DIR, "bbb_profile_data.json")
                with open(main_output_file, "w", encoding="utf-8") as json_file:
                    json.dump(scraped_data, json_file, ensure_ascii=False, indent=2)
                logging.info(f"Persisted BBB profile to: {output_file} and {main_output_file}")
            except Exception as persist_err:
                logging.warning(f"Failed to persist BBB profile data: {persist_err}")
        
        # Print the scraped data to stdout for the API to capture
        print("SCRAPED_DATA_START")
        print(json.dumps(scraped_data, ensure_ascii=False, indent=2))
        print("SCRAPED_DATA_END")
        
    except Exception as e:
        print(f"Error processing {args.business_name}: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()




