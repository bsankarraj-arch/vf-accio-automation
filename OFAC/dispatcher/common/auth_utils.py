# auth_utils.py
import os
import time
import logging
from common.aws_2 import get_secret

prod_flag = os.getenv("ENVIRONMENT", "dev").lower() == "prod"
# prod_url's
base_url = "https://verifiedfirst.bgsecured.com/"
prod_login_url = "https://verifiedfirst.bgsecured.com/"
prod_ofac_url =  "https://verifiedfirst.bgsecured.com/c/s2/worklist?report_name_selector=s%3AOFAC%20Automation%20Report"
# dev_url's
base_url = "https://vfbeta.bgsecured.com/"
dev_login_url = "https://vfbeta.bgsecured.com/sysops/sysop_home9.html"
dev_ofac_url = "https://vfbeta.bgsecured.com/c/s2/worklist?dynamic_report_name=s:OFAC%20Automation%20Report"


if prod_flag:
    login_url = prod_login_url
    ofac_url = prod_ofac_url
else:
    login_url = dev_login_url
    ofac_url = dev_ofac_url


def login_to_portal(page, max_retries=3):
    """Handles authentication to the portal."""
    try:
        # Retrieve secrets once
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

            # Handle optional popup/overlay if it exists
            try:
                page.get_by_role("button", name="X").click(timeout=3000)
            except:
                logging.info("Overlay button not found, continuing...")

            logging.info("🖱️ Clicking Sign In...")
            page.locator("#login_button").click()
            
            # Wait for navigation to complete
            page.wait_for_load_state("networkidle")
            
            logging.info(f"✅ Login successful on attempt {attempt}.")
            return True 

        except Exception as e:
            logging.error(f"⚠️ Attempt {attempt} failed: {e}")
            os.makedirs("screenshots", exist_ok=True)
            page.screenshot(path=f"screenshots/login_error_attempt_{attempt}.png")
            
            if attempt == max_retries:
                logging.error("❌ All login attempts failed.")
                raise e 
            
            time.sleep(5)

def get_worklist_urls(page):
    """Navigates to the OFAC worklist and extracts all task URLs."""
    target_url = ofac_url
    
    try:
        logging.info(f"🚀 Navigating to Worklist: {target_url}")
        page.goto(target_url, wait_until="networkidle", timeout=60000)

        # Ensure the table rows are loaded
        page.wait_for_selector("table#t1 tbody tr", timeout=15000)
        
        # Locate all rows in the table
        rows = page.locator("table#t1 tbody tr")
        row_count = rows.count()
        
        logging.info(f"Found {row_count} total rows in table. Filtering for OFAC tasks...")
        
        urls = []
        for i in range(row_count):
            row = rows.nth(i)
            
            # Look for the link in the second column (Request description)
            # The HTML shows: <td><a target="_blank" href="...">Office of Foreign Assets Control...</a></td>
            link_locator = row.locator('td:nth-child(2) a[href*="fill_edit"]')
            
            if link_locator.count() > 0:
                url = link_locator.get_attribute("href")
                # Ensure it's an absolute URL if the portal uses relative paths
                if url.startswith('/'):
                    url = f"{base_url}{url}"
                
                urls.append(url)
        
        logging.info(f"Successfully extracted {len(urls)} OFAC URLs.")
        return urls

    except Exception as e:
        logging.error(f"❌ Failed to extract worklist: {e}")
        page.screenshot(path="screenshots/worklist_extraction_error.png")
        return []