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

# def get_db_connection():
#     """Establishes connection to the PostgreSQL database."""
#     try:
#         return psycopg2.connect(
#             host=os.getenv("DB_HOST"),
#             database=os.getenv("DB_NAME"),
#             user=os.getenv("DB_USER"),
#             password=os.getenv("DB_PASS"),
#             port=os.getenv("DB_PORT")
#         )
#     except Exception as e:
#         logging.error(f"❌ Database connection error: {e}")
#         return None
    

def update_sam_inprogress():
    """
    Checks for stuck 'inprogress' jobs older than 1 hour 
    and resets them to 'new' before scraping starts.
    """
    conn = get_db_connection()
    if conn is None: 
        return

    try:
        cur = conn.cursor()
        
        # Wrapped the SQL string and added execution block
        query = """
            UPDATE "SAM_Operations"
            SET status = 'new', modified_datetime = NOW()
            WHERE status = 'inprogress'
              AND modified_datetime < NOW() - INTERVAL '1 hour';
        """
        
        cur.execute(query)
        conn.commit()
        logging.info(f"🔄 Checked and reset stuck 'inprogress' jobs to 'new' (Rows affected: {cur.rowcount}).")
        
    except Exception as e:
        logging.error(f"❌ Error updating inprogress statuses: {e}")
        conn.rollback()
    finally:
        conn.close()

def insert_sam_urls(url_list, table_name="SAM_Operations"):
    """
    Inserts a list of portal URLs into the SAM_Operations table.
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
        cur.execute(f'SELECT COALESCE(MAX(id), 0) FROM "{table_name}"')
        current_max_id = cur.fetchone()[0]
        
        # 2. Prepare data for batch insert
        data_to_insert = []
        for i, url in enumerate(url_list, start=1):
            new_id = current_max_id + i
            data_to_insert.append((new_id, url, "new"))

        # 3. Perform Batch Insert
        query = f'''
            INSERT INTO "{table_name}" (id, url, status, created_datetime) 
            VALUES (%s, %s, %s, NOW())
        '''
        
        execute_batch(cur, query, data_to_insert)
        conn.commit()
        logging.info(f"✅ Successfully inserted {len(url_list)} records into {table_name}.")
        
    except Exception as e:
        logging.error(f"❌ Error inserting into {table_name}: {e}")
        conn.rollback()
    finally:
        conn.close()