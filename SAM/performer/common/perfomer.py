import logging
import tkinter as tk
import pyperclip  
import platform
import re
import time
from playwright.sync_api import sync_playwright
from common.auth_utils import login_to_portal
from common.db_utils import get_new_urls_and_mark_inprogress, update_url_status
from common.email_utils import send_failure_email  # Ensure this matches your project filename
from common.db_utils import get_execution_flags

flags = get_execution_flags()

sam_search_url = "https://sam.gov/search/?page=1&pageSize=25&sort=-relevance&index=ex&sfm%5Bstatus%5D%5Bis_active%5D=true&sfm%5BsimpleSearch%5D%5BkeywordRadio%5D=ANY"
# Configure clipboard backend for Linux
if platform.system() == "Linux":
    try:
        pyperclip.set_clipboard("xclip")
    except:
        pass

logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class SAMPerformer:
    def __init__(self):
        self.table_name = "SAM_Operations"
        # self.root = tk.Tk()
        # self.root.withdraw()
        self.max_retries = 3

    def retry_action(self, action_callable, action_name="Action", *args, **kwargs):
        """Generic retry wrapper with exponential backoff for SAM stability."""
        last_exception = None
        for attempt in range(1, self.max_retries + 1):
            try:
                return action_callable(*args, **kwargs)
            except Exception as e:
                last_exception = e
                logging.warning(f"⚠️ {action_name} failed (Attempt {attempt}/{self.max_retries}): {e}")
                if attempt < self.max_retries:
                    time.sleep(2 ** attempt)  # Backoff: 2s, 4s...
        
        logging.error(f"❌ {action_name} failed permanently after {self.max_retries} attempts.")
        raise last_exception

    def perform_login(self, page):
        return self.retry_action(login_to_portal, "Login", page)

    def extract_name(self, page):
        def _logic():
            suffixes = r'\b(jr\.?|sr\.?|ii|iii|iv|v)\b'            
            raw_last = page.locator(".eip-col-name_lastnow").inner_text(timeout=5000).strip()
            raw_first = page.locator(".eip-col-name_first").inner_text(timeout=5000).strip()

            # Clean Last Name (Remove Suffixes)
            last = re.sub(suffixes, '', raw_last, flags=re.IGNORECASE).strip()
            # Clean First Name (Take only the first word)
            first = raw_first.split()[0] if raw_first else ""

            full_name = f"{last}, {first}"
            clean_result = " ".join(full_name.split())
            logging.info(f"🏷️ Extracted Name for SAM: {clean_result}")
            return clean_result
        
        return self.retry_action(_logic, "Name Extraction")

    def execute_search_flow(self, context, work_page, clean_name):
        search_page = context.new_page()
        
        def _flow():
            pyperclip.copy("")
            sam_url = sam_search_url
            search_page.goto(sam_url, wait_until="networkidle")
            
            keyword_selector = 'input[name="keyword-text"]'
            search_page.wait_for_selector(keyword_selector, timeout=15000)
            
            keyword_field = search_page.locator(keyword_selector)
            keyword_field.click()
            keyword_field.fill(clean_name)
            keyword_field.press("Enter")
            
            # SAM can be slow to update result counts, wait for load
            search_page.wait_for_load_state("networkidle")
            search_page.wait_for_timeout(3000) 

            # Keyboard Copy
            search_page.bring_to_front()
            is_mac = (platform.system() == "Darwin")
            select_key = "Meta+A" if is_mac else "Control+A"
            copy_key = "Meta+C" if is_mac else "Control+C"
            
            search_page.keyboard.press(select_key)
            search_page.keyboard.press(copy_key)
            time.sleep(1)

            # Clipboard Fallback
            clipboard_content = pyperclip.paste()
            if not clipboard_content:
                pyperclip.copy(search_page.locator("body").inner_text())

            # Paste to Work Page
            work_page.bring_to_front()
            work_page.locator(".notes-dropzone").click() 
            paste_key = "Meta+V" if is_mac else "Control+V"
            work_page.keyboard.press(paste_key)
            work_page.locator("button.save-notes-btn").click()

            # Result Logic
            no_results = search_page.locator("h1.ng-star-inserted", has_text="No matches found").is_visible()
            disposition = work_page.locator("#disposition")
            
            if no_results:
                logging.info(f"✅ Clear: {clean_name}")
                disposition.select_option("clear")
            else:
                logging.warning(f"⚠️ Potential Hits Found: {clean_name}")                
                disposition.select_option("hits")

            work_page.locator('input[name="status"][value="complete"]').check()
            submit_btn = work_page.locator('input.fillorder-submitter[value="submit"]')
            submit_btn.wait_for(state="visible", timeout=5000)
            submit_btn.click()
            return True

        try:
            return self.retry_action(_flow, "SAM Search Flow")
        finally:
            search_page.close()

    def process_transaction(self, context, target_url):
        work_page = context.new_page()
        try:
            logging.info(f"🔍 Processing SAM: {target_url}")
            self.retry_action(lambda: work_page.goto(target_url, wait_until="domcontentloaded"), "Page Load")
            
            name = self.extract_name(work_page)
            if self.execute_search_flow(context, work_page, name):
                update_url_status(target_url, "completed", self.table_name)

        except Exception as e:
            error_msg = f"SAM Transaction failed for {target_url}. Error: {str(e)}"
            logging.error(f"❌ {error_msg}")
            update_url_status(target_url, "error", self.table_name)
            send_failure_email(error_msg) 
        finally:
            work_page.close()

    def run(self):
        process_key = "sam"
        if not flags.get(process_key, True):
            logging.info(f"🛑 Kill switch active for {process_key.upper()}. Exiting.")
            return
        with sync_playwright() as p:
            browser = None
            try:
                browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
                context = browser.new_context(viewport={'width': 1920, 'height': 1080})
                main_page = context.new_page()

                if not self.perform_login(main_page):
                    send_failure_email("SAM Login failed after multiple retries. Check Portal status.")
                    return

                logging.info(f"🚀 Starting SAM Processing Queue")
                df_pending = get_new_urls_and_mark_inprogress(self.table_name)
                
                if df_pending.empty:
                    logging.info("☕ No pending SAM items.")
                else:
                    for _, row in df_pending.iterrows():
                        self.process_transaction(context, row['url'])
                        
            except Exception as e:
                critical_error = f"CRITICAL SAM SYSTEM ERROR: {str(e)}"
                logging.critical(critical_error)
                send_failure_email(critical_error)
            finally:
                if browser:
                    browser.close()
                    logging.info("🏁 Browser closed. SAM Process ended.")

if __name__ == "__main__":
    performer = SAMPerformer()
    performer.run()