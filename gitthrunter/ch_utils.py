from datetime import datetime, timedelta
from clickhouse_connect import get_client
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

console = Console()

def get_clickhouse_client():
    return get_client(host='play.clickhouse.com', port=443, username='play', password='', secure=True)

def execute_sharded_query(ch_client, base_query, initial_start_date=None, chunk_size_days=150, quiet=False):
    """
    Executes a ClickHouse query in sharded chunks to handle large result sets.
    """
    all_rows = []
    all_column_names = []
    all_column_types = []

    # Default to 2024-01-01 if no start date (github_events has data from ~2011)
    current_start_date = initial_start_date if initial_start_date else datetime(2024, 1, 1)
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    # Calculate total chunks for progress bar
    total_days = (today - current_start_date).days
    total_chunks = max(1, (total_days // chunk_size_days) + 1)
    chunk_count = 0

    progress_ctx = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
        transient=True,
        disable=quiet
    )

    with progress_ctx as progress:
        task = progress.add_task(f"Sharded query ({chunk_size_days}d chunks)", total=total_chunks)

        while True:
            if current_start_date > today:
                break

            next_end_date = current_start_date + timedelta(days=chunk_size_days)
            if next_end_date > today + timedelta(days=1):
                next_end_date = today + timedelta(days=1)

            sharded_query = f"""
            SELECT * FROM (
                {base_query.strip()}
            ) WHERE created_at >= '{current_start_date.strftime('%Y-%m-%d %H:%M:%S')}'
              AND created_at < '{next_end_date.strftime('%Y-%m-%d %H:%M:%S')}'
            ORDER BY created_at ASC
            """

            chunk_count += 1
            progress.update(task, completed=chunk_count,
                          description=f"Chunk {chunk_count}: {current_start_date.strftime('%Y-%m-%d')} to {next_end_date.strftime('%Y-%m-%d')}")

            try:
                result = ch_client.query(sharded_query)

                if not all_column_names:
                    all_column_names = result.column_names
                    all_column_types = result.column_types

                all_rows.extend(result.result_rows)

                if not result.result_rows:
                    break

                last_row_created_at = None
                if result.result_rows and 'created_at' in result.column_names:
                    created_at_index = result.column_names.index('created_at')
                    last_row_created_at = result.result_rows[-1][created_at_index]
                    if isinstance(last_row_created_at, str):
                        last_row_created_at = datetime.strptime(last_row_created_at, '%Y-%m-%d %H:%M:%S')
                    if last_row_created_at.tzinfo is not None:
                        last_row_created_at = last_row_created_at.replace(tzinfo=None)

                if next_end_date.tzinfo is not None:
                    next_end_date = next_end_date.replace(tzinfo=None)

                if last_row_created_at and last_row_created_at >= next_end_date:
                    current_start_date = last_row_created_at + timedelta(seconds=1)
                else:
                    current_start_date = next_end_date

            except Exception as e:
                if "TOO_MANY_ROWS_OR_BYTES" in str(e) or "Code: 396" in str(e):
                    if not quiet:
                        console.print(f"[yellow]Chunk too large, reducing to {chunk_size_days // 2}d chunks[/yellow]")
                    if chunk_size_days > 1:
                        return execute_sharded_query(ch_client, base_query, current_start_date, chunk_size_days // 2, quiet)
                    else:
                        raise Exception("Chunk size at minimum (1 day) but still too large")
                else:
                    raise e

    class MockClickHouseResult:
        def __init__(self, rows, column_names, column_types):
            self.result_rows = rows
            self.column_names = column_names
            self.column_types = column_types

    return MockClickHouseResult(all_rows, all_column_names, all_column_types)
