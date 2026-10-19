-- ai_prompt_injection.sql
-- Detects AI prompt injection attacks in GitHub events
--
-- IMPORTANT: Body field searches are expensive on ClickHouse playground.
-- This query uses title field (efficient) with event_type filtering.
-- For body searches, use shorter time ranges or run during off-peak hours.
--
-- Attack patterns detected:
--   1. XML-style context breaking (</formatted_context>, <additional_instructions>)
--   2. Classic prompt injection ("ignore previous instructions")
--   3. System override attempts ("SYSTEM OVERRIDE", "diagnostic mode")
--   4. Role hijacking ("You are now", "Act as if")
--
-- Observed in the wild:
--   - XML context breaking in issue titles targeting AI GitHub Actions
--   - "SYSTEM OVERRIDE" / untrusted_context breakouts in issue bodies
--   - hackerbot-claw (Feb 2026 - CLAUDE.md prompt injection)

-- QUERY 1: Title-based injection (EFFICIENT - use this first)
-- Catches: XML context-break injection, system override in titles
SELECT
    created_at,
    event_type,
    actor_login,
    repo_name,
    title
FROM github_events
WHERE event_type IN ('IssuesEvent', 'PullRequestEvent', 'IssueCommentEvent')
AND (
    -- XML context breaking
    title LIKE '%</formatted_context>%' OR
    title LIKE '%<additional_instructions>%' OR
    title LIKE '%</system>%' OR
    title LIKE '%</instructions>%' OR
    title LIKE '%</prompt>%' OR
    title LIKE '%</untrusted%' OR

    -- System override
    title LIKE '%SYSTEM OVERRIDE%' OR
    title LIKE '%MAINTENANCE MODE%' OR

    -- Role hijacking in titles (rare but high signal)
    title LIKE '%You are now%' OR
    title LIKE '%ignore all previous%'
)
-- Exclusions: legitimate uses
AND title NOT LIKE '%nix-community%'  -- Nix uses <system> legitimately
AND title NOT LIKE '%CLI%prompt%'     -- CLI tool documentation

-- QUERY 2: Body-based injection (EXPENSIVE - use with date filter)
-- Uncomment and add date filter like: AND created_at > '2026-06-01'
/*
SELECT
    created_at,
    event_type,
    actor_login,
    repo_name,
    substring(body, 1, 500) as body_preview
FROM github_events
WHERE event_type IN ('IssuesEvent', 'IssueCommentEvent')
AND created_at > now() - INTERVAL 7 DAY  -- REQUIRED: limit date range
AND (
    -- Clear injection markers (highest signal)
    body LIKE '%</untrusted_context>%' OR
    body LIKE '%SYSTEM OVERRIDE%' OR
    body LIKE '%</formatted_context>%' OR
    body LIKE '%<additional_instructions>%' OR

    -- Classic prompt injection phrases
    body LIKE '%ignore previous instructions%' OR
    body LIKE '%ignore all previous%' OR
    body LIKE '%disregard previous%' OR
    body LIKE '%forget your instructions%' OR

    -- Role hijacking
    body LIKE '%You are now%' AND body LIKE '%mode%' OR
    body LIKE '%Pretend you are%'
)
-- Exclude security research discussions
AND body NOT LIKE '%prompt injection vulnerability%'
AND body NOT LIKE '%security research%'
AND actor_login NOT LIKE '%[bot]'
*/

-- QUERY 3: Specific attacker signatures
-- Signatures of observed patterns

/*
-- XML context-break pattern
SELECT * FROM github_events
WHERE title LIKE '%</formatted_context><additional_instructions>%'
AND created_at > '2025-01-01'

-- untrusted_context + SYSTEM OVERRIDE pattern
SELECT * FROM github_events
WHERE body LIKE '%</untrusted_context>%'
AND body LIKE '%SYSTEM OVERRIDE%'
AND created_at > '2026-01-01'

-- hackerbot-claw CLAUDE.md injection (Feb 2026)
-- Search for modifications to CLAUDE.md files
SELECT * FROM github_events
WHERE event_type = 'PushEvent'
AND (
    ref LIKE '%CLAUDE.md%' OR
    ref LIKE '%cursorrules%' OR
    ref LIKE '%copilot-instructions%'
)
AND actor_login NOT IN (repo owner patterns)
*/
