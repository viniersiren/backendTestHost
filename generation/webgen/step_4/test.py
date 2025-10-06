from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager
import requests
import os
import time
import re
from bs4 import BeautifulSoup
import urllib.parse
import logging
import traceback
import random
import json
import argparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Create output directory
def ensure_dir_exists(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)
        logging.info(f"Created directory: {directory}")

def clean_filename(name):
    """Clean the filename by removing invalid characters"""
    # Replace any character that isn't alphanumeric, space, or underscore with an underscore
    clean_name = re.sub(r'[^\w\s]', '_', name)
    # Replace multiple spaces with a single underscore
    clean_name = re.sub(r'\s+', '_', clean_name)
    return clean_name

def download_image(url, save_path):
    """Download image from URL and save to specified path"""
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        logging.info(f"Successfully downloaded: {save_path}")
        return True
    except Exception as e:
        logging.error(f"Failed to download {url}: {str(e)}")
        return False

def scroll_to_element(driver, element):
    """Scroll to make an element visible"""
    try:
        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
        time.sleep(0.3)  # Short delay for scroll to complete
    except Exception as e:
        logging.error(f"Error scrolling to element: {str(e)}")

def scroll_page(driver, scroll_amount=300, num_scrolls=10, delay=0.3):
    """Scroll down the page gradually to load content"""
    logging.info(f"Scrolling page to load content...")
    
    for i in range(num_scrolls):
        driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
        time.sleep(delay)
        
    # Scroll back to top
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(delay)

def extract_model_number(card):
    """Extract model number from a product card if available"""
    try:
        # Try to find the model number using the selector pattern
        model_div = card.find_elements(By.CSS_SELECTOR, "div.sui-flex.sui-text-xs.sui-text-subtle.sui-font-normal")
        if model_div:
            for div in model_div:
                text = div.text.strip()
                if text.startswith("Model#"):
                    # Extract the model number
                    model_number = text.replace("Model#", "").strip()
                    return model_number
        
        # Alternative selector
        model_div = card.find_elements(By.XPATH, ".//div[contains(text(), 'Model#')]")
        if model_div:
            for div in model_div:
                text = div.text.strip()
                model_number = text.replace("Model#", "").strip()
                return model_number
                
        return None
    except Exception as e:
        logging.error(f"Error extracting model number: {str(e)}")
        return None

def wait_for_model_number_change(driver, card, original_model, max_wait_time=None):
    """
    Wait indefinitely for model number to change after clicking a color variant button
    
    Args:
        driver: WebDriver instance
        card: Product card element
        original_model: Original model number to compare against
        max_wait_time: Maximum time to wait in seconds (None means wait indefinitely)
    
    Returns:
        New model number if changed, None otherwise
    """
    try:
        start_time = time.time()
        check_interval = 0.05  # Check every 50ms for faster response
        check_counter = 0
        
        while max_wait_time is None or time.time() - start_time < max_wait_time:
            # Check if model number has changed
            current_model = extract_model_number(card)
            
            # If we have a new valid model number that's different from the original
            if current_model and current_model != original_model:
                elapsed = time.time() - start_time
                logging.info(f"Model number changed from {original_model} to {current_model} after {elapsed:.2f} seconds")
                return current_model
            
            # Log progress every 20 seconds of waiting
            check_counter += 1
            if check_counter % 400 == 0:  # 400 * 0.05s = 20s
                elapsed = time.time() - start_time
                logging.info(f"Still waiting for model number to change... ({elapsed:.1f}s elapsed)")
                
            # Short wait before checking again (50ms)
            time.sleep(check_interval)
        
        # We should never reach here if max_wait_time is None
        if max_wait_time is not None:
            logging.info(f"Model number did not change from {original_model} after {max_wait_time} seconds")
        return None
    except Exception as e:
        logging.error(f"Error waiting for model number change: {str(e)}")
        return None

def get_card_data(card):
    """Extract all data (title, brand, model) from a card"""
    try:
        # Get brand
        try:
            brand_element = card.find_element(By.CSS_SELECTOR, "p[data-testid='attribute-brandname-above']")
            brand_text = brand_element.text.strip()
        except NoSuchElementException:
            brand_text = "Unknown"
        
        # Get product title
        try:
            title_element = card.find_element(By.CSS_SELECTOR, "span[data-testid='attribute-product-label']")
            title_text = title_element.text.strip()
        except NoSuchElementException:
            title_text = "Unknown Product"
        
        # Get model number
        model_number = extract_model_number(card)
        
        # Get image URL
        try:
            img_element = card.find_element(By.CSS_SELECTOR, "div[data-testid='product-image__wrapper'] img")
            img_url = img_element.get_attribute('src')
        except NoSuchElementException:
            img_url = None
            
        return {
            'brand': brand_text,
            'title': title_text,
            'model_number': model_number,
            'img_url': img_url
        }
    except Exception as e:
        logging.error(f"Error extracting card data: {str(e)}")
        return {'brand': 'Unknown', 'title': 'Unknown Product', 'model_number': None, 'img_url': None}

def process_card_variants_with_click(driver, card, output_dir, card_index):
    """Process a single product card and its variants using clicking approach"""
    image_metadata = []
    
    try:
        # Scroll card into view
        scroll_to_element(driver, card)
        
        # Get initial card data
        card_data = get_card_data(card)
        brand_text = card_data['brand']
        title_text = card_data['title']
        original_model_number = card_data['model_number']
        img_url = card_data['img_url']
        
        if not img_url:
            logging.warning(f"No image URL found for card {card_index}, skipping")
            return image_metadata
        
        # Create filename for main image
        full_title = f"{brand_text}_{title_text}"
        clean_title = clean_filename(full_title)
        filename = f"{card_index}_{clean_title}.jpg"
        save_path = os.path.join(output_dir, filename)
        
        # Download main image
        if download_image(img_url, save_path):
            logging.info(f"Product {card_index}: {full_title}")
            
            # Add metadata for main image
            image_metadata.append({
                'original_filename': filename,
                'brand': brand_text,
                'product': title_text,
                'type': 'main',
                'color': 'default',
                'index': card_index,
                'model_number': original_model_number
            })
            
            # Find color variant buttons
            color_buttons_container = card.find_elements(By.CSS_SELECTOR, "div.sui-inline-flex.sui-flex-wrap.sui-items-center")
            if color_buttons_container:
                color_buttons = color_buttons_container[0].find_elements(By.CSS_SELECTOR, "button[aria-pressed]")
                
                # Skip if no variant buttons or only one option
                if not color_buttons or len(color_buttons) <= 1:
                    return image_metadata
                
                # Process each variant (skip first button as it's already selected/processed)
                variant_count = 0
                for i, button in enumerate(color_buttons[1:], 1):
                    try:
                        # Random delay between variants (0.1-0.4 seconds)
                        random_delay = random.uniform(0.1, 0.4)
                        time.sleep(random_delay)
                        
                        # Skip if it's a "more" button
                        button_text = button.text.strip().lower()
                        if "more" in button_text or "+more" in button_text:
                            logging.info("Found 'more' button, skipping")
                            continue
                        
                        # Get the color name before action
                        color_value = button.get_attribute('value')
                        if not color_value:
                            # Try to get the color from the image
                            img_in_button = button.find_elements(By.TAG_NAME, "img")
                            if img_in_button:
                                alt_text = img_in_button[0].get_attribute('alt')
                                if alt_text:
                                    color_value = alt_text
                                else:
                                    src = img_in_button[0].get_attribute('src')
                                    if src:
                                        color_value = os.path.basename(src).split('.')[0]
                        
                        if not color_value:
                            color_value = f"variant_{i}"
                        
                        # Scroll to ensure button is visible
                        scroll_to_element(driver, button)
                        
                        # Click the button
                        logging.info(f"Clicking variant button and waiting for model number change...")
                        driver.execute_script("arguments[0].click();", button)
                        
                        # Wait for model number change after click - wait indefinitely
                        updated_model_number = wait_for_model_number_change(driver, card, original_model_number, max_wait_time=None)
                        
                        # We should always get a model number change since we wait indefinitely
                        # But let's add a safety check just in case
                        if not updated_model_number:
                            logging.warning(f"No model number change detected for variant {i} despite waiting. Skipping.")
                            continue
                        
                        # Get updated card data after model change
                        updated_card_data = get_card_data(card)
                        
                        # Get updated title (might change after click)
                        updated_title = updated_card_data['title']
                        
                        # If title didn't change but model did, use model in title
                        if (updated_title == title_text) and updated_model_number != original_model_number:
                            updated_title = f"{title_text} - {updated_model_number}"
                        # If neither changed, use color (though at this point we know model changed)
                        elif updated_title == title_text:
                            updated_title = f"{title_text} - {color_value}"
                        
                        # Get updated image URL
                        updated_img_url = updated_card_data['img_url']
                        if not updated_img_url:
                            logging.warning(f"No updated image URL found for variant {i}, skipping")
                            continue
                        
                        # Create filename with variant info
                        clean_updated_title = clean_filename(updated_title)
                        clean_color = clean_filename(color_value)
                        variant_count += 1
                        
                        # Include model number in filename
                        variant_filename = f"{card_index}_v{variant_count}_{clean_updated_title}_{clean_color}_model_{updated_model_number}.jpg"
                        
                        variant_save_path = os.path.join(output_dir, variant_filename)
                        
                        # Download variant image
                        if download_image(updated_img_url, variant_save_path):
                            logging.info(f"Downloaded color variant: {clean_color} for product {card_index}")
                            
                            # Add metadata for variant
                            image_metadata.append({
                                'original_filename': variant_filename,
                                'brand': brand_text,
                                'product': updated_title,
                                'type': 'variant',
                                'color': color_value,
                                'index': card_index * 1000 + variant_count,
                                'parent_filename': filename,
                                'model_number': updated_model_number,
                                'original_model_number': original_model_number
                            })
                        
                        # Random delay between variants (0.1-0.4 seconds)
                        random_delay = random.uniform(0.1, 0.4)
                        time.sleep(random_delay)
                        
                    except Exception as e:
                        logging.error(f"Error processing variant {i} for card {card_index}: {str(e)}")
                        traceback.print_exc()
        
    except Exception as e:
        logging.error(f"Error processing card {card_index}: {str(e)}")
        traceback.print_exc()
    
    return image_metadata

def get_pagination_links(driver):
    """Find pagination links to navigate through all pages"""
    try:
        pagination = driver.find_element(By.CSS_SELECTOR, "nav[aria-label='Pagination Navigation']")
        # Get all number buttons/links - exclude arrows
        page_links = pagination.find_elements(By.CSS_SELECTOR, "li a[aria-label^='Go to Page'], li a[aria-current='true'], li button[aria-label^='Go to Page']")
        
        # Extract max page number
        max_page = 1
        for link in page_links:
            try:
                page_text = link.text.strip()
                if page_text and page_text.isdigit():
                    page_num = int(page_text)
                    if page_num > max_page:
                        max_page = page_num
            except Exception:
                continue
                
        logging.info(f"Found {max_page} pages of results")
        return max_page
    except Exception as e:
        logging.error(f"Error finding pagination: {str(e)}")
        return 1  # Default to 1 page if pagination not found

def navigate_to_page(driver, page_num):
    """Navigate to a specific page"""
    try:
        logging.info(f"Navigating to page {page_num}")
        
        # Find pagination
        pagination = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "nav[aria-label='Pagination Navigation']"))
        )
        
        # Scroll to pagination
        scroll_to_element(driver, pagination)
        
        # Find the specific page link
        if page_num == 1:
            # First page might be specially marked
            page_link = pagination.find_element(By.CSS_SELECTOR, "li a[aria-current='true']")
        else:
            page_link = pagination.find_element(By.CSS_SELECTOR, f"li a[aria-label='Go to Page {page_num}'], li button[aria-label='Go to Page {page_num}']")
        
        # Click on the page link
        driver.execute_script("arguments[0].click();", page_link)
        
        # Wait for the page to load
        time.sleep(3)
        
        # Scroll the page to load all content
        scroll_page(driver)
        
        return True
    except NoSuchElementException:
        # Try using next button repeatedly if exact page link not found
        try:
            for _ in range(page_num - 1):
                next_button = pagination.find_element(By.CSS_SELECTOR, "li a[aria-label='Skip to Next Page']")
                driver.execute_script("arguments[0].click();", next_button)
                time.sleep(3)
                scroll_page(driver)
            return True
        except Exception as e:
            logging.error(f"Error navigating with next button: {str(e)}")
            return False
    except Exception as e:
        logging.error(f"Error navigating to page {page_num}: {str(e)}")
        return False

def scrape_products_one_by_one(max_pages=None, max_images=None):
    """
    Scrape images from the Home Depot website, one card at a time
    
    Args:
        max_pages (int, optional): Maximum number of pages to scrape. Default is all pages.
        max_images (int, optional): Maximum number of images to download. Default is all images.
    """
    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'raw_data', 'shingles')
    ensure_dir_exists(output_dir)
    
    # Set up Selenium WebDriver
    options = Options()
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    
    # Uncomment to run headless (no browser window)
    # options.add_argument("--headless")
    
    logging.info("Setting up Chrome WebDriver...")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    # Initialize list to store image metadata
    all_image_metadata = []
    
    try:
        # Navigate to the Home Depot roofing page
        url = 'https://www.homedepot.com/b/Building-Materials-Roofing/N-5yc1vZaq7m?NCNI-5&searchRedirect=roof&semanticToken=k27r10r10f22040000000e_202504010433278121042422963_us-east1-zxwv%20k27r10r10f22040000000e%20%3E%20st%3A%7Broof%7D%3Ast%20ml%3A%7B24%7D%3Aml%20nr%3A%7Broof%7D%3Anr%20nf%3A%7Bn%2Fa%7D%3Anf%20qu%3A%7Broof%7D%3Aqu%20ie%3A%7B0%7D%3Aie%20qr%3A%7Broof%7D%3Aqr'
        logging.info(f"Navigating to URL: {url}")
        driver.get(url)
        
        # Wait for the page to load
        time.sleep(5)
        
        # Initial scroll to load content
        scroll_page(driver)
        
        # Get total number of pages
        total_pages = get_pagination_links(driver)
        
        # Apply max_pages limit if specified
        if max_pages and max_pages > 0 and max_pages < total_pages:
            logging.info(f"Limiting scraping to {max_pages} pages (out of {total_pages})")
            total_pages = max_pages
        else:
            logging.info(f"Scraping all {total_pages} pages")
        
        # Initialize counters
        total_card_count = 0
        total_images_downloaded = 0
        
        # Process each page
        for current_page in range(1, total_pages + 1):
            # Check if we've reached the max images limit
            if max_images and total_images_downloaded >= max_images:
                logging.info(f"Reached maximum image limit of {max_images}. Stopping.")
                break
                
            if current_page > 1:
                # Navigate to next page
                if not navigate_to_page(driver, current_page):
                    logging.error(f"Failed to navigate to page {current_page}, skipping")
                    continue
            
            # Find all product cards on current page
            logging.info(f"Looking for product cards on page {current_page}...")
            
            # Wait for product cards to be visible after page navigation
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#browse-search-pods-1 > div, div.results-wrapped div.sui-relative.sui-flex.sui-flex-col.sui-h-full"))
            )
            
            product_cards = driver.find_elements(By.CSS_SELECTOR, "#browse-search-pods-1 > div > div > div")
            
            if not product_cards:
                logging.info("No product cards found with primary selector. Trying alternate selector...")
                product_cards = driver.find_elements(By.CSS_SELECTOR, "div.results-wrapped div.sui-relative.sui-flex.sui-flex-col.sui-h-full")
            
            if not product_cards:
                logging.warning(f"No product cards found on page {current_page}, skipping")
                continue
                
            logging.info(f"Found {len(product_cards)} product cards on page {current_page}")
            
            # Process each card individually
            page_images_count = 0
            
            for i, card in enumerate(product_cards):
                card_index = total_card_count + i + 1
                
                # Check if we're approaching the max images limit
                if max_images and total_images_downloaded >= max_images:
                    logging.info(f"Reached maximum image limit of {max_images}. Stopping.")
                    break
                
                # Process this card and its variants
                logging.info(f"Processing card {card_index} of {total_card_count + len(product_cards)}...")
                card_metadata = process_card_variants_with_click(driver, card, output_dir, card_index)
                
                # Update counters
                card_images_count = len(card_metadata)
                page_images_count += card_images_count
                total_images_downloaded += card_images_count
                
                # Add metadata
                all_image_metadata.extend(card_metadata)
                
                # Log progress
                if max_images:
                    logging.info(f"Downloaded {total_images_downloaded} of maximum {max_images} images")
                
                # Brief pause between cards
                time.sleep(0.2)
            
            # Update total card count
            total_card_count += len(product_cards)
            
            logging.info(f"Page {current_page} complete: {page_images_count} images downloaded")
            logging.info(f"Running total: {total_images_downloaded} images")
        
        logging.info(f"Scraping complete! Downloaded {total_images_downloaded} images from {total_card_count} products")
        
        # Save metadata to JSON file
        metadata_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'step_4', 'shingle_images_metadata.json')
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(all_image_metadata, f, indent=2)
        logging.info(f"Saved metadata for {len(all_image_metadata)} images to {metadata_file}")
        
    except Exception as e:
        logging.error(f"Error during scraping: {str(e)}")
        traceback.print_exc()
        
        # Save metadata even if there was an error
        if all_image_metadata:
            metadata_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'step_4', 'shingle_images_metadata.json')
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(all_image_metadata, f, indent=2)
            logging.info(f"Saved metadata for {len(all_image_metadata)} images to {metadata_file}")
    finally:
        driver.quit()
        logging.info("WebDriver closed")

def count_images():
    """Count the number of shingle images downloaded"""
    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'raw_data', 'shingles')
    
    try:
        # Get all jpg files in the directory
        image_files = [f for f in os.listdir(output_dir) if f.endswith('.jpg')]
        
        # Count total images
        total_images = len(image_files)
        
        # Count main products vs variants
        main_images = len([f for f in image_files if not "_v" in f])
        variant_images = total_images - main_images
        
        logging.info(f"Image Statistics:")
        logging.info(f"Total images: {total_images}")
        logging.info(f"Main product images: {main_images}")
        logging.info(f"Variant images: {variant_images}")
        
        return total_images, main_images, variant_images
        
    except Exception as e:
        logging.error(f"Error counting images: {str(e)}")
        return 0, 0, 0

if __name__ == "__main__":
    # Set up command line argument parsing
    parser = argparse.ArgumentParser(description='Download shingle images from Home Depot - Optimized Version')
    parser.add_argument('--max-pages', type=int, help='Maximum number of pages to scrape (default: all pages)')
    parser.add_argument('--max-images', type=int, help='Maximum number of images to download (default: all images)')
    
    args = parser.parse_args()
    
    logging.info("Starting optimized Home Depot image scraper")
    logging.info(f"Max pages: {args.max_pages if args.max_pages else 'All'}")
    logging.info(f"Max images: {args.max_images if args.max_images else 'All'}")
    logging.info(f"Using CLICK approach and waiting INDEFINITELY for model number changes")
    logging.info(f"Processing products strictly ONE BY ONE with randomized delays (0.1-0.4s) between variants")
    
    # Run the optimized scraper
    scrape_products_one_by_one(max_pages=args.max_pages, max_images=args.max_images)
    
    # Count downloaded images
    count_images()
    
    logging.info("Script completed") 