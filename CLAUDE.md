# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**WebFormsService** is a feature development project that follows the SpecKit workflow methodology for systematic feature specification, planning, and implementation. The repository uses a structured approach to break down features from initial concept through implementation.

## SpecKit Workflow System

This repository implements a feature development workflow with the following phases:

### Phase 1: Specification (`/speckit.specify`)
Creates a technology-agnostic feature specification focused on **WHAT** and **WHY**, not **HOW**.

**Key Concepts:**
- Feature branches follow pattern: `###-feature-name` (e.g., `001-user-auth`)
- Specs stored in `specs/###-feature-name/spec.md`
- Focus on user scenarios, acceptance criteria, and business value
- Quality validated via `specs/###-feature-name/checklists/requirements.md`

**Important:** Specifications must be free of implementation details (no languages, frameworks, APIs). They are written for business stakeholders, not developers.

### Phase 2: Planning (`/speckit.plan`)
Converts the specification into a technical implementation plan with architecture decisions.

**Key Artifacts:**
- `plan.md` - Technical architecture, tech stack, file structure
- `research.md` - Technology choices with rationale
- `data-model.md` - Entities, relationships, validation rules
- `contracts/` - API contracts (OpenAPI/GraphQL schemas)
- `quickstart.md` - Integration scenarios

**Process Flow:**
1. Phase 0: Research & resolve clarifications → `research.md`
2. Phase 1: Design contracts and data models → `data-model.md`, `contracts/`, `quickstart.md`
3. Agent context update via `.specify/scripts/bash/update-agent-context.sh claude`

### Phase 3: Task Breakdown (`/speckit.tasks`)
Generates an actionable, dependency-ordered task list from the plan.

**Task Structure:**
- **Phases:** Setup, Tests, Core, Integration, Polish
- **Parallel markers:** `[P]` indicates tasks that can run concurrently
- **Dependencies:** Sequential tasks must run in order
- Tasks affecting same files must run sequentially

### Phase 4: Implementation (`/speckit.implement`)
Executes the implementation following the task plan with TDD approach.

**Execution Rules:**
- Validates checklist completion before starting (can override)
- Phase-by-phase execution with validation checkpoints
- Tests written before implementation (TDD)
- Marks completed tasks as `[X]` in tasks.md
- Progress tracking with error handling

### Additional Commands

**`/speckit.clarify`** - Identifies underspecified areas and asks targeted clarification questions (max 5).

**`/speckit.analyze`** - Cross-artifact consistency analysis for spec.md, plan.md, and tasks.md.

**`/speckit.checklist`** - Generates custom validation checklists for current feature.

**`/speckit.constitution`** - Creates/updates project constitution with development principles.

## Architecture & Key Scripts

### Script Locations
All utility scripts are in `.specify/scripts/bash/`:

- **`check-prerequisites.sh`** - Validates feature directory structure and returns JSON with paths
  - Usage: `.specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks`

- **`create-new-feature.sh`** - Creates new feature branch and initializes spec file
  - Checks remote/local branches and spec directories for highest feature number
  - Usage: `.specify/scripts/bash/create-new-feature.sh --json "$ARGUMENTS" --number N --short-name "feature-name"`

- **`setup-plan.sh`** - Initializes planning phase and returns paths
  - Usage: `.specify/scripts/bash/setup-plan.sh --json`

- **`update-agent-context.sh`** - Updates AI agent context files with new technologies
  - Usage: `.specify/scripts/bash/update-agent-context.sh claude`
  - Preserves manual additions between markers

### Template System
Templates in `.specify/templates/`:

- `spec-template.md` - Feature specification structure
- `plan-template.md` - Technical planning structure
- `tasks-template.md` - Task breakdown format
- `checklist-template.md` - Validation checklist format
- `agent-file-template.md` - Agent context file structure

### Constitution Framework
`.specify/memory/constitution.md` defines project-wide development principles and constraints. Currently uses placeholder structure but can be customized with:

- Core development principles (TDD, library-first, CLI interfaces, etc.)
- Technology constraints
- Quality gates
- Governance rules

## Working with Features

### Starting a New Feature
1. Run `/speckit.specify [feature description]`
2. System generates short-name and checks for existing branches
3. Creates `specs/###-feature-name/` with spec.md
4. Validates specification quality via requirements checklist
5. Addresses any [NEEDS CLARIFICATION] markers (max 3)

### Branch Numbering
- System checks: remote branches, local branches, and spec directories
- Finds highest number for matching short-name
- Increments by 1 for new branch
- Example: If `001-user-auth` exists, next is `002-user-auth`

### Path Handling
- **Always use absolute paths** when running scripts
- Scripts output JSON with absolute paths (parse `FEATURE_DIR`, `SPEC_FILE`, `BRANCH_NAME`, etc.)
- Bash single-quote escaping: `'I'\''m Groot'` or use double quotes: `"I'm Groot"`

### Quality Gates
Checklists validate:
- Specification completeness (no implementation leaks)
- Requirement clarity (testable, measurable)
- Success criteria (technology-agnostic, user-focused)
- Plan-spec consistency
- Contract coverage

### TDD Approach
- Tests written before implementation
- Test tasks appear before corresponding implementation tasks
- Contract tests validate API specifications
- Integration tests verify cross-component behavior

## Key Principles

### Specification Phase
- **What/Why, not How:** No languages, frameworks, or APIs
- **User-centric:** Written for business stakeholders
- **Testable requirements:** All requirements must have clear acceptance criteria
- **Reasonable defaults:** Make informed guesses, limit clarifications to 3 max
- **Success criteria:** Must be measurable, technology-agnostic, and verifiable

### Planning Phase
- **Research first:** Resolve all unknowns before design
- **Constitution compliance:** Check against project principles
- **Contract-driven:** API contracts generated from functional requirements
- **Data model clarity:** Extract entities from spec with validation rules

### Implementation Phase
- **Respect task order:** Honor dependencies and parallel markers
- **Phase validation:** Complete each phase before next
- **File coordination:** Tasks on same files run sequentially
- **Progress tracking:** Report completion, handle errors gracefully
- **Mark completion:** Update tasks.md with `[X]` for completed tasks

## Common Patterns

### Ignore File Management
Implementation phase auto-creates/verifies ignore files based on tech stack:
- Git → `.gitignore`
- Docker → `.dockerignore`
- ESLint → `.eslintignore`
- Technology-specific patterns (Node.js, Python, C#, Go, etc.)

### Checklist Validation
Before implementation starts:
1. Scans `FEATURE_DIR/checklists/` for all checklist files
2. Counts total/completed/incomplete items per checklist
3. Blocks implementation if incomplete (can override)
4. Displays status table with pass/fail for each checklist

### Multi-Phase Execution
Each command is independent but sequential:
1. `/speckit.specify` → spec.md + requirements.md checklist
2. `/speckit.clarify` → resolve ambiguities (optional)
3. `/speckit.plan` → plan.md + research.md + data-model.md + contracts/
4. `/speckit.tasks` → tasks.md with dependency-ordered task list
5. `/speckit.implement` → executes tasks, creates implementation

### Error Handling
- Non-parallel tasks: Halt on failure
- Parallel tasks `[P]`: Continue with successes, report failures
- Provide clear error context for debugging
- Suggest recovery steps

## Development Notes

- Repository is git-enabled (branch: `main`, main branch: `main`)
- No existing codebase beyond SpecKit framework
- Ready for feature development following the workflow
- Constitution template ready for customization with project-specific principles
