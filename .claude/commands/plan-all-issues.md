---
name: plan-all-issues
description: Automatically plan and execute all open GitHub issues sequentially
arguments: []
---

# Plan and Execute All Issues

## Compound Engineering Skills & Agents

- **Planning**: `/workflows:plan` - Generate detailed implementation plans
- **Execution**: `/workflows:work` - Execute implementation plans
- **Code Review**: `/workflows:review` - Review code changes
- **Testing**: `/workflows:test` - Run and validate tests
- **Documentation**: `/workflows:document` - Update documentation

## Step 1: Read Required Context

Use `/workflows:plan` context gathering to read:

- `docs/DEVELOPMENT_PLAN.md`
- `docs/PHASE_1_ISSUES.md`
- `docs/TSD.md`
- `docs/SDD.md`
- `docs/DECISIONS.md`
- `CLAUDE.md`

## Step 2: Get All Open Issues

```bash
gh issue list --state open --json number,title --jq 'sort_by(.number) | .[] | "\(.number)|\(.title)"'
```

## Step 3: Process Each Issue Sequentially

For each issue from the list above, perform the following steps automatically:

### 3a. Create Feature Branch

```bash
git checkout main
git pull origin main
git checkout -b feature/issue-{ISSUE_NUMBER}
```

### 3b. Read Issue Details

```bash
gh issue view {ISSUE_NUMBER} --json number,title,body,labels
```

### 3c. Generate Implementation Plan

Invoke `/workflows:plan` with context:

- **Issue**: #{ISSUE_NUMBER}
- **Reference Docs**: DEVELOPMENT_PLAN.md, PHASE_1_ISSUES.md, TSD.md, SDD.md, DECISIONS.md
- **Output**: `docs/plans/issue-{ISSUE_NUMBER}-plan.md`

### 3d. Execute the Plan

Invoke `/workflows:work` to:

1. Create new files as specified in the plan
2. Modify existing files
3. Write tests for new functionality

### 3e. Validate Implementation

Invoke `/workflows:test` to:

1. Run linting and fix issues
2. Run unit tests
3. Verify acceptance criteria

```bash
npm run lint --fix 2>/dev/null || true
npm test 2>/dev/null || true
```

### 3f. Review Changes

Invoke `/workflows:review` to:

1. Self-review code changes
2. Check for issues or improvements
3. Apply any fixes

### 3g. Commit Changes

```bash
git add -A
git commit -m "feat: implement issue #{ISSUE_NUMBER} - {ISSUE_TITLE}"
```

### 3h. Push and Create PR

```bash
git push -u origin feature/issue-{ISSUE_NUMBER}
gh pr create --title "feat: #{ISSUE_NUMBER} - {ISSUE_TITLE}" --body "## Summary

Implements #{ISSUE_NUMBER}

## Changes
- [AUTO-GENERATED LIST OF CHANGES]

## Plan
See \`docs/plans/issue-{ISSUE_NUMBER}-plan.md\`

Closes #{ISSUE_NUMBER}"
```

### 3i. Update Documentation

Invoke `/workflows:document` to update `/docs/*.md` files:

- Check off completed items in todo lists
- Update `DECISIONS.md` with any architectural decisions made
- Link to the issue number where relevant

### 3j. Move to Next Issue

```bash
git checkout main
git pull origin main
```

Repeat steps 3a-3j for the next issue.

## Step 4: Final Summary

```bash
echo "=== Completed Issues ==="
gh pr list --state open --json number,title,url --jq '.[] | "PR #\(.number): \(.title) - \(.url)"'
```

## Execution Mode

**IMPORTANT**: Execute this entire workflow autonomously using the Compound Engineering workflows. Do not pause for user confirmation between issues. Process each issue completely (plan → work → test → review → commit → PR → document) before moving to the next one. If an error occurs on one issue, log it and continue to the next issue.
