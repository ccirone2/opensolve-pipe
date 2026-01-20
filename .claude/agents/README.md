# Claude Code Agents

This directory contains specialized agents for the OpenSolve Pipe project.

## Available Agents

### hydraulics-reviewer

**Purpose:** Reviews hydraulic calculations and solver implementations for correctness

**Invoke when:**

- Implementing new hydraulic calculations
- Modifying solver logic
- Adding pump curve functionality
- Updating friction factor calculations

**Checks:**

- Darcy-Weisbach equation usage
- Friction factor calculations (Colebrook equation)
- K-factor resolution order
- Unit consistency
- Conservation laws (mass, energy)
- Pump curve interpolation
- Network solver convergence

**Location:** `.claude/agents/hydraulics-reviewer.md`

---

### tsd-compliance

**Purpose:** Ensures code follows Technical Specification Document

**Invoke when:**

- Before merging PRs
- After significant implementation work
- When unsure about design decisions

**Checks:**

- API contract compliance
- Data model structure
- URL encoding format
- Unit system handling
- Error response format

**Location:** `.claude/agents/tsd-compliance.md`

---

### ui-review

**Purpose:** Reviews frontend UI/UX using Playwright MCP and applies fixes

**Invoke when:**

- After implementing new UI components
- Before merging frontend PRs
- When users report visual/interaction bugs
- During regression testing
- Validating responsive design

**Prerequisites:**

- Frontend running (`pnpm dev` on port 5173 or `pnpm preview` on port 4173)
- Playwright MCP server available

**Checks:**

- Homepage elements and navigation
- Project page functionality (Panel/Results views)
- Solve workflow and loading states
- Results display and data rendering
- Responsive layouts (desktop, tablet, mobile)
- Accessibility (aria labels, keyboard nav, contrast)
- Keyboard shortcuts (Ctrl+Enter)

**Workflows:**

- **Quick Health Check:** Basic element verification
- **Full Regression Test:** Comprehensive UI validation
- **Post-Fix Verification:** Confirm issue resolution

**Output:** Detailed report with screenshots, categorized issues (Critical/Major/Minor), and code fixes with file paths

**Location:** `.claude/agents/ui-review.md`

---

## Usage

Agents are invoked automatically by Claude Code when relevant tasks are detected, or you can explicitly request an agent review:

```text
Review the UI using the ui-review agent
Run the hydraulics-reviewer on the solver changes
Check TSD compliance for this PR
```

## Adding New Agents

1. Create a new `.md` file in this directory
2. Include YAML frontmatter with `name`, `description`, and `model`
3. Document the agent's purpose, triggers, and checks
4. Update this README with the new agent
