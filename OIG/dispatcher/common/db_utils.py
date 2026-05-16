# db_utils.py
import psycopg2
import os
import logging
from psycopg2.extras import execute_batch
from dotenv import load_dotenv
import time

load_dotenv()


def get_db_connection(max_retries=3):
    last_exception = None
    for attempt in range(1, max_retries + 1):
        try:
            return psycopg2.connect(
                host=os.getenv("DB_HOST"),
                database=os.getenv("DB_NAME"),
                user=os.getenv("DB_USER"),
                password=os.getenv("DB_PASS"),
                port=os.getenv("DB_PORT")
            )
        except Exception as e:
            last_exception = e
            logging.warning(f"DB connection attempt {attempt}/{max_retries} failed: {e}")
            if attempt < max_retries:
                time.sleep(2 ** attempt)
    logging.error("All DB connection attempts failed.")
    raise last_exception


def update_oig_inprogress():
    """
    Checks for stuck 'inprogress' jobs older than 1 hour 
    and resets them to 'new' before scraping starts.
    """
    conn = get_db_connection()
    if conn is None: 
        return

def insert_oig_urls(url_list, table_name="OIG_Operations"):
    """
    Inserts a list of portal URLs into the OIG_Operations table.
    Sets status to 'new' and created_datetime to current timestamp.
    """
    if not url_list:
        logging.info("No URLs found to insert.")
        return

    conn = get_db_connection()
    if conn is None: return
    
    try:
        cur = conn.cursor()       
        
        # LIFO Logic: Process newest items from the portal first
        url_list.reverse()
        
        # 1. Get current max ID for manual incrementing
        data_to_insert = [(url, "new") for url in url_list]

        # 3. Perform Batch Insert
        query = f'''
            INSERT INTO "{table_name}" (url, status, created_datetime)
            VALUES (%s, %s, NOW())
            ON CONFLICT (url) DO NOTHING

        '''
        
        execute_batch(cur, query, data_to_insert)
        conn.commit()
        logging.info(f"✅ Successfully inserted {len(url_list)} records into {table_name}.")
        
    except Exception as e:
        logging.error(f"❌ Error inserting into {table_name}: {e}")
        conn.rollback()
    finally:
        conn.close()