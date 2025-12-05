# ghdig.py

import argparse
from rich.console import Console
from .commands import handle_gist, handle_pr, handle_commit, handle_user, handle_absence
from .html_renderer import main as render_main

console = Console()

def main():
    parser = argparse.ArgumentParser(description="A tool for GitHub digging.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output for debugging.")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Gist subcommand
    gist_parser = subparsers.add_parser("gist", help="Handle GitHub Gists")
    gist_parser.add_argument("gist_id_or_url", type=str, help="Gist ID or URL")
    gist_parser.set_defaults(func=handle_gist)

    # PR subcommand
    pr_parser = subparsers.add_parser("pr", help="Handle GitHub Pull Requests")
    pr_parser.add_argument("repo_url", type=str, help="GitHub repository URL")
    pr_parser.set_defaults(func=handle_pr)

    # Commit subcommand
    commit_parser = subparsers.add_parser("commit", help="Handle GitHub Commits")
    commit_parser.add_argument("commit_url", type=str, help="GitHub commit URL")
    commit_parser.set_defaults(func=handle_commit)

    # User subcommand
    user_parser = subparsers.add_parser("user", help="Analyze a GitHub user")
    user_parser.add_argument("user", type=str, help="GitHub username or URL")
    user_parser.set_defaults(func=handle_user)

    # Render subcommand
    render_parser = subparsers.add_parser("render", help="Render user analysis HTML report")
    render_parser.add_argument("user", type=str, help="GitHub username")
    render_parser.set_defaults(func=lambda args: render_main(args.user))

    # Absence subcommand
    absence_parser = subparsers.add_parser("absence", help="Check for absent users and repos from a ClickHouse query")
    absence_parser.add_argument("query", type=str, help="ClickHouse query to extract usernames and repos")
    absence_parser.set_defaults(func=handle_absence)

    args = parser.parse_args()

    if hasattr(args, "func"):
        # Pass all args to the handler function
        args.func(args)
    else:
        console.print("[bold red]Error:[/bold red] No command provided. Use --help for usage.")
        parser.print_help()

if __name__ == "__main__":
    main()
