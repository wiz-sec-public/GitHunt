## Query Files

### `queries/potential_attacks.sql`

This query identifies potential attack attempts by searching for suspicious patterns (e.g., `|bash`, `base64,-d`, `webhook.site`) within the `head_ref` or `ref` fields of `github_events`. It excludes certain known benign repositories and filters events created after a specific date.

```sql
select created_at, event_type, actor_login, repo_name, title, ref, head_ref
from github_events
where ((
head_ref like '%|bash%' or
head_ref like '%base64,-d%' or
-- ... (and other suspicious patterns) ...
)) and
repo_name not like 'QuebecBashing/%' and repo_name not like '%/ascpc-insecure-context-injection' and repo_name not like '%/gravy-overflow'
and created_at > '2025-01-01 00:00:00'
order by created_at desc