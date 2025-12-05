import sqlite3
import time
from datetime import datetime
from rich.console import Console
import db_utils
import api_enricher

class MockClickHouseResultForEnricher:
    def __init__(self, rows, column_names, column_types):
        self.result_rows = rows
        self.column_names = column_names
        self.column_types = column_types

def identify_un_enriched_actors(sqlite_conn):
    """
    Identifies actor logins that exist in cached tables but are missing
    enrichment data (company, location, email) in the github_users_history_enrichment table.
    """
    console = Console()
    cursor = sqlite_conn.cursor()
    un_enriched_actors = set()

    # Get all unique actor_logins from all cached tables
    all_actor_logins = set()
    try:
        cursor.execute(f"SELECT DISTINCT actor_login FROM cached_potential_attacks WHERE actor_login IS NOT NULL AND actor_login != ''") # TKTK LIMIT
        logins = cursor.fetchall()
        for login in logins:
            all_actor_logins.add(login[0])
    except sqlite3.OperationalError as e:
        console.print(f"[bold red]  Error extracting from cached_potential_attacks: {e}[/bold red]")

    if not all_actor_logins:
        console.print("[bold yellow]No unique actor_logins found in cached_potential_attacks tables.[/bold yellow]")
        return set()

    # Check the enrichment table for existing data
    enrichment_table_name = db_utils._sanitize_table_name("github_users_history_enrichment")
    cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{enrichment_table_name}'")
    table_exists = cursor.fetchone()

    if table_exists:
        # Get actor_logins that have a relevant field filled
        enriched_actors_query = f"""
        SELECT DISTINCT login FROM {enrichment_table_name}
        WHERE (company IS NOT NULL AND company != '')
          OR (location IS NOT NULL AND location != '')
          OR (email IS NOT NULL AND email != '')
          OR (blog IS NOT NULL and blog != '')
        """
        try:
            cursor.execute(enriched_actors_query)
            fully_enriched_logins = {row[0] for row in cursor.fetchall()}
            un_enriched_actors = all_actor_logins - fully_enriched_logins
        except sqlite3.OperationalError as e:
            console.print(f"[bold red]Error querying enrichment table: {e}. Assuming all actors need enrichment.[/bold red]")
            un_enriched_actors = all_actor_logins
    else:
        console.print("[bold yellow]Enrichment table does not exist. All actors will be considered un-enriched.[/bold yellow]")
        un_enriched_actors = all_actor_logins

    console.print(f"[bold blue]Number of un-enriched actors: {len(un_enriched_actors)}[/bold blue]")
    return un_enriched_actors

def enrich_actor_logins(sqlite_conn, ch_client):
    console = Console()
    console.print("[bold blue]Starting actor login enrichment...[/bold blue]")

    # 1. Grab all unique actor_login's from the database that need enrichment
    unique_actor_logins_for_ch = set()
    unique_actor_logins_for_api = identify_un_enriched_actors(sqlite_conn)

    # Separate actors for ClickHouse vs. API enrichment
    # For now, all un-enriched actors will first attempt ClickHouse enrichment
    # Later, we can refine this to prioritize API for certain cases or as a fallback
    unique_actor_logins_for_ch = unique_actor_logins_for_api

    if not unique_actor_logins_for_ch and not unique_actor_logins_for_api:
        console.print("[bold yellow]No unique actor_logins found that need enrichment. Skipping.[/bold yellow]")
        return

    if unique_actor_logins_for_ch:
        console.print(f"[bold green]Found {len(unique_actor_logins_for_ch)} unique actor_logins for ClickHouse enrichment. Querying ClickHouse...[/bold green]")

        enrichment_query_name = "github_users_history_enrichment"
        run_date = datetime.now() # This run_date is for metadata, not for caching logic

        # We'll fetch data in chunks to avoid very long IN clauses
        chunk_size = 500
        all_user_data_rows = []
        all_user_data_column_names = []
        all_user_data_column_types = []

        for i in range(0, len(unique_actor_logins_for_ch), chunk_size):
            login_chunk = list(unique_actor_logins_for_ch)[i:i + chunk_size]
            login_list_str = ', '.join(f"'{login}'" for login in login_chunk)

            ch_query = f"SELECT * FROM github_users_history WHERE login IN ({login_list_str})"

            try:
                console.print(f"  [dim]Querying ClickHouse for chunk {i//chunk_size + 1}...[/dim]")
                ch_result = ch_client.query(ch_query)

                if not all_user_data_column_names:
                    all_user_data_column_names = ch_result.column_names
                    all_user_data_column_types = ch_result.column_types

                all_user_data_rows.extend(ch_result.result_rows)

            except Exception as e:
                console.print(f"[bold red]  Error querying ClickHouse for actor logins: {e}[bold red]")
                # Continue to next chunk even if one fails

        if not all_user_data_rows:
            console.print("[bold yellow]No user data fetched from ClickHouse. Skipping persistence.[/bold yellow]")
        else:
            # 3. Persist the data in the database using upsert
            mock_result = MockClickHouseResultForEnricher(all_user_data_rows, all_user_data_column_names, all_user_data_column_types)
            db_utils.upsert_enrichment_results(sqlite_conn, enrichment_query_name, run_date, mock_result)

    # Re-evaluate un-enriched actors after ClickHouse enrichment
    unique_actor_logins_for_api = identify_un_enriched_actors(sqlite_conn)

    # Now, handle API enrichment for any remaining un-enriched actors
    if unique_actor_logins_for_api:
        console.print(f"[bold green]Found {len(unique_actor_logins_for_api)} unique actor_logins for API enrichment. Querying GitHub API...[/bold green]")
        api_enriched_rows = []
        api_enriched_column_names = []
        api_enriched_column_types = []

        # Define the columns we expect from GitHub API enrichment
        # These should match the fields being updated in api_enricher.py
        expected_api_columns = [
            "login", "company", "location", "email", "bio", "blog",
            "twitter_username", "public_repos", "followers", "following",
            "created_at", "updated_at"
        ]
        # Map GitHub API types to SQLite types for persistence
        api_column_types_map = {
            "login": "TEXT", "company": "TEXT", "location": "TEXT", "email": "TEXT",
            "bio": "TEXT", "blog": "TEXT", "twitter_username": "TEXT",
            "public_repos": "NUMERIC", "followers": "NUMERIC", "following": "NUMERIC",
            "created_at": "TEXT", "updated_at": "TEXT"
        }
        api_enriched_column_names = expected_api_columns
        api_enriched_column_types = [api_column_types_map[col] for col in expected_api_columns]

        for actor_login in unique_actor_logins_for_api:
            console.print(f"  [dim]Enriching {actor_login} via GitHub API...[/dim]")
            # Create a mock actor data dictionary for api_enricher
            mock_actor_data = {"actor": actor_login}

            # Check if the actor is already marked as a 404 actor
            if db_utils.is_404_actor(sqlite_conn, actor_login):
                console.print(f"  [dim]Skipping {actor_login} as it's a known 404 actor.[/dim]")
                continue

            enriched_data, status_code = api_enricher.enrich_actor_with_github_data(mock_actor_data)

            if status_code == 404:
                console.print(f"  [yellow]Actor {actor_login} returned 404. Marking as 404 actor.[/yellow]")
                db_utils.insert_404_actor(sqlite_conn, actor_login, actor_login) # Store actor_login as both actor_login and actor for simplicity
                continue # Skip further processing for this actor

            if enriched_data: # Check if enrichment was successful
                # Convert the dictionary to a list of values in the expected order
                row_values = [enriched_data.get(col) for col in expected_api_columns]
                api_enriched_rows.append(row_values)

            time.sleep(1) # Sleep to avoid rate limiting

        print(api_enriched_rows)
        if api_enriched_rows:
            api_mock_result = MockClickHouseResultForEnricher(api_enriched_rows, api_enriched_column_names, api_enriched_column_types)
            # Persist API enriched data using upsert
            db_utils.upsert_enrichment_results(sqlite_conn, enrichment_query_name, run_date, api_mock_result)
            console.print("[bold green]API enrichment data persisted.[/bold green]")
        else:
            console.print("[bold yellow]No user data fetched from GitHub API. Skipping persistence.[/bold yellow]")

    console.print("[bold blue]Actor login enrichment complete.[/bold blue]")

def enrich_single_actor(sqlite_conn, actor_login):
    """
    Enriches a single actor login using the GitHub API and persists the data.
    """
    console = Console()
    console.print(f"[bold blue]Starting enrichment for single actor: {actor_login}...[/bold blue]")
    run_date = datetime.now()
    enrichment_query_name = "github_users_history_enrichment"

    # Similar to the bulk API enrichment part, but for a single actor
    expected_api_columns = [
        "login", "company", "location", "email", "bio", "blog",
        "twitter_username", "public_repos", "followers", "following",
        "created_at", "updated_at"
    ]
    api_column_types_map = {
        "login": "TEXT", "company": "TEXT", "location": "TEXT", "email": "TEXT",
        "bio": "TEXT", "blog": "TEXT", "twitter_username": "TEXT",
        "public_repos": "NUMERIC", "followers": "NUMERIC", "following": "NUMERIC",
        "created_at": "TEXT", "updated_at": "TEXT"
    }
    api_enriched_column_names = expected_api_columns
    api_enriched_column_types = [api_column_types_map[col] for col in expected_api_columns]

    mock_actor_data = {"actor": actor_login}
    if db_utils.is_404_actor(sqlite_conn, actor_login):
        console.print(f"  [dim]Skipping {actor_login} as it's a known 404 actor.[/dim]")
        return

    enriched_data, status_code = api_enricher.enrich_actor_with_github_data(mock_actor_data)

    if status_code == 404:
        console.print(f"  [yellow]Actor {actor_login} returned 404. Marking as 404 actor.[/yellow]")
        db_utils.insert_404_actor(sqlite_conn, actor_login, actor_login)
        return

    if enriched_data:
        row_values = [enriched_data.get(col) for col in expected_api_columns]
        api_mock_result = MockClickHouseResultForEnricher([row_values], api_enriched_column_names, api_enriched_column_types)
        db_utils.upsert_enrichment_results(sqlite_conn, enrichment_query_name, run_date, api_mock_result)
        console.print("[bold green]API enrichment data persisted.[/bold green]")
    else:
        console.print(f"[bold yellow]No user data fetched from GitHub API for {actor_login}. Skipping persistence.[/bold yellow]")

    console.print(f"[bold blue]Enrichment for {actor_login} complete.[/bold blue]")