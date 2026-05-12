import logging
from playwright.sync_api import sync_playwright
from auth_utils import login_to_portal, get_worklist_urls
from db_utils import insert_ofac_urls

# Basic logging setup
logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')

def main():
    with sync_playwright() as p:
        # Launch Browser
        browser = p.chromium.launch(headless=True) 
        page = browser.new_page()

        try:
            # Step 1: Login via auth_utils
            if login_to_portal(page):
                
                # Step 2: Extract URLs from the OFAC worklist
                task_urls = get_worklist_urls(page)
                
                # Step 3: Insert directly into OFAC_Operations
                if task_urls:
                    insert_ofac_urls(task_urls)
                else:
                    logging.info("Worklist is empty. Nothing to dispatch.")
            
        except Exception as e:
            logging.error(f"Dispatcher crashed: {e}")
        finally:
            logging.info("Closing browser...")
            browser.close()

if __name__ == "__main__":
    main()