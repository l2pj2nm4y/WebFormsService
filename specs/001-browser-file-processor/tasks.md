# Tasks: Browser Extension File Processing System

**Input**: Design documents from `/specs/001-browser-file-processor/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: TDD is mandatory per Constitution Principle II (NON-NEGOTIABLE). All tests MUST be written first and FAIL before implementation.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/`, `tests/` at repository root (as specified in plan.md)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure per plan.md

- [ ] T001 Create project directory structure per plan.md (src/, tests/, storage/)
- [ ] T002 Initialize Python 3.11+ project with Poetry and pyproject.toml dependencies
- [ ] T003 [P] Configure black, ruff, and mypy for code quality in pyproject.toml
- [ ] T004 [P] Create .env.example template with all required environment variables
- [ ] T005 [P] Setup Docker Compose file for local Redis in docker-compose.yml
- [ ] T006 [P] Create .gitignore for Python project (venv, __pycache__, .env, storage/)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### Configuration & Logging

- [ ] T007 Implement configuration management in src/lib/config.py with Pydantic BaseSettings
- [ ] T008 [P] Implement structured JSON logging in src/lib/logging.py with trace IDs
- [ ] T009 [P] Implement file path validation in src/lib/validation.py (path traversal, size limits)

### Data Models (All Stories Depend On These)

- [ ] T010 [P] Create Session model in src/models/session.py with validation
- [ ] T011 [P] Create FileTriplet model in src/models/session.py with path validators
- [ ] T012 [P] Create FactFile model in src/models/fact.py with field validators
- [ ] T013 [P] Create PromptFile model in src/models/prompt.py with bracketed notation support
- [ ] T014 [P] Create ProcessingResult model in src/models/result.py with metrics
- [ ] T015 [P] Create MasterFolder model in src/models/master.py
- [ ] T016 [P] Create EmbeddingsIndex and PageEmbedding models in src/models/master.py

### Storage Layer (All Stories Need This)

- [ ] T017 Create StorageInterface abstract base class in src/services/storage/cloud_adapter.py
- [ ] T018 [P] Implement LocalStorage class in src/services/storage/cloud_adapter.py
- [ ] T019 [P] Implement S3Storage class in src/services/storage/cloud_adapter.py with boto3

### Redis Coordination (All Stories Need This)

- [ ] T020 Create RedisConnection manager in src/services/coordination/__init__.py
- [ ] T021 [P] Implement session queue operations in src/services/coordination/session_queue.py
- [ ] T022 [P] Implement master lock operations with context manager in src/services/coordination/master_lock.py

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Process Session Files to Extract Page Facts (Priority: P1) 🎯 MVP

**Goal**: Analyze screenshots to generate fact files for page identification (visual headings, layout patterns, form elements, content keywords)

**Independent Test**: Upload session folder with screenshot/HTML/metadata triplets → verify fact files generated with all required fields

### Contract Tests for User Story 1 (TDD - MUST WRITE FIRST)

> **CRITICAL**: Write these tests FIRST, ensure they FAIL before implementation

- [ ] T023 [P] [US1] Contract test for fact extraction AI in tests/contract/test_ai_contracts.py::test_fact_extraction_contract
- [ ] T024 [P] [US1] Contract test for storage read operations in tests/contract/test_storage_contracts.py::test_storage_read_write
- [ ] T025 [P] [US1] Contract test for Redis session queue in tests/contract/test_redis_contracts.py::test_session_queue_fifo

### Unit Tests for User Story 1 (TDD - MUST WRITE FIRST)

- [ ] T026 [P] [US1] Unit test for fact extractor in tests/unit/test_fact_extractor.py
- [ ] T027 [P] [US1] Unit test for session storage operations in tests/unit/test_session_storage.py
- [ ] T028 [P] [US1] Unit test for triplet processor stage in tests/unit/test_triplet_processor.py (fact extraction only)

### Implementation for User Story 1

- [ ] T029 [US1] Implement AI fact extraction service in src/services/ai/fact_extractor.py with Pydantic AI
- [ ] T030 [US1] Implement session storage read operations in src/services/storage/session_storage.py
- [ ] T031 [US1] Implement triplet processor stage (fact extraction only) in src/services/pipeline/triplet_processor.py
- [ ] T032 [US1] Add session orchestration (claim → load → process facts → write) in src/services/orchestrator.py
- [ ] T033 [US1] Add comprehensive logging for all fact extraction operations per FR-016
- [ ] T034 [US1] Add error handling with context per FR-018 for fact extraction failures

### Integration Tests for User Story 1 (After Implementation)

- [ ] T035 [US1] Integration test for complete fact extraction pipeline in tests/integration/test_pipeline_integration.py::test_fact_extraction_end_to_end

**Checkpoint**: US1 complete - system can process sessions and generate fact files independently

---

## Phase 4: User Story 2 - Generate JSON Schema Prompts from Screenshots (Priority: P2)

**Goal**: Extend P1 with prompt/schema generation for form automation (comprehensive field definitions with bracketed notation)

**Independent Test**: Provide form screenshots → verify schema files contain complete field definitions with proper type annotations and constraints

### Contract Tests for User Story 2 (TDD - MUST WRITE FIRST)

- [ ] T036 [P] [US2] Contract test for prompt generation AI in tests/contract/test_ai_contracts.py::test_prompt_generation_contract

### Unit Tests for User Story 2 (TDD - MUST WRITE FIRST)

- [ ] T037 [P] [US2] Unit test for prompt generator in tests/unit/test_prompt_generator.py
- [ ] T038 [P] [US2] Unit test for triplet processor (prompt generation) in tests/unit/test_triplet_processor.py::test_prompt_generation

### Implementation for User Story 2

- [ ] T039 [US2] Implement AI prompt generation service in src/services/ai/prompt_generator.py with bracketed notation
- [ ] T040 [US2] Extend triplet processor to generate prompts in src/services/pipeline/triplet_processor.py
- [ ] T041 [US2] Update orchestrator to process both facts and prompts in src/services/orchestrator.py
- [ ] T042 [US2] Add logging for prompt generation operations per FR-016
- [ ] T043 [US2] Add error handling for prompt generation failures per FR-018

### Integration Tests for User Story 2 (After Implementation)

- [ ] T044 [US2] Integration test for complete triplet processing (facts + prompts) in tests/integration/test_pipeline_integration.py::test_complete_triplet_processing

**Checkpoint**: US1 + US2 complete - system generates both fact files and prompt files for all triplets

---

## Phase 5: User Story 3 - Batch Process Multiple Session Folders (Priority: P3)

**Goal**: Enable concurrent session processing with FIFO queue management and consolidated reporting

**Independent Test**: Submit 3 sessions simultaneously → verify all processed correctly with consolidated statistics and no cross-contamination

### Contract Tests for User Story 3 (TDD - MUST WRITE FIRST)

- [ ] T045 [P] [US3] Contract test for concurrent session claims in tests/contract/test_redis_contracts.py::test_session_queue_no_duplicates
- [ ] T046 [P] [US3] Contract test for master lock exclusivity in tests/contract/test_redis_contracts.py::test_master_lock_exclusive

### Unit Tests for User Story 3 (TDD - MUST WRITE FIRST)

- [ ] T047 [P] [US3] Unit test for session queue operations in tests/unit/test_session_queue.py
- [ ] T048 [P] [US3] Unit test for master lock operations in tests/unit/test_master_lock.py
- [ ] T049 [P] [US3] Unit test for within-session merger in tests/unit/test_session_merger.py
- [ ] T050 [P] [US3] Unit test for master merger in tests/unit/test_master_merger.py

### Implementation for User Story 3

#### AI Services for Matching & Merging

- [ ] T051 [P] [US3] Implement AI similarity scoring service in src/services/ai/similarity_scorer.py
- [ ] T052 [P] [US3] Implement AI embeddings generation service in src/services/ai/embeddings.py

#### Storage for Master Operations

- [ ] T053 [US3] Implement master storage write operations in src/services/storage/master_storage.py with lock checks

#### Pipeline Stages for Merging

- [ ] T054 [US3] Implement session merger stage (within-session matching) in src/services/pipeline/session_merger.py
- [ ] T055 [US3] Implement master merger stage (cross-session matching) in src/services/pipeline/master_merger.py
- [ ] T056 [US3] Implement combined prompt generator stage in src/services/pipeline/combiner.py

#### Orchestration & Reporting

- [ ] T057 [US3] Extend orchestrator for complete pipeline (triplet → session merge → master merge → combined) in src/services/orchestrator.py
- [ ] T058 [US3] Implement worker loop for continuous session processing in src/main.py
- [ ] T059 [US3] Add consolidated statistics reporting per FR-017 in src/services/orchestrator.py
- [ ] T060 [US3] Add comprehensive logging for all merge operations per FR-016
- [ ] T061 [US3] Add error handling for merge failures per FR-018

### Integration Tests for User Story 3 (After Implementation)

- [ ] T062 [US3] Integration test for Redis coordination (queue + locks) in tests/integration/test_redis_integration.py
- [ ] T063 [US3] Integration test for complete pipeline with merging in tests/integration/test_pipeline_integration.py::test_complete_pipeline_with_merging
- [ ] T064 [US3] Integration test for concurrent session processing in tests/integration/test_pipeline_integration.py::test_concurrent_sessions

**Checkpoint**: All user stories complete - system supports batch processing with merging and consolidated reporting

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

### Testing & Quality

- [ ] T065 [P] Run pytest with coverage and verify 80% unit, 70% integration coverage per Constitution Principle II
- [ ] T066 [P] Run mypy type checking and fix any type errors
- [ ] T067 [P] Run black and ruff formatting/linting across all source files
- [ ] T068 [P] Add docstrings to all public functions and classes per Constitution Principle III

### Documentation

- [ ] T069 [P] Create README.md with project overview and quickstart reference
- [ ] T070 [P] Document environment variables in .env.example with descriptions
- [ ] T071 [P] Add inline code comments for complex algorithms (similarity scoring, embeddings search)
- [ ] T072 [P] Create ADR for AI provider selection in docs/adr/001-openrouter-selection.md

### Operational

- [ ] T073 Create health check endpoint in src/main.py using FastAPI
- [ ] T074 [P] Add metrics collection for AI operations (tokens, latency, cost) per FR-016
- [ ] T075 [P] Implement retry logic with exponential backoff for AI API calls per contracts/ai-models.md
- [ ] T076 [P] Add file size validation enforcement per FR-020 in src/lib/validation.py
- [ ] T077 [P] Add file type validation per FR-021 in src/lib/validation.py

### Validation

- [ ] T078 Run quickstart.md validation with test session data
- [ ] T079 Verify zero code changes work between local (Docker) and production Redis per FR-026
- [ ] T080 Performance test: 5 sessions (50 triplets) in 10 minutes per SC-010

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational phase completion - MVP entry point
- **User Story 2 (Phase 4)**: Depends on Foundational phase completion - Can run parallel with US1/US3 if staffed
- **User Story 3 (Phase 5)**: Depends on Foundational phase completion - Can run parallel with US1/US2 if staffed
- **Polish (Phase 6)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P2)**: Can start after Foundational (Phase 2) - Extends US1 but independently testable
- **User Story 3 (P3)**: Can start after Foundational (Phase 2) - Builds on US1+US2 but independently testable

### Within Each User Story

- Contract tests FIRST (MUST FAIL before implementation)
- Unit tests SECOND (MUST FAIL before implementation)
- Implementation THIRD (make tests pass)
- Integration tests LAST (validate end-to-end)

### Parallel Opportunities

**Phase 1 (Setup)**: All tasks marked [P] can run in parallel

**Phase 2 (Foundational)**:
- Configuration/Logging tasks (T007-T009) can run in parallel
- All model tasks (T010-T016) can run in parallel after T007 completes
- Storage and Redis tasks (T017-T022) can run in parallel after models complete

**Phase 3 (US1)**:
- All contract tests (T023-T025) can run in parallel
- All unit tests (T026-T028) can run in parallel after contract tests
- Implementation tasks (T029-T034) must be sequential due to dependencies

**Phase 4 (US2)**:
- Contract and unit tests (T036-T038) can run in parallel
- Implementation tasks (T039-T043) must be sequential

**Phase 5 (US3)**:
- Contract tests (T045-T046) can run in parallel
- Unit tests (T047-T050) can run in parallel
- AI services (T051-T052) can run in parallel
- Pipeline stages (T054-T056) must be sequential
- Integration tests (T062-T064) can run in parallel after implementation

**Phase 6 (Polish)**: Most tasks marked [P] can run in parallel

---

## Parallel Example: User Story 1

```bash
# STEP 1: Launch all contract tests together (MUST FAIL):
Task T023: "Contract test for fact extraction AI in tests/contract/test_ai_contracts.py::test_fact_extraction_contract"
Task T024: "Contract test for storage read operations in tests/contract/test_storage_contracts.py::test_storage_read_write"
Task T025: "Contract test for Redis session queue in tests/contract/test_redis_contracts.py::test_session_queue_fifo"

# STEP 2: Launch all unit tests together (MUST FAIL):
Task T026: "Unit test for fact extractor in tests/unit/test_fact_extractor.py"
Task T027: "Unit test for session storage operations in tests/unit/test_session_storage.py"
Task T028: "Unit test for triplet processor stage in tests/unit/test_triplet_processor.py"

# STEP 3: Implement sequentially to make tests pass:
Task T029 → T030 → T031 → T032 → T033 → T034

# STEP 4: Integration test:
Task T035: "Integration test for complete fact extraction pipeline"
```

---

## Parallel Example: User Story 3

```bash
# After Foundational complete, User Stories can run in parallel:

# Team Member A works on US1:
Tasks T023-T035 (Fact extraction story)

# Team Member B works on US2:
Tasks T036-T044 (Prompt generation story)

# Team Member C works on US3:
Tasks T045-T064 (Batch processing story)

# All three stories complete independently and integrate at the end
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (6 tasks)
2. Complete Phase 2: Foundational (16 tasks - CRITICAL)
3. Complete Phase 3: User Story 1 (13 tasks)
4. **STOP and VALIDATE**: Test US1 independently with real session data
5. Deploy/demo if ready

**MVP Task Count**: 35 tasks
**Estimated MVP Time**: 3-5 days for experienced developer
**MVP Deliverable**: Working system that processes sessions and generates fact files

### Incremental Delivery

1. Complete Setup + Foundational → **Foundation ready** (22 tasks)
2. Add User Story 1 → Test independently → **Deploy/Demo (MVP!)** (+13 tasks = 35 total)
3. Add User Story 2 → Test independently → **Deploy/Demo (Fact + Prompt generation)** (+9 tasks = 44 total)
4. Add User Story 3 → Test independently → **Deploy/Demo (Full batch processing)** (+20 tasks = 64 total)
5. Polish & Cross-Cutting → **Production ready** (+16 tasks = 80 total)

Each story adds value without breaking previous stories

### Parallel Team Strategy

With 3 developers:

1. **Week 1**: Team completes Setup + Foundational together (22 tasks)
2. **Week 2** (Once Foundational is done):
   - Developer A: User Story 1 (13 tasks)
   - Developer B: User Story 2 (9 tasks)
   - Developer C: User Story 3 (20 tasks)
3. **Week 3**: Integration, testing, polish (16 tasks)

Stories complete and integrate independently

---

## Task Summary

**Total Tasks**: 80

**By Phase**:
- Phase 1 (Setup): 6 tasks
- Phase 2 (Foundational): 16 tasks
- Phase 3 (US1 - P1): 13 tasks
- Phase 4 (US2 - P2): 9 tasks
- Phase 5 (US3 - P3): 20 tasks
- Phase 6 (Polish): 16 tasks

**By Type**:
- Test tasks: 28 (35% - TDD compliant)
- Implementation tasks: 52 (65%)

**Parallel Opportunities**: 42 tasks marked [P] (52.5%)

**MVP Scope**: 35 tasks (Setup + Foundational + US1)

**Independent Test Criteria**:
- US1: Upload session → verify fact files with all required fields
- US2: Provide form screenshot → verify schema with proper field definitions
- US3: Submit 3 sessions → verify consolidated stats and no cross-contamination

**Format Validation**: ✅ All 80 tasks follow checklist format with ID, optional [P], Story label (where applicable), and file paths

---

## Notes

- **[P] tasks**: Different files, no dependencies - can run in parallel
- **[Story] label**: Maps task to specific user story (US1, US2, US3) for traceability
- **TDD Enforcement**: Constitution Principle II (NON-NEGOTIABLE) requires tests first
- **Each user story**: Independently completable and testable
- **Test Verification**: ALL tests MUST FAIL before implementing
- **Commit Frequency**: After each task or logical group
- **Checkpoints**: Validate story independently before moving to next
- **Avoid**: Vague tasks, same file conflicts, cross-story dependencies that break independence
