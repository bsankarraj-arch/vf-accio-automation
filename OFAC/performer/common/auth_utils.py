# auth_utils.py
import os
import time
import logging
from common.aws_2 import get_secret


prod_flag = os.getenv("ENVIRONMENT", "dev").lower() == "prod"
# prod_url's
prod_login_url = "https://verifiedfirst.bgsecured.com/"
# dev_url's
dev_login_url = "https://vfbeta.bgsecured.com/sysops/sysop_home9.html"

if prod_flag:
    login_url = prod_login_url
else:    
    login_url = dev_login_url

def login_to_portal(page, max_retries=3):


    username, password, account = get_secret()
    try:
        uid, pwd, acc = get_secret()
    except Exception as e:
        logging.error(f"Failed to retrieve secrets from AWS: {e}")
        raise e

    for attempt in range(1, max_retries + 1):
        try:
            logging.info(f"🌐 Login Attempt {attempt}/{max_retries}...")           
            
            page.goto(login_url, 
                      wait_until="domcontentloaded", timeout=60000)
            page.get_by_role("textbox", name="account").fill(acc, timeout=10000)
            page.locator("input[name='userid']").fill(uid)
            page.locator("input[name='password']").fill(pwd)

            try:
                page.get_by_role("button", name="X").click(timeout=3000)
            except:
                logging.info("button not found/already closed, continuing...")
            logging.info("🖱️ Clicking Sign In...")
            page.locator("#login_button").click()
            page.wait_for_timeout(5000)  # Wait for potential redirects/loading
            page.wait_for_load_state("networkidle")
            
            
            logging.info(f"✅ Login successful on attempt {attempt}.")
            return True # Exit function successfully

        except Exception as e:
            logging.error(f"⚠️ Attempt {attempt} failed: {e}")
            page.screenshot(path=f"screenshots/login_error_attempt_{attempt}.png")
            
            if attempt == max_retries:
                logging.error("❌ All login attempts failed.")
                raise e 
            
            
            time.sleep(5)