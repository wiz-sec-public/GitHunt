# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GitHunt is a collection of tools for investigating GitHub supply chain attacks, presented at Black Hat Europe 2025. It contains three main components that query ClickHouse (play.clickhouse.com) for GitHub event data and the GitHub API for enrichment.

## Components

### ghdig
CLI tool for investigating GitHub artifacts (gists, PRs, commits, users). Run as a Python module from repo root:
```bash
cd ghdig && pip install -r requirements.txt
python -m ghdig <command> [options]
```

Commands: `gist`, `pr`, `commit`, `user`, `render`, `absence`

Requires `GITHUB_TOKEN` in `ghdig/.env`.

### gitthrunter
Query runner that detects suspicious GitHub activity:
```bash
cd gitthrunter && pip install -r requirements.txt

# Run query (table output by default)
python main.py potential_attacks_v2.sql --start_date "2026-01-01 00:00:00"

# Machine-parsable output formats
python main.py potential_attacks_v2.sql -f json -o results.json
python main.py potential_attacks_v2.sql -f jsonl -q | jq '.actor_login'
python main.py potential_attacks_v2.sql -f csv --limit 100

# Enrich actors with GitHub profile data
python main.py --enrich              # bulk enrichment
python main.py --enrich <username>     # single actor

# View results in Flask app
python app.py
```

**CLI Options:**
- `--output / -f`: Output format (`table`, `json`, `jsonl`, `csv`)
- `-o / --output-file`: Write to file instead of stdout
- `--limit N`: Limit number of results
- `--quiet / -q`: Suppress progress output (for scripting)
- `--no-cache`: Bypass SQLite cache, run fresh query

Queries live in `gitthrunter/queries/`. Results cached in SQLite (`query_results.db`).

**Primary query:** `potential_attacks_v2.sql` - detects command injection in branch names, PR titles, issue bodies. Event-type filtered for efficiency.

### potential_attacks_demo
Flask demo app showing attack investigation workflow:
```bash
cd potential_attacks_demo && pip install -r requirements.txt
flask run
```

## Architecture

- All tools connect to ClickHouse's public playground (`play.clickhouse.com`) for GitHub event data
- GitHub API calls require a personal access token for rate limits and authentication
- Output artifacts (cloned repos, gists, analysis JSON) go to `ghdig/outputs/` (gitignored)
- Large query results automatically shard by date chunks to avoid ClickHouse row limits (300B rows/hour quota)

## ClickHouse github_events Schema

Key searchable text fields for attack detection:
- `head_ref`: PR branch name (PullRequestEvent, PullRequestReviewEvent)
- `ref`: Branch/tag reference (PushEvent, CreateEvent, DeleteEvent)
- `title`: Issue/PR title (IssuesEvent, IssueCommentEvent)
- `body`: Issue/PR/comment body (IssuesEvent, IssueCommentEvent, PullRequestReviewCommentEvent, ReleaseEvent)

Query efficiency: filter by `event_type` before searching text fields to avoid scanning events where fields are empty.

## Key Dependencies

- `clickhouse-connect`: ClickHouse client
- `rich`: CLI output formatting
- `GitPython`: Git operations for cloning repos/gists
- `gh-fake-analyzer`: GitHub account analysis
- `Flask`: Web interfaces
