# BHEU Demos

This repository contains three demos for Black Hat Europe 2025's **[The Forensic Trail On GitHub: Hunting For Supply Chain Activity](https://blackhat.com/eu-25/briefings/schedule/index.html#the-forensic-trail-on-github-hunting-for-supply-chain-activity-48832)**


1.  **`potential_attacks_demo`**: A Flask web application that shows a demo of identifying and investigating an attack based off the public GH firehose.
2.  **`ghdig`**: A command-line tool for investigating GitHub activity.
3. **`gitthrunter`**: A toy tool that identifies suspicious GitHub activity, enriches it, and renders it for futher investigation.

---

## `potential_attacks_demo`

### Running the demo

1.  Navigate to the `potential_attacks_demo` directory:
    ```bash
    cd potential_attacks
    ```
2.  Install the required dependencies:
    ```bash
    pip install -r requirements.txt
    ```
3.  Run the Flask application:
    ```bash
    flask run
    ```
4.  Open your web browser and go to `http://127.0.0.1:5000` to see the demo.

---

## `ghdig`

### Installation

1.  Navigate to the `ghdig` directory:
    ```bash
    cd ghdig
    ```
2.  Install the required dependencies:
    ```bash
    pip install -r requirements.txt
    ```

### Configuration

`ghdig` requires a GitHub Personal Access Token to interact with the GitHub API.

1.  Create a file named `.env` in the `ghdig` directory.
2.  Add your GitHub token to the file like this:

    ```
    GITHUB_TOKEN=your_github_token_here
    ```

### Usage

The tool is run as a Python module from the root of the project.

```bash
python -m ghdig <command> [options]
```

### Commands

Here are the available commands and examples of how to use them:

*   **`gist`**: Handles GitHub Gists.
    *   **Usage:** `python -m ghdig gist <gist_id_or_url>`
    *   **Example:** `python -m ghdig gist https://gist.github.com/mmvojwip/e9975a3a16acc492e3e7f677b6276cb2`

*   **`pr`**: Handles GitHub Pull Requests.
    *   **Usage:** `python -m ghdig pr <repo_url>`
    *   **Example:** `python -m ghdig pr https://github.com/7finney/ethcode`

*   **`commit`**: Handles GitHub Commits.
    *   **Usage:** `python -m ghdig commit <commit_url>`
    *   **Example:** `python -m ghdig commit https://github.com/mmvojwip/agentkit/commit/023f11f08cc7b82036a78580202143381d703b9a`

*   **`user`**: Analyzes a GitHub user.
    *   **Usage:** `python -m ghdig user <username_or_url>`
    *   **Example:** `python -m ghdig user mmvojwip`

*   **`render`**: Renders a user analysis HTML report.
    *   **Usage:** `python -m ghdig render <username>`
    *   **Example:** `python -m ghdig render mmvojwip`

*   **`absence`**: Checks for absent users and repos from a ClickHouse query.
    *   **Usage:** `python -m ghdig absence "<query>"`
    *   **Example:** `python -m ghdig absence "$(< ghdig/tjactions_demo_query.sql)"`

## `gitthrunter`

### Installation

1.  Navigate to the `gitthrunter` directory:
    ```bash
    cd gitthrunter
    ```
2.  Install the required dependencies:
    ```bash
    pip install -r requirements.txt
    ```

## Usage

To run a query, execute the `main.py` script and provide the path to your SQL query file located in the `queries/` directory.

```bash
python main.py potential_attacks.sql --start_date "2025-09-01 00:00:00"
```

_Note: --start\_date may be necessary to cut down on query size_

Then, enrich the actor data:

```bash
python main.py potential_attacks.sql --enrich
```

_Note: enrichment will likely have issues with rate limits if a github token is not configured_


Finally, start the app:

```bash
python app.py
```