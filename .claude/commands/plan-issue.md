---
name: plan-issue
description: Create a detailed implementation plan for a GitHub issue using /workflows:plan
arguments:
  - name: issue
    description: "GitHub issue number"
    required: true
---

# Plan Issue #$ARGUMENTS.issue

## Step 1: Ensure Issue Exists on GitHub

Check if the issue exists:

```bash
gh issue view $ARGUMENTS.issue --json number,title,body,state 2>/dev/null || echo "ISSUE_NOT_FOUND"
```

If `ISSUE_NOT_FOUND`, create it from `docs/PHASE_1_ISSUES.md`:

1. Read `docs/PHASE_1_ISSUES.md` to find Issue #$ARGUMENTS.issue details
2. Create the issue:

```bash
gh issue create --title "[TITLE FROM PHASE_1_ISSUES.md]" --body "[BODY FROM PHASE_1_ISSUES.md]"
```

## Step 2: Read Required Context

Before planning, read these files:

```bash
cat docs/DEVELOPMENT_PLAN.md
cat docs/PHASE_1_ISSUES.md
cat docs/TSD.md
cat CLAUDE.md
```

## Step 3: Create Feature Branch

```bash
git checkout main
git pull origin main
git checkout -b feature/issue-$ARGUMENTS.issue
```

## Step 4: Generate Implementation Plan

Now invoke the compound-engineering planning workflow:

**Context for /workflows:plan:**

- **Issue**: #$ARGUMENTS.issue
- **Reference Docs**:
  - `docs/DEVELOPMENT_PLAN.md` - Overall phase structure and milestones
  - `docs/PHASE_1_ISSUES.md` - Detailed issue requirements
  - `docs/TSD.md` - Technical implementation specifications
  - `docs/SDD.md` - Architecture and data models
  - `docs/DECISIONS.md` - Prior architectural decisions
- **Constraints**: Follow TSD folder structure, use specified tech stack
- **Output**: Save plan to `docs/plans/issue-$ARGUMENTS.issue-plan.md`

Run:

```
/workflows:plan
```

## Step 5: Link Plan to GitHub Issue

After plan is created, comment on the issue:

```bash
gh issue comment $ARGUMENTS.issue --body "## 📋 Implementation Plan Created

**Branch**: \`feature/issue-$ARGUMENTS.issue\`
**Plan**: \`docs/plans/issue-$ARGUMENTS.issue-plan.md\`

### Summary
[INSERT 2-3 SENTENCE SUMMARY]

### Next Steps
1. Review plan
2. Run \`/workflows:work\` to execute
"
```

## Step 6: Ready for Work

Plan complete. To execute:

```
/workflows:work
```

## Step 7: Update /docs

Update the /\*.md files in /docs with checks in todo lists. Create/update the DECISIONS.md with
changes from original planning documents.
