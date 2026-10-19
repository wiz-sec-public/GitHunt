import argparse
import csv
import json
import os
import sqlite3
import sys
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from db_utils import persist_query_results, get_last_run_timestamp, check_existing_results, initialize_sqlite_db
from ch_utils import get_clickhouse_client, execute_sharded_query
from enricher import enrich_actor_logins, enrich_single_actor

console = Console()

def format_row(row, column_names):
    """Format a row as a dictionary with proper datetime handling."""
    result = {}
    for i, item in enumerate(row):
        col_name = column_names[i]
        if isinstance(item, datetime):
            result[col_name] = item.strftime('%Y-%m-%d %H:%M:%S')
        elif item is None:
            result[col_name] = None
        else:
            result[col_name] = str(item) if not isinstance(item, (int, float, bool)) else item
    return result

def output_results(rows, column_names, output_format, output_file=None, quiet=False):
    """Output results in the specified format."""
    if not rows:
        if not quiet:
            console.print("[yellow]No results[/yellow]")
        return

    if output_format == 'table':
        table = Table(show_header=True, header_style="bold magenta")
        for col in column_names:
            table.add_column(col)
        for row in rows:
            formatted = format_row(row, column_names)
            table.add_row(*[str(v) if v is not None else '' for v in formatted.values()])
        console.print(table)

    elif output_format == 'json':
        data = [format_row(row, column_names) for row in rows]
        output = json.dumps(data, indent=2)
        if output_file:
            with open(output_file, 'w') as f:
                f.write(output)
            if not quiet:
                console.print(f"[green]Wrote {len(rows)} rows to {output_file}[/green]")
        else:
            print(output)

    elif output_format == 'jsonl':
        lines = [json.dumps(format_row(row, column_names)) for row in rows]
        output = '\n'.join(lines)
        if output_file:
            with open(output_file, 'w') as f:
                f.write(output)
            if not quiet:
                console.print(f"[green]Wrote {len(rows)} rows to {output_file}[/green]")
        else:
            print(output)

    elif output_format == 'csv':
        if output_file:
            with open(output_file, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=column_names)
                writer.writeheader()
                for row in rows:
                    writer.writerow(format_row(row, column_names))
            if not quiet:
                console.print(f"[green]Wrote {len(rows)} rows to {output_file}[/green]")
        else:
            writer = csv.DictWriter(sys.stdout, fieldnames=column_names)
            writer.writeheader()
            for row in rows:
                writer.writerow(format_row(row, column_names))

def main():
    parser = argparse.ArgumentParser(
        description="Run ClickHouse queries for GitHub supply chain attack detection.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py potential_attacks.sql --start_date "2026-01-01 00:00:00"
  python main.py potential_attacks.sql --output json -o results.json
  python main.py potential_attacks.sql --output csv --limit 100
  python main.py --enrich
  python main.py --enrich <username>
        """
    )
    parser.add_argument("query_file", nargs='?', help="Query file in 'queries/' directory")
    parser.add_argument("--start_date", type=str, help="Start date (YYYY-MM-DD HH:MM:SS). Disables caching.")
    parser.add_argument("--enrich", nargs='?', const=True, default=False,
                        help="Enrich actors. Use as flag for bulk or with username for single actor.")
    parser.add_argument("--output", "-f", choices=['table', 'json', 'jsonl', 'csv'], default='table',
                        help="Output format (default: table)")
    parser.add_argument("-o", "--output-file", type=str, help="Write output to file instead of stdout")
    parser.add_argument("--limit", type=int, help="Limit number of results")
    parser.add_argument("--quiet", "-q", action='store_true', help="Suppress progress output (for scripting)")
    parser.add_argument("--no-cache", action='store_true', help="Bypass cache, always run fresh query")
    args = parser.parse_args()

    query = None
    if args.query_file:
        query_path = os.path.join("queries", args.query_file)
        if not os.path.exists(query_path):
            console.print(f"[red]Error: Query file '{query_path}' not found.[/red]")
            return 1
        with open(query_path, 'r') as f:
            query = f.read()

    if not args.query_file and not args.enrich:
        console.print("[red]Error: Either a query_file must be provided or --enrich must be used.[/red]")
        parser.print_help()
        return 1

    conn = sqlite3.connect('query_results.db')
    initialize_sqlite_db(conn)
    ch_client = get_clickhouse_client()

    query_name = os.path.basename(args.query_file) if args.query_file else None
    today = datetime.now()

    # Handle enrichment mode
    if args.enrich:
        if isinstance(args.enrich, str):
            if not args.quiet:
                console.print(f"[blue]Enriching single actor: {args.enrich}[/blue]")
            enrich_single_actor(conn, args.enrich)
        else:
            if not args.quiet:
                console.print("[blue]Starting bulk actor login enrichment...[/blue]")
            enrich_actor_logins(conn, ch_client)
        conn.close()
        return 0

    if not query_name:
        console.print("[red]Error: query_file is required when --enrich is not used.[/red]")
        conn.close()
        return 1

    disable_cache_persist = args.no_cache
    last_run_timestamp = None

    if args.start_date:
        try:
            start_datetime = datetime.strptime(args.start_date, '%Y-%m-%d %H:%M:%S')
            if not args.quiet:
                console.print(f"[dim]Query from {start_datetime.strftime('%Y-%m-%d %H:%M:%S')} (manual)[/dim]")
            last_run_timestamp = start_datetime
            disable_cache_persist = True
        except ValueError:
            console.print("[red]Error: Invalid start_date format. Use YYYY-MM-DD HH:MM:SS.[/red]")
            return 1
    elif not args.no_cache:
        existing_results = check_existing_results(conn, query_name, today)
        if existing_results:
            rows, column_names, _ = existing_results
            if args.limit:
                rows = rows[:args.limit]
            output_results(rows, column_names, args.output, args.output_file, args.quiet)
            conn.close()
            return 0
        else:
            last_run_timestamp = get_last_run_timestamp(conn, query_name)
            if last_run_timestamp and not args.quiet:
                console.print(f"[dim]Query from {last_run_timestamp.strftime('%Y-%m-%d %H:%M:%S')}[/dim]")
            elif not args.quiet:
                console.print("[dim]Query all available logs (no previous run)[/dim]")

    # Build modified query with timestamp filter
    modified_query = query
    if last_run_timestamp:
        timestamp_str = last_run_timestamp.strftime('%Y-%m-%d %H:%M:%S')
        if "WHERE" in query.upper():
            modified_query = query.strip() + f"\nAND created_at > '{timestamp_str}'"
        else:
            modified_query = query.strip() + f"\nWHERE created_at > '{timestamp_str}'"
        modified_query += "\nORDER BY created_at DESC"

    if args.limit:
        modified_query += f"\nLIMIT {args.limit}"

    try:
        if not args.quiet:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
                transient=True
            ) as progress:
                progress.add_task("Querying ClickHouse...", total=None)
                result = ch_client.query(modified_query)
        else:
            result = ch_client.query(modified_query)

        if len(result.result_rows) == 0:
            if not args.quiet:
                console.print("[yellow]No results[/yellow]")
        else:
            output_results(result.result_rows, result.column_names, args.output, args.output_file, args.quiet)
            if not disable_cache_persist:
                persist_query_results(conn, query_name, today, result)

    except Exception as e:
        if "TOO_MANY_ROWS_OR_BYTES" in str(e) or "Code: 396" in str(e):
            if not args.quiet:
                console.print(f"[yellow]Query too large, using sharded execution...[/yellow]")
            try:
                result = execute_sharded_query(ch_client, query, last_run_timestamp, quiet=args.quiet)
                rows = result.result_rows
                if args.limit:
                    rows = rows[:args.limit]
                output_results(rows, result.column_names, args.output, args.output_file, args.quiet)
                if not disable_cache_persist:
                    persist_query_results(conn, query_name, today, result)
            except Exception as sharded_e:
                console.print(f"[red]Sharded query failed: {sharded_e}[/red]")
                conn.close()
                return 1
        else:
            console.print(f"[red]Query failed: {e}[/red]")
            conn.close()
            return 1

    conn.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())
