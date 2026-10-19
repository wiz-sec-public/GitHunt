-- ai_prompt_injection_body.sql
-- Body field search for AI prompt injection (EXPENSIVE)
-- MUST use with date filter to avoid ClickHouse byte limits
--
-- Usage: python main.py ai_prompt_injection_body.sql --start_date "2026-06-01 00:00:00"

SELECT
    created_at,
    event_type,
    actor_login,
    repo_name,
    title,
    substring(body, 1, 500) as body_preview
FROM github_events
WHERE event_type IN ('IssuesEvent', 'IssueCommentEvent', 'PullRequestReviewCommentEvent')
AND (
    -- HIGH SIGNAL: Clear injection markers
    -- These are XML-style context breaks that shouldn't appear in normal issues
    body LIKE '%</untrusted_context>%' OR
    body LIKE '%</formatted_context>%' OR
    body LIKE '%<additional_instructions>%' OR
    body LIKE '%<system_override>%' OR

    -- MEDIUM SIGNAL: System override language
    body LIKE '%SYSTEM OVERRIDE%' OR
    body LIKE '%MAINTENANCE MODE ACTIVATED%' OR
    body LIKE '%diagnostic mode%' OR
    body LIKE '%admin override%' OR

    -- MEDIUM SIGNAL: Classic prompt injection
    body LIKE '%ignore previous instructions%' OR
    body LIKE '%ignore all previous%' OR
    body LIKE '%disregard previous%' OR
    body LIKE '%forget your instructions%' OR
    body LIKE '%new instructions:%' OR

    -- MEDIUM SIGNAL: Role hijacking
    (body LIKE '%You are now%' AND body LIKE '%mode%') OR
    body LIKE '%Pretend you are%' OR
    body LIKE '%Act as if you%'
)
-- Exclusions
AND actor_login NOT LIKE '%[bot]'
AND body NOT LIKE '%security research%'
AND body NOT LIKE '%prompt injection vulnerability%'
AND body NOT LIKE '%CVE-%'
AND repo_name NOT LIKE '%/security%'
AND repo_name NOT LIKE '%pentest%'
