import os
import webbrowser
from git import Repo, GitCommandError
from rich.console import Console
from rich.prompt import Prompt
from .user_analyzer import analyze_user
from .utils import (
    extract_repo_info,
    get_missing_issue_ids,
    validate_github_url,
    extract_commit_info,
    find_fork_event_in_clickhouse,
    get_gist_hash_from_input,
    extract_username,
    extract_entities_from_query,
)
import requests

console = Console()

def debug_print(verbose, message):
    if verbose:
        console.print(f"[bold yellow]DEBUG:[/bold yellow] {message}")

def handle_pr(args):
    debug_print(args.verbose, f"Handling PR for repo: {args.repo_url}")
    console.print(f"[bold blue]Searching repository for candidate deleted PRs:[/bold blue] {args.repo_url}")
    owner, repo = extract_repo_info(args.repo_url)
    if not owner or not repo:
        console.print(f"[bold red]Error:[/bold red] Invalid GitHub repository URL: {args.repo_url}")
        return
    debug_print(args.verbose, f"Extracted owner '{owner}' and repo '{repo}'")
    console.print(f"[bold green]Fetching Issues for:[/bold green] {owner}/{repo}")
    missing_issue_ids = get_missing_issue_ids(owner, repo)

    if missing_issue_ids:
        console.print(f"[bold magenta]Found {len(missing_issue_ids)} missing ID(s):[/bold magenta] [cyan]{', '.join(f'#{issue_id}' for issue_id in missing_issue_ids)}[/cyan]")
        debug_print(args.verbose, f"Missing issue IDs: {missing_issue_ids}")

        repo_dir = f"ghdig/outputs/repos/{owner}/{repo}"
        repo_url_full = f"https://github.com/{owner}/{repo}.git"
        debug_print(args.verbose, f"Repo directory: {repo_dir}")
        debug_print(args.verbose, f"Full repo URL: {repo_url_full}")

        if not os.path.exists(repo_dir):
            console.print(f"[bold cyan]Cloning repository (shallow):[/bold cyan] {repo_url_full}")
            try:
                local_repo = Repo.clone_from(repo_url_full, repo_dir)
                console.print(f"[bold green]Successfully cloned[/bold green] {repo_url_full} to {repo_dir}")
            except Exception as e:
                console.print(f"[bold red]Error cloning repository:[/bold red] {e}")
                debug_print(args.verbose, f"Cloning failed with exception: {e}")
                return
        else:
            console.print(f"[bold yellow]Repository already exists:[/bold yellow] {repo_dir}. Fetching latest.")
            try:
                local_repo = Repo(repo_dir)
                local_repo.remotes.origin.fetch()
            except Exception as e:
                console.print(f"[bold red]Error fetching from existing repository:[/bold red] {e}")
                debug_print(args.verbose, f"Fetching failed with exception: {e}")
                return

        for issue_id in missing_issue_ids:
            debug_print(args.verbose, f"Processing missing issue ID: {issue_id}")
            try:
                # Equivalent to git fetch origin pull/{id}/head:pr/{id}
                fetch_ref = f"pull/{issue_id}/head:pr/{issue_id}"
                debug_print(args.verbose, f"Fetching ref: {fetch_ref}")
                local_repo.remotes.origin.fetch(fetch_ref)
                console.print(f"[bold green]Successfully fetched PR[/bold green] #{issue_id}")

                # Find the base commit and list committers
                try:
                    pr_head = local_repo.commit(f"pr/{issue_id}")
                    debug_print(args.verbose, f"PR head commit for #{issue_id}: {pr_head.hexsha}")
                    # Assuming 'main' or 'master' as the default branch
                    # Need to ensure the default branch is fetched
                    try:
                        local_repo.remotes.origin.fetch('main')
                        default_branch_ref = 'main'
                    except GitCommandError:
                        try:
                            local_repo.remotes.origin.fetch('master')
                            default_branch_ref = 'master'
                        except GitCommandError:
                            console.print(f"[bold yellow]Warning:[/bold yellow] Could not fetch 'main' or 'master' for repository. Cannot determine merge base.")
                            default_branch_ref = None

                    debug_print(args.verbose, f"Default branch ref: {default_branch_ref}")

                    merge_base_commit = None
                    if default_branch_ref:
                        default_branch_commit = local_repo.commit(default_branch_ref)
                        merge_bases = local_repo.merge_base(pr_head, default_branch_commit)
                        if merge_bases:
                            merge_base_commit = merge_bases[0]
                            console.print(f"  [bold blue]Base commit for PR #{issue_id}:[/bold blue] {merge_base_commit.hexsha}")
                            debug_print(args.verbose, f"Merge base for PR #{issue_id}: {merge_base_commit.hexsha}")
                        else:
                            console.print(f"  [bold yellow]Warning:[/bold yellow] No common merge base found for PR #{issue_id} with {default_branch_ref}.")

                    committers = set()
                    if merge_base_commit:
                        for commit in local_repo.iter_commits(f"{merge_base_commit.hexsha}..pr/{issue_id}"):
                            committers.add(f"{commit.author.name} <{commit.author.email}>")
                    else:
                        # If no merge base, just list committers on the PR branch itself
                        console.print(f"  [bold yellow]Listing committers directly from PR branch for[/bold yellow] #{issue_id} (no merge base found).")
                        for commit in local_repo.iter_commits(f"pr/{issue_id}"):
                            committers.add(f"{commit.author.name} <{commit.author.email}>")

                    debug_print(args.verbose, f"Committers for PR #{issue_id}: {committers}")

                    if committers:
                        console.print(f"  [bold blue]Committers on PR #{issue_id}:[/bold blue]")
                        for committer_info in sorted(list(committers)):
                            console.print(f"    - {committer_info}")
                    else:
                        console.print(f"  [bold yellow]No committers found for PR[/bold yellow] #{issue_id} (perhaps it's a merge commit or empty PR).")

                except GitCommandError as e:
                    console.print(f"[bold red]Error processing PR[/bold red] #{issue_id} after fetch: {e}")
                    debug_print(args.verbose, f"GitCommandError while processing PR #{issue_id}: {e}")
                except Exception as e:
                    console.print(f"[bold red]An unexpected error occurred while processing PR[/bold red] #{issue_id}: {e}")
                    debug_print(args.verbose, f"Unexpected error while processing PR #{issue_id}: {e}")

            except GitCommandError as e:
                if "couldn't find remote ref" in e.stderr:
                    console.print(f"[bold yellow]Warning:[/bold yellow] PR #{issue_id} not found or inaccessible. Skipping.")
                else:
                    console.print(f"[bold red]Error fetching PR[/bold red] #{issue_id}: {e}")
                debug_print(args.verbose, f"GitCommandError while fetching PR #{issue_id}: {e}")
            except Exception as e:
                console.print(f"[bold red]An unexpected error occurred while fetching PR[/bold red] #{issue_id}: {e}")
                debug_print(args.verbose, f"Unexpected error while fetching PR #{issue_id}: {e}")
    else:
        console.print("[bold green]No missing Issue IDs found.[/bold green]")

def handle_commit(args):
    debug_print(args.verbose, f"Handling commit: {args.commit_url}")
    console.print(f"[bold blue]Handling commit:[/bold blue] {args.commit_url}")
    if not validate_github_url(args.commit_url):
        console.print(f"[bold red]Error:[/bold red] Invalid GitHub URL provided: {args.commit_url}")
        return

    owner, repo, commit_sha = extract_commit_info(args.commit_url)
    if not owner or not repo or not commit_sha:
        console.print(f"[bold red]Error:[/bold red] Could not extract owner, repository, or commit SHA from the URL: {args.commit_url}")
        return

    debug_print(args.verbose, f"Extracted commit info: Owner={owner}, Repo={repo}, SHA={commit_sha}")
    console.print(f"[bold green]Extracted commit info:[/bold green] Owner: {owner}, Repo: {repo}, Commit SHA: {commit_sha}")
    # Stub: Further commit handling logic would go here

    # Use clickhouse to try to find the fork event
    console.print(f"[bold green]Attempting to infer forked repository[/bold green]")
    actor_login, forked_repo_name = find_fork_event_in_clickhouse(repo, owner)
    debug_print(args.verbose, f"ClickHouse result: actor_login={actor_login}, forked_repo_name={forked_repo_name}")

    if forked_repo_name:
        console.print(f"[bold green]Found potential forked repository:[/bold green] {forked_repo_name} by {actor_login}")
    else:
        console.print(f"[bold yellow]No fork event found for repository:[/bold yellow] {repo}")
        forked_repo_name = Prompt.ask("Could not infer the forked repository. Please provide the full GitHub repository name (e.g., 'owner/repo') that this commit was forked from:")
        debug_print(args.verbose, f"User provided forked repo: {forked_repo_name}")

    # create a URL for the commit on the parent repositry
    parent_commit_url = f"https://github.com/{forked_repo_name}/commit/{commit_sha}"
    console.print(f"[bold blue]Opening parent commit URL:[/bold blue] {parent_commit_url}")
    debug_print(args.verbose, f"Opening URL: {parent_commit_url}")
    # open browser to commit
    webbrowser.open(parent_commit_url)


def handle_user(args):
    debug_print(args.verbose, f"Analyzing user: {args.user}")
    console.print(f"[bold blue]Analyzing user:[/bold blue] {args.user}")
    username = extract_username(args.user)
    if not username:
        console.print(f"[bold red]Error:[/bold red] Invalid GitHub username or URL: {args.user}")
        return
    debug_print(args.verbose, f"Extracted username: {username}")
    analyze_user(username, args.verbose)


def handle_gist(args):
    debug_print(args.verbose, f"Handling gist: {args.gist_id_or_url}")
    console.print(f"[bold blue]Handling gist:[/bold blue] {args.gist_id_or_url}")
    gist_hash = get_gist_hash_from_input(args.gist_id_or_url)
    if not gist_hash:
        console.print(f"[bold red]Error:[/bold red] Invalid gist input: '{args.gist_id_or_url}'. Please provide a valid gist hash or URL.")
        return None

    debug_print(args.verbose, f"Extracted gist hash: {gist_hash}")
    console.print(f"[bold green]Extracted gist hash:[/bold green] {gist_hash}")

    # Check if the public gist URL returns 404
    public_gist_url = f"https://gist.github.com/{gist_hash}"
    debug_print(args.verbose, f"Checking public gist URL: {public_gist_url}")
    try:
        response = requests.get(public_gist_url)
        debug_print(args.verbose, f"Gist URL response status code: {response.status_code}")
        if response.status_code == 404:
            console.print(f"[bold yellow]Warning:[/bold yellow] Public gist URL '{public_gist_url}' returned 404. Attempting to clone via SSH.")
            clone_gist_ssh(gist_hash, args.verbose)
        elif response.status_code == 200:
            console.print(f"[bold green]Success:[/bold green] Public gist URL '{public_gist_url}' is accessible.")
            # Further processing for accessible gist can go here
        else:
            console.print(f"[bold yellow]Info:[/bold yellow] Public gist URL '{public_gist_url}' returned status code: {response.status_code}")
    except requests.exceptions.RequestException as e:
        console.print(f"[bold red]Error:[/bold red] checking gist URL '{public_gist_url}': {e}")
        debug_print(args.verbose, f"RequestException while checking gist URL: {e}")

    return gist_hash

def clone_gist_ssh(gist_hash, verbose=False):
    clone_url = f"git@gist.github.com:{gist_hash}.git"
    clone_dir = f"ghdig/outputs/gists/{gist_hash}"
    debug_print(verbose, f"Cloning gist via SSH from {clone_url} to {clone_dir}")
    try:
        console.print(f"[bold cyan]Cloning[/bold cyan] '{clone_url}' into '{clone_dir}'...")
        Repo.clone_from(clone_url, clone_dir)
        console.print(f"[bold green]Successfully cloned[/bold green] gist '{gist_hash}' to '{clone_dir}'")
    except Exception as e:
        console.print(f"[bold red]Error cloning gist[/bold red] '{gist_hash}': {e}")
        debug_print(verbose, f"Error cloning gist: {e}")

def handle_absence(args):
    debug_print(args.verbose, f"Handling absence with query: {args.query}")
    console.print(f"[bold blue]Checking for absent users and repos...[/bold blue]")

    usernames, repos = extract_entities_from_query(args.query, args.verbose)

    if not usernames and not repos:
        console.print("[bold yellow]No usernames or repos extracted from the query.[/bold yellow]")
        return

    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        console.print("[bold red]Error:[/bold red] GITHUB_TOKEN not found in .env file.")
        return

    headers = {"Authorization": f"token {github_token}"}
    absent_users = []
    absent_repos = []

    with requests.Session() as session:
        session.headers.update(headers)

        console.print(f"[bold yellow]Checking {len(usernames)} candidate users[/bold yellow]")
        for user in usernames:
            url = f"https://api.github.com/users/{user}"
            try:
                response = session.get(url)
                if response.status_code == 404:
                    absent_users.append(user)
                    console.print(f"[bold red]Absent user:[/bold red] {user}")
                else:
                    debug_print(args.verbose, f"User {user} found.")
            except requests.RequestException as e:
                console.print(f"[bold red]Error checking user {user}:[/bold red] {e}")

        console.print(f"[bold yellow]Checking {len(repos)} candidate repos[/bold yellow]")
        for repo in repos:
            url = f"https://api.github.com/repos/{repo}"
            try:
                response = session.get(url)
                if response.status_code == 404:
                    absent_repos.append(repo)
                    console.print(f"[bold red]Absent repo:[/bold red] {repo}")
                else:
                    debug_print(args.verbose, f"Repo {repo} found.")
            except requests.RequestException as e:
                console.print(f"[bold red]Error checking repo {repo}:[/bold red] {e}")

    console.print("\n[bold green]Absence Check Complete[/bold green]")
    if absent_users:
        console.print(f"[bold magenta]Absent Users:[/bold magenta] {', '.join(absent_users)}")
    else:
        console.print("[bold green]No absent users found.[/bold green]")

    if absent_repos:
        console.print(f"[bold magenta]Absent Repos:[/bold magenta] {', '.join(absent_repos)}")
    else:
        console.print("[bold green]No absent repos found.[/bold green]")