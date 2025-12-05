import sqlite3
import re
import os
from datetime import datetime

DATABASE = 'query_results.db'

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def get_potential_attacks():
    conn = get_db()
    cursor = conn.execute('SELECT * FROM cached_potential_attacks')
    attacks = cursor.fetchall()
    conn.close()
    return [dict(row) for row in attacks]

def get_payloads():
    conn = get_db()
    cursor = conn.execute("""
        SELECT
            actor_login,
            title,
            COALESCE(ref, head_ref) as payload_ref
        FROM
            cached_potential_attacks
        WHERE
            (title IS NOT NULL AND title != '') OR (COALESCE(ref, head_ref) IS NOT NULL AND COALESCE(ref, head_ref) != '')
        GROUP BY
            actor_login,
            title,
            payload_ref
        ORDER BY
            actor_login,
            title,
            payload_ref;
    """)
    payloads_data_raw = cursor.fetchall()
    conn.close()

    payloads_by_actor = {}
    for row in payloads_data_raw:
        actor_login = row['actor_login']
        if actor_login not in payloads_by_actor:
            payloads_by_actor[actor_login] = []
        payloads_by_actor[actor_login].append({
            'title': row['title'],
            'payload_ref': row['payload_ref']
        })
    return payloads_by_actor

def get_actors():
    conn = get_db()

    cursor = conn.execute("SELECT login as actor_login, * FROM cached_github_users_history_enrichment")
    actors_data_raw = cursor.fetchall()

    four_o_four_actors_cursor = conn.execute("SELECT actor_login FROM four_o_four_actors")
    four_o_four_actors = {row['actor_login'] for row in four_o_four_actors_cursor.fetchall()}

    actors_processed_data = {}

    for row in actors_data_raw:
        actor_login = row['actor_login']
        enricher_data = {}
        fields_to_drop = ["followers", "following", "hireable","site_admin","type"]
        for k in row.keys():
            if k != 'actor_login' and k not in fields_to_drop:
                value = row[k]
                if value is not None and value != '' and not (isinstance(value, (list, dict)) and not value):
                    enricher_data[k] = value

        actors_processed_data[actor_login] = {
            'latest_enricher_result': enricher_data,
            'event_counts': {},
            'repos': []
        }

    event_counts_cursor = conn.execute("SELECT actor_login, event_type, COUNT(*) as count FROM cached_potential_attacks GROUP BY actor_login, event_type")
    for row in event_counts_cursor.fetchall():
        actor_login = row['actor_login']
        event_type = row['event_type']
        count = row['count']
        if actor_login in actors_processed_data:
            actors_processed_data[actor_login]['event_counts'][event_type] = count

    repos_cursor = conn.execute("SELECT DISTINCT actor_login, repo_name FROM cached_potential_attacks WHERE repo_name IS NOT NULL AND repo_name != ''")
    for row in repos_cursor.fetchall():
        actor_login = row['actor_login']
        repo_name = row['repo_name']
        if actor_login in actors_processed_data:
            actors_processed_data[actor_login]['repos'].append(repo_name)

    conn.close()

    return actors_processed_data, four_o_four_actors

def _sanitize_table_name(query_name):
    """Converts a query name (filename) into a valid SQLite table name."""
    # Remove file extension and replace non-alphanumeric characters with underscores
    name_without_ext = os.path.splitext(query_name)[0]
    sanitized_name = re.sub(r'\W|^(?=\d)', '_', name_without_ext)
    return f"cached_{sanitized_name}"

def _get_sqlite_type(ch_type):
    """Maps ClickHouse data types to SQLite data types."""
    # Ensure ch_type is a string before performing string operations
    ch_type_str = str(ch_type)
    if ch_type_str in ['Int8', 'Int16', 'Int32', 'Int64', 'UInt8', 'UInt16', 'UInt32', 'UInt64', 'Float32', 'Float64']:
        return 'NUMERIC'
    elif ch_type_str.startswith('DateTime') or ch_type_str.startswith('Date'):
        return 'TEXT'  # Store as ISO format string
    elif ch_type_str.startswith('String') or ch_type_str.startswith('FixedString'):
        return 'TEXT'
    elif ch_type_str == 'Bool':
        return 'INTEGER' # 0 or 1
    else:
        return 'TEXT' # Default to TEXT for unknown types

def persist_query_results(conn, query_name, run_date, results):
    cursor = conn.cursor()
    sanitized_table_name = _sanitize_table_name(query_name)

    # Create dynamic table based on query results
    columns_with_types = []
    for i, col_name in enumerate(results.column_names):
        sqlite_type = _get_sqlite_type(results.column_types[i])
        columns_with_types.append(f'"{col_name}" {sqlite_type}') # Quote column names to handle special characters

    create_table_sql = f"""
    CREATE TABLE IF NOT EXISTS {sanitized_table_name} (
        {', '.join(columns_with_types)}
    )
    """
    cursor.execute(create_table_sql)
    conn.commit()


    # Insert new results into the dedicated table
    if results.result_rows:
        placeholders = ', '.join(['?'] * len(results.column_names))
        insert_sql = f"INSERT INTO {sanitized_table_name} VALUES ({placeholders})"

        # Format datetime objects to string for SQLite
        formatted_rows = []
        for row in results.result_rows:
            formatted_row = []
            for i, item in enumerate(row):
                if isinstance(item, datetime):
                    formatted_row.append(item.strftime('%Y-%m-%d %H:%M:%S'))
                else:
                    formatted_row.append(item)
            formatted_rows.append(formatted_row)

        cursor.executemany(insert_sql, formatted_rows)
        conn.commit()

    # Update query_results_metadata
    # Check if an entry for this query_name already exists
    cursor.execute("SELECT 1 FROM query_results_metadata WHERE query_name = ?", (query_name,))
    exists = cursor.fetchone()

    if exists:
        update_metadata_sql = """
        UPDATE query_results_metadata
        SET last_updated = ?
        WHERE query_name = ?
        """
        cursor.execute(update_metadata_sql, (run_date.strftime('%Y-%m-%d %H:%M:%S'), query_name))
    else:
        insert_metadata_sql = """
        INSERT INTO query_results_metadata (query_name, last_updated) VALUES (?, ?)
        """
        cursor.execute(insert_metadata_sql, (query_name, run_date.strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    print(f"Query results for '{query_name}' persisted successfully in table '{sanitized_table_name}'.")

def upsert_enrichment_results(conn, query_name, run_date, results):
    cursor = conn.cursor()
    sanitized_table_name = _sanitize_table_name(query_name)

    # Create table with 'login' as primary key if it's the enrichment table
    # This assumes 'login' is always the first column in the results for enrichment
    columns_with_types = []
    for i, col_name in enumerate(results.column_names):
        sqlite_type = _get_sqlite_type(results.column_types[i])
        if col_name == 'login' and query_name == "github_users_history_enrichment":
            columns_with_types.append(f'"{col_name}" {sqlite_type} PRIMARY KEY')
        else:
            columns_with_types.append(f'"{col_name}" {sqlite_type}')

    create_table_sql = f"""
    CREATE TABLE IF NOT EXISTS {sanitized_table_name} (
        {', '.join(columns_with_types)}
    )
    """
    cursor.execute(create_table_sql)
    conn.commit()

    if results.result_rows:
        column_names_str = ', '.join(f'"{col}"' for col in results.column_names)
        placeholders = ', '.join(['?'] * len(results.column_names))

        # SQLite's INSERT OR REPLACE handles upsert if a PRIMARY KEY is defined
        # If 'login' is not defined as PRIMARY KEY, this will just insert
        insert_or_replace_sql = f"""
        INSERT OR REPLACE INTO {sanitized_table_name} ({column_names_str})
        VALUES ({placeholders})
        """

        formatted_rows = []
        for row in results.result_rows:
            formatted_row = []
            for i, item in enumerate(row):
                if isinstance(item, datetime):
                    formatted_row.append(item.strftime('%Y-%m-%d %H:%M:%S'))
                else:
                    formatted_row.append(item)
            formatted_rows.append(formatted_row)

        cursor.executemany(insert_or_replace_sql, formatted_rows)
        conn.commit()

    # Update query_results_metadata (same as persist_query_results)
    cursor.execute("SELECT 1 FROM query_results_metadata WHERE query_name = ?", (query_name,))
    exists = cursor.fetchone()

    if exists:
        update_metadata_sql = """
        UPDATE query_results_metadata
        SET last_updated = ?
        WHERE query_name = ?
        """
        cursor.execute(update_metadata_sql, (run_date.strftime('%Y-%m-%d %H:%M:%S'), query_name))
    else:
        insert_metadata_sql = """
        INSERT INTO query_results_metadata (query_name, last_updated) VALUES (?, ?)
        """
        cursor.execute(insert_metadata_sql, (query_name, run_date.strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    print(f"Query results for '{query_name}' upserted successfully in table '{sanitized_table_name}'.")

def get_last_run_timestamp(conn, query_name):
    cursor = conn.cursor()
    select_sql = """
    SELECT MAX(last_updated) FROM query_results_metadata
    WHERE query_name = ?
    """
    cursor.execute(select_sql, (query_name,))
    result = cursor.fetchone()
    if result and result[0]:
        return datetime.strptime(result[0], '%Y-%m-%d %H:%M:%S')
    return None

def check_existing_results(conn, query_name, run_date):
    cursor = conn.cursor()
    sanitized_table_name = _sanitize_table_name(query_name)

    # Check if the dedicated table exists and has data for today
    # First, check if the metadata indicates a run today
    check_metadata_sql = """
    SELECT last_updated FROM query_results_metadata
    WHERE query_name = ? AND DATE(last_updated) = DATE(?)
    LIMIT 1
    """
    try:
        cursor.execute(check_metadata_sql, (query_name, run_date.strftime('%Y-%m-%d %H:%M:%S')))
        metadata_result = cursor.fetchone()

        if metadata_result:
            # Now check if the actual data table exists and has rows
            cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{sanitized_table_name}'")
            table_exists = cursor.fetchone()
            if table_exists:
                cursor.execute(f"SELECT * FROM {sanitized_table_name}")
                rows = cursor.fetchall()
                if rows:
                    # Get column names from the table info
                    cursor.execute(f"PRAGMA table_info({sanitized_table_name})")
                    column_info = cursor.fetchall()
                    column_names = [col[1] for col in column_info]
                    column_types = [col[2] for col in column_info] # Extract column types
                    print(f"Found existing results for '{query_name}' from today. Using cached results from table '{sanitized_table_name}'.")
                    return rows, column_names, column_types # Return column types as well
        return None
    except sqlite3.OperationalError as e:
        # This error occurs if the table doesn't exist, which is fine if it's the first run
        print(f"Table '{sanitized_table_name}' does not exist yet or other DB error: {e}")
        return None
    except sqlite3.Error as e:
        print(f"SQLite error checking for existing results: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred while checking for existing results: {e}")
        return None

def initialize_sqlite_db(conn):
    cursor = conn.cursor()
    create_metadata_table_sql = """
    CREATE TABLE IF NOT EXISTS query_results_metadata (
        query_name TEXT PRIMARY KEY,
        last_updated TEXT
    )
    """
    cursor.execute(create_metadata_table_sql)
    conn.commit()
    create_404_actors_table(conn)

def create_404_actors_table(conn):
    cursor = conn.cursor()
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS four_o_four_actors (
        actor_login TEXT PRIMARY KEY,
        actor TEXT
    )
    """
    cursor.execute(create_table_sql)
    conn.commit()

def insert_404_actor(conn, actor_login, actor):
    cursor = conn.cursor()
    insert_sql = """
    INSERT OR IGNORE INTO four_o_four_actors (actor_login, actor)
    VALUES (?, ?)
    """
    cursor.execute(insert_sql, (actor_login, actor))
    conn.commit()

def is_404_actor(conn, actor_login):
    cursor = conn.cursor()
    select_sql = """
    SELECT 1 FROM four_o_four_actors WHERE actor_login = ?
    """
    cursor.execute(select_sql, (actor_login,))
    return cursor.fetchone() is not None