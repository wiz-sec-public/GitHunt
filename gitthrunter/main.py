import argparse
import os
import sqlite3
from datetime import datetime
from rich.console import Console
from rich.table import Table

from db_utils import persist_query_results, get_last_run_timestamp, check_existing_results, initialize_sqlite_db
from ch_utils import get_clickhouse_client, execute_sharded_query
from enricher import enrich_actor_logins, enrich_single_actor

def display_results(rows, column_names):
    console = Console()
    table = Table(show_header=True, header_style="bold magenta")

    for column_name in column_names:
        table.add_column(column_name)

    for row in rows:
        formatted_row = []
        for item in row:
            if isinstance(item, datetime):
                formatted_row.append(item.strftime('%Y-%m-%d %H:%M:%S'))
            else:
                formatted_row.append(str(item))
        table.add_row(*formatted_row)

    console.print(table)

def main():
    parser = argparse.ArgumentParser(description="Run ClickHouse queries from files or enrich data.")
    parser.add_argument("query_file", nargs='?', help="Path to the query file in the 'queries' directory (optional if --enrich is used).")
    parser.add_argument("--start_date", help="Start date for the query in YYYY-MM-DD HH:MM:SS format. Disables caching and persistence.", type=str)
    parser.add_argument("--enrich", nargs='?', const=True, default=False, help="Enrich actor login data. Can be used as a flag (--enrich) for bulk enrichment or with a specific actor login (--enrich <actor_login>).")
    args = parser.parse_args()

    query = None
    if args.query_file:
        query_path = os.path.join("queries", args.query_file)
        if not os.path.exists(query_path):
            print(f"Error: Query file '{query_path}' not found.")
            return
        with open(query_path, 'r') as f:
            query = f.read()

    if not args.query_file and not args.enrich:
        print("Error: Either a query_file must be provided or --enrich must be used.")
        parser.print_help()
        return

    conn = sqlite3.connect('query_results.db')
    initialize_sqlite_db(conn)
    ch_client = get_clickhouse_client()

    query_name = None
    if args.query_file:
        query_name = os.path.basename(args.query_file)

    today = datetime.now()

    if args.enrich:
        if isinstance(args.enrich, str):
            # A specific actor login is provided
            print(f"Enriching single actor: {args.enrich}")
            enrich_single_actor(conn, args.enrich)
        else:
            # --enrich is used as a flag for bulk enrichment
            print("Starting bulk actor login enrichment...")
            enrich_actor_logins(conn, ch_client)
        conn.close()
        return

    # If we are here, it means --enrich was not used, so query_file must be present
    if not query_name:
        print("Error: query_file is required when --enrich is not used.")
        conn.close()
        return

    disable_cache_persist = False
    last_run_timestamp = None

    if args.start_date:
        try:
            start_datetime = datetime.strptime(args.start_date, '%Y-%m-%d %H:%M:%S')
            print(f"Running query against logs since {start_datetime.strftime('%Y-%m-%d %H:%M:%S')} (manual override).")
            last_run_timestamp = start_datetime
            disable_cache_persist = True
        except ValueError:
            print("Error: Invalid start_date format. Please use YYYY-MM-DD HH:MM:SS.")
            return
    else:
        existing_results = check_existing_results(conn, query_name, today)

        if existing_results:
            rows, column_names, _ = existing_results
            display_results(rows, column_names)
            conn.close()
            return
        else:
            last_run_timestamp = get_last_run_timestamp(conn, query_name)
            if last_run_timestamp:
                print(f"Running query against logs since {last_run_timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                print("Running query against all available logs (no previous run found).")

    modified_query = query # Initialize modified_query with the original query

    # If a last_run_timestamp exists, we assume the original query does not contain
    # a WHERE clause on `created_at` and we append it.
    # If the original query already contains a WHERE clause, this logic might need
    # to be more sophisticated (e.g., using a SQL parser).
    if last_run_timestamp:
        timestamp_str = last_run_timestamp.strftime('%Y-%m-%d %H:%M:%S')
        # Check if the query already has a WHERE clause
        if "WHERE" in query.upper():
            # If it has a WHERE clause, append the created_at condition with AND
            modified_query = query.strip() + f"\nAND created_at > '{timestamp_str}'"
        else:
            # If no WHERE clause, add one
            modified_query = query.strip() + f"\nWHERE created_at > '{timestamp_str}'"
        modified_query += "\nORDER BY created_at DESC" # Ensure ordering for sharding

    try:
        result = ch_client.query(modified_query)
        if len(result.result_rows) == 0:
            print("No results")
        else:
            display_results(result.result_rows, result.column_names)

            if not disable_cache_persist:
                persist_query_results(conn, query_name, today, result)

    except Exception as e:
        if "TOO_MANY_ROWS_OR_BYTES" in str(e) or "Code: 396" in str(e):
            print(f"Query too large, attempting sharded query: {e}")
            try:
                # Pass the original query (without the appended WHERE clause) to sharded query
                # as sharded_query will add its own WHERE clause for date ranges.
                result = execute_sharded_query(ch_client, query, last_run_timestamp)
                display_results(result.result_rows, result.column_names)
                if not disable_cache_persist:
                    persist_query_results(conn, query_name, today, result)
            except Exception as sharded_e:
                print(f"Error executing sharded ClickHouse query: {sharded_e}")
                conn.close() # Close connection on sharded query error
                return # Exit main function
        else:
            print(f"Error executing ClickHouse query: {e}")
            conn.close() # Close connection on general query error
            return # Exit main function

    conn.close()

if __name__ == "__main__":
    main()
