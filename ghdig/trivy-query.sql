SELECT distinct actor_login, repo_name 
FROM github_events 
WHERE 
  (event_type = 'ForkEvent' and (repo_name like 'aquasecurity/%' or repo_name == 'actions/checkout')) 
  AND created_at > '2025-03-16 00:00:00' 
  AND created_at < '2025-03-20 00:00:00'
