import argparse
import logging
import time
import random
import json
import pandas as pd
import os
import sys
import webbrowser
import requests
import tempfile
import shutil

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from selenium.webdriver.common.keys import Keys

##############################################################################
# 1) WEB DRIVER INIT
##############################################################################
def web_driver(headless=False):
    """
    Initializes and returns a Selenium WebDriver with enhanced anti-detection options.
    """
    options = Options()
    
    if headless:
        options.add_argument("--headless=new")
    
    # Enhanced anti-detection arguments
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-plugins")
    options.add_argument("--disable-images")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-tools")
    options.add_argument("--no-first-run")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-translate")
    options.add_argument("--disable-background-timer-throttling")
    options.add_argument("--disable-renderer-backgrounding")
    options.add_argument("--disable-backgrounding-occluded-windows")
    options.add_argument("--disable-client-side-phishing-detection")
    options.add_argument("--disable-sync")
    options.add_argument("--disable-default-apps")
    options.add_argument("--hide-scrollbars")
    options.add_argument("--mute-audio")
    
    # Cache and cookie clearing for better CAPTCHA detection
    options.add_argument("--disable-application-cache")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-background-timer-throttling")
    options.add_argument("--disable-client-side-phishing-detection")
    options.add_argument("--disable-component-update")
    options.add_argument("--disable-default-apps")
    options.add_argument("--disable-hang-monitor")
    options.add_argument("--disable-prompt-on-repost")
    options.add_argument("--disable-web-security")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--no-first-run")
    options.add_argument("--disable-background-mode")
    options.add_argument("--disable-logging")
    options.add_argument("--silent")
    options.add_argument("--log-level=3")
    
    # Fresh session settings
    options.add_argument("--incognito")
    options.add_argument("--disable-plugins-discovery")
    options.add_argument("--disable-preconnect")
    
    # Use temporary user data directory for complete cache isolation
    temp_dir = tempfile.mkdtemp()
    options.add_argument(f"--user-data-dir={temp_dir}")
    options.add_argument("--disable-extensions-file-access-check")
    options.add_argument("--disable-extensions-http-throttling")
    
    # More realistic user agent from ScrapeHero tutorial
    user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/119.0.0.0 Safari/537.36"
    )
    options.add_argument(f"user-agent={user_agent}")
    
    # Additional anti-detection measures
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    # Disable image loading to speed up and reduce detection
    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.default_content_settings.popups": 0,
        "profile.managed_default_content_settings.media_stream": 2,
    }
    options.add_experimental_option("prefs", prefs)
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    # Clear cache and cookies for fresh session
    try:
        driver.delete_all_cookies()
        driver.execute_script("window.localStorage.clear();")
        driver.execute_script("window.sessionStorage.clear();")
        logging.info("✅ Cache and cookies cleared for fresh session")
    except Exception as e:
        logging.warning(f"Could not clear cache: {e}")
    
    # Execute additional scripts to hide automation
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    driver.execute_script("Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]})")
    driver.execute_script("Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']})")
    driver.execute_script("Object.defineProperty(navigator, 'platform', {get: () => 'Win32'})")
    
    return driver

##############################################################################
# 2) LOAD BBB PROFILE DATA
##############################################################################
def load_bbb_profile_data():
    """
    Load business information from BBB profile data JSON file.
    """
    bbb_file_path = "/Users/rhettburnham/Desktop/projects/roofing-co/public/data/output/individual/step_1/raw/bbb_profile_data.json"
    
    if not os.path.exists(bbb_file_path):
        logging.error(f"BBB profile data file not found at {bbb_file_path}")
        return None
    
    try:
        with open(bbb_file_path, 'r', encoding='utf-8') as f:
            bbb_data = json.load(f)
        logging.info(f"Loaded BBB data for business: {bbb_data.get('business_name', 'Unknown')}")
        return bbb_data
    except (json.JSONDecodeError, FileNotFoundError) as e:
        logging.error(f"Error loading BBB profile data: {e}")
        return None

##############################################################################
# 3) HANDLE YELP OVERLAY AND CAPTCHA
##############################################################################
def handle_yelp_overlay(driver):
    """
    Handle the potential Yelp app download overlay that may appear.
    """
    try:
        # Look for the overlay with the "Stay on browser" option
        overlay_selector = "body > yelp-react-root > div:nth-child(1) > div.search-container__09f24__gtmZk.border-color--default__09f24__JbNoB > div.overlay-color-cohort__09f24__mZXcv.y-css-17ekefs"
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, overlay_selector))
        )
        
        # Click "Stay on browser" button
        stay_on_browser_button = driver.find_element(By.CSS_SELECTOR, "div.close-button.y-css-v4nulb > p")
        stay_on_browser_button.click()
        logging.info("Clicked 'Stay on browser' to dismiss overlay.")
        time.sleep(2)
        
    except TimeoutException:
        logging.info("No overlay detected, proceeding with search.")
    except Exception as e:
        logging.warning(f"Error handling overlay: {e}")

def check_for_captcha(driver):
    """
    Check if Yelp is showing a CAPTCHA or bot detection page.
    """
    page_source = driver.page_source.lower()
    page_title = driver.title.lower()
    
    captcha_indicators = [
        "we want to make sure you are not a robot",
        "verification required",
        "captcha",
        "robot",
        "suspicious activity",
        "automated traffic",
        "same network",
        "network"
    ]
    
    for indicator in captcha_indicators:
        if indicator in page_source or indicator in page_title:
            logging.error(f"CAPTCHA/Bot detection found: '{indicator}' detected")
            return True
    
    return False

def create_manual_navigation_html(url):
    """
    Create an HTML file with manual navigation instructions.
    """
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Yelp Manual Navigation Required</title>
        <style>
            body {{ 
                font-family: Arial, sans-serif; 
                margin: 40px; 
                background-color: #f5f5f5; 
            }}
            .container {{ 
                background-color: white; 
                padding: 30px; 
                border-radius: 10px; 
                box-shadow: 0 2px 10px rgba(0,0,0,0.1); 
                max-width: 800px; 
                margin: 0 auto; 
            }}
            h1 {{ 
                color: #d32323; 
                text-align: center; 
            }}
            .instructions {{ 
                background-color: #e7f3ff; 
                padding: 20px; 
                border-radius: 5px; 
                margin: 20px 0; 
            }}
            .button {{ 
                background-color: #d32323; 
                color: white; 
                padding: 15px 30px; 
                border: none; 
                border-radius: 5px; 
                font-size: 16px; 
                cursor: pointer; 
                margin: 10px 5px; 
            }}
            .button:hover {{ 
                background-color: #b71c1c; 
            }}
            .url-box {{ 
                background-color: #f9f9f9; 
                padding: 10px; 
                border: 1px solid #ddd; 
                border-radius: 3px; 
                font-family: monospace; 
                word-break: break-all; 
                margin: 10px 0; 
            }}
            .countdown {{ 
                font-size: 24px; 
                font-weight: bold; 
                color: #d32323; 
                text-align: center; 
                margin: 20px 0; 
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔍 Manual Yelp Navigation Required</h1>
            
            <div class="instructions">
                <h3>📋 Instructions:</h3>
                <ol>
                    <li><strong>Open the Yelp URL in a new browser tab/window</strong></li>
                    <li><strong>Navigate to the business page</strong></li>
                    <li><strong>Complete any CAPTCHAs if they appear</strong></li>
                    <li><strong>Wait for the scraper to automatically continue</strong></li>
                </ol>
            </div>
            
            <div class="url-box">
                <strong>Target URL:</strong> {url}
            </div>
            
            <p style="text-align: center;">
                <button class="button" onclick="window.open('{url}', '_blank')">
                    🔗 Open Yelp Page in New Tab
                </button>
            </p>
            
            <div class="countdown">
                <p>⏰ Scraper will automatically continue in <span id="countdown">30</span> seconds</p>
            </div>
            
            <div class="instructions">
                <h3>💡 Tips:</h3>
                <ul>
                    <li>The scraper will automatically switch to your Yelp page after 30 seconds</li>
                    <li>Make sure you're on the correct business page before the countdown ends</li>
                    <li>If you see a CAPTCHA, solve it before the countdown ends</li>
                    <li>Keep this window open - the scraper needs it to identify the correct tab</li>
                </ul>
            </div>
        </div>
        
        <script>
            let countdown = 30;
            const countdownElement = document.getElementById('countdown');
            
            const timer = setInterval(() => {{
                countdown--;
                countdownElement.textContent = countdown;
                
                if (countdown <= 0) {{
                    clearInterval(timer);
                    countdownElement.textContent = '0';
                    document.querySelector('.countdown p').innerHTML = '✅ Scraper is now starting...';
                }}
            }}, 1000);
        </script>
    </body>
    </html>
    """
    
    # Save to temp directory
    temp_dir = os.path.join("public", "data", "output", "leads", "temp")
    os.makedirs(temp_dir, exist_ok=True)
    html_file = os.path.join(temp_dir, "manual_navigation.html")
    
    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    logging.info(f"Manual navigation HTML created: {html_file}")
    return html_file

def wait_for_manual_navigation(driver, target_url):
    """
    Wait 30 seconds for user to manually navigate to Yelp, then switch to the correct window.
    """
    logging.info("=" * 60)
    logging.info("🔍 MANUAL NAVIGATION MODE")
    logging.info("=" * 60)
    logging.info("Instructions:")
    logging.info("1. Open the Yelp business page in a new tab/window")
    logging.info("2. Complete any CAPTCHAs if they appear")
    logging.info("3. Wait for the scraper to automatically continue")
    logging.info("=" * 60)
    
    # Create HTML interface
    html_file = create_manual_navigation_html(target_url)
    
    # Open HTML file directly in Selenium
    try:
        html_url = f"file://{os.path.abspath(html_file)}"
        logging.info(f"📄 Opening HTML interface in browser: {html_url}")
        driver.get(html_url)
        logging.info("✅ Manual navigation interface loaded")
    except Exception as e:
        logging.warning(f"Could not open HTML interface: {e}")
        logging.info(f"📁 Please manually open: {html_file}")
        return False
    
    # Wait for page to load
    time.sleep(2)
    
    # Store the initial window handle (HTML interface)
    initial_window = driver.current_window_handle
    initial_windows = driver.window_handles
    
    logging.info(f"HTML interface window: {initial_window}")
    logging.info(f"Initial window count: {len(initial_windows)}")
    logging.info("⏳ Waiting 30 seconds for manual navigation...")
    logging.info("👆 Please click 'Open Yelp Page in New Tab' and navigate to the business page")
    
    # Show countdown
    for i in range(30, 0, -1):
        if i % 5 == 0 or i <= 5:
            logging.info(f"⏰ {i} seconds remaining...")
        time.sleep(1)
    
    logging.info("🔄 Time's up! Looking for your Yelp page...")
    
    # Get all current windows
    try:
        all_windows = driver.window_handles
        logging.info(f"Total windows now: {len(all_windows)}")
        
        # Find the window that's NOT the HTML interface
        target_window = None
        for window in all_windows:
            if window != initial_window:
                # Switch to this window to check its URL
                try:
                    driver.switch_to.window(window)
                    current_url = driver.current_url
                    logging.info(f"Checking window with URL: {current_url}")
                    
                    # If it's a Yelp page, use this window
                    if "yelp.com" in current_url.lower():
                        target_window = window
                        logging.info(f"✅ Found Yelp window: {current_url}")
                        break
                    elif not current_url.startswith("file://"):
                        # If it's not the HTML file and not Yelp, might still be useful
                        target_window = window
                        logging.info(f"📄 Found non-HTML window: {current_url}")
                except Exception as e:
                    logging.warning(f"Error checking window {window}: {e}")
                    continue
        
        # Switch to the target window
        if target_window:
            driver.switch_to.window(target_window)
            final_url = driver.current_url
            logging.info(f"🎯 Switched to window: {final_url}")
            
            # Check if we're on Yelp
            if "yelp.com" in final_url.lower():
                logging.info("✅ Successfully on Yelp page!")
                return True
            else:
                logging.warning(f"⚠️ Not on Yelp page. Currently on: {final_url}")
                return False
        else:
            logging.error("❌ Could not find a suitable window to switch to")
            logging.info("💡 Make sure you opened the Yelp page in a NEW TAB")
            return False
            
    except Exception as e:
        logging.error(f"Error during window switching: {e}")
        return False

def simulate_human_behavior(driver):
    """
    Simulate human-like browsing behavior.
    """
    # Random scroll
    driver.execute_script("window.scrollTo(0, Math.floor(Math.random() * 1000));")
    time.sleep(random.uniform(1, 3))
    
    # Random mouse movements (simulate by changing window size slightly)
    current_size = driver.get_window_size()
    driver.set_window_size(current_size['width'] + random.randint(-10, 10), 
                          current_size['height'] + random.randint(-10, 10))

def generate_yelp_url(business_name, address):
    """
    Generate a Yelp search URL for the given business and address (manual navigation).
    """
    try:
        from urllib.parse import quote
        q_name = quote(business_name or '')
        q_addr = quote(address or '')
        # Desktop search URL for better UX during manual navigation
        search_url = f"https://www.yelp.com/search?find_desc={q_name}&find_loc={q_addr}"
        return [search_url]
    except Exception:
        return ["https://www.yelp.com/"]

##############################################################################
# 4) NAVIGATE TO YELP BUSINESS PAGE
##############################################################################
def navigate_to_yelp_business(driver, business_name, address):
    """
    Navigate to the specific Yelp business page using manual navigation.
    """
    try:
        # Get the direct Yelp URL
        urls_to_try = generate_yelp_url(business_name, address)
        url = urls_to_try[0]  # We only have one URL now
        
        logging.info(f"Target Yelp URL: {url}")
        
        # Use manual navigation approach
        logging.info("🔍 Starting manual navigation process...")
        
        # Start with a blank page
        driver.get("about:blank")
        time.sleep(2)
        
        # Wait for user to manually navigate to Yelp
        success = wait_for_manual_navigation(driver, url)
        
        if success:
            logging.info("✅ Manual navigation successful!")
            
            # Handle potential overlay
            handle_yelp_overlay(driver)
            
            # Simulate human behavior
            simulate_human_behavior(driver)
            
            return True
        else:
            logging.warning("⚠️ Manual navigation failed or user didn't navigate to Yelp")
            return False
            
    except Exception as e:
        logging.error(f"Error during Yelp navigation: {e}")
        return False

def download_image(img_url, save_path, filename):
    """
    Download an image from URL and save it to the specified path.
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
        }
        
        response = requests.get(img_url, headers=headers, timeout=30)
        response.raise_for_status()
        
        # Ensure the directory exists
        os.makedirs(save_path, exist_ok=True)
        
        # Save the image
        full_path = os.path.join(save_path, filename)
        with open(full_path, 'wb') as f:
            f.write(response.content)
        
        logging.info(f"Downloaded image: {filename}")
        return full_path
        
    except Exception as e:
        logging.error(f"Error downloading image {img_url}: {e}")
        return None

def scrape_business_info(driver):
    """
    Scrape business information from the current Yelp page, focusing on services and images.
    """
    try:
        current_url = driver.current_url
        logging.info(f"Scraping business info from: {current_url}")
        
        # Initialize data structure
        business_data = {
            "yelp_business_name": "N/A",
            "yelp_services": [],
            "yelp_hours": {},
            "bus_web": "",
            "yelp_url": current_url,
            "scraping_status": "SUCCESS",
            "page_title": "N/A",
            "social_links": {}
        }
        
        # Get page title for debugging
        try:
            business_data["page_title"] = driver.title
            logging.info(f"Page title: {driver.title}")
        except:
            pass
        
        # Log page source preview for debugging only (not stored in output)
        try:
            page_source = driver.page_source
            logging.info(f"Page source preview (first 200 chars): {page_source[:200]}...")
        except:
            pass
        
        # Wait for page to load
        time.sleep(random.uniform(2, 4))
        
        # Try to scrape business name first
        try:
            business_name_selectors = [
                "h1[data-testid='business-name']",
                "h1.css-1x9iesk",
                "h1",
                "h2"
            ]
            
            for selector in business_name_selectors:
                try:
                    name_element = driver.find_element(By.CSS_SELECTOR, selector)
                    if name_element and name_element.text.strip():
                        business_data["yelp_business_name"] = name_element.text.strip()
                        logging.info(f"Found business name: {business_data['yelp_business_name']}")
                        break
                except:
                    continue
        except Exception as e:
            logging.warning(f"Could not find business name: {e}")
        
        # Note: yelp_images are not included in JSON output per requirements
        
        # Focus on scraping services using the specific selector
        try:
            logging.info("Attempting to scrape services using data-testid selector...")
            
            # First try to click the button to reveal full services list
            try:
                reveal_button = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "#main-content > section:nth-child(5) > button"))
                )
                driver.execute_script("arguments[0].click();", reveal_button)
                logging.info("✅ Clicked button to reveal full services list")
                time.sleep(2)  # Wait for services to load
            except TimeoutException:
                logging.info("No reveal button found or couldn't click it, proceeding with visible services")
            except Exception as e:
                logging.warning(f"Error clicking reveal button: {e}")
            
            # Use the specific selector for service offerings
            service_elements = driver.find_elements(By.CSS_SELECTOR, 'p[data-testid="Service Offering"]')
            
            if service_elements:
                services = []
                for element in service_elements:
                    try:
                        service_text = element.text.strip()
                        if service_text:
                            services.append(service_text)
                            logging.info(f"Found service: {service_text}")
                    except Exception as e:
                        logging.warning(f"Error getting text from service element: {e}")
                
                business_data["yelp_services"] = services
                logging.info(f"Total services found: {len(services)}")
            else:
                logging.warning("No service elements found with data-testid='Service Offering'")
                
                # Try alternative selectors for services
                alternative_selectors = [
                    'p.y-css-1mwo47a',
                    '.arrange__09f24__LDfbs p',
                    '[data-testid*="Service"]',
                    'p[data-testid*="service"]'
                ]
                
                for selector in alternative_selectors:
                    try:
                        logging.info(f"Trying alternative selector: {selector}")
                        alt_elements = driver.find_elements(By.CSS_SELECTOR, selector)
                        if alt_elements:
                            logging.info(f"Found {len(alt_elements)} elements with selector: {selector}")
                            alt_services = []
                            for element in alt_elements[:10]:  # Limit to first 10
                                try:
                                    text = element.text.strip()
                                    if text and len(text) < 100:  # Reasonable service name length
                                        alt_services.append(text)
                                        logging.info(f"Alternative service found: {text}")
                                except:
                                    pass
                            if alt_services:
                                business_data["yelp_services"] = alt_services
                                break
                    except Exception as e:
                        logging.warning(f"Error with alternative selector {selector}: {e}")
                        continue
        
        except Exception as e:
            logging.error(f"Error scraping services: {e}")
            business_data["scraping_status"] = "SERVICES_ERROR"
            business_data["error_message"] = str(e)
        
        # Extract bus_web information
        try:
            logging.info("Attempting to extract bus_web information...")
            bus_web_selector = "body > yelp-react-root > div:nth-child(1) > div.biz-details-page-container-outer__09f24__pZBzx.y-css-mhg9c5 > div > div.y-css-1ehjqp6 > div.y-css-1mxaxb3 > aside > section:nth-child(3) > div > div:nth-child(1) > div > div.y-css-8x4us > p.y-css-qn4gww > a"
            
            try:
                bus_web_element = driver.find_element(By.CSS_SELECTOR, bus_web_selector)
                business_data["bus_web"] = bus_web_element.text.strip()
                logging.info(f"Found bus_web: {business_data['bus_web']}")
            except:
                business_data["bus_web"] = ""
                logging.info("No bus_web found, leaving blank")
                
        except Exception as e:
            logging.warning(f"Error extracting bus_web: {e}")
            business_data["bus_web"] = ""
        
        # Scrape images from media showcase
        try:
            logging.info("Attempting to scrape images from media showcase...")
            
            # Determine if we should avoid disk writes (memory-only mode)
            memory_only = os.environ.get('MEMORY_ONLY', '0') == '1'
            
            # Only create images directory when not in memory-only mode
            img_dir = "/Users/rhettburnham/Desktop/projects/roofing-co/public/data/output/individual/step_2/yelp_img"
            if not memory_only:
                os.makedirs(img_dir, exist_ok=True)
            
            # Try multiple selectors for the media showcase
            media_selectors = [
                '[data-testid="mediaShowcase"] img',
                '#main-content > section:nth-child(3) img',
                '.media-item__09f24__aOzKr img',
                '.y-css-mhg9c5 img'
            ]
            
            images_found = False
            downloaded_images = []  # accumulate in-memory references for JSON payload
            for selector in media_selectors:
                try:
                    logging.info(f"Trying image selector: {selector}")
                    img_elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    
                    if img_elements:
                        logging.info(f"Found {len(img_elements)} images with selector: {selector}")
                        
                        for i, img_element in enumerate(img_elements):
                            try:
                                img_src = img_element.get_attribute("src")
                                img_alt = img_element.get_attribute("alt") or f"Image {i+1}"
                                
                                if img_src and "yelpcdn.com" in img_src:
                                    # Extract filename from URL or create one
                                    if "/bphoto/" in img_src:
                                        # Extract the unique ID from Yelp URL
                                        photo_id = img_src.split("/bphoto/")[1].split("/")[0]
                                        filename = f"yelp_image_{i+1}_{photo_id}.jpg"
                                    else:
                                        filename = f"yelp_image_{i+1}.jpg"
                                    
                                    if memory_only:
                                        # Do not write to disk; keep in memory and include in JSON
                                        image_info = {
                                            "filename": filename,
                                            "original_url": img_src,
                                            "url": img_src,
                                            "alt_text": img_alt,
                                            "local_path": None,
                                            "download_status": "memory_only"
                                        }
                                        downloaded_images.append(image_info)
                                    else:
                                        # Download the image to disk
                                        saved_path = download_image(img_src, img_dir, filename)
                                        if saved_path:
                                            image_info = {
                                                "filename": filename,
                                                "original_url": img_src,
                                                "alt_text": img_alt,
                                                "local_path": saved_path,
                                                "download_status": "success"
                                            }
                                            downloaded_images.append(image_info)
                                            logging.info(f"Successfully downloaded: {filename}")
                                        else:
                                            image_info = {
                                                "filename": filename,
                                                "original_url": img_src,
                                                "alt_text": img_alt,
                                                "local_path": None,
                                                "download_status": "failed"
                                            }
                                            downloaded_images.append(image_info)
                                            logging.warning(f"Failed to download: {filename}")
                                
                            except Exception as e:
                                logging.error(f"Error processing image {i}: {e}")
                                continue
                        
                        if downloaded_images:
                            # Mark that we found images
                            images_found = True
                            # If memory-only, attach to business_data for in-memory consumption
                            if memory_only:
                                business_data["downloaded_images"] = downloaded_images
                                logging.info(f"✅ Collected {len(downloaded_images)} images in memory (included in JSON output)")
                            else:
                                logging.info(f"✅ Successfully processed {len(downloaded_images)} images!")
                            break
                        
                except Exception as e:
                    logging.warning(f"Error with image selector {selector}: {e}")
                    continue
            
            if not images_found:
                logging.warning("No images found with any selector")
        
        except Exception as e:
            logging.error(f"Error scraping images: {e}")
            business_data["image_error"] = str(e)
        
        # Scrape business hours from the hours table
        try:
            logging.info("Attempting to scrape business hours...")
            
            # Try multiple selectors for the hours table
            hours_selectors = [
                '#location-and-hours > section > div.arrange__09f24__LDfbs.gutter-4__09f24__dajdg.y-css-mhg9c5 > div.arrange-unit__09f24__rqHTg.arrange-unit-fill__09f24__CUubG.y-css-mhg9c5 > div > div > table',
                'table.hours-table__09f24__KR8wh',
                '.hours-table__09f24__KR8wh',
                'table[class*="hours-table"]'
            ]
            
            hours_found = False
            for selector in hours_selectors:
                try:
                    logging.info(f"Trying hours selector: {selector}")
                    table_element = driver.find_element(By.CSS_SELECTOR, selector)
                    
                    if table_element:
                        logging.info("Found hours table, extracting daily hours...")
                        
                        # Extract hours from table rows
                        hours_data = {}
                        
                        # Find all table rows with day information
                        rows = table_element.find_elements(By.CSS_SELECTOR, 'tr')
                        
                        for row in rows:
                            try:
                                # Look for day name in th element
                                day_elements = row.find_elements(By.CSS_SELECTOR, 'th p.day-of-the-week__09f24__JJea_')
                                if day_elements:
                                    day_name = day_elements[0].text.strip()
                                    
                                    # Look for hours in td element
                                    hours_elements = row.find_elements(By.CSS_SELECTOR, 'td p.no-wrap__09f24__c3plq')
                                    if hours_elements:
                                        hours_text = hours_elements[0].text.strip()
                                        
                                        # Check for closed status
                                        closed_elements = row.find_elements(By.CSS_SELECTOR, 'td .open-status__09f24__YH9PK')
                                        status = ""
                                        if closed_elements:
                                            status = closed_elements[0].text.strip()
                                        
                                        hours_data[day_name] = {
                                            "hours": hours_text,
                                            "status": status if status else "Open"
                                        }
                                        
                                        logging.info(f"Found hours for {day_name}: {hours_text} ({status if status else 'Open'})")
                                    
                            except Exception as e:
                                logging.warning(f"Error processing hours row: {e}")
                                continue
                        
                        if hours_data:
                            business_data["yelp_hours"] = hours_data
                            hours_found = True
                            logging.info(f"✅ Successfully extracted hours for {len(hours_data)} days!")
                            break
                        else:
                            logging.warning("No hours data found in table")
                        
                except Exception as e:
                    logging.warning(f"Error with hours selector {selector}: {e}")
                    continue
            
            if not hours_found:
                logging.warning("No hours table found with any selector")
                business_data["yelp_hours"] = {}
        
        except Exception as e:
            logging.error(f"Error scraping hours: {e}")
            business_data["hours_error"] = str(e)
        
        # Check if we got any meaningful data
        if business_data["yelp_services"] or business_data["yelp_hours"]:
            hours_count = len(business_data["yelp_hours"])
            logging.info(f"✅ Successfully scraped {len(business_data['yelp_services'])} services and hours for {hours_count} days!")
            business_data["scraping_status"] = "SUCCESS"
        elif business_data["yelp_business_name"] != "N/A":
            logging.info(f"✅ Got business name but no services or hours")
            business_data["scraping_status"] = "PARTIAL_SUCCESS"
        else:
            logging.warning("❌ No meaningful data extracted")
            business_data["scraping_status"] = "NO_DATA"
        
        return business_data
        
    except Exception as e:
        logging.error(f"Error scraping business info: {e}")
        return {
            "yelp_business_name": "Scraping Error",
            "yelp_services": [],
            "yelp_hours": {},
            "bus_web": "",
            "yelp_url": driver.current_url,
            "scraping_status": "ERROR",
            "error_message": str(e),
            "page_title": driver.title if hasattr(driver, 'title') else "N/A",
            "social_links": {}
        }

##############################################################################
# 6) MAIN FUNCTION
##############################################################################
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--yelp-url', dest='yelp_url', default=None)
    args = parser.parse_args()
    # Setup logging
    log_dir = os.path.join("public", "data", "output", "leads", "raw")
    os.makedirs(log_dir, exist_ok=True)
    log_filename = os.path.join(log_dir, 'yelp_scraper.log')
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_filename, mode='a'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    logging.info("="*60)
    logging.info("YELP SCRAPER - Manual Navigation Mode")
    logging.info("="*60)
    logging.info("This scraper uses manual navigation to avoid CAPTCHA issues:")
    logging.info("1. Opens browser with HTML interface")
    logging.info("2. Waits 30 seconds for you to navigate to Yelp")
    logging.info("3. Automatically switches to your Yelp tab")
    logging.info("4. Scrapes the business information")
    logging.info("="*60)
    
    # Load BBB profile data
    bbb_data = load_bbb_profile_data()
    if not bbb_data:
        logging.error("Could not load BBB profile data. Exiting.")
        return
    
    business_name = bbb_data.get("business_name", "")
    address = bbb_data.get("address", "")
    
    if not business_name or not address:
        logging.error("Missing business name or address in BBB data. Exiting.")
        return
    
    logging.info(f"Business: {business_name}")
    logging.info(f"Address: {address}")
    
    # Initialize web driver (non-headless for manual navigation)
    driver = web_driver(headless=False)
    
    # Initial delay to appear more human-like
    initial_startup_delay = random.uniform(2, 4)
    logging.info(f"Initial startup delay: {initial_startup_delay:.2f} seconds")
    time.sleep(initial_startup_delay)
    
    try:
        # Navigate to Yelp business page (direct if URL provided, otherwise manual)
        if args.yelp_url:
            logging.info(f"Direct Yelp URL provided via args: {args.yelp_url}")
            driver.get(args.yelp_url)
            time.sleep(2)
            handle_yelp_overlay(driver)
            simulate_human_behavior(driver)
            navigation_success = True
        else:
            # Re-enable manual navigation flow (opens local HTML and waits)
            navigation_success = navigate_to_yelp_business(driver, business_name, address)
        
        if navigation_success:
            logging.info("✅ Successfully navigated to Yelp business page!")
            
            # Scrape business information (focusing on services)
            yelp_data = scrape_business_info(driver)
            
            # Add BBB data for reference
            yelp_data["business_name_from_bbb"] = business_name
            yelp_data["address_from_bbb"] = address
            
        else:
            logging.warning("❌ Failed to navigate to Yelp business page")
            
            # Create fallback data
            yelp_data = {
                "yelp_business_name": "Navigation Failed",
                "yelp_services": [],
                "yelp_hours": {},
                "bus_web": "",
                "yelp_url": "https://m.yelp.com/biz/cowboys-vaqueros-construction-sharpsburg-7",
                "scraping_status": "NAVIGATION_FAILED",
                "note": "Manual navigation failed. User may not have navigated to Yelp or timed out.",
                "business_name_from_bbb": business_name,
                "address_from_bbb": address,
                "suggestion": "Try running the scraper again and make sure to navigate to Yelp within 30 seconds"
            }
        
        # Output (memory-only supported)
        memory_only = os.environ.get('MEMORY_ONLY', '0') == '1'
        if memory_only:
            print('YELP_RESULTS_START')
            print(json.dumps(yelp_data))
            print('YELP_RESULTS_END')
        else:
            # Save the data to step_2 directory as requested
            output_file = "/Users/rhettburnham/Desktop/projects/roofing-co/public/data/output/individual/step_2/yelp_scrape.json"
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(yelp_data, f, ensure_ascii=False, indent=4)
            
            logging.info(f"✅ Yelp data saved to {output_file}")
        logging.info(f"📊 Scraping status: {yelp_data.get('scraping_status', 'SUCCESS')}")
        
        # Summary
        logging.info("="*60)
        logging.info("SCRAPING SUMMARY")
        logging.info("="*60)
        logging.info(f"Business Name: {yelp_data.get('yelp_business_name', 'N/A')}")
        logging.info(f"Services Found: {len(yelp_data.get('yelp_services', []))}")
        if yelp_data.get('yelp_services'):
            logging.info("Services List:")
            for i, service in enumerate(yelp_data['yelp_services'], 1):
                logging.info(f"  {i}. {service}")
        
        logging.info("Images: Downloaded locally but not included in JSON output")
        
        logging.info(f"Hours Found: {len(yelp_data.get('yelp_hours', {}))}")
        if yelp_data.get('yelp_hours'):
            logging.info("Business Hours:")
            for day, hours in yelp_data['yelp_hours'].items():
                logging.info(f"  {day}: {hours['hours']} ({hours['status']})")
        
        logging.info(f"Status: {yelp_data.get('scraping_status', 'SUCCESS')}")
        logging.info("="*60)
            
    except Exception as e:
        logging.error(f"An error occurred during scraping: {e}", exc_info=True)
        
        # Create error data
        error_data = {
            "yelp_business_name": "Scraping Error",
            "yelp_services": [],
            "yelp_hours": {},
            "bus_web": "",
            "yelp_url": "https://m.yelp.com/biz/cowboys-vaqueros-construction-sharpsburg-7",
            "scraping_status": "ERROR",
            "error_message": str(e),
            "business_name_from_bbb": business_name,
            "address_from_bbb": address
        }
        
        # Output based on memory mode
        memory_only_err = os.environ.get('MEMORY_ONLY', '0') == '1'
        if memory_only_err:
            print('YELP_RESULTS_START')
            print(json.dumps(error_data))
            print('YELP_RESULTS_END')
        else:
            # Save error data to step_2 directory
            output_file = "/Users/rhettburnham/Desktop/projects/roofing-co/public/data/output/individual/step_2/yelp_scrape.json"
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(error_data, f, ensure_ascii=False, indent=4)
            
            logging.info(f"💾 Error data saved to {output_file}")
        
    finally:
        if driver:
            driver.quit()
            logging.info("🚪 Browser closed.")
            
        # Clean up temporary directory
        try:
            temp_dirs = [d for d in os.listdir(tempfile.gettempdir()) if d.startswith('tmp') and 'chrome' in d.lower()]
            for temp_dir in temp_dirs:
                try:
                    shutil.rmtree(os.path.join(tempfile.gettempdir(), temp_dir))
                except:
                    pass
            logging.info("🧹 Temporary cache directories cleaned up")
        except Exception as e:
            logging.warning(f"Could not clean up temp directories: {e}")

if __name__ == "__main__":
    main() 