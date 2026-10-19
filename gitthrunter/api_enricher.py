"""
API Enricher for GitHub Actor Data
"""

import os
import requests
from pathlib import Path

GITHUB_API_BASE_URL = "https://api.github.com"

def _load_github_token():
    """Load GITHUB_TOKEN from environment or .env file."""
    token = os.getenv("GITHUB_TOKEN")
    if token:
        return token

    # Try loading from .env in current directory or parent
    for env_path in [Path(".env"), Path("../.env"), Path("../ghdig/.env")]:
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("GITHUB_TOKEN="):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None

def get_github_user_data(username: str) -> tuple[dict | None, int]:
    """
    Fetches user data from the GitHub API.
    Returns a tuple of (user_data, status_code).
    """
    headers = {}
    github_token = _load_github_token()
    if github_token:
        headers["Authorization"] = f"token {github_token}"

    url = f"{GITHUB_API_BASE_URL}/users/{username}"
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Raise an HTTPError for bad responses (4xx or 5xx)
        return response.json(), response.status_code
    except requests.exceptions.HTTPError as http_err:
        if response.status_code != 404:
            print(f"HTTP error occurred: {http_err} - Response: {response.text}")
        return None, response.status_code
    except requests.exceptions.ConnectionError as conn_err:
        print(f"Connection error occurred: {conn_err}")
        return None, -1 # Custom status for connection error
    except requests.exceptions.Timeout as timeout_err:
        print(f"Timeout error occurred: {timeout_err}")
        return None, -2 # Custom status for timeout error
    except requests.exceptions.RequestException as req_err:
        print(f"An unexpected error occurred: {req_err}")
        return None, -3 # Custom status for other request errors
    return None, 0 # Default return for unexpected cases

def enrich_actor_with_github_data(actor_data: dict) -> tuple[dict, int]:
    """
    Enriches actor data with information from GitHub if a username is available
    and certain fields are missing.
    Returns a tuple of (enriched_actor_data, status_code).
    """
    username = actor_data.get("actor") # Assuming 'actor' field holds the GitHub username
    if not username:
        print(actor_data)
        return actor_data, 200 # Return original data and a success status if no username

    github_data, status_code = get_github_user_data(username)
    if github_data: # Check if github_data (the dictionary) is not None
        actor_data["login"] = username
        actor_data["company"] = actor_data.get("company") or github_data.get("company")
        actor_data["location"] = actor_data.get("location") or github_data.get("location")
        actor_data["email"] = actor_data.get("email") or github_data.get("email")
        actor_data["bio"] = actor_data.get("bio") or github_data.get("bio")
        actor_data["blog"] = actor_data.get("blog") or github_data.get("blog")
        actor_data["twitter_username"] = actor_data.get("twitter_username") or github_data.get("twitter_username")
        actor_data["public_repos"] = actor_data.get("public_repos") or github_data.get("public_repos")
        actor_data["followers"] = actor_data.get("followers") or github_data.get("followers")
        actor_data["following"] = actor_data.get("following") or github_data.get("following")
        actor_data["created_at"] = actor_data.get("created_at") or github_data.get("created_at")
        actor_data["updated_at"] = actor_data.get("updated_at") or github_data.get("updated_at")

    return actor_data, status_code
