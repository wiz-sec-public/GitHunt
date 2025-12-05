from flask import Flask, jsonify, render_template, redirect, url_for
import sqlite3
import json
from api_enricher import search_prs_mentioning_user

app = Flask(__name__)
DATABASE = 'demo.db'

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    return redirect(url_for('demo'))

@app.route('/demo')
def demo():
    conn = get_db()
    query = "SELECT *, COALESCE(ref, head_ref) as coalesced_ref FROM cached_potential_attacks WHERE coalesced_ref LIKE '%{IFS}%' AND created_at >= '2025-10-01' ORDER BY created_at DESC"
    attacks = conn.execute(query).fetchall()
    conn.close()
    return render_template('dark_demo.html', attacks=attacks)

@app.route('/case/<int:case_id>')
def case(case_id):
    cases = {
        1: "Microsoft",
        2: "DataDog",
        3: "Adyen"
    }
    filters = {
        1: "%microsoft%",
        2: "%documentation%",
        3: "%adyen%"
    }
    company_name = cases.get(case_id, "Unknown")
    db_filter = filters.get(case_id)

    conn = get_db()

    attacks = []
    if db_filter:
        query = "SELECT *, COALESCE(ref, head_ref) as coalesced_ref FROM cached_potential_attacks WHERE repo_name LIKE ? AND created_at >= '2025-01-01' GROUP BY actor_login, event_type, coalesced_ref ORDER BY created_at ASC"
        cursor = conn.execute(query, (db_filter,))
        attacks = cursor.fetchall()

    actor_logins = sorted(list(set([attack['actor_login'] for attack in attacks])))

    # Fetch enrichment data for these actors
    actors_enrichment = {}
    if actor_logins:
        # Create a string of placeholders for the query
        placeholders = ','.join('?' for _ in actor_logins)
        enrichment_query = f"SELECT * FROM cached_github_users_history_enrichment WHERE login IN ({placeholders})"
        cursor = conn.execute(enrichment_query, actor_logins)
        for row in cursor.fetchall():
            actors_enrichment[row['login']] = dict(row)

    four_o_four_actors_cursor = conn.execute("SELECT actor_login FROM four_o_four_actors")
    four_o_four_actors = {row['actor_login'] for row in four_o_four_actors_cursor.fetchall()}

    case_404_actors = [actor for actor in actor_logins if actor in four_o_four_actors]

    de_aliasing_info = {}
    alias_enrichment_data = {}
    if case_404_actors:
        all_potential_aliases = set()
        for actor in case_404_actors:
            search_results, status_code = search_prs_mentioning_user(actor)
            if search_results and search_results.get('items'):
                authors = {item['user']['login'] for item in search_results['items']}
                de_aliasing_info[actor] = list(authors)
                all_potential_aliases.update(authors)

        # Fetch enrichment data for all identified potential aliases
        if all_potential_aliases:
            placeholders = ','.join('?' for _ in all_potential_aliases)
            alias_enrichment_query = f"SELECT * FROM cached_github_users_history_enrichment WHERE login IN ({placeholders})"
            cursor = conn.execute(alias_enrichment_query, list(all_potential_aliases))
            for row in cursor.fetchall():
                alias_enrichment_data[row['login']] = dict(row)


    # Grouping logic
    grouped_actors = {}
    processed_actors = set()

    # First, handle the 404'd actors and their groups
    for actor in case_404_actors:
        if actor in processed_actors:
            continue

        aliases = de_aliasing_info.get(actor, [])
        group_key = tuple(sorted(aliases)) if aliases else actor

        if group_key not in grouped_actors:
            grouped_actors[group_key] = {'primary_actor': None, 'aliases': set(), 'enrichment': {}}

        # Add the 404'd actor to the group
        grouped_actors[group_key]['aliases'].add(actor)
        processed_actors.add(actor)

        # Find other 404'd actors that belong to the same group
        for other_actor in case_404_actors:
            if other_actor not in processed_actors and tuple(sorted(de_aliasing_info.get(other_actor, []))) == group_key:
                grouped_actors[group_key]['aliases'].add(other_actor)
                processed_actors.add(other_actor)

        # Add the potential aliases found through de-aliasing
        grouped_actors[group_key]['aliases'].update(aliases)

        # Determine the primary actor for the group (prefer a non-404 alias)
        non_404_aliases = [a for a in aliases if a not in four_o_four_actors]
        if non_404_aliases:
            grouped_actors[group_key]['primary_actor'] = non_404_aliases[0]
        else:
            # If all aliases are 404 or no aliases, pick the first 404 actor
            grouped_actors[group_key]['primary_actor'] = actor

    # Add remaining non-404 actors as their own groups
    for actor in actor_logins:
        if actor not in processed_actors:
            grouped_actors[actor] = {
                'primary_actor': actor,
                'aliases': {actor},
                'enrichment': actors_enrichment.get(actor, {})
            }

    # Now, populate the enrichment data for all aliases in each group
    for group_key, group_data in grouped_actors.items():
        for alias in group_data['aliases']:
            if alias in actors_enrichment:
                group_data['enrichment'][alias] = actors_enrichment[alias]
            if alias in alias_enrichment_data:
                group_data['enrichment'][alias] = alias_enrichment_data[alias]


    conn.close()
    return render_template('case.html', case_id=case_id, company_name=company_name, attacks=attacks, actors=grouped_actors, actors_enrichment=actors_enrichment, four_o_four_actors=four_o_four_actors, de_aliasing_info=de_aliasing_info, alias_enrichment_data=alias_enrichment_data)

if __name__ == '__main__':
    app.run(debug=True)