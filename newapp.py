import re
import json
import time
import logging
from typing import Optional
from datetime import datetime, timedelta
from json import JSONDecodeError
from bs4 import BeautifulSoup
from fastapi import FastAPI, Query
from seleniumwire import webdriver  # Updated: Use selenium-wire for proxies
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="TikTok Scraper API")

def create_driver():
    chrome_options = Options()
    # chrome_options.add_argument("--headless=new")  # Comment out for debugging (watch browser)
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1280,1600")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # Selenium-wire proxy options (this is where you add the proxy)
    seleniumwire_options = {
        'proxy': {
            'http': 'http://20.210.113.32:80',  # Replace with a working proxy (e.g., from free-proxy-list.net)
            'https': 'http://20.210.113.32:80',  # Same proxy for HTTPS
            'no_proxy': 'localhost,127.0.0.1'  # Exclude local addresses
        }
    }
    
    # Optional: Add proxy auth if your proxy requires username/password
    # seleniumwire_options['proxy']['username'] = 'your_username'
    # seleniumwire_options['proxy']['password'] = 'your_password'
    
    # Create driver with both Chrome and Selenium-wire options
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=chrome_options,
        seleniumwire_options=seleniumwire_options
    )
    
    # Stealth scripts
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    driver.execute_script("Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]})")
    
    return driver

def parse_count(text: str) -> Optional[int]:
    if not text:
        return None
    # Improved cleaning: Remove all non-alphanumeric except K/M/B
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
            return None

def parse_relative_time(relative_text: str) -> Optional[int]:
    """Approximate Unix timestamp from relative time like '2 days ago'."""
    if not relative_text:
        return None
    now = datetime.now()
    try:
        num = int(re.search(r'(\d+)', relative_text).group(1))
        if 'second' in relative_text or 's' in relative_text:
            return int((now - timedelta(seconds=num)).timestamp())
        elif 'minute' in relative_text or 'm' in relative_text:
            return int((now - timedelta(minutes=num)).timestamp())
        elif 'hour' in relative_text or 'h' in relative_text:
            return int((now - timedelta(hours=num)).timestamp())
        elif 'day' in relative_text or 'd' in relative_text:
            return int((now - timedelta(days=num)).timestamp())
        elif 'week' in relative_text or 'w' in relative_text:
            return int((now - timedelta(weeks=num * 7)).timestamp())
        # Add more if needed (month/year)
    except:
        pass
    return None

def scrape_post_details(driver, username: str, post_id: str) -> dict:
    url = f"https://www.tiktok.com/@{username}/video/{post_id}"
    driver.get(url)
    
    wait = WebDriverWait(driver, 15)  # Increased timeout
    try:
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        # Multiple scrolls to trigger full loading
        for _ in range(2):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")
            time.sleep(1)
        time.sleep(2)  # Extra wait for JS
        print(f"Page loaded for post {post_id}, source length: {len(driver.page_source)}")  # Debug print
    except TimeoutException:
        print(f"Timeout loading page for post {post_id}")  # Debug print
        return {"post_id": post_id, "error": "Page load timeout"}
    
    # Extract likes, comments, shares via CSS (reliable)
    likes = None
    try:
        likes_el = driver.find_element(By.CSS_SELECTOR, 'strong[data-e2e="like-count"]')
        likes = parse_count(likes_el.text)
    except NoSuchElementException:
        pass
    
    comments = None
    try:
        comments_el = driver.find_element(By.CSS_SELECTOR, 'strong[data-e2e="comment-count"]')
        comments = parse_count(comments_el.text)
    except NoSuchElementException:
        pass
    
    shares = None
    try:
        shares_el = driver.find_element(By.CSS_SELECTOR, 'strong[data-e2e="share-count"]')
        shares = parse_count(shares_el.text)
    except NoSuchElementException:
        pass
    
    # Fallback for views via CSS
    views_css = None
    try:
        views_el = driver.find_element(By.CSS_SELECTOR, 'strong[data-e2e="video-views"], [data-e2e="video-views"] strong, .video-meta-item-views strong, .tiktok-1qmt4c-DivVideoMetaItem')
        views_css = parse_count(views_el.text)
        print(f"CSS views fallback for {post_id}: {views_css}")  # Debug
    except NoSuchElementException:
        pass
    
    # Fallback for description via CSS/BS4
    description_css = None
    try:
        desc_el = driver.find_element(By.CSS_SELECTOR, '[data-e2e="video-desc"], .video-caption, .desc-text, [data-e2e="browse-video-desc"]')
        description_css = desc_el.text.strip()
        print(f"CSS description fallback for {post_id}: {description_css[:50]}...")  # Debug preview
    except NoSuchElementException:
        pass
    
    # Fallback for timestamp via CSS (relative time)
    timestamp_css = None
    try:
        time_el = driver.find_element(By.CSS_SELECTOR, '[data-e2e="video-time"], .video-time, time, [data-e2e="browse-video-time"]')
        relative_time = time_el.text.strip().lower()
        timestamp_css = parse_relative_time(relative_time)
        print(f"CSS timestamp fallback for {post_id}: {relative_time} -> {timestamp_css}")  # Debug
    except NoSuchElementException:
        pass
    
    # JSON extraction (primary for views/timestamp/desc)
    views_json, timestamp_json, description_json = None, None, None
    hashtags = []
    script_found = False
    try:
        # Wait specifically for SIGI_STATE with content
        def script_has_content(driver):
            soup = BeautifulSoup(driver.page_source, "lxml")
            script = soup.select_one("script#SIGI_STATE")
            return script and len(script.text.strip()) > 100  # Ensure non-empty
        
        wait.until(lambda d: script_has_content(d))
        soup = BeautifulSoup(driver.page_source, "lxml")
        script = soup.select_one("script#SIGI_STATE")
        if script and script.text.strip():
            script_found = True
            print(f"SIGI_STATE found for {post_id}, length: {len(script.text)}")  # Debug
            data = json.loads(script.text)
            # Original path
            item = data.get("ItemModule", {}).get(str(post_id), {})
            if not item:
                # Fallback: Search all modules for post_id
                for key, module in data.items():
                    if isinstance(module, dict) and str(post_id) in module:
                        item = module[str(post_id)]
                        print(f"Found item in module: {key}")  # Debug
                        break
            if item:
                stats = item.get("stats", {})
                views_json = int(stats.get("playCount", 0))
                timestamp_json = item.get("createTime")
                description_json = item.get("desc", "")
                if description_json:
                    hashtags = re.findall(r'#\w+', description_json)
                print(f"JSON success for {post_id}: views={views_json}, desc len={len(description_json)}")  # Debug
            else:
                print(f"Item not found in JSON for {post_id}")  # Debug
        else:
            print(f"No/empty SIGI_STATE for {post_id}")  # Debug
    except (TimeoutException, JSONDecodeError, KeyError, Exception) as e:
        print(f"JSON failed for {post_id}: {str(e)}")  # Debug print
        logger.error(f"JSON parsing failed for post {post_id}: {e}")
    
    # Combine: Prioritize JSON, fallback to CSS
    views = views_json or views_css
    timestamp = timestamp_json or timestamp_css
    description = description_json or description_css
    if description:
        hashtags = re.findall(r'#\w+', description)  # Re-extract if fallback used
    
    print(f"Final data for {post_id}: views={views}, timestamp={timestamp}, desc={description[:30] if description else None}")  # Debug summary
    
    return {
        "post_id": post_id,
        "likes": likes,
        "comments": comments,
        "shares": shares,
        "views": views,
        "timestamp": timestamp,
        "description": description,
        "hashtags": hashtags,
    }

@app.get("/profile")
def scrape_profile(username: str = Query(...), max_posts: int = Query(5, ge=1, le=20)):
    driver = create_driver()
    url = f"https://www.tiktok.com/@{username}"
    driver.get(url)
    
    wait = WebDriverWait(driver, 15)
    try:
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(3)  # Extra wait for profile
    except TimeoutException:
        driver.quit()
        return {"error": "Failed to load profile page"}
    
    # Profile details (with existence checks)
    bio = None
    try:
        bio_el = driver.find_element(By.CSS_SELECTOR, 'h2[data-e2e="user-bio"], [data-e2e="user-bio"]')
        bio = bio_el.text.strip()
    except NoSuchElementException:
        pass
    
    followers = None
    try:
        followers_el = driver.find_element(By.CSS_SELECTOR, 'strong[data-e2e="followers-count"]')
        followers = parse_count(followers_el.text)
    except NoSuchElementException:
        pass
    
    following = None
    try:
        following_el = driver.find_element(By.CSS_SELECTOR, 'strong[data-e2e="following-count"]')
        following = parse_count(following_el.text)
    except NoSuchElementException:
        pass
    
    likes = None
    try:
        likes_el = driver.find_element(By.CSS_SELECTOR, 'strong[data-e2e="likes-count"]')
        likes = parse_count(likes_el.text)
    except NoSuchElementException:
        pass
   
    # Get post IDs
    post_ids = []
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'a[href*="/video/"]')))
        elements = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/video/"]')
        for el in elements:
            href = el.get_attribute("href")
            if href and "/video/" in href:
                pid = href.split("/")[-1].split("?")[0].split("#")[0]  # Cleaner extraction
                if pid.isdigit() and len(pid) > 10 and pid not in post_ids:  # Valid ID check
                    post_ids.append(pid)
            if len(post_ids) >= max_posts:
                break
        print(f"Found {len(post_ids)} post IDs for {username}: {post_ids}")  # Debug
    except Exception as e:
        print(f"Error getting post IDs: {e}")  # Debug
        logger.error(f"Error getting post IDs: {e}")
    
    # Scrape posts
    posts = []
    for i, pid in enumerate(post_ids):
        try:
            post_data = scrape_post_details(driver, username, pid)
            posts.append(post_data)
            if i < len(post_ids) - 1:  # Don't sleep after last
                time.sleep(3)  # Slower rate limit
        except Exception as e:
            print(f"Error scraping post {pid}: {e}")  # Debug
            logger.error(f"Error scraping post {pid}: {e}")
            posts.append({"post_id": pid, "error": str(e)})
    
    driver.quit()
    return {
        "profile": {
            "username": username,
            "bio": bio,
            "followers": followers,
            "following": following,
            "likes": likes
        },
        "posts": posts
    }
