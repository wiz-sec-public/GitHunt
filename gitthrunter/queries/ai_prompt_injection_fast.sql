-- ai_prompt_injection_fast.sql
-- Fast query for AI prompt injection detection (title field only)
-- Use this for regular monitoring - efficient on ClickHouse playground
--
-- For body field searches, use ai_prompt_injection_body.sql with date filters

SELECT
    created_at,
    event_type,
    actor_login,
    repo_name,
    title
FROM github_events
WHERE event_type IN ('IssuesEvent', 'PullRequestEvent')
AND (
    -- XML context breaking
    -- Pattern: title contains closing XML tags to break out of context
    title LIKE '%</formatted_context>%' OR
    title LIKE '%<additional_instructions>%' OR
    title LIKE '%</instructions>%' OR
    title LIKE '%</untrusted%' OR

    -- System override attempts
    title LIKE '%SYSTEM OVERRIDE%' OR
    title LIKE '%CRITICAL SYSTEM%' OR
    title LIKE '%MAINTENANCE MODE ACTIVATED%' OR

    -- Direct instruction override
    title LIKE '%ignore all previous%' OR
    title LIKE '%disregard previous%'
)
-- Exclusions (legitimate uses)
AND title NOT LIKE '%nix-community%'
AND title NOT LIKE '%chaotic-cx%'
AND title NOT LIKE '%CLI%'
AND title NOT LIKE '%pagination%'
AND title NOT LIKE '%template%'
AND repo_name NOT LIKE '%/atrament%'
