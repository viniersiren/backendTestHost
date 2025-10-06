#!/usr/bin/env python3
# public/data/generation/webgen/step_2/google_img_web.py

import os
import sys
import argparse
import time
import random
import logging
import json
import subprocess
import requests
from bs4 import BeautifulSoup
import importlib.util
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys

try:
    # Prefer chromedriver_py just like ScrapeReviews.py
    from chromedriver_py import binary_path  # type: ignore
except Exception:
    binary_path = None
    try:
        from webdriver_manager.chrome import ChromeDriverManager  # type: ignore
    except Exception:
        ChromeDriverManager = None  # type: ignore


OUTPUT_DIR = "/Users/rhettburnham/Desktop/projects/roofing-co/public/data/output/individual/step_2/gmaps_photos"

# Tunables for performance and reliability
SCROLL_SLEEP_MIN = 0.15
SCROLL_SLEEP_MAX = 0.30
NO_GROWTH_THRESHOLD_DEFAULT = 2  # Reduced from 3 for faster bottom-button attempts


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
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-infobars")
    options.add_argument("--incognito")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    # Disable images for faster loading (we still scrape URLs from styles)
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

    try:
        if binary_path:
            driver = webdriver.Chrome(service=Service(binary_path), options=options)
        elif ChromeDriverManager is not None:
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        else:
            driver = webdriver.Chrome(options=options)
    except Exception as e:
        # One more fallback using webdriver_manager if available
        if ChromeDriverManager is not None:
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        else:
            raise e

    try:
        driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
    except Exception:
        pass
    return driver


def create_manual_navigation_html(url: str) -> str:
    """
    Create a lightweight HTML page instructing the user to open the target
    Google Maps URL in a new tab. Returns the absolute path to the HTML file.
    """
    try:
        temp_dir = os.path.join("public", "data", "output", "leads", "temp")
        os.makedirs(temp_dir, exist_ok=True)
        html_file = os.path.join(temp_dir, "manual_navigation_google.html")

        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset=\"utf-8\" />
          <title>Google Maps Manual Navigation</title>
          <style>
            body { font-family: Arial, sans-serif; margin: 40px; background: #0f172a; color: #e2e8f0; }
            .container { background: #111827; padding: 24px; border-radius: 12px; max-width: 820px; margin: 0 auto; box-shadow: 0 8px 24px rgba(0,0,0,0.35); }
            h1 { margin: 0 0 12px; font-size: 22px; }
            .url-box { background:#0b1220; border:1px solid #1f2937; padding: 12px; border-radius: 8px; word-break: break-all; font-family: monospace; color:#93c5fd; }
            .button { margin-top: 16px; background:#2563eb; color:#fff; padding: 12px 18px; border-radius: 8px; border:none; cursor:pointer; font-weight: 700; }
            .button:hover { background:#1d4ed8; }
            .countdown { margin-top: 14px; color:#60a5fa; font-weight:600; }
            .tips { margin-top: 16px; color:#9ca3af; font-size: 14px; }
          </style>
        </head>
        <body>
          <div class=\"container\">
            <h1>Manual Google Maps Navigation</h1>
            <p>Click the button below to open the Google Maps URL in a new tab. Complete any prompts. The scraper will switch to your tab automatically.</p>
            <div class=\"url-box\">URL_PLACEHOLDER</div>
            <button class=\"button\" onclick=\"window.open('URL_PLACEHOLDER', '_blank')\">Open Google Maps</button>
            <div class=\"countdown\">Starting in <span id=\"count\">30</span> seconds...</div>
            <div class=\"tips\">Keep this window open. Make sure the new tab is on Google Maps for the target place.</div>
          </div>
          <script>
            let c = 30; const el = document.getElementById('count');
            const t = setInterval(() => { c--; if (el) el.textContent = c; if (c <= 0) clearInterval(t); }, 1000);
          </script>
        </body>
        </html>
        """
        html_content = html_content.replace("URL_PLACEHOLDER", url)
        with open(html_file, "w", encoding="utf-8") as f:
            f.write(html_content)
        return os.path.abspath(html_file)
    except Exception:
        return ""


def wait_for_manual_navigation(driver, target_domain_hint: str = "google.com") -> bool:
    """
    Wait ~30 seconds, then attempt to switch to a non-file window that looks
    like Google Maps. Returns True on success.
    """
    try:
        initial_window = driver.current_window_handle
        time.sleep(30)

        all_windows = driver.window_handles
        for w in all_windows:
            try:
                if w == initial_window:
                    continue
                driver.switch_to.window(w)
                cur = driver.current_url.lower()
                if target_domain_hint in cur:
                    return True
                # Accept any non-file URL as a potential success
                if not cur.startswith("file://"):
                    return True
            except Exception:
                continue
    except Exception:
        return False
    return False


def extract_image_url_from_style(style_attribute: str):
    try:
        if 'background-image' in style_attribute:
            # url("...") or url('...')
            start = style_attribute.find('url(')
            if start != -1:
                start_q = style_attribute.find('"', start)
                alt_start_q = style_attribute.find("'", start)
                if start_q == -1 or (alt_start_q != -1 and alt_start_q < start_q):
                    start_q = alt_start_q
                if start_q != -1:
                    end_q = style_attribute.find(style_attribute[start_q], start_q + 1)
                    if end_q != -1:
                        return style_attribute[start_q + 1:end_q]
    except Exception:
        return None
    return None


def download_image_from_url(image_url: str, save_dir: str, filename: str) -> bool:
    try:
        os.makedirs(save_dir, exist_ok=True)
        resp = requests.get(image_url, timeout=20)
        resp.raise_for_status()
        with open(os.path.join(save_dir, filename), 'wb') as f:
            f.write(resp.content)
        return True
    except Exception as e:
        logging.error(f"Failed to download {image_url}: {e}")
        return False


def try_click(driver, selector: str, timeout: int = 8) -> bool:
    """Attempt multiple strategies to click the target element."""
    try:
        # Wait for presence and (ideally) clickable state
        try:
            el = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
            )
            el.click()
            return True
        except Exception:
            el = WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
            )
        # Scroll into view and try JS click
        driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", el)
        time.sleep(0.15)
        try:
            driver.execute_script("arguments[0].click();", el)
            return True
        except Exception:
            pass
        # ActionChains click
        try:
            ActionChains(driver).move_to_element(el).pause(0.2).click(el).perform()
            return True
        except Exception:
            pass
        # Key-based activation
        try:
            el.send_keys(Keys.ENTER)
            return True
        except Exception:
            pass
        try:
            el.send_keys(Keys.SPACE)
            return True
        except Exception:
            pass
    except Exception:
        return False
    return False


def js_click_with_retries(driver, selector: str, attempts: int = 10, sleep_sec: float = 0.2) -> bool:
    """Rapid JS-based click attempts for speed-sensitive controls."""
    for _ in range(max(1, attempts)):
        try:
            clicked = driver.execute_script(
                "var el=document.querySelector(arguments[0]); if(!el){return false;} var btn=el.closest('button')||el; btn.click(); return true;",
                selector
            )
            if clicked:
                return True
        except Exception:
            pass
        time.sleep(sleep_sec)
    return False


def maybe_handle_google_consent(driver):
    """Dismiss Google consent/accept banners if they appear."""
    try:
        # Quick JS search by innerText to avoid fragile selectors
        script = (
            "var labels=['accept all','i agree','accept','agree'];"
            "var nodes=Array.from(document.querySelectorAll('button, input[type=\"submit\"]'));"
            "for (var n of nodes){ var t=(n.innerText||n.value||'').toLowerCase();"
            " for (var l of labels){ if(t.includes(l)){ n.click(); return true; } } }"
            "return false;"
        )
        if driver.execute_script(script):
            logging.info("Dismissed consent banner via JS innerText match.")
            time.sleep(0.25)
            return
        # Fallback: common aria-labels
        candidates = [
            "button[aria-label*='Accept']",
            "button[aria-label*='agree']",
        ]
        for sel in candidates:
            if try_click(driver, sel, timeout=2):
                logging.info(f"Dismissed consent banner via selector: {sel}")
                time.sleep(0.25)
                return
    except Exception:
        pass

def scrape_google_maps_photos(url: str, headless: bool = False, max_scroll_attempts: int = 20):
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logging.info(f"[google_img_web] Effective headless param: {headless}")

    # Import ScrapeReviews.web_driver to mimic EXACT driver behavior when available
    driver = None
    try:
        reviews_path = Path(__file__).resolve().parents[1] / 'step_1' / 'ScrapeReviews.py'
        if reviews_path.exists():
            spec = importlib.util.spec_from_file_location('ScrapeReviews', str(reviews_path))
            mod = importlib.util.module_from_spec(spec)
            assert spec and spec.loader
            spec.loader.exec_module(mod)
            if hasattr(mod, 'web_driver'):
                # Force visible regardless of CLI flag
                driver = mod.web_driver(headless=False)
                logging.info('Initialized WebDriver via ScrapeReviews.web_driver (forced visible)')
    except Exception as e:
        logging.warning(f'Falling back to local web_driver due to import error: {e}')
        driver = None

    if driver is None:
        # Force visible regardless of CLI flag
        driver = web_driver(headless=False)
        logging.info('Initialized WebDriver via local web_driver (forced visible)')

    try:
        # Minimal marker that a Chrome window is up
        print("LAUNCHED_BROWSER")
    except Exception:
        pass

    # Position visible window on macOS right half
    # Position visible window on macOS right half (we force visible above)
    if sys.platform == 'darwin':
        _position_window_right_half(driver)

    images = []
    unique_urls = set()
    try:
        # Normalize URL to https://www.google.com to reduce redirects
        try:
            if isinstance(url, str) and url.startswith('http://google.com'):
                url = url.replace('http://google.com', 'https://www.google.com', 1)
        except Exception:
            pass

        # Direct navigation, similar to ScrapeReviews.py startup
        logging.info(f"Navigating to URL: {url}")
        driver.get(url)

        # Handle consent overlays quickly
        maybe_handle_google_consent(driver)

        # Wait for main content (mirror reviews flow)
        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.w6VYqd"))
            )
            logging.info("Main page loaded.")
        except Exception as e:
            logging.error(f"Main page did not load: {e}")
            return {"images": [], "saved": 0}

        # Small settle delay only
        time.sleep(0.2)

        # FAST CLICK: Try the top-left Photos filter button immediately
        fast_first_button_selector = "#QA0Szd > div > div > div.w6VYqd > div.bJzME.tTVLSc > div > div.e07Vkf.kA9KIf > div > div > div:nth-child(1) > div > div > button:nth-child(1)"
        try:
            clicked_fast = js_click_with_retries(driver, fast_first_button_selector, attempts=10, sleep_sec=0.15)
            if clicked_fast:
                logging.info("Clicked fast first Photos filter button.")
            else:
                # Minimal fallback wait
                try_click(driver, fast_first_button_selector, timeout=2)
        except Exception:
            pass

        # Attempt to click the provided image/button path first (if present)
        primary_img_selector = "#QA0Szd > div > div > div.w6VYqd > div:nth-child(2) > div > div.e07Vkf.kA9KIf > div > div > div:nth-child(18) > div.fp2VUc > div.cRLbXd > div.dryRY > div:nth-child(1) > button > img"
        clicked = False
        try:
            el_present = WebDriverWait(driver, 4).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, primary_img_selector))
            )
            try:
                # Click closest button if available, else click the image
                driver.execute_script(
                    "var el=document.querySelector(arguments[0]); if(!el){return false;} var btn=el.closest('button')||el; btn.click(); return true;",
                    primary_img_selector
                )
                logging.info("Clicked primary image/button selector via JS parent button.")
                clicked = True
            except Exception:
                pass
        except Exception:
            pass

        # If that failed, click Photos tab/button (multiple fallbacks + robust clicking)
        if not clicked:
            selectors = [
                "button[role='tab'][aria-label*='Photos']",
                "#QA0Szd > div > div > div.w6VYqd > div:nth-child(2) > div > div.e07Vkf.kA9KIf > div > div > div:nth-child(3) > div > div > button.hh2c6.G7m0Af",
                "#QA0Szd > div > div > div.w6VYqd > div.bJzME.tTVLSc > div > div.e07Vkf.kA9KIf > div > div > div:nth-child(1) > div > div > button:nth-child(1) > div.LRkQ2 > div.a52Cae",
                "div.bJzME.tTVLSc div.e07Vkf.kA9KIf div:nth-child(1) div button:nth-child(1) div.LRkQ2 div.a52Cae",
            ]
            for sel in selectors:
                if try_click(driver, sel, timeout=8):
                    logging.info(f"Clicked photo-related control via selector: {sel}")
                    clicked = True
                    break
        if not clicked:
            logging.error("Could not locate a clickable Photos control.")
            return {"images": [], "saved": 0}

        time.sleep(0.3)

        # Locate the scrollable container (use requested selector as primary)
        scroll_container = None
        primary_container = "#QA0Szd > div > div > div.w6VYqd > div:nth-child(2) > div > div.e07Vkf.kA9KIf"
        try:
            scroll_container = WebDriverWait(driver, 6).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, primary_container))
            )
            logging.info(f"Found scroll container (primary): {primary_container}")
        except TimeoutException:
            container_selectors = [
                "#QA0Szd > div > div > div.w6VYqd > div:nth-child(2) > div > div.e07Vkf.kA9KIf > div",
                "#QA0Szd div.e07Vkf.kA9KIf",
                "div.m6QErb.DxyBCb.kA9KIf.dS8AEf.XiKgde",
            ]
            for sel in container_selectors:
                try:
                    scroll_container = WebDriverWait(driver, 6).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, sel))
                    )
                    logging.info(f"Found scroll container (fallback): {sel}")
                    break
                except TimeoutException:
                    continue

        def get_tile_count() -> int:
            try:
                return int(driver.execute_script("return document.querySelectorAll(\"div.Uf0tqf[style*='background-image']\").length;"))
            except Exception:
                return 0

        # Scroll to load images: prefer container scrolling, fallback to window scrolling, monitor tile count
        attempts = 0
        prev_count = get_tile_count()
        logging.info(f"Initial photo tiles count: {prev_count}")
        no_growth_threshold = NO_GROWTH_THRESHOLD_DEFAULT
        while attempts < max_scroll_attempts:
            try:
                if scroll_container is not None:
                    driver.execute_script("arguments[0].scrollTo(0, arguments[0].scrollHeight);", scroll_container)
                else:
                    # Container not found; try window scroll
                    driver.execute_script("window.scrollBy(0, 1200);")
                # Nudge scroll up/down to trigger lazy loads
                driver.execute_script("window.scrollBy(0, 200);")
                driver.execute_script("window.scrollBy(0, -120);")
            except Exception:
                pass

            time.sleep(random.uniform(SCROLL_SLEEP_MIN, SCROLL_SLEEP_MAX))

            # If we didn't have a container, try to locate it again as DOM may have changed
            if scroll_container is None:
                for sel in container_selectors:
                    try:
                        scroll_container = driver.find_element(By.CSS_SELECTOR, sel)
                        logging.info(f"Found scroll container late: {sel}")
                        break
                    except Exception:
                        continue

            new_count = get_tile_count()
            if new_count > prev_count:
                logging.info(f"Loaded more tiles: {prev_count} -> {new_count}")
                prev_count = new_count
                attempts = 0
            else:
                attempts += 1
                logging.info(f"No new tiles. Attempt {attempts}/{max_scroll_attempts}")
                # When bottom is hit (a few consecutive no-growth attempts), click the bottom button robustly
                if attempts >= no_growth_threshold:
                    bottom_button_selector = "#QA0Szd > div > div > div.w6VYqd > div:nth-child(2) > div > div.e07Vkf.kA9KIf > div > div > div:nth-child(18) > div.fp2VUc > div.cRLbXd > div.dryRY > div:nth-child(1) > button"
                    try:
                        el = driver.execute_script("return document.querySelector(arguments[0])", bottom_button_selector)
                        if el:
                            # Ensure in view
                            driver.execute_script("arguments[0].scrollIntoView({block:'center', inline:'center'});", el)
                            time.sleep(0.1)
                            # Try native click first via wait
                            try:
                                if try_click(driver, bottom_button_selector, timeout=2):
                                    logging.info("Clicked bottom button via try_click.")
                                else:
                                    # JS retries
                                    if js_click_with_retries(driver, bottom_button_selector, attempts=6, sleep_sec=0.1):
                                        logging.info("Clicked bottom button via JS retries.")
                                    else:
                                        # ActionChains fallback
                                        try:
                                            ActionChains(driver).move_to_element(el).pause(0.1).click(el).perform()
                                            logging.info("Clicked bottom button via ActionChains.")
                                        except Exception:
                                            logging.info("Bottom button click attempts failed.")
                            finally:
                                # Brief wait to allow any dynamic load
                                time.sleep(0.2)
                    except Exception:
                        pass

        # Final attempt to click the provided bottom button after scroll loop
        try:
            bottom_button_selector = "#QA0Szd > div > div > div.w6VYqd > div:nth-child(2) > div > div.e07Vkf.kA9KIf > div > div > div:nth-child(18) > div.fp2VUc > div.cRLbXd > div.dryRY > div:nth-child(1) > button"
            el = driver.execute_script("return document.querySelector(arguments[0])", bottom_button_selector)
            if el:
                driver.execute_script("arguments[0].scrollIntoView({block:'center', inline:'center'});", el)
                time.sleep(0.1)
                if not try_click(driver, bottom_button_selector, timeout=2):
                    js_click_with_retries(driver, bottom_button_selector, attempts=6, sleep_sec=0.1)
                time.sleep(0.2)
                # Nudge scroll once more to trigger any lazy load
                try:
                    if scroll_container is not None:
                        driver.execute_script("arguments[0].scrollTo(0, arguments[0].scrollHeight);", scroll_container)
                    else:
                        driver.execute_script("window.scrollBy(0, 1200);")
                except Exception:
                    pass
        except Exception:
            pass

        logging.info("Finished scrolling. Parsing page source for images.")

        soup = BeautifulSoup(driver.page_source, "html.parser")

        # Target the photo grid area first if present
        grid_parent = soup.select_one(
            "#QA0Szd div.m6QErb.DxyBCb.kA9KIf.dS8AEf.XiKgde div.m6QErb.XiKgde"
        )
        search_scope = grid_parent if grid_parent else soup

        # Find divs that carry background-image style (Google photo tiles)
        tiles = search_scope.select("div.Uf0tqf[style*='background-image']")
        logging.info(f"Found {len(tiles)} tiles with background images.")

        # Fallback: also collect from <img> tags if present
        img_nodes = search_scope.select("img[src*='googleusercontent']") or search_scope.select("img[src*='gstatic']")
        if img_nodes:
            logging.info(f"Found {len(img_nodes)} <img> nodes with potential photo sources.")
        else:
            logging.info("No <img> nodes matched googleusercontent/gstatic patterns.")

        idx = 0
        for tile in tiles:
            style_attr = tile.get('style', '')
            url = extract_image_url_from_style(style_attr)
            if url and url not in unique_urls:
                unique_urls.add(url)
                idx += 1
                images.append({
                    "index": idx,
                    "url": url,
                    "filename": f"gmaps_photo_{idx}.jpg"
                })

        # Add img srcs as secondary source
        for node in img_nodes:
            try:
                src = node.get('src') or ''
                if not src:
                    continue
                if src.startswith('data:'):
                    continue
                if src not in unique_urls:
                    unique_urls.add(src)
                    idx += 1
                    images.append({
                        "index": idx,
                        "url": src,
                        "filename": f"gmaps_photo_{idx}.jpg"
                    })
            except Exception:
                continue

        logging.info(f"Collected {len(images)} unique image URLs.")

        # Download
        saved = 0
        for img in images:
            if download_image_from_url(img["url"], OUTPUT_DIR, img["filename"]):
                saved += 1

        return {"images": images, "saved": saved, "output_dir": OUTPUT_DIR}

    finally:
        try:
            driver.quit()
        except Exception:
            pass


def main():
    def str2bool(v):
        if isinstance(v, bool):
            return v
        s = str(v).strip().lower()
        if s in ('yes', 'true', 't', '1', 'y'): return True
        if s in ('no', 'false', 'f', '0', 'n', ''): return False
        return False

    parser = argparse.ArgumentParser(description='Scrape Google Maps business photos')
    parser.add_argument('--business-name', required=True, help='Name of the business')
    parser.add_argument('--google-maps-url', help='Google Maps URL (same URL used for reviews/photos)')
    parser.add_argument('--google-reviews-url', help='Alias for the same Google Maps URL (compat)')
    parser.add_argument('--headless', type=str2bool, nargs='?', const=True, default=False, help='Run browser in headless mode')
    parser.add_argument('--max-scroll-attempts', type=int, default=20, help='Max consecutive scroll attempts with no growth')

    args = parser.parse_args()

    url = args.google_maps_url or args.google_reviews_url
    if not url:
        # Emit empty structured block rather than exiting with non-zero
        output = {
            "business_name": args.business_name,
            "total_images": 0,
            "total_saved": 0,
            "output_dir": OUTPUT_DIR,
            "images": [],
            "error": "Missing google maps url"
        }
        print("SCRAPED_PHOTOS_DATA_START")
        print(json.dumps(output, ensure_ascii=False, indent=2))
        print("SCRAPED_PHOTOS_DATA_END")
        return

    print(f"Processing: {args.business_name}")
    print(f"Google Maps URL: {url}")
    print(f"Headless mode: {args.headless}")

    try:
        result = scrape_google_maps_photos(
            url=url,
            headless=args.headless,
            max_scroll_attempts=args.max_scroll_attempts
        )
    except Exception as e:
        # Ensure we always emit a block so backend can parse it
        result = {"images": [], "saved": 0, "error": str(e)}

    # Emit structured output for API to capture
    output = {
        "business_name": args.business_name,
        "total_images": len(result.get('images', [])),
        "total_saved": result.get('saved', 0),
        "output_dir": result.get('output_dir', OUTPUT_DIR),
        "images": result.get('images', []),
    }
    if result.get('error'):
        output['error'] = result.get('error')

    print("SCRAPED_PHOTOS_DATA_START")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    print("SCRAPED_PHOTOS_DATA_END")


if __name__ == "__main__":
    main()


