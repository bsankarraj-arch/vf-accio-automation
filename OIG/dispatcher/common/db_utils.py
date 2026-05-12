# db_utils.py
import psycopg2
import os
import logging
from psycopg2.extras import execute_batch
from dotenv import load_dotenv

load_dotenv()

def get_db_connection():
    """Establishes connection to the PostgreSQL database."""
    try:
        return psycopg2.connect(
            host=os.getenv("DB_HOST"),
            database=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASS"),
            port=os.getenv("DB_PORT")
        )
    except Exception as e:
        logging.error(f"❌ Database connection error: {e}")
        return None

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