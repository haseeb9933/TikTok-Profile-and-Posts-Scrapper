import re
import json
import time
import random
from bs4 import BeautifulSoup
from fastapi import FastAPI, Query

# Selenium imports
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

# NEW IMPORT for making Selenium undetectable
from selenium_stealth import stealth

app = FastAPI(title="TikTok Scraper API")

# ----------------- SETUP DRIVER -----------------
def create_driver():
    """Initializes Selenium to use a real, existing Chrome profile."""
    # --- Use the path you provided here ---
    chrome_user_data_path = r"C:\Users\Hp\AppData\Local\Google\Chrome\User Data"
    chrome_profile_directory = "Profile 2" 
    # --------------------------------------------------------------------
    options = Options()
    options.add_argument(f"user-data-dir={chrome_user_data_path}")
    options.add_argument(f"profile-directory={chrome_profile_directory}")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,1600")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    stealth(driver, languages=["en-US", "en"], vendor="Google Inc.", platform="Win32",
        webgl_vendor="Intel Inc.", renderer="Intel Iris OpenGL Engine", fix_hairline=True)
    return driver

# ----------------- HELPER -----------------
def parse_count(text: str):
    if not text: return None
    text = text.strip().upper()
    if 'K' in text: return int(float(text.replace('K', '')) * 1000)
    if 'M' in text: return int(float(text.replace('M', '')) * 1_000_000)
    if 'B' in text: return int(float(text.replace('B', '')) * 1_000_000_000)
    try: return int(text.replace(",", ""))
    except (ValueError, AttributeError): return None

# ----------------- SCRAPE PROFILE + POSTS -----------------
@app.get("/profile")
def scrape_profile(username: str = Query(..., description="The TikTok username to scrape."), max_posts: int = Query(5, ge=1, le=30, description="Maximum number of recent posts to scrape.")):
    driver = create_driver()
    url = f"https://www.tiktok.com/@{username}"
    wait = WebDriverWait(driver, 15)
    posts = []
    profile_data = {"username": username, "bio": None, "followers": None, "following": None, "likes": None}
    
    try:
        driver.get(url)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '[data-e2e="user-post-item"]')))
        
        # Profile Info
        try: profile_data["bio"] = driver.find_element(By.CSS_SELECTOR, 'h2[data-e2e="user-bio"]').text
        except: pass
        try: profile_data["followers"] = parse_count(driver.find_element(By.CSS_SELECTOR, 'strong[data-e2e="followers-count"]').text)
        except: pass
        try: profile_data["following"] = parse_count(driver.find_element(By.CSS_SELECTOR, 'strong[data-e2e="following-count"]').text)
        except: pass
        try: profile_data["likes"] = parse_count(driver.find_element(By.CSS_SELECTOR, 'strong[data-e2e="likes-count"]').text)
        except: pass

        first_video = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'div[data-e2e="user-post-item"] a')))
        driver.execute_script("arguments[0].click();", first_video)

        for i in range(max_posts):
            modal_wait = WebDriverWait(driver, 10)
            modal_wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'strong[data-e2e="like-count"]')))
            time.sleep(random.uniform(1.5, 3))

            try:
                soup = BeautifulSoup(driver.page_source, "html.parser")
                script_tag = soup.find("script", id="__UNIVERSAL_DATA_FOR_REHYDRATION__")
                
                if script_tag:
                    data = json.loads(script_tag.string)
                    item_module = data.get("__DEFAULT_SCOPE__", {}).get("webapp.video-detail", {}).get("itemInfo", {}).get("itemStruct", {})

                    if item_module:
                        posts.append({
                            "post_id": item_module.get("id"), "description": item_module.get("desc"),
                            "timestamp": item_module.get("createTime"),
                            "hashtags": [tag.get("hashtagName") for tag in item_module.get("textExtra", []) if tag.get("hashtagName")],
                            "likes": item_module.get("stats", {}).get("diggCount"), "shares": item_module.get("stats", {}).get("shareCount"),
                            "comments": item_module.get("stats", {}).get("commentCount"), "views": item_module.get("stats", {}).get("playCount"),
                        })
                
                if i < max_posts - 1:
                    next_button = driver.find_element(By.CSS_SELECTOR, 'button[data-e2e="arrow-right"]')
                    next_button.click()
            except (NoSuchElementException, TimeoutException):
                print("Could not find the 'Next' button or video timed out. Ending scrape.")
                break
            except Exception as e:
                print(f"An error occurred while scraping post #{i+1}: {e}")
                break
    
    except Exception as e:
        print(f"An error occurred: {e}")
        # --- MODIFICATION: Keep browser open on error ---
        input("An error occurred. The browser will stay open for inspection. Press Enter in this terminal to close it...")
    
    finally:
        driver.quit()

    return {
        "profile": profile_data,
        "posts": posts
    }