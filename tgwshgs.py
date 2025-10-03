import re
import json
import time
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

def parse_count(text: str) -> int:
    """Parse views text like '12.3K' to integer (12300)."""
    if not text:
        return 0
    text = re.sub(r'[^\d.KMB]', '', text.strip().upper())
    if text.endswith('K'):
        return int(float(text[:-1]) * 1000)
    elif text.endswith('M'):
        return int(float(text[:-1]) * 1000000)
    elif text.endswith('B'):
        return int(float(text[:-1]) * 1000000000)
    else:
        try:
            return int(text)
        except ValueError:
            return 0

def scrape_views(post_url: str) -> int:
    """Scrape views from a TikTok post URL."""
    options = Options()
    # options.add_argument("--headless=new")  # Uncomment for headless (no browser window)
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")  # Suppress GPU errors
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,800")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-web-security")  # Helps with some loading issues
    options.add_argument("--disable-features=VizDisplayCompositor")  # Reduce detection
    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # Optional proxy (uncomment and replace if blocked/direct IP fails)
    # options.add_argument("--proxy-server=http://103.187.111.3:80")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    driver.execute_script("Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]})")
    
    try:
        driver.get(post_url)
        wait = WebDriverWait(driver, 30)  # Increased timeout
        
        # Wait for page body
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        
        # Aggressive scrolling to load dynamic content (TikTok needs this)
        for _ in range(5):  # More scrolls
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")
            time.sleep(2)
        driver.execute_script("window.scrollTo(0, 0);")  # Scroll back up
        time.sleep(3)  # Extra wait for JS
        
        print(f"Page source length: {len(driver.page_source)}")  # Debug: Should be >100k for full load
        
        # Extract post ID from URL for JSON lookup
        post_id = post_url.split("/video/")[-1].split("?")[0].split("#")[0]
        print(f"Scraping views for post ID: {post_id}")
        
        # Try expanded CSS fallback first (more selectors for views)
        views_css = 0
        css_selectors = [
            'strong[data-e2e="video-views"]',
            '[data-e2e="video-views"] strong',
            '.video-meta-item-views strong',
            '[data-e2e="share-video-views"]',
            '.xgqpgg strong',  # Common TikTok class for counts
            'div[role="button"] strong'  # Generic for engagement counts
        ]
        for selector in css_selectors:
            try:
                views_el = driver.find_element(By.CSS_SELECTOR, selector)
                text = views_el.text.strip()
                if 'view' in text.lower() or any(c in text for c in ['K', 'M', 'B']):  # Validate it's views
                    views_css = parse_count(text)
                    print(f"CSS fallback views ({selector}): {views_css}")
                    break
            except NoSuchElementException:
                continue
        if views_css == 0:
            print("No CSS views found with any selector")
        
        # Primary: JSON from #SIGI_STATE (with polling loop for reliability)
        views_json = 0
        max_attempts = 15  # 30s total (2s per attempt)
        for attempt in range(max_attempts):
            try:
                # Check for SIGI_STATE script
                script_el = driver.find_element(By.CSS_SELECTOR, "script#SIGI_STATE")
                script_text = script_el.get_attribute("innerHTML")
                print(f"Attempt {attempt + 1}: SIGI_STATE length: {len(script_text) if script_text else 0}")
                
                if script_text and len(script_text.strip()) > 100:  # Ensure content
                    soup = BeautifulSoup(script_text, "lxml")  # Parse directly from attribute
                    data = json.loads(script_text)
                    # Find post data
                    item = data.get("ItemModule", {}).get(post_id, {})
                    if not item:
                        # Fallback search across modules
                        for module in data.values():
                            if isinstance(module, dict) and post_id in module:
                                item = module[post_id]
                                print(f"Found item in module: {post_id}")
                                break
                    if item:
                        stats = item.get("stats", {})
                        views_json = int(stats.get("playCount", 0))
                        print(f"JSON views found: {views_json}")
                        break  # Success, exit loop
                    else:
                        print(f"Post item not found in JSON (attempt {attempt + 1})")
            except Exception as e:
                print(f"Exception in JSON parsing attempt {attempt + 1}: {e}")
                time.sleep(2)
    except Exception as e:
        print(f"Exception in scrape_views: {e}")
    finally:
        driver.quit()