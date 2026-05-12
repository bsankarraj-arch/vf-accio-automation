import psycopg2
import os
import pandas as pd
from psycopg2.extras import execute_values
from dotenv import load_dotenv
import logging

load_dotenv()

def get_db_connection():
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
    

def get_execution_flags():
    """Reads the control flags from the public schema."""
    conn = get_db_connection()
    if conn is None: return {}
    try:
        cur = conn.cursor()
        cur.execute('SELECT oig, sam, ofac FROM "public"."performer_flag_table" LIMIT 1')
        row = cur.fetchone()
        return {"oig": row[0], "sam": row[1], "ofac": row[2]} if row else {}
    except Exception as e:
        logging.error(f"❌ Error reading flags: {e}")
        return {}
    finally:
        conn.close()

def get_new_urls_and_mark_inprogress(table_name):
    """
    Fetches 'new' records, marks them 'inprogress', 
    and sets the modified_datetime to now.
    """
    conn = get_db_connection()
    if conn is None: return pd.DataFrame()
    
    try:
        # We update the status and retrieve the URLs in one atomic transaction
        query = f'''
            UPDATE "{table_name}" 
            SET status = 'inprogress', modified_datetime = NOW()
            WHERE id IN (
                SELECT id FROM "{table_name}" 
                WHERE status = 'new' 
                ORDER BY created_datetime ASC 
                LIMIT 100
            )
            RETURNING url;
        '''
        df = pd.read_sql(query, conn)
        return df
    except Exception as e:
        logging.error(f"❌ Error fetching/locking URLs in {table_name}: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

def update_url_status(url, status, table_name):
    """Updates status and modified_datetime upon completion or error."""
    conn = get_db_connection()
    if conn is None: return

    try:
        cur = conn.cursor()
        query = f'''
            UPDATE "{table_name}" 
            SET status = %s, modified_datetime = NOW() 
            WHERE url = %s
        '''
        cur.execute(query, (status, url))
        conn.commit()
        logging.info(f"✔️ {url} updated to {status} in {table_name}")
    except Exception as e:
        logging.error(f"❌ Error updating status for {url}: {e}")
        conn.rollback()
    finally:
        conn.close()

def insert_urls_to_table(df, table_name):
    """Inserts records in reverse order (LIFO) with manual ID calculation."""
    conn = get_db_connection()
    if conn is None or df.empty: return
    
    try:
        cur = conn.cursor()       
        
        df = df.iloc[::-1].reset_index(drop=True)
        
        # 1. Get current max ID
        cur.execute(f'SELECT COALESCE(MAX(id), 0) FROM "{table_name}"')
        current_max_id = cur.fetchone()[0]
        
        data_to_insert = []
        for i, row in enumerate(df.itertuples(index=False), start=1):
            new_id = current_max_id + i
            # Format: (id, url, status)
            data_to_insert.append((new_id, row.url, "new"))

        # 3. Batch Insert
        query = f'''
            INSERT INTO "{table_name}" (id, url, status, created_datetime) 
            VALUES (%s, %s, %s, NOW())
        '''
        
        from psycopg2.extras import execute_batch
        execute_batch(cur, query, data_to_insert)
        
        conn.commit()
        logging.info(f"✅ Successfully inserted {len(df)} records into {table_name} (LIFO Order).")
        
    except Exception as e:
        logging.error(f"❌ Error inserting into {table_name}: {e}")
        conn.rollback()
    finally:
        conn.close()