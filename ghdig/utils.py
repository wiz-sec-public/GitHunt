import os
import requests
import re
from rich.console import Console
from rich.prompt import Prompt
from clickhouse_connect import get_client

console = Console()

def get_clickhouse_client():
    return get_client(host='play.clickhouse.com', port=443, username='play', password='', secure=True)

def debug_print(verbose, message):
    if verbose:
        console.print(f"[bold yellow]DEBUG:[/bold yellow] {message}")

def find_fork_event_in_clickhouse(repo_name, actor_name, verbose=False):
    """
    Queries ClickHouse to find fork events for a given repository name.
    """
    query = f"""
    select actor_login, repo_name
    from github_events
    where event_type = 'ForkEvent' and repo_name like '%/{repo_name}' and actor_login = '{actor_name}'
    order by created_at desc limit 1
    """
    debug_print(verbose, f"Querying ClickHouse for fork event for repo '{repo_name}' by actor '{actor_name}'")
    console.print(f"[bold blue]Querying ClickHouse for fork event:[/bold blue] {repo_name}")
    try:
        ch_client = get_clickhouse_client()
        result = ch_client.query(query)
        if result and result.result_rows:
            repo_name = result.result_rows[0][1]
            actor_name = result.result_rows[0][0]
            debug_print(verbose, f"Found fork event: repo '{repo_name}', actor '{actor_name}'")
            return actor_name, repo_name
        debug_print(verbose, "No fork event found.")
        return None, None
    except requests.exceptions.RequestException as e:
        console.print(f"[bold red]Error querying ClickHouse:[/bold red] {e}")
        debug_print(verbose, f"ClickHouse query failed: {e}")
        return None, None

def validate_github_url(url, verbose=False):
    """
    Validates if the given URL is a valid GitHub URL.
    """
    debug_print(verbose, f"Validating GitHub URL: {url}")
    if not isinstance(url, str):
        debug_print(verbose, "URL is not a string.")
        return False
    # Basic check for GitHub domain
    if "github.com" not in url.lower():
        debug_print(verbose, "URL does not contain 'github.com'.")
        return False
    # More robust URL validation could be added here if needed
    debug_print(verbose, "URL appears to be a valid GitHub URL.")
    return True

def extract_repo_info(repo_url, verbose=False):
    # Extracts owner and repo name from a GitHub repository URL
    debug_print(verbose, f"Extracting repo info from URL: {repo_url}")
    if "github.com" not in repo_url:
        debug_print(verbose, "URL does not contain 'github.com'.")
        return None, None

    # Remove common prefixes/suffixes
    processed_url = repo_url.replace("https://github.com/", "")
    processed_url = processed_url.replace("git@github.com:", "")
    processed_url = processed_url.replace(".git", "")

    parts = processed_url.split('/')
    if len(parts) >= 2:
        owner = parts[0]
        repo = parts[1]
        debug_print(verbose, f"Extracted owner '{owner}' and repo '{repo}'")
        return owner, repo

    debug_print(verbose, "Could not extract owner and repo from URL.")
    return None, None

def extract_commit_info(commit_url, verbose=False):
    # Extracts owner, repo name, and commit SHA from a GitHub commit URL
    debug_print(verbose, f"Extracting commit info from URL: {commit_url}")
    if "github.com" not in commit_url or "/commit/" not in commit_url:
        debug_print(verbose, "URL is not a valid GitHub commit URL.")
        return None, None, None

    try:
        parts = commit_url.split("/commit/")
        if len(parts) > 1:
            commit_sha = parts[1].split('/')[0]
            repo_parts = parts[0].replace("https://github.com/", "").split('/')
            if len(repo_parts) >= 2:
                owner = repo_parts[0]
                repo = repo_parts[1]
                debug_print(verbose, f"Extracted owner '{owner}', repo '{repo}', and SHA '{commit_sha}'")
                return owner, repo, commit_sha
    except Exception as e:
        debug_print(verbose, f"Error extracting commit info: {e}")
        pass

    debug_print(verbose, "Could not extract commit info from URL.")
    return None, None, None

def get_missing_issue_ids(owner, repo, verbose=False):
    debug_print(verbose, f"Getting missing issue IDs for {owner}/{repo}")
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        console.print("[bold red]Error:[/bold red] GITHUB_TOKEN not found in .env file. Please set it up.")
        return None

    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json"
    }
    all_issue_numbers = set()
    max_issue_id = 0
    page = 1
    per_page = 100 # GitHub API default is 30, max is 100

    while True:
        api_url = f"https://api.github.com/repos/{owner}/{repo}/issues?state=all&page={page}&per_page={per_page}"
        debug_print(verbose, f"Fetching issues from {api_url}")

        try:
            response = requests.get(api_url, headers=headers)
            response.raise_for_status() # Raise an exception for HTTP errors

            issues = response.json()
            if not issues:
                debug_print(verbose, "No more issues to fetch.")
                break # No more issues to fetch

            for issue in issues:
                issue_number = issue['number']
                all_issue_numbers.add(issue_number)
                if issue_number > max_issue_id:
                    max_issue_id = issue_number

            # Check for Link header to determine if there are more pages
            if 'link' in response.headers:
                if 'rel="next"' not in response.headers['link']:
                    debug_print(verbose, "Last page of issues reached.")
                    break # No more pages
            else:
                debug_print(verbose, "No 'link' header in response, assuming single page.")
                break # No link header, assume only one page or last page

            page += 1

        except requests.exceptions.RequestException as e:
            console.print(f"[bold red]Error fetching issues:[/bold red] {e}")
            debug_print(verbose, f"Request to {api_url} failed: {e}")
            return None

    if max_issue_id == 0:
        debug_print(verbose, "No issues found in the repository.")
        return [] # No issues found

    all_possible_issue_ids = set(range(1, max_issue_id + 1))
    missing_issue_ids = sorted(list(all_possible_issue_ids - all_issue_numbers))
    debug_print(verbose, f"Found {len(missing_issue_ids)} missing issue IDs: {missing_issue_ids}")

    return missing_issue_ids

def get_gist_hash_from_input(gist_input, verbose=False):
    debug_print(verbose, f"Getting gist hash from input: {gist_input}")
    # Check if it's a valid hash directly
    if is_valid_gist_hash(gist_input, verbose):
        debug_print(verbose, f"Input is a valid gist hash: {gist_input}")
        return gist_input

    # Check if it's a valid URL and extract hash
    gist_url_prefix = "gist.github.com/"
    if gist_url_prefix in gist_input:
        try:
            # Extract the hash from the URL
            # Example: https://gist.github.com/username/32-char-hash
            parts = gist_input.split(gist_url_prefix)
            if len(parts) > 1:
                hash_part = parts[1].split('/')[-1]
                if is_valid_gist_hash(hash_part, verbose):
                    debug_print(verbose, f"Extracted gist hash from URL: {hash_part}")
                    return hash_part
        except Exception as e:
            debug_print(verbose, f"Error extracting gist hash from URL: {e}")
            pass # Fall through to return None

    debug_print(verbose, "Could not determine a valid gist hash from the input.")
    return None

def is_valid_gist_hash(s, verbose=False):
    # A GitHub Gist hash is typically 32 characters long and consists of hexadecimal characters.
    is_valid = len(s) == 32 and all(c in "0123456789abcdefABCDEF" for c in s)
    debug_print(verbose, f"Validating '{s}' as gist hash: {is_valid}")
    return is_valid

def extract_username(user_input, verbose=False):
    debug_print(verbose, f"Extracting username from input: {user_input}")
    if "github.com/" in user_input:
        username = user_input.split("github.com/")[-1].split('/')[0]
        debug_print(verbose, f"Extracted username from URL: {username}")
        return username
    debug_print(verbose, f"Input is assumed to be a username: {user_input}")
    return user_input

def extract_entities_from_query(query, verbose=False):
    """
    Extracts usernames and repositories from a ClickHouse query,
    with improved column detection.
    """
    debug_print(verbose, "Extracting entities from query")
    usernames = set()
    repos = set()

    try:
        ch_client = get_clickhouse_client()
        result = ch_client.query(query)

        user_cols = []
        repo_cols = []

        user_col_names = Prompt.ask("Enter comma-separated column IDs for [bold magenta]usernames[/bold magenta] (or press Enter to skip)")
        if user_col_names:
            user_cols = user_col_names.split(',')

        repo_col_names = Prompt.ask("Enter comma-separated column IDs for [bold magenta]repositories[/bold magenta] (or press Enter to skip)")
        if repo_col_names:
            repo_cols = repo_col_names.split(',')

        if not user_cols and not repo_cols:
            console.print("[bold red]No columns specified for usernames or repositories. Aborting.[/bold red]")
            return [], []

        # Process rows
        for row in result.result_rows:
            for col_idx_str in user_cols:
                col_idx = int(col_idx_str)
                if row[col_idx]:
                    usernames.add(row[col_idx])

            for col_idx_str in repo_cols:
                col_idx = int(col_idx_str)
                if row[col_idx]:
                    repos.add(row[col_idx])
                    # Also extract username from repo name if possible
                    if '/' in row[col_idx] and row[col_idx] != '/':
                        usernames.add(row[col_idx].split('/')[0])

        debug_print(verbose, f"Extracted {len(usernames)} unique usernames and {len(repos)} unique repos")
        return list(usernames), list(repos)

    except Exception as e:
        console.print(f"[bold red]Error executing ClickHouse query:[/bold red] {e}")
        debug_print(verbose, f"Query execution failed: {e}")
        return [], []