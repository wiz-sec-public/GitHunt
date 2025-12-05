import json
import pytz
from datetime import datetime

def get_user_timezone(active_hours):
    """
    Analyzes the user's active hours to determine their most likely timezone.

    Args:
        active_hours (dict): A dictionary with hours (as strings '0'-'23') as keys
                             and activity counts as values.

    Returns:
        A string with potential timezone offsets and examples.
    """
    if not active_hours or not any(active_hours.values()):
        return "Not enough data to determine timezone."

    # Find the hour with the most activity
    peak_hour = int(max(active_hours, key=active_hours.get))

    # Assume peak activity is between 9 AM and 5 PM local time
    # Calculate potential UTC offsets
    potential_offsets = sorted(list(set([(hour - peak_hour) for hour in range(9, 18)])))

    # Group timezones by offset
    timezones_by_offset = {offset: [] for offset in potential_offsets}
    for tz_name in pytz.all_timezones:
        tz = pytz.timezone(tz_name)
        try:
            offset_hours = datetime.now(tz).utcoffset().total_seconds() / 3600
            if offset_hours in timezones_by_offset:
                timezones_by_offset[offset_hours].append(tz_name)
        except pytz.exceptions.NonExistentTimeError:
            # Skip timezones that are currently in a DST transition
            continue


    if not any(timezones_by_offset.values()):
        return "Could not determine timezone."

    # Format the output
    output_parts = []
    for offset, timezones in timezones_by_offset.items():
        if timezones:
            # Show the UTC offset and a few examples
            example_timezones = ", ".join(timezones[:3])
            if len(timezones) > 3:
                example_timezones += ", ..."
            output_parts.append(f"UTC{offset:+.1f} (e.g., {example_timezones})")

    return "<br>".join(output_parts)


def render_html(data):
    # Basic CSS for tabs
    style = """
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif, "Apple Color Emoji", "Segoe UI Emoji";
            background-color: #0d1117;
            color: #c9d1d9;
            margin: 0;
            padding: 20px;
        }
        h1, h3, h4 { color: #c9d1d9; border-bottom: 1px solid #30363d; padding-bottom: 8px; }
        h1 { font-size: 2em; }
        .tab {
            overflow: hidden;
            border-bottom: 1px solid #30363d;
            margin-bottom: 20px;
        }
        .tab button {
            background-color: transparent;
            color: #c9d1d9;
            float: left;
            border: none;
            outline: none;
            cursor: pointer;
            padding: 14px 16px;
            transition: 0.3s;
            font-size: 16px;
            border-bottom: 2px solid transparent;
        }
        .tab button:hover {
            color: #58a6ff;
            border-bottom: 2px solid #30363d;
        }
        .tab button.active {
            color: #c9d1d9;
            border-bottom: 2px solid #f78166;
            font-weight: 600;
        }
        .tabcontent {
            display: none;
            padding: 6px 12px;
            border: 1px solid #30363d;
            border-top: none;
            background-color: #161b22;
            border-radius: 0 0 6px 6px;
        }
        ul { list-style-type: none; padding-left: 0; }
        li { margin-bottom: 8px; }
        strong { color: #8b949e; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { text-align: left; padding: 8px; border-bottom: 1px solid #30363d; }
        th { background-color: #161b22; }
        img { border: 1px solid #30363d; }
    </style>
    """

    # Prepare data for Chart.js
    labels = [str(h) for h in range(24)]
    active_hours_data = data.get('active_hours', {})
    chart_data = [active_hours_data.get(l, 0) for l in labels]


    # JavaScript for tab functionality and Chart.js
    script = f"""
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script>
        let activeHoursChart = null;
        const chartData = {json.dumps(chart_data)};
        const chartLabels = {json.dumps(labels)};

        function renderActiveHoursChart() {{
            if (activeHoursChart) {{
                activeHoursChart.destroy();
            }}
            var ctx = document.getElementById('activeHoursChart').getContext('2d');
            activeHoursChart = new Chart(ctx, {{
                type: 'bar',
                data: {{
                    labels: chartLabels,
                    datasets: [{{
                        label: 'Activity Count',
                        data: chartData,
                        backgroundColor: 'rgba(75, 192, 192, 0.2)',
                        borderColor: 'rgba(75, 192, 192, 1)',
                        borderWidth: 1
                    }}]
                }},
                options: {{
                    scales: {{
                        y: {{
                            beginAtZero: true
                        }}
                    }}
                }}
            }});
        }}

        function openTab(evt, tabName) {{
            var i, tabcontent, tablinks;
            tabcontent = document.getElementsByClassName("tabcontent");
            for (i = 0; i < tabcontent.length; i++) {{
                tabcontent[i].style.display = "none";
            }}
            tablinks = document.getElementsByClassName("tablinks");
            for (i = 0; i < tablinks.length; i++) {{
                tablinks[i].className = tablinks[i].className.replace(" active", "");
            }}
            document.getElementById(tabName).style.display = "block";
            evt.currentTarget.className += " active";

            if (tabName === 'active_hours') {{
                renderActiveHoursChart();
            }}
        }}
        document.addEventListener("DOMContentLoaded", function() {{
            if(document.getElementsByClassName("tablinks")[0]) {{
               document.getElementsByClassName("tablinks")[0].click();
            }}
        }});
    </script>
    """

    html_content = f"<html><head><title>User Analysis</title>{style}{script}</head><body>"
    html_content += "<h1>User Analysis</h1>"

    # Create tab buttons
    html_content += '<div class="tab">'
    for key in data.keys():
        if key not in ['keys', 'unique_emails_owner', 'gh_fake_analyzer']:
            html_content += f'<button class="tablinks" onclick="openTab(event, \'{key}\')">{key.replace("_", " ").title()}</button>'
    html_content += '</div>'

    # Create tab content
    for key, value in data.items():
        if key in ['keys', 'unique_emails_owner', 'gh_fake_analyzer']:
            continue
        html_content += f'<div id="{key}" class="tabcontent">'
        html_content += f"<h3>{key.replace('_', ' ').title()}</h3>"
        if key == 'active_hours':
            if isinstance(value, dict) and any(value.values()):
                html_content += '<canvas id="activeHoursChart" width="400" height="100"></canvas>'
                # Display estimated timezone
                timezone_info = get_user_timezone(value)
                html_content += "<h4>Estimated User Timezone</h4>"
                html_content += f"<p>Based on activity, the user's timezone could be in one of the following offsets:<br>{timezone_info}</p>"
            else:
                html_content += "<p>No activity data to display.</p>"
        elif key == 'user_info' and isinstance(value, dict):
            # Handle user_info specifically
            html_content += "<div>"
            if value.get('avatar_url'):
                html_content += f'<img src="{value["avatar_url"]}" alt="User Avatar" width="100" height="100" style="border-radius: 50%;">'

            # Display username if available
            if value.get('login'):
                html_content += f"<p><strong>Username:</strong> {value['login']}</p>"

            # Display other non-empty fields from the provided list
            for sub_key, sub_value in value.items():
                if sub_key in ['created_at', 'updated_at'] and sub_value:
                    html_content += f"<p><strong>{sub_key.replace('_', ' ').title()}:</strong> {sub_value}</p>"

            # Display keys and unique emails within the user_info tab
            if data.get('keys') and (data['keys'].get('ssh_keys') or data['keys'].get('gpg_keys')):
                html_content += "<h3>Keys</h3>"
                html_content += "<ul>"
                for sub_key, sub_value in data['keys'].items():
                    if sub_value is not None and sub_value != '':
                        print(sub_value)
                        if sub_key == 'ssh_keys':
                            html_content += f"<li><strong>{sub_key}:</strong><pre>{sub_value}</pre></li>"
                        else:
                            html_content += f"<li><strong>{sub_key}:</strong> {sub_value}</li>"
                html_content += "</ul>"

            if data.get('unique_emails_owner'):
                html_content += "<h3>Unique Emails Owner</h3>"
                if not data['unique_emails_owner']:
                    html_content += "<p>No data available.</p>"
                else:
                    html_content += "<table>"
                    for item in data['unique_emails_owner']:
                        # Safely parse the string representation of the dictionary
                        try:
                            import ast
                            item_dict = ast.literal_eval(item) if isinstance(item, str) else item
                            email = item_dict.get('email', 'N/A')
                            name = item_dict.get('name', 'N/A')
                            html_content += f"<tr><td>{name} <{email}></td></tr>"
                        except (ValueError, SyntaxError):
                            html_content += f"<tr><td>{item}</td></tr>" # Fallback for malformed strings
                    html_content += "</table>"

            html_content += "</div>"
        elif isinstance(value, dict):
            html_content += "<ul>"
            for sub_key, sub_value in value.items():
                if sub_value is not None and sub_value != '':
                    html_content += f"<li><strong>{sub_key}:</strong> {sub_value}</li>"
            html_content += "</ul>"
        elif isinstance(value, list):
            if not value:
                html_content += "<p>No data available.</p>"
            else:
                html_content += "<table>"
                # Special headers for clickhouse_activity
                if key == 'clickhouse_activity' and value and isinstance(value[0], list):
                    headers = ["Event Type", "Actor", "Repo", "Time", "Creator User"]
                    html_content += "<tr>" + "".join(f"<th>{h}</th>" for h in headers) + "</tr>"
                    for item in value:
                        html_content += "<tr>" + "".join(f"<td>{cell}</td>" for cell in item) + "</tr>"
                else:
                    # Generic list rendering
                    html_content += "<tr><th>Item</th></tr>"
                    for item in value:
                        html_content += f"<tr><td>{item}</td></tr>"
                html_content += "</table>"
        else:
            html_content += f"<p>{value}</p>"
        html_content += '</div>'

    html_content += "</body></html>"
    return html_content

def main(username):
    """
    Generates an HTML report from a user's analysis JSON file.

    Args:
        username (str): The GitHub username.
    """
    output_dir = "ghdig/outputs"
    file_path = f'{output_dir}/{username}_analysis.json'
    try:
        with open(file_path, 'r') as f:
            analysis_results = json.load(f)
    except FileNotFoundError:
        print(f"Error: Analysis file not found at {file_path}")
        return

    html_output = render_html(analysis_results)
    output_filename = f'{output_dir}/{username}_analysis.html'
    with open(output_filename, 'w') as f:
        f.write(html_output)
    print(f"HTML report generated at {output_filename}")

if __name__ == "__main__":
    # This part is for direct script execution, you might want to adapt it to take a username
    # For example: python src/html_renderer.py gogo2464
    import sys
    if len(sys.argv) > 1:
        main(sys.argv[1])
    else:
        # Default for backward compatibility or testing
        main('gogo2464')