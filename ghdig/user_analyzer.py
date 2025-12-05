import json
import subprocess
import tempfile
import os
from rich.console import Console
from .utils import get_clickhouse_client
from datetime import datetime

import requests
import dotenv

dotenv.load_dotenv()
console = Console()

def debug_print(verbose, message):
    if verbose:
        console.print(f"[bold yellow]DEBUG:[/bold yellow] {message}")

def _make_github_api_request(url, verbose=False):
    """Make a request to the GitHub API with authentication."""
    debug_print(verbose, f"Making API request to {url}")
    github_token = os.getenv("GITHUB_TOKEN")
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json"
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        debug_print(verbose, f"API request successful, status code: {response.status_code}")
        return response
    except requests.exceptions.RequestException as e:
        debug_print(verbose, f"API request failed: {e}")
        return e

def get_user_info(username, verbose=False):
    """Hit the GH api and get information on the user directly"""
    api_url = f"https://api.github.com/users/{username}"
    response = _make_github_api_request(api_url, verbose)
    if isinstance(response, requests.Response):
        return response.json()
    return {"error": str(response)}

def check_user_keys(username, verbose=False):
    """Check if the user has keys set (github.com/{username}.keys, github.com/{username}.gpg)"""
    keys_url = f"https://github.com/{username}.keys"
    gpg_url = f"https://github.com/{username}.gpg"
    keys_content = None
    gpg_content = None

    debug_print(verbose, f"Checking for SSH keys at {keys_url}")
    try:
        response = requests.get(keys_url)
        if response.status_code == 200 and response.text:
            keys_content = response.text
            debug_print(verbose, "Found SSH keys.")
    except requests.exceptions.RequestException as e:
        debug_print(verbose, f"Error checking SSH keys: {e}")
        pass

    debug_print(verbose, f"Checking for GPG keys at {gpg_url}")
    try:
        response = requests.get(gpg_url)
        if response.status_code == 200 and response.text and "Note: This user hasn't uploaded any GPG keys." not in response.text:
            gpg_content = response.text
            debug_print(verbose, "Found GPG keys.")
    except requests.exceptions.RequestException as e:
        debug_print(verbose, f"Error checking GPG keys: {e}")
        pass

    return {"ssh_keys": keys_content, "gpg_keys": gpg_content}

def search_clickhouse(username, verbose=False):
    """Search clickhouse for activity in the last year by both actor_login, created_by_user, and unique repo_name like "{username}/%"""
    query = f"""
    SELECT event_type,actor_login,repo_name,created_at,creator_user_login
    FROM github_events
    WHERE created_at > now() - INTERVAL 1 YEAR
     AND (actor_login = '{username}'
     OR creator_user_login = '{username}'
     OR repo_name like '{username}/%')
     ORDER BY created_at DESC
    """
    debug_print(verbose, f"Executing ClickHouse query for user {username}")
    try:
        client = get_clickhouse_client()
        result = client.query(query)
        debug_print(verbose, f"ClickHouse query returned {len(result.result_rows)} rows.")
        return result.result_rows
    except Exception as e:
        debug_print(verbose, f"ClickHouse query failed: {e}")
        return {"error": str(e)}

def calculate_active_hours(activity, verbose=False):
    """Calculate active hours from clickhouse activity
    For each line in clickhouse results, get `created_at`
    Get hour from `created_at` timestamp
    Group by clock hour
    """
    if not activity or "error" in activity:
        return {}

    hour_counts = {i: 0 for i in range(24)}
    for event in activity:
        if len(event) > 3:
            timestamp_str = event[3]
            if isinstance(timestamp_str, str):
                try:
                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    hour = timestamp.hour
                    hour_counts[hour] += 1
                except ValueError:
                    # Handle cases where the string is not a valid ISO format
                    pass
            elif isinstance(timestamp_str, datetime):
                hour = timestamp_str.hour
                hour_counts[hour] += 1

    debug_print(verbose, f"Calculated active hours: {hour_counts}")
    return hour_counts

def check_deleted_repos(activity, verbose=False):
    """Check for any deleted repos in clickhouse interactions"""
    if not activity or "error" in activity:
        return []

    repos = set(event[2] for event in activity if len(event) > 2 and event[2])
    deleted_repos = []
    debug_print(verbose, f"Checking {len(repos)} repos for deletion status.")
    for repo in repos:
        api_url = f"https://api.github.com/repos/{repo}"
        response = _make_github_api_request(api_url, verbose)
        if isinstance(response, requests.Response) and response.status_code == 404:
            deleted_repos.append(repo)
            debug_print(verbose, f"Detected deleted repo: {repo}")
    return deleted_repos


def user_deleted(user, verbose=False):
    """Check if a user is deleted by trying to fetch their info."""
    api_url = f"https://api.github.com/users/{user}"
    response = _make_github_api_request(api_url, verbose)
    if isinstance(response, requests.Response):
        is_deleted = response.status_code == 404
        debug_print(verbose, f"User {user} deleted status: {is_deleted}")
        return is_deleted
    return False

def check_deleted_users(activity, verbose=False):
    """Check for any deleted users in clickhouse interactions"""
    found_users = set()
    deleted_users = set()
    for line in activity:
        actor_username = line[1]
        repo_name = line[2]
        creator = line[4]
        repo_user = repo_name.split('/')[0]
        found_users.update([actor_username,repo_user,creator])

    debug_print(verbose, f"Checking {len(found_users)} users for deletion status.")
    for user in found_users:
        if user_deleted(user, verbose):
            deleted_users.add(user)
            debug_print(verbose, f"Detected deleted user: {user}")

    return list(set(deleted_users))

def run_gh_fake_analyzer(username, verbose=False):
    """Run gh-fake-analyzer and return the JSON output."""
    output_dir = "ghdig/outputs"
    with tempfile.TemporaryDirectory() as temp_dir:
        command = ["gh-analyze", username, "--out_path", temp_dir]
        debug_print(verbose, f"Running command: {' '.join(command)}")

        try:
            # Get the current environment and add the GH_TOKEN
            env = os.environ.copy()
            github_token = os.getenv("GITHUB_TOKEN")
            if github_token:
                env["GH_TOKEN"] = github_token
                debug_print(verbose, "Setting GH_TOKEN for gh-analyze subprocess.")

            # Change working directory to redirect dependency outputs
            result = subprocess.run(command, capture_output=True, text=True, check=True, env=env, cwd=output_dir)
            debug_print(verbose, f"gh-analyze stdout: {result.stdout}")
            debug_print(verbose, f"gh-analyze stderr: {result.stderr}")

            output_file_path = os.path.join(temp_dir, username, "report.json")

            if not os.path.exists(output_file_path):
                error_msg = f"Output file not found at {output_file_path}"
                debug_print(verbose, error_msg)
                return {"error": error_msg}

            with open(output_file_path, 'r') as f:
                return json.load(f)

        except FileNotFoundError:
            error_msg = "gh-analyze command not found. Make sure it's in your PATH."
            debug_print(verbose, error_msg)
            return {"error": error_msg}
        except subprocess.CalledProcessError as e:
            error_msg = f"gh-analyze failed: {e.stderr}"
            debug_print(verbose, error_msg)
            return {"error": error_msg}
        except Exception as e:
            error_msg = str(e)
            debug_print(verbose, error_msg)
            return {"error": error_msg}

def analyze_user(username, verbose=False):
    """
    Run all user analysis steps and aggregate the results, with caching.
    """
    debug_print(verbose, f"Starting analysis for user: {username}")
    output_dir = "ghdig/outputs"
    os.makedirs(output_dir, exist_ok=True)
    cache_file = os.path.join(output_dir, f"{username}_analysis.json")
    if os.path.exists(cache_file):
        with open(cache_file, 'r') as f:
            results = json.load(f)
            print("Loaded results from cache.")
            if verbose:
                print(json.dumps(results, indent=4))
            return

    clickhouse_activity = search_clickhouse(username, verbose)
    gh_fake_analyzer_results = run_gh_fake_analyzer(username, verbose)

    unique_emails_owner = []
    if "unique_emails" in gh_fake_analyzer_results and gh_fake_analyzer_results["unique_emails"]:
        owner_emails = gh_fake_analyzer_results["unique_emails"][0].get("owner", [])

        # Process emails to be case-insensitive and unique
        seen_emails = set()
        unique_emails_list = []
        for item in owner_emails:
            email_lower = item['email'].lower()
            if email_lower not in seen_emails:
                seen_emails.add(email_lower)
                unique_emails_list.append(item)

        unique_emails_owner = unique_emails_list
        debug_print(verbose, f"Found and processed unique emails for owner: {unique_emails_owner}")

    results = {
        "user_info": get_user_info(username, verbose),
        "keys": check_user_keys(username, verbose),
        "clickhouse_activity": clickhouse_activity,
        "active_hours": calculate_active_hours(clickhouse_activity, verbose),
        "deleted_repos": check_deleted_repos(clickhouse_activity, verbose),
        "deleted_users": check_deleted_users(clickhouse_activity, verbose),
        "gh_fake_analyzer": gh_fake_analyzer_results,
        "unique_emails_owner": unique_emails_owner,
    }

    debug_print(verbose, "Saving analysis results to cache file.")
    with open(cache_file, 'w') as f:
        # Custom JSON serialization for datetime objects
        def json_default(o):
            if isinstance(o, datetime):
                return o.isoformat()
            raise TypeError(f"Object of type {o.__class__.__name__} is not JSON serializable")
        json.dump(results, f, indent=4, default=json_default)

    if verbose:
        print(json.dumps(results, indent=4, default=json_default))
