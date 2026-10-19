-- potential_attacks_v2.sql
-- Enhanced query based on 2026 YTD actor analysis
-- V2.1: Added nslookup, /etc/passwd, proc/self, hackmoltrepeat patterns
-- V2.2: Added title field searching for issue/PR title injection
-- V2.3: Added body field for issue/PR body injection (high value for AI prompt injection)
-- V2.4: Event-type filtering for efficiency (search fields only where populated)
-- V2.5: Fixed operator precedence - wrapped OR blocks in parentheses
-- Total: +17 new patterns, bot exclusions, training repo exclusions
-- Estimated: ~90% coverage (up from 70-75%), ~5% FP rate (down from 8-12%)
--
-- NOTE: body field search may timeout on ClickHouse playground due to size.
-- Use potential_attacks_fast.sql for regular monitoring (excludes body field).
--
-- Field -> Event Type mapping (from schema analysis):
--   head_ref: PullRequestEvent, PullRequestReviewEvent, PullRequestReviewCommentEvent
--   ref: PushEvent, CreateEvent, DeleteEvent
--   title: IssuesEvent, IssueCommentEvent
--   body: IssuesEvent, IssueCommentEvent, PullRequestReviewCommentEvent,
--         PullRequestReviewEvent, ReleaseEvent, CommitCommentEvent

select
    created_at, event_type, actor_login, repo_name, title, ref, head_ref, body
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
    ) or (
        -- BODY: Issues, comments, reviews, releases (may timeout on large scans)
        event_type in ('IssuesEvent', 'IssueCommentEvent', 'PullRequestReviewCommentEvent',
                       'PullRequestReviewEvent', 'ReleaseEvent', 'CommitCommentEvent')
        and (
            body like '%${(%' or
            body like '%{IFS}%' or
            body like '%|bash%' or
            body like '%$(curl%' or
            body like '%.oastify.%' or
            body like '%webhook.site%' or
            -- AI prompt injection patterns (e.g. hackerbot-claw targeting @claude)
            body like '%ignore previous instructions%' or
            body like '%SYSTEM DIAGNOSTIC MODE%' or
            body like '%print all environment variables%'
        )
    )
)
-- EXCLUSIONS: Known false positives (applies to ALL pattern blocks above)
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
