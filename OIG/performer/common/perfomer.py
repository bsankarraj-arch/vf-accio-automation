import logging
import tkinter as tk
import pyperclip  
import platform
import re
import time
from playwright.sync_api import sync_playwright
from common.auth_utils import login_to_portal
from common.db_utils import get_new_urls_and_mark_inprogress, update_url_status
from common.email_utils import send_failure_email  # Updated import to match OFAC 
from common.db_utils import get_execution_flags

flags = get_execution_flags()


oig_search_url = "https://exclusions.oig.hhs.gov/"

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

class OIGPerformer:
    def __init__(self):
        self.table_name = "OIG_Operations"
        # self.root = tk.Tk()
        # self.root.withdraw()
        self.max_retries = 3

    def retry_action(self, action_callable, action_name="Action", *args, **kwargs):
        """Generic retry wrapper with exponential backoff."""
        last_exception = None
        for attempt in range(1, self.max_retries + 1):
            try:
                return action_callable(*args, **kwargs)
            except Exception as e:
                last_exception = e
                logging.warning(f"⚠️ {action_name} failed (Attempt {attempt}/{self.max_retries}): {e}")
                if attempt < self.max_retries:
                    time.sleep(2 ** attempt) 
        
        logging.error(f"❌ {action_name} failed permanently after {self.max_retries} attempts.")
        raise last_exception

    def perform_login(self, page):
        return self.retry_action(login_to_portal, "Login", page)

    def extract_name(self, page):
        def _logic():
            suffixes = r'\b(jr\.?|sr\.?|ii|iii|iv|v)\b'            
            raw_last = page.locator(".eip-col-name_lastnow").inner_text(timeout=5000).strip()
            raw_first = page.locator(".eip-col-name_first").inner_text(timeout=5000).strip()

            last = re.sub(suffixes, '', raw_last, flags=re.IGNORECASE).strip()
            first = raw_first.split()[0] if raw_first else ""
            
            logging.info(f"🏷️ Extracted for OIG: {last}, {first}")
            return last, first
        
        return self.retry_action(_logic, "Name Extraction")

    def execute_search_flow(self, context, work_page, last, first):
        search_page = context.new_page()
        
        def _flow():
            pyperclip.copy("")
            search_page.goto(oig_search_url, wait_until="networkidle")
            
            # Search logic
            search_page.locator("#ctl00_cpExclusions_txtSPLastName").fill(last)
            search_page.locator("#ctl00_cpExclusions_txtSPFirstName").fill(first)
            search_page.locator("#ctl00_cpExclusions_ibSearchSP").click()
            search_page.wait_for_load_state("networkidle")

            
            search_page.bring_to_front()
            is_mac = (platform.system() == "Darwin")
            select_key = "Meta+A" if is_mac else "Control+A"
            copy_key = "Meta+C" if is_mac else "Control+C"
            
            search_page.keyboard.press(select_key)
            search_page.keyboard.press(copy_key)
            time.sleep(1)

            clipboard_content = pyperclip.paste()
            if not clipboard_content or len(clipboard_content) < 5:
                pyperclip.copy(search_page.locator("body").inner_text())

            # Paste to Work Page
            work_page.bring_to_front()
            work_page.locator(".notes-dropzone").click() 
            paste_key = "Meta+V" if is_mac else "Control+V"
            work_page.keyboard.press(paste_key)
            work_page.locator("button.save-notes-btn").click()

            # Result Validation
            

            # Now perform your check
            
            no_results_found = search_page.locator("#ctl00_cpExclusions_pnlEmpty").is_visible()
            disposition = work_page.locator("#disposition")
            
            if no_results_found:
                logging.info(f"✅ Clear: {last}, {first}")
                disposition.select_option("clear")
            else:
                logging.warning(f"⚠️ Potential Match Found: {last}, {first}")
                disposition.select_option("hits")

            # Mark complete and Submit
            work_page.locator('input[name="status"][value="complete"]').check()
            submit_btn = work_page.locator('input.fillorder-submitter[value="submit"]')
            submit_btn.wait_for(state="visible", timeout=5000)
            submit_btn.click()
            return True

        try:
            return self.retry_action(_flow, "OIG Search Flow")
        finally:
            search_page.close()

    def process_transaction(self, context, target_url):
        work_page = context.new_page()
        try:
            logging.info(f"🔍 Processing OIG: {target_url}")
            self.retry_action(lambda: work_page.goto(target_url, wait_until="domcontentloaded"), "Page Load")
            
            last, first = self.extract_name(work_page)
            if self.execute_search_flow(context, work_page, last, first):
                update_url_status(target_url, "completed", self.table_name)

        except Exception as e:
            error_msg = f"OIG Transaction failed for {target_url}. Error: {str(e)}"
            logging.error(f"❌ {error_msg}")
            update_url_status(target_url, "error", self.table_name)
            send_failure_email(error_msg) 
        finally:
            work_page.close()

    def run(self):
        process_key = "oig"
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
                    send_failure_email("OIG Login failed after multiple retries.")
                    return

                df_pending = get_new_urls_and_mark_inprogress(self.table_name)
                
                if df_pending.empty:
                    logging.info("☕ No pending OIG items.")
                else:
                    for _, row in df_pending.iterrows():
                        self.process_transaction(context, row['url'])
                        
            except Exception as e:
                critical_error = f"CRITICAL OIG SYSTEM ERROR: {str(e)}"
                logging.critical(critical_error)
                send_failure_email(critical_error)
            finally:
                if browser:
                    browser.close()

if __name__ == "__main__":
    performer = OIGPerformer()
    performer.run()