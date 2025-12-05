SELECT distinct actor_login, repo_name 
FROM github_events 
WHERE 
  (event_type = 'ForkEvent' and repo_name = 'tj-actions/changed-files') 
  AND created_at > '2025-02-01 00:00:00' 
  AND created_at < '2025-03-18 00:00:00'
