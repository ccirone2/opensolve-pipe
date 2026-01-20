# Review Frontend UI/UX

Use the UI review agent (`.claude/agents/ui-review.md`) to perform a comprehensive review of the frontend.

## Prerequisites

1. Ensure the frontend is running:

   ```bash
   cd apps/web && pnpm dev
   ```

2. Confirm it's accessible at `http://localhost:5173`

## Review Tasks

Using Playwright MCP:

### 1. Homepage Review

- **Navigate to homepage** (`http://localhost:5173`)
- Take a screenshot
- Verify all elements per TSD.md Section 8:
  - Page title contains "OpenSolve Pipe"
  - Main heading visible
  - "New Project" button/link visible and clickable
  - Features section displays correctly
- Check responsive layout at 375px, 768px, and 1280px widths
- Screenshot each viewport size

### 2. New Project Flow

- Click the "New Project" button/link
- Screenshot the project page
- Verify:
  - Panel/Results view switcher is visible
  - Solve button is present and accessible
  - Add component button is available
  - Project name is editable

### 3. Build a Simple Piping System

Build a complete system to test all component creation workflows. Take screenshots at each step to verify menus and layouts:

#### Step 3.1: Add Reservoir (Source)

- Click "Add Component" button
- Screenshot the component selection menu
- Select "Reservoir" component type
- Screenshot the reservoir configuration form
- Fill in reservoir parameters (elevation, head)
- Save the component
- Screenshot showing reservoir in the system

#### Step 3.2: Add Pump

- Click "Add Component" button
- Screenshot menu (verify it's clean and well-structured)
- Select "Pump" component type
- Screenshot the pump configuration form
- Configure pump curve or select a preset
- Save the component
- Screenshot showing pump added downstream of reservoir

#### Step 3.3: Add Piping Segments

- Add pipe segment from reservoir to pump suction
- Screenshot pipe configuration form (verify material/size dropdowns work)
- Configure pipe: material, diameter, length, roughness
- Add pipe segment from pump discharge
- Screenshot the growing system layout

#### Step 3.4: Add Valve

- Click "Add Component" button
- Select "Valve" component type
- Screenshot valve configuration form
- Configure valve type and Cv/K-factor
- Save and screenshot the updated system

#### Step 3.5: Add Final Pipe and Tank (Destination)

- Add pipe segment after valve
- Add "Tank" component as destination
- Configure tank parameters (elevation, level)
- Screenshot the complete system layout

#### Step 3.6: Verify System Navigation

- Screenshot the panel navigator showing all components
- Test breadcrumb navigation between components
- Verify prev/next navigation works
- Screenshot each navigation state

### 4. Test Solve Workflow

- Click the "Solve" button
- Screenshot immediately to capture loading state
- Verify loading indicator appears (spinner, disabled button, etc.)
- Wait for solve to complete
- Screenshot the results view
- Verify:
  - Convergence status indicator (green checkmark for success)
  - Results tables render (Node, Link, Pump tables)
  - Pump operating point displayed
  - Any warnings section if applicable

### 5. Results View Inspection

- Switch to Results view if not already visible
- Screenshot the full results layout
- Verify:
  - All result values are populated
  - Units are displayed correctly
  - Tables are readable and well-formatted
- Test responsive layout of results at 375px width
- Screenshot mobile results view

### 6. Accessibility Audit

- Use `browser_snapshot` to get accessibility tree
- Check for missing aria-labels on interactive elements
- Verify keyboard navigation:
  - Tab through all elements
  - Verify focus indicators are visible
  - Screenshot focus states
- Test Ctrl+Enter shortcut triggers solve
- Verify color contrast meets WCAG AA

### 7. Edge Cases

- Test empty project state (no components)
- Test solving with incomplete system (should show validation errors)
- Screenshot error states and messages
- Verify error messages are clear and actionable

## Reference Docs

- `/docs/TSD.md` - Technical specifications (Section 8 for frontend)
- `/docs/PRD.md` - Product requirements and UX goals
- `/docs/DEVELOPMENT_PLAN.md` - Implementation details

## Generate Report

After completing all checks, generate a report following this format:

```markdown
## UI/UX Review Report

**Date:** [timestamp]
**Frontend URL:** http://localhost:5173
**Viewports Tested:** 375px, 768px, 1280px

### Screenshots Captured
1. Homepage (desktop/tablet/mobile)
2. Component selection menu
3. Each component configuration form
4. System build progress
5. Navigation states
6. Solve loading state
7. Results view
8. Error states

### Critical Issues
[List any blocking issues]

### Major Issues
[List significant UX problems]

### Minor Issues
[List polish items]

### Passed Checks
[List all validations that passed]

### Overall Status: [PASS/FAIL/NEEDS_ATTENTION]
```

## Apply Fixes

For any issues found:

1. Categorize by severity (Critical/Major/Minor)
2. Provide code fixes with exact file paths
3. Apply fixes using the appropriate edit tools
4. Re-run the affected checks to verify fixes
5. Run `cd apps/web && pnpm test:e2e` to ensure fixes don't break E2E tests
