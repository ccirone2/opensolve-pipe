# OpenSolve Pipe - Claude Code Configuration

This directory contains Claude Code configuration, including custom skills, agents, and hooks tailored for OpenSolve Pipe development.

## Structure

```
.claude/
├── settings.json           # Claude Code settings and plugins
├── auto-updates.json       # Automatic file update configuration
│
├── skills/                 # Custom domain knowledge
│   ├── hydraulics/
│   │   └── SKILL.md        # Hydraulic engineering reference
│   └── data-model/
│       └── SKILL.md        # Component chain model conventions
│
├── agents/                 # Specialized review agents
│   ├── hydraulics-reviewer.md    # Reviews hydraulic calculations
│   └── tsd-compliance.md         # Verifies TSD compliance
│
├── hooks/                  # Event-driven automation
│   ├── stop-iterate.json   # Feedback and iteration loop
│   └── block-dangerous.json      # Safety guard for commands
│
└── README.md               # This file
```

## Plugins

### compound-engineering

Core development workflow plugin providing:

- **Workflows:** `/workflows:plan`, `/workflows:work`, `/workflows:review`, `/workflows:compound`
- **Commands:** `/deepen-plan`, `/changelog`
- **Agents:** Planning, review, architecture, documentation
- **Skills:** Frontend design, compound docs

**Configuration:** `.claude/settings.json`

## Custom Skills

### hydraulics

**Purpose:** Hydraulic engineering domain knowledge for solver development

**Use when:**
- Implementing Darcy-Weisbach calculations
- Adding component types with hydraulic behavior
- Reviewing head loss calculations
- Need K-factors, roughness values, or unit conversions

**Contents:**
- Friction factor calculations (Colebrook equation)
- K-factor resolution order
- Standard L/D values (Crane TP-410)
- Pipe material roughness
- Unit conversion reference
- NPSH calculation formulas
- Validation checklist

**Location:** `.claude/skills/hydraulics/SKILL.md`

### opensolve-pipe-data-model

**Purpose:** Component chain data model conventions

**Use when:**
- Creating or modifying component interfaces
- Working with project structure
- Adding new component types
- Debugging component chain issues

**Contents:**
- Component chain model (vs node-link graph)
- Component ID conventions
- PipingSegment structure
- Component type definitions
- Validation rules
- Solver conversion patterns
- Example systems

**Location:** `.claude/skills/data-model/SKILL.md`

## Custom Agents

### hydraulics-reviewer

**Purpose:** Reviews hydraulic calculations for correctness

**Invoke when:**
- Completing solver implementation
- Reviewing PRs with hydraulic code
- Validating calculation accuracy
- Need expert physics/math review

**Checks:**
- Darcy-Weisbach usage (not Hazen-Williams)
- K-factor resolution order
- NPSH calculations
- Conservation laws
- Numerical stability
- Edge cases

**Output:** Detailed review with correctness rating, accuracy concerns, recommendations, and verified calculations

**Location:** `.claude/agents/hydraulics-reviewer.md`

### tsd-compliance

**Purpose:** Ensures code follows Technical Specification Document

**Invoke when:**
- Adding new API endpoints
- Modifying data models
- Restructuring files/directories
- Need compliance verification before PR

**Checks:**
- File locations (TSD Section 3)
- Data model alignment (TSD Section 4)
- API contracts (TSD Section 7)
- Solver implementation (TSD Section 5)
- Unit conversion (TSD Section 6)
- URL encoding (TSD Section 4.4)

**Output:** Compliance report with pass/fail status, violations with TSD references, and required changes

**Location:** `.claude/agents/tsd-compliance.md`

## Custom Hooks

### stop-iterate

**Event:** `stop`

**Purpose:** Provides feedback after task completion and iterates up to 5 times for quality improvement

**Configuration:**
- Max iterations: 5
- Quality threshold: 0.9
- Test coverage threshold: 93%

**Checks:**
- Test coverage (≥93%)
- Linting (zero errors)
- Type checking (zero errors)

**Behavior:**
- Iteration 1-4: Provides specific feedback and continues
- Iteration 5: Stops with summary
- High quality (<90%): Stops early with success message

**Location:** `.claude/hooks/stop-iterate.json`

### block-dangerous

**Event:** `preToolUse`

**Purpose:** Blocks dangerous commands that could harm system or data

**Blocked Patterns:**
- `rm -rf /` (outside safe dirs)
- `mkfs` (filesystem formatting)
- `DROP DATABASE` (database destruction)
- Credential exposure (echo $PASSWORD)
- Network scanning (nmap, nikto)
- Insecure permissions (chmod 777)
- Force push to main/master

**Warning Patterns:**
- `rm -rf` (general)
- `git push --force`
- `DELETE FROM` without WHERE

**Location:** `.claude/hooks/block-dangerous.json`

## Auto-Updates

Automatic file maintenance triggered by events:

### Triggers

**onFileChange:**
- Python files → Update API types, changelog
- TypeScript models → Update changelog
- Documentation → Validate consistency

**onCommit:**
- All files → Update changelog

**onPRMerge:**
- Update version, changelog, regenerate API client

**onArchitectureChange:**
- SDD/TSD changes → Update DECISIONS.md

### Managed Files

**docs/CHANGELOG.md**
- Format: keep-a-changelog
- Sections: Added, Changed, Deprecated, Removed, Fixed, Security

**docs/DECISIONS.md**
- Format: ADR (Architecture Decision Records)
- Template: Context, Decision, Consequences

**apps/web/src/lib/api/types.ts**
- Generated from: `apps/api/src/opensolve_pipe/models/*.py`
- Generator: pydantic-to-typescript

**docs/API.md**
- Generated from: `apps/api/src/opensolve_pipe/routers/*.py`
- Generator: fastapi-to-markdown

**Configuration:** `.claude/auto-updates.json`

## Usage Examples

### Using Skills

```
# Invoke hydraulics skill
When implementing the Darcy-Weisbach solver, use the hydraulics skill
for reference K-factors and friction factor calculations.

# Invoke data-model skill
When adding a new Valve component, consult the opensolve-pipe-data-model
skill for ID conventions and structure requirements.
```

### Using Agents

```
# Review hydraulic calculations
Agent: hydraulics-reviewer
Task: Review apps/api/src/opensolve_pipe/services/solver/simple.py

# Check TSD compliance
Agent: tsd-compliance
Task: Verify apps/api/src/opensolve_pipe/routers/solve.py follows TSD Section 7
```

### Workflow with Hooks

```
# Hooks run automatically

# stop-iterate hook runs after task completion
Task: Implement simple solver
→ Iteration 1: Fix linting errors
→ Iteration 2: Improve test coverage to 94%
→ Iteration 3: Complete (quality threshold met)

# block-dangerous hook runs before bash commands
Command: rm -rf apps/api/tests
→ WARNING: Potentially dangerous rm -rf command
→ Proceeds with caution

Command: rm -rf /
→ BLOCKED: Dangerous command detected
→ Execution prevented
```

## Customization

### Add New Skill

1. Create directory: `.claude/skills/my-skill/`
2. Create file: `.claude/skills/my-skill/SKILL.md`
3. Add frontmatter:
   ```yaml
   ---
   name: my-skill
   description: Brief description
   ---
   ```
4. Document knowledge and usage

### Add New Agent

1. Create file: `.claude/agents/my-agent.md`
2. Add frontmatter:
   ```yaml
   ---
   name: my-agent
   description: What this agent does
   model: inherit
   ---
   ```
3. Define review process and output format

### Add New Hook

1. Create file: `.claude/hooks/my-hook.json`
2. Define configuration:
   ```json
   {
     "name": "my-hook",
     "event": "preToolUse|postToolUse|stop",
     "description": "...",
     ...
   }
   ```

### Modify Auto-Updates

Edit `.claude/auto-updates.json`:

```json
{
  "files": {
    "path/to/file.ts": {
      "autoGenerate": true,
      "source": "path/to/source",
      "trigger": "onFileChange"
    }
  }
}
```

## Best Practices

1. **Use skills for reference** - Don't duplicate skill content in prompts
2. **Invoke agents for review** - Let specialized agents do deep analysis
3. **Trust the hooks** - They prevent common mistakes
4. **Keep auto-updates enabled** - Maintains consistency
5. **Document new patterns** - Update skills when learning new approaches

## Troubleshooting

### Skill Not Loading

- Check file location: `.claude/skills/{skill-name}/SKILL.md`
- Verify frontmatter format
- Ensure markdown syntax is valid

### Agent Not Working

- Check file location: `.claude/agents/{agent-name}.md`
- Verify frontmatter has `name`, `description`, `model`
- Check for syntax errors in markdown

### Hook Not Triggering

- Verify event name matches: `stop`, `preToolUse`, `postToolUse`
- Check JSON syntax
- Ensure patterns compile (regex patterns)

### Auto-Update Failed

- Check source file exists
- Verify generator script is available
- Review error message in notification

## Resources

- [compound-engineering plugin docs](https://github.com/compound-hq/compound-engineering)
- [Claude Code documentation](https://docs.anthropic.com/claude-code)
- [Skills reference](https://docs.anthropic.com/claude-code/skills)
- [Agents reference](https://docs.anthropic.com/claude-code/agents)
- [Hooks reference](https://docs.anthropic.com/claude-code/hooks)
