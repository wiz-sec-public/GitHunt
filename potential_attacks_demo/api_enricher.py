"""
API Enricher for GitHub Actor Data
"""

import os
import requests
import json

# Placeholder for GitHub API base URL
GITHUB_API_BASE_URL = "https://api.github.com"

def get_github_user_data(username: str) -> tuple[dict | None, int]:
    """
    Fetches user data from the GitHub API.
    Returns a tuple of (user_data, status_code).
    """
    headers = {}
    github_token = os.getenv("GITHUB_TOKEN")
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

def search_prs_mentioning_user(username: str) -> tuple[dict | None, int]:
    """
    Searches for pull requests mentioning a specific user.
    Returns a tuple of (search_results, status_code).
    """
    headers = {}
    github_token = os.getenv("GITHUB_TOKEN")
    if github_token:
        headers["Authorization"] = f"token {github_token}"

    # The query parameter needs to be properly encoded
    query = f'"{username}" is:pr'
    url = f"{GITHUB_API_BASE_URL}/search/issues"
    params = {'q': query}

    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json(), response.status_code
    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err} - Response: {response.text}")
        return None, response.status_code
    except requests.exceptions.RequestException as req_err:
        print(f"An unexpected error occurred: {req_err}")
        return None, -3
    return None, 0

if __name__ == "__main__":
    # Example usage:
    test_username = "octocat" # Replace with a real GitHub username for testing
    print(f"Fetching GitHub data for {test_username}...")
    user_data = get_github_user_data(test_username)
    if user_data:
        print(json.dumps(user_data, indent=2))

        # Simulate an actor record missing some data
        mock_actor = {"actor": test_username, "company": None, "location": None, "email": None}
        print("\nEnriching mock actor data:")
        enriched_actor = enrich_actor_with_github_data(mock_actor)
        print(json.dumps(enriched_actor, indent=2))
    else:
        print(f"Could not fetch data for {test_username}")

    test_username_no_data = "nonexistentuser12345"
    print(f"\nFetching GitHub data for {test_username_no_data} (should fail)...")
    user_data_no_data = get_github_user_data(test_username_no_data)
    if user_data_no_data:
        print(json.dumps(user_data_no_data, indent=2))
    else:
        print(f"Successfully handled no data for {test_username_no_data}")