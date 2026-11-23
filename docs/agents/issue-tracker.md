# Issue tracker

Implementation specs and tasks live in GitHub Issues in `jrudavicius/home-server`. Use the authenticated `gh` CLI for this workflow.

## Repository and issue operations

- Run `gh repo view --json nameWithOwner` from this checkout to verify the repository. Use `--repo jrudavicius/home-server` for writes so an upstream repository cannot be selected accidentally.
- Read an issue with `gh issue view NUMBER --repo jrudavicius/home-server --json number,title,body,labels,comments`.
- List issues with `gh issue list --repo jrudavicius/home-server --state open --json number,title,body,labels`, adding label filters for the workflow.
- Create an issue with `gh issue create --repo jrudavicius/home-server --title TITLE --body-file FILE`. Use a body file for multiline Markdown so shell quoting preserves the exact text.
- Add or remove labels with `gh issue edit NUMBER --repo jrudavicius/home-server --add-label LABEL` or `--remove-label LABEL`. Use the mapping in [triage-labels.md](triage-labels.md).
- Add a comment with `gh issue comment NUMBER --repo jrudavicius/home-server --body-file FILE` when the requested workflow calls for it.
- When closing an issue with an explanation, post the explanation first, then use `gh issue close NUMBER --repo jrudavicius/home-server`.

## Specs and product requirements

When a skill says "publish to the issue tracker", create a GitHub issue. When it says "fetch the relevant ticket", read the issue body, labels, and comments.

Product requirements may remain as repository documents under `docs/`. A later implementation spec should link to its source product document. A product PRD does not need to be moved into the issue tracker merely to complete this setup.

Reserve `ready-for-agent` for fully specified implementation specs and tickets that an agent can execute. Wayfinder maps and their decision tickets use only `wayfinder:*` labels. Raw incoming requests go through the triage workflow.

## Parent issues and blockers

Use GitHub's native sub-issue relationships and issue dependencies when available.

- Link a child with `gh issue edit PARENT --repo jrudavicius/home-server --add-sub-issue CHILD`.
- Add a blocker with `gh issue edit CHILD --repo jrudavicius/home-server --add-blocked-by BLOCKER`.
- The REST equivalents use numeric issue database IDs, not issue numbers or node IDs.
- If the relationship is unavailable, use `Part of #PARENT` in the child and a task list in the parent. For blockers, put `Blocked by: #NUMBER, #NUMBER` at the top of the child.
- Work blockers first. A ticket is startable when all its blockers are closed; inspect their states rather than just counting listed relationships.

## Pull requests as a triage surface

**PRs as a request surface: no.**

If this is changed to `yes`, external PRs follow the same triage roles as issues using the equivalent `gh pr` operations. GitHub shares a number space between issues and PRs, so resolve the object type before acting on a bare number.

## Wayfinding

- The map is one issue labeled `wayfinder:map`.
- Decision tickets are child issues labeled `wayfinder:research`, `wayfinder:prototype`, `wayfinder:grilling`, or `wayfinder:task`.
- Create these additional labels only when using the wayfinding workflow.
- Choose an open, unassigned child whose blockers are all closed, in map order.
- Claim it by assigning it to the driving developer.
- To resolve it, record the answer, close the child, and add a short decision summary with a link to the map.
