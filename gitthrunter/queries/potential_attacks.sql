select
    created_at, event_type, actor_login, repo_name, title, ref, head_ref
from
    github_events
where ((
    head_ref like '%|bash%' or
    head_ref like '%base64,-d%' or
    head_ref like '%webhook.site%' or
    head_ref like '%oastify.com%' or
    head_ref like '%curl,%' or
    head_ref like '%githubusercontent.com%' or
    head_ref like '%{IFS}%' or
    head_ref like '%${(%'
    ) or (
        ref like '%|bash%' or
        ref like '%base64,-d%' or
        ref like '%webhook.site%' or
        ref like '%oastify.com%' or
        ref like '%curl,%' or
        ref like '%githubusercontent.com%' or
        ref like '%{IFS}%' or
        ref like '%${(%'
    ))
    and repo_name not like 'QuebecBashing/%'
    and repo_name not like '%/ascpc-insecure-context-injection'
    and repo_name not like '%/gravy-overflow'