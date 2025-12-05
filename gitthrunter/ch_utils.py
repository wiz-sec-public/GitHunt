from datetime import datetime, timedelta
from clickhouse_connect import get_client

def get_clickhouse_client():
    return get_client(host='play.clickhouse.com', port=443, username='play', password='', secure=True)

def execute_sharded_query(ch_client, base_query, initial_start_date=None, chunk_size_days=150):
    """
    Executes a ClickHouse query in sharded chunks to handle large result sets.
    """
    all_rows = []
    all_column_names = []
    all_column_types = []

    current_start_date = initial_start_date if initial_start_date else datetime(2023, 1, 1) # A very old date to start from
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) # Get today's date, stripped of time

    while True:
        if current_start_date > today: # Stop if we've processed up to today
            break
        next_end_date = current_start_date + timedelta(days=chunk_size_days)
        if next_end_date > today + timedelta(days=1): # Ensure next_end_date doesn't go too far into the future
            next_end_date = today + timedelta(days=1)

        # Construct the sharded query
        # Wrap the base query as a subquery to safely apply sharding conditions
        sharded_query = f"""
        SELECT * FROM (
            {base_query.strip()}
        ) WHERE created_at >= '{current_start_date.strftime('%Y-%m-%d %H:%M:%S')}'
          AND created_at < '{next_end_date.strftime('%Y-%m-%d %H:%M:%S')}'
        ORDER BY created_at ASC
        """

        print(f"Executing chunk from {current_start_date.strftime('%Y-%m-%d %H:%M:%S')} to {next_end_date.strftime('%Y-%m-%d %H:%M:%S')}")

        try:
            result = ch_client.query(sharded_query)

            if not all_column_names: # Store column names and types only once
                all_column_names = result.column_names
                all_column_types = result.column_types

            all_rows.extend(result.result_rows)

            if not result.result_rows: # No more data in this chunk, or reached the end
                break

            # If the last row's created_at is less than next_end_date, it means we've processed all data up to next_end_date
            # and can move to the next chunk. Otherwise, if it's equal or greater, it means there's more data
            # within this chunk that needs to be fetched, so we adjust current_start_date to the last row's created_at
            # to avoid missing data.
            last_row_created_at = None
            if result.result_rows and 'created_at' in result.column_names:
                created_at_index = result.column_names.index('created_at')
                last_row_created_at = result.result_rows[-1][created_at_index]
                if isinstance(last_row_created_at, str):
                    last_row_created_at = datetime.strptime(last_row_created_at, '%Y-%m-%d %H:%M:%S')
                # Ensure last_row_created_at is offset-naive for comparison
                if last_row_created_at.tzinfo is not None:
                    last_row_created_at = last_row_created_at.replace(tzinfo=None)

            # Ensure next_end_date is offset-naive for comparison
            if next_end_date.tzinfo is not None:
                next_end_date = next_end_date.replace(tzinfo=None)

            if last_row_created_at and last_row_created_at >= next_end_date:
                current_start_date = last_row_created_at + timedelta(seconds=1) # Move to the next second
            else:
                current_start_date = next_end_date # Move to the next chunk

        except Exception as e:
            if "TOO_MANY_ROWS_OR_BYTES" in str(e) or "Code: 396" in str(e):
                print(f"Chunk too large, attempting to reduce chunk size for {current_start_date.strftime('%Y-%m-%d %H:%M:%S')} to {next_end_date.strftime('%Y-%m-%d %H:%M:%S')}.")
                # Implement retry with smaller chunk size
                if chunk_size_days > 1:
                    # Recursively call with half the chunk size
                    return execute_sharded_query(ch_client, base_query, current_start_date, chunk_size_days // 2)
                else:
                    print("Cannot reduce chunk size further (already 1 day). Aborting sharded query.")
                    raise e # Re-raise if chunk size is already 1 day and still too large
            else:
                raise e # Re-raise other exceptions

    # Create a mock result object similar to what ch_client.query returns
    class MockClickHouseResult:
        def __init__(self, rows, column_names, column_types):
            self.result_rows = rows
            self.column_names = column_names
            self.column_types = column_types

    return MockClickHouseResult(all_rows, all_column_names, all_column_types)