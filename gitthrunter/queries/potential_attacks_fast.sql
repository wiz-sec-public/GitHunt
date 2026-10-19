-- potential_attacks_fast.sql
-- Fast query: searches head_ref, ref, title only (no body field)
-- Use this for regular monitoring. Use potential_attacks_v2.sql for deep scans.
--
-- Based on V2.4 patterns but excludes body field which causes byte limit issues.

select
    created_at, event_type, actor_login, repo_name, title, ref, head_ref
from
    github_events
where (
    (
        -- HEAD_REF: Only in PR-related events
        event_type in ('PullRequestEvent', 'PullRequestReviewEvent', 'PullRequestReviewCommentEvent')
        and (
            head_ref like '%|bash%' or
            head_ref like '%base64,-d%' or
            head_ref like '%webhook.site%' or
            head_ref like '%.oastify.%' or
            head_ref like '%curl,%' or
            head_ref like '%gist.githubusercontent.com%' or
            head_ref like '%{IFS}%' or
            head_ref like '%${(%' or
            head_ref like '%|id;%' or
            head_ref like '%;echo%' or
            head_ref like '%;curl%' or
            head_ref like '%;wget%' or
            head_ref like '%`curl%' or
            head_ref like '%`echo%' or
            head_ref like '%$(ping%' or
            head_ref like '%{curl,%' or
            head_ref like '%|cat%' or
            head_ref like '%$(python%' or
            head_ref like '%$(printf%' or
            head_ref like '%;touch%' or
            head_ref like '%loadstring(%' or
            head_ref like '%oast.fun%' or
            head_ref like '%pipedream.net%' or
            head_ref like '%interact.sh%' or
            head_ref like '%dnslog.cn%' or
            head_ref like '%ceye.io%' or
            head_ref like '%$(nslookup%' or
            head_ref like '%/etc/passwd%' or
            head_ref like '%proc/self%' or
            head_ref like '%hackmoltrepeat%'
        )
    ) or (
        -- REF: Only in Push/Create/Delete events
        event_type in ('PushEvent', 'CreateEvent', 'DeleteEvent')
        and (
            ref like '%|bash%' or
            ref like '%base64,-d%' or
            ref like '%webhook.site%' or
            ref like '%.oastify.%' or
            ref like '%curl,%' or
            ref like '%gist.githubusercontent.com%' or
            ref like '%{IFS}%' or
            ref like '%${(%' or
            ref like '%|id;%' or
            ref like '%;echo%' or
            ref like '%;curl%' or
            ref like '%;wget%' or
            ref like '%`curl%' or
            ref like '%`echo%' or
            ref like '%$(ping%' or
            ref like '%{curl,%' or
            ref like '%|cat%' or
            ref like '%$(python%' or
            ref like '%$(printf%' or
            ref like '%;touch%' or
            ref like '%loadstring(%' or
            ref like '%oast.fun%' or
            ref like '%pipedream.net%' or
            ref like '%interact.sh%' or
            ref like '%dnslog.cn%' or
            ref like '%ceye.io%' or
            ref like '%$(nslookup%' or
            ref like '%/etc/passwd%' or
            ref like '%proc/self%' or
            ref like '%hackmoltrepeat%'
        )
    ) or (
        -- TITLE: Only in Issue events
        event_type in ('IssuesEvent', 'IssueCommentEvent')
        and (
            title like '%${(%' or
            title like '%{IFS}%' or
            title like '%|bash%' or
            title like '%|id;%' or
            title like '%;curl%' or
            title like '%.oastify.%' or
            title like '%webhook.site%'
        )
    )
)
-- Exclusions (wrapped in parentheses to apply to all OR blocks above)
and repo_name not like 'QuebecBashing/%'
and repo_name not like '%/ascpc-insecure-context-injection'
and repo_name not like '%/gravy-overflow'
and actor_login not like 'renovate%'
and actor_login not like 'dependabot%'
and ref not like 'refs/heads/renovate/%'
and head_ref not like 'renovate/%'
and repo_name not like '%/lab001'
and repo_name not like '%/lab002'
and repo_name not like '%/lab003'
and repo_name not like 'sec4us-%'
