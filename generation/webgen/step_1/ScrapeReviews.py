import logging
import time
import random
import json
import os
import subprocess
import sys
import requests
import urllib.parse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
## Use system ChromeDriver via Selenium, matching ScrapeBBB.py approach
from bs4 import BeautifulSoup
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

def web_driver(headless=True):
    """
    Initializes and returns a Selenium WebDriver with specified options.
    
    Parameters:
    ----------
    headless : bool
        Whether to run Chrome in headless mode (no visible browser).
    
    Returns:
    -------
    driver : selenium.webdriver.Chrome
        Configured Selenium WebDriver instance.
    """
    options = Options()
    
    if headless:
        options.add_argument("--headless=new")  # Use headless mode
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-infobars")
    options.add_argument("--incognito")  # Private mode
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    # On macOS in visible mode, request right-half placement before Chrome shows
    if not headless and sys.platform == 'darwin':
        left, top, right, bottom = _get_macos_screen_bounds()
        screen_width = max(0, right - left)
        screen_height = max(0, bottom - top)
        half_width = max(400, screen_width // 2)
        pos_x = left + (screen_width - half_width)
        pos_y = top
        options.add_argument(f"--window-position={pos_x},{pos_y}")
        options.add_argument(f"--window-size={half_width},{screen_height}")
    
    # Disable images for faster loading
    prefs = {"profile.managed_default_content_settings.images": 2}
    options.add_experimental_option("prefs", prefs)
    
    # Set user agent to mimic a real browser
    user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/113.0.5672.63 Safari/537.36"
    )
    options.add_argument(f"user-agent={user_agent}")
    
    # Additional stealth options to make headless Chrome less detectable
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    # Initialize WebDriver using system ChromeDriver (same approach as ScrapeBBB.py)
    driver = webdriver.Chrome(
        service=ChromeService(),
        options=options
    )
    
    # Additional stealth measures
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    return driver

def _get_macos_screen_bounds():
    """
    Attempts to get the primary screen bounds on macOS using AppleScript.
    Returns (left, top, right, bottom). Falls back to a 1920x1080 screen if detection fails.
    """
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
    # Fallback to 1920x1080 if detection fails
    return 0, 0, 1920, 1080

def _position_window_right_half(driver):
    """
    Positions the browser window on the right half of the primary screen (macOS).
    No-op if the driver does not support window management or on failure.
    """
    try:
        left, top, right, bottom = _get_macos_screen_bounds()
        screen_width = max(0, right - left)
        screen_height = max(0, bottom - top)
        # Place the window on the right half
        half_width = max(400, screen_width // 2)
        pos_x = left + (screen_width - half_width)
        pos_y = top
        driver.set_window_size(half_width, screen_height)
        driver.set_window_position(pos_x, pos_y)
    except Exception:
        # If anything goes wrong, ignore positioning rather than failing the scrape
        pass

def download_image_from_url(image_url, save_dir, filename):
    """
    Downloads an image from a URL and saves it to the specified directory.
    
    Parameters:
    ----------
    image_url : str
        The URL of the image to download.
    save_dir : str
        The directory to save the image in.
    filename : str
        The filename to save the image as.
    
    Returns:
    -------
    bool
        True if download was successful, False otherwise.
    """
    try:
        # Create the directory if it doesn't exist
        os.makedirs(save_dir, exist_ok=True)
        
        # Download the image
        response = requests.get(image_url, timeout=10)
        response.raise_for_status()
        
        # Save the image
        file_path = os.path.join(save_dir, filename)
        with open(file_path, 'wb') as f:
            f.write(response.content)
        
        logging.info(f"Successfully downloaded image: {filename}")
        return True
        
    except Exception as e:
        logging.error(f"Failed to download image {filename}: {e}")
        return False

def extract_image_url_from_style(style_attribute):
    """
    Extracts the image URL from a style attribute containing background-image.
    
    Parameters:
    ----------
    style_attribute : str
        The style attribute string.
    
    Returns:
    -------
    str or None
        The extracted image URL, or None if not found.
    """
    try:
        if 'background-image' in style_attribute:
            # Extract URL from background-image: url("...")
            start = style_attribute.find('url("') + 5
            end = style_attribute.find('")', start)
            if start > 4 and end > start:
                return style_attribute[start:end]
    except Exception as e:
        logging.error(f"Error extracting image URL from style: {e}")
    
    return None

def scrape_google_maps_reviews(url, headless=True, max_reviews=50):
    """
    Scrapes reviews from a Google Maps business page.
    
    Parameters:
    ----------
    url : str
        The Google Maps URL of the place.
    headless : bool
        Whether to run Chrome in headless mode (no visible browser).
    max_reviews : int
        The maximum number of reviews to scrape.
    
    Returns:
    -------
    reviews_data : list of dict
        A list of dictionaries containing 'name', 'rating', 'date', and 'review_text'.
    """
    
    # Setup logging (console only, no file writes in memory-only mode)
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(message)s')
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console.setFormatter(formatter)
    logging.getLogger('').addHandler(console)
    
    # Initialize the WebDriver
    driver = web_driver(headless=headless)
    
    # When visible on macOS, move the window to the right half of the screen
    if not headless and sys.platform == 'darwin':
        _position_window_right_half(driver)
    
    reviews_data = []
    downloaded_images = []
    
    try:
        logging.info(f"Navigating to URL: {url}")
        driver.get(url)
        
        # Wait for the main content to load
        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.m6QErb"))
            )
            logging.info("Main page loaded successfully.")
        except Exception as e:
            logging.error(f"Main page did not load properly: {e}")
            return []
        
        time.sleep(3)  # Additional wait to ensure complete load
        
        # 3) CLICK THE REVIEWS BUTTON FIRST
        try:
            logging.info("Looking for and clicking the reviews button...")
            reviews_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button[role='tab'][aria-label*='Reviews']"))
            )
            reviews_button.click()
            logging.info("Successfully clicked the reviews button.")
            time.sleep(3)  # Wait for reviews to load
        except Exception as e:
            logging.error(f"Could not find or click the reviews button: {e}")
            return []
        
        # 4) LOCATE THE REVIEWS CONTAINER AND SCROLL
        try:
            logging.info("Locating the reviews container for scrolling...")
            primary_selector = "#QA0Szd > div > div > div.w6VYqd > div:nth-child(2) > div > div.e07Vkf.kA9KIf > div > div > div.m6QErb.DxyBCb.kA9KIf.dS8AEf.XiKgde"
            fallback_selector = "#QA0Szd > div > div > div.w6VYqd > div:nth-child(2) > div > div.e07Vkf.kA9KIf > div"
            try:
                reviews_container = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, primary_selector))
                )
                logging.info(f"Found reviews container via primary selector: {primary_selector}")
            except TimeoutException:
                reviews_container = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, fallback_selector))
                )
                logging.info(f"Primary selector failed; using fallback selector: {fallback_selector}")
            logging.info("Found reviews container, starting to scroll...")

            last_height = driver.execute_script("return arguments[0].scrollHeight;", reviews_container)
            scroll_attempts = 0
            max_scroll_attempts = 15

            while len(reviews_data) < max_reviews:
                # Scroll down
                driver.execute_script("arguments[0].scrollTo(0, arguments[0].scrollHeight);", reviews_container)
                logging.info("Scrolled to the bottom of the reviews container.")
                time.sleep(random.uniform(2, 3))  # Randomized delay
                
                # Calculate new scroll height and compare with last scroll height
                new_height = driver.execute_script("return arguments[0].scrollHeight;", reviews_container)
                if new_height == last_height:
                    scroll_attempts += 1
                    logging.info(f"Scroll height unchanged. Attempt {scroll_attempts}/{max_scroll_attempts}.")
                    if scroll_attempts >= max_scroll_attempts:
                        logging.info("No more new reviews loaded after multiple attempts; stopping scroll.")
                        break
                else:
                    last_height = new_height
                    scroll_attempts = 0
                    logging.info(f"New scroll height: {new_height}")
        except Exception as e:
            logging.error(f"Error occurred during scrolling: {e}")
            return []
        
        logging.info("Finished scrolling. Parsing the page.")
        
        # Now use BeautifulSoup to extract the reviews with the new HTML structure
        soup = BeautifulSoup(driver.page_source, "html.parser")
        
        # Direct approach - find all review divs with the class "jftiEf fontBodyMedium"
        review_divs = soup.find_all("div", class_="jftiEf fontBodyMedium")
        logging.info(f"Found {len(review_divs)} review divs.")
        
        if not review_divs:
            logging.warning("No reviews found with class 'jftiEf fontBodyMedium'.")
            return []
        
        # # Also find and download review images (COMMENTED OUT - Pure memory storage)
        # logging.info("Looking for review images to download...")
        # img_dump_dir = "/Users/rhettburnham/Desktop/projects/roofing-co/public/data/output/leads/final/img_dump"
        # image_buttons = soup.find_all("button", class_="Tya61d")
        # logging.info(f"Found {len(image_buttons)} image buttons with class 'Tya61d'")
        # 
        # downloaded_images = []
        # for idx, img_button in enumerate(image_buttons):
        #     try:
        #         # Extract image URL from style attribute
        #         style_attr = img_button.get('style', '')
        #         image_url = extract_image_url_from_style(style_attr)
        #         
        #         if image_url:
        #             # Create a safe filename
        #             safe_filename = f"review_image_{idx + 1}.jpg"
        #             
        #             # Download the image
        #             if download_image_from_url(image_url, img_dump_dir, safe_filename):
        #                 downloaded_images.append({
        #                     "filename": safe_filename,
        #                     "url": image_url,
        #                     "index": idx + 1
        #                 })
        #                 logging.info(f"Downloaded image {idx + 1}: {safe_filename}")
        #             else:
        #                 logging.warning(f"Failed to download image {idx + 1}")
        #         else:
        #             logging.warning(f"No image URL found in button {idx + 1}")
        #             
        #     except Exception as e:
        #         logging.error(f"Error processing image button {idx + 1}: {e}")
        #         continue
        # 
        # logging.info(f"Successfully downloaded {len(downloaded_images)} images to {img_dump_dir}")
        
        # Pure memory storage - just collect image URLs without downloading
        logging.info("Looking for review images...")
        image_buttons = soup.find_all("button", class_="Tya61d")
        logging.info(f"Found {len(image_buttons)} image buttons with class 'Tya61d'")
        
        downloaded_images = []
        for idx, img_button in enumerate(image_buttons):
            try:
                # Extract image URL from style attribute
                style_attr = img_button.get('style', '')
                image_url = extract_image_url_from_style(style_attr)
                
                if image_url:
                    downloaded_images.append({
                        "filename": f"review_image_{idx + 1}.jpg",
                        "url": image_url,
                        "index": idx + 1
                    })
                    logging.info(f"Found image {idx + 1}: {image_url}")
                else:
                    logging.warning(f"No image URL found in button {idx + 1}")
                    
            except Exception as e:
                logging.error(f"Error processing image button {idx + 1}: {e}")
                continue
        
        logging.info(f"Found {len(downloaded_images)} images (stored in memory only)")
        
        for idx, review_div in enumerate(review_divs, start=1):
            try:
                # Extract name from the d4r55 class
                name_div = review_div.find("div", class_="d4r55")
                name = name_div.text.strip() if name_div else "N/A"
                logging.info(f"Review {idx}: Extracted name - {name}")
                
                # Extract rating from kvMYJc span with aria-label
                rating_span = review_div.find("span", class_="kvMYJc")
                if rating_span and rating_span.has_attr("aria-label"):
                    rating_text = rating_span["aria-label"]  # e.g., "5 stars"
                    rating = rating_text.split(" ")[0]
                    logging.info(f"Review {idx}: Extracted rating - {rating}")
                else:
                    rating = "N/A"
                    logging.warning(f"Review {idx}: span with class 'kvMYJc' or 'aria-label' not found.")
                
                # Extract date from rsqaWe span
                date_span = review_div.find("span", class_="rsqaWe")
                date = date_span.text.strip() if date_span else "N/A"
                logging.info(f"Review {idx}: Extracted date - {date}")
                
                # Extract review text from wiI7pd span
                text_span = review_div.find("span", class_="wiI7pd")
                review_text = text_span.text.strip() if text_span else "N/A"
                logging.info(f"Review {idx}: Extracted review text - {review_text}")
                
                # Append to the list
                reviews_data.append({
                    "name": name,
                    "rating": rating,
                    "date": date,
                    "review_text": review_text,
                    "has_images": False  # Will be updated if images are found for this review
                })
                
                logging.info(f"Review {idx} scraped successfully.")
                
                # Break if we've reached the maximum number of reviews
                if len(reviews_data) >= max_reviews:
                    logging.info(f"Reached the maximum desired reviews: {max_reviews}")
                    break
                
            except Exception as e:
                logging.error(f"Error scraping review {idx}: {e}")
                continue
    
    finally:
        # Close the browser
        logging.info("Closing the browser.")
        driver.quit()
    
    # Return both reviews and downloaded images
    return {
        'reviews': reviews_data,
        'downloaded_images': downloaded_images
    }

# this is the portion tht is good for the formatting data=!4m8!3m7!1s0x88f4c38a8b36c047:0xce9384a70f8a8f54!8m2!3d33.422357!4d-84.640692!9m1!1b1!16s%2Fg%2F11jnxrwqxz? ..enr
# example complete code "https://www.google.com/maps/place/Su's+Chinese+Cuisine/@33.7965679,-84.3735687,17z/data=!3m1!5s0x88f50436a5b9d505:0xebc3274b663fcac7!4m18!1m9!3m8!1s0x88f505e262e394d5:0xba8cbf84b539def8!2sSu's+Chinese+Cuisine!8m2!3d33.7965679!4d-84.3709938!9m1!1b1!16s%2Fg%2F11mtfm60_1!3m7!1s0x88f505e262e394d5:0xba8cbf84b539def8!8m2!3d33.7965679!4d-84.3709938!9m1!1b1!16s%2Fg%2F11mtfm60_1?entry=ttu&g_ep=EgoyMDI1MDEwOC4wIKXMDSoASAFQAw%3D%3D"
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Scrape Google Maps reviews for a business')
    parser.add_argument('--business-name', required=True, help='Name of the business')
    parser.add_argument('--google-reviews-url', required=True, help='Google Maps reviews URL')
    parser.add_argument('--headless', type=bool, default=False, help='Run browser in headless mode')
    parser.add_argument('--max-reviews', type=int, default=50, help='Maximum number of reviews to scrape')
    
    args = parser.parse_args()
    
    print(f"Processing: {args.business_name}")
    print(f"Google Reviews URL: {args.google_reviews_url}")
    print(f"Headless mode: {args.headless}")
    
    # Scrape reviews and get both reviews and downloaded images
    result = scrape_google_maps_reviews(
        url=args.google_reviews_url,
        headless=args.headless,
        max_reviews=args.max_reviews
    )
    
    # Extract reviews and downloaded images from the result
    if isinstance(result, dict):
        scraped_reviews = result.get('reviews', [])
        downloaded_images = result.get('downloaded_images', [])
    else:
        # Fallback for old format
        scraped_reviews = result
        downloaded_images = []
    
    # Create comprehensive output with both reviews and image information
    output_data = {
        "business_name": args.business_name,
        "total_reviews": len(scraped_reviews),
        "total_images_downloaded": len(downloaded_images),
        "reviews": scraped_reviews,
        "downloaded_images": downloaded_images
    }
    
    # # Save scraped reviews to a JSON file (COMMENTED OUT - Pure memory storage)
    # RAW_DATA_DIR = "/Users/rhettburnham/Desktop/projects/roofing-co/public/data/output/individual/step_1/raw"
    # os.makedirs(RAW_DATA_DIR, exist_ok=True)
    # output_file = os.path.join(RAW_DATA_DIR, "reviews.json")
    # with open(output_file, "w", encoding="utf-8") as json_file:
    #     json.dump(output_data, json_file, ensure_ascii=False, indent=4)
    # print(f"Reviews saved to {output_file}")
    
    print(f"Successfully scraped {len(scraped_reviews)} reviews for {args.business_name}")
    print(f"Downloaded {len(downloaded_images)} images")
    
    # Print the scraped data to stdout for the API to capture
    print("SCRAPED_REVIEWS_DATA_START")
    print(json.dumps(output_data, ensure_ascii=False, indent=2))
    print("SCRAPED_REVIEWS_DATA_END")

