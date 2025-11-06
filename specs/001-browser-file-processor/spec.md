# Feature Specification: Browser Extension File Processing System

**Feature Branch**: `001-browser-file-processor`
**Created**: 2025-01-06
**Status**: Draft
**Input**: User description: "Browser extension file processing system with AI analysis for screenshots, HTML, and metadata to generate fact files and prompt files"

## Clarifications

### Session 2025-01-06

- Q: How should the system coordinate exclusive access to prevent write conflicts when multiple backends update the same master folder? → A: Redis-based coordination for session queue and master folder locking (works locally via Docker and in production)
- Q: When multiple sessions arrive, what determines processing priority/order? → A: FIFO by arrival timestamp - sessions processed in strict upload order
- Q: When a session writes fact/schema files to a master folder, how should conflicts be handled if a file with the same name already exists? → A: Merge with transformation - input files are analyzed/manipulated to create different outputs that are merged to master (merge process is separate task, use simple overwrite for MVP)
- Q: How should page identity matching work when comparing fact files within a session? → A: Within-session page matching uses AI similarity scoring with threshold on fact files
- Q: Should cross-session (session-to-master) page matching use the same AI similarity approach, or a different strategy? → A: Master maintains page embeddings index for fast similarity search, updated when facts change or new pages added

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Process Session Files to Extract Page Facts (Priority: P1)

The browser extension uploads captured form-filling sessions as organized file sets. The system automatically analyzes these files to identify and characterize each webpage, producing standardized fact files that enable page matching and recognition.

**Why this priority**: Core value proposition - without page identification, the system cannot provide meaningful analysis or matching capabilities. This is the foundation for all downstream features.

**Independent Test**: Can be fully tested by uploading a session folder with numbered screenshot/HTML/metadata triplets and verifying that fact files are generated with visual headings, layout patterns, form elements, and content keywords extracted from the screenshots.

**Acceptance Scenarios**:

1. **Given** a session folder with correctly sequenced file triplets (001-screenshot.png, 001-page.html, 001-metadata.json), **When** the system processes the session, **Then** a corresponding fact file (001-page.facts.json) is generated for each triplet containing visual headings, visual sections, form element detection, layout pattern, and content keywords
2. **Given** a screenshot showing a form with visible input fields and buttons, **When** AI analysis is performed, **Then** the fact file correctly identifies all visible form elements (field types, button labels) and marks has_forms as true
3. **Given** multiple sessions are processed, **When** fact extraction completes, **Then** the system reports success rate, processing time, and token usage statistics for each session
4. **Given** a session with 10 sequenced file triplets, **When** processing occurs, **Then** all 10 fact files are generated in sequence order maintaining the original numbering

---

### User Story 2 - Generate JSON Schema Prompts from Screenshots (Priority: P2)

The system analyzes form screenshots to generate comprehensive JSON schema structures that describe all editable fields, their types, validation rules, and metadata. These schema files serve as structured prompts for form automation and data extraction.

**Why this priority**: Extends the page identification capability (P1) to provide actionable schema information needed for form filling automation. Builds on top of the fact extraction foundation.

**Independent Test**: Can be tested independently by providing form screenshots and verifying that generated schema files contain complete field definitions with proper type annotations, validation constraints, required/optional indicators, and metadata descriptions following the bracketed notation format.

**Acceptance Scenarios**:

1. **Given** a screenshot of a form with text inputs, dropdowns, and checkboxes, **When** schema extraction is performed, **Then** a JSON schema file is generated with all visible editable fields mapped to appropriate data types (string, number, boolean, array)
2. **Given** a form showing required field indicators (asterisks or "required" labels), **When** schema is extracted, **Then** fields are correctly marked as [Required: type - description] or [Optional: type - description]
3. **Given** a dropdown or radio button group with visible options, **When** schema extraction occurs, **Then** the field uses enumeration format [Required: string - One of: option1|option2|option3]
4. **Given** a form with file upload fields showing format restrictions (e.g., "PDF only"), **When** schema is generated, **Then** file fields include constraint annotations like [Required: file - Upload document, Allowed: PDF, DOC]

---

### User Story 3 - Batch Process Multiple Session Folders (Priority: P3)

Users can submit multiple browser extension sessions for batch processing. The system processes each session independently, generating both fact files and schema files for all pages across all sessions, providing consolidated statistics and reporting.

**Why this priority**: Operational efficiency feature that builds on P1 and P2. Enables processing of multiple form-filling sessions without manual intervention but is not required for MVP functionality.

**Independent Test**: Can be tested by submitting 3 session folders simultaneously and verifying that all sessions are processed correctly with separate outputs maintained, consolidated success/failure reporting provided, and no cross-contamination between sessions.

**Acceptance Scenarios**:

1. **Given** 5 session folders submitted for batch processing, **When** processing starts, **Then** each session is processed independently with outputs saved to respective session folders
2. **Given** batch processing of multiple sessions, **When** one session fails, **Then** other sessions continue processing and failure is reported with specific session identifier and error details
3. **Given** completed batch processing, **When** results are reported, **Then** consolidated statistics show total sessions, total files processed, success rates, average processing time per session, and total AI token usage across all sessions
4. **Given** concurrent session processing, **When** system resources are limited, **Then** processing proceeds sequentially or with controlled parallelism without failures

---

### Edge Cases

- What happens when a screenshot file is corrupted or unreadable (invalid format, 0 bytes)?
- What happens when a file triplet is incomplete (missing screenshot, HTML, or metadata)?
- What happens when sequence numbers are non-contiguous (001, 002, 005) or duplicated?
- How does the system handle extremely large screenshots (>10MB) or very long HTML files (>1MB)?
- What happens when AI returns malformed JSON or fails to extract any meaningful data?
- How does the system handle session folders with no files or empty folders?
- What happens when file names don't follow the expected pattern (missing sequence number prefix)?
- How does the system behave when AI rate limits are hit or API calls timeout?
- What happens with very simple pages (no forms, minimal content) versus complex multi-section pages?
- How are screenshots with non-English text or special characters handled in fact extraction?
- What happens when Redis connection is lost during session claim or master lock operations?
- How does the system handle Redis lock expiration if processing takes longer than expected?
- What happens when a backend crashes while holding a master folder lock?
- How are orphaned sessions handled if a backend fails mid-processing?
- What happens when two backends simultaneously attempt to claim the same session from the queue?
- How does the system handle AI similarity scoring failures during page matching?
- What happens when embeddings index becomes corrupted or out of sync with master folder contents?
- How are conflicting prompt merges resolved when AI matching produces ambiguous results?
- What happens when a session contains pages from multiple websites (cross-site navigation)?
- How does the system handle master folder storage limits or quota exhaustion?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST accept session folders where each folder is identified by a unique session GUID
- **FR-002**: System MUST recognize file triplets using sequence number prefixes (001-, 002-, 003-, etc.)
- **FR-003**: System MUST process each triplet by pairing screenshot files (.png, .jpg) with corresponding HTML files (.html) and metadata files (.json) based on matching sequence numbers
- **FR-004**: System MUST use AI vision models to analyze screenshot content and extract visual characteristics
- **FR-005**: System MUST generate fact files (.facts.json) for each processed triplet containing:
  - visual_headings: Array of main headings/titles visible on the page (up to 5)
  - visual_sections: Array describing visual layout sections (header, content, sidebar, footer)
  - form_elements: Object with has_forms boolean, visible_fields array, and buttons array
  - layout_pattern: String describing overall layout pattern
  - content_keywords: Array of 3-5 key descriptive terms about page content/purpose
- **FR-006**: System MUST generate JSON schema files (.schema.json) for each processed triplet containing comprehensive field definitions with bracketed notation format [Required/Optional: type - description, constraints]
- **FR-007**: System MUST map all visible editable form elements to appropriate data types (string, email, phone, date, datetime, number, boolean, array, file, object)
- **FR-008**: System MUST identify required versus optional fields based on visual indicators (asterisks, "required" labels, validation hints)
- **FR-009**: System MUST extract validation constraints visible on forms (character limits, format patterns, value ranges, allowed file types)
- **FR-010**: System MUST detect enumerated options from dropdowns, radio buttons, and select menus and format as "One of: option1|option2|option3"
- **FR-011**: System MUST organize related fields into logical nested structures using objects and arrays for repeating elements
- **FR-012**: System MUST include metadata annotations (_description, _required, _sensitive, _arrayDescription, _minItems, _maxItems) in schema files
- **FR-013**: System MUST exclude non-editable elements from schemas (buttons, links, static labels, disabled fields, display-only elements, navigation controls)
- **FR-014**: System MUST maintain sequence order when processing file triplets within a session
- **FR-015**: System MUST save fact files and schema files in the same session folder as their source files
- **FR-016**: System MUST log all AI operations including prompt content, model used, response time, token usage, and costs
- **FR-017**: System MUST track processing statistics including success counts, failure counts, success rates, and average processing times
- **FR-018**: System MUST handle processing failures gracefully by logging errors with context (operation, input snapshot, system state) and continuing with remaining files
- **FR-019**: System MUST validate file paths to prevent path traversal attacks and sanitize all file operations
- **FR-020**: System MUST enforce file size limits to prevent resource exhaustion (maximum file sizes per type)
- **FR-021**: System MUST verify file types match expectations before processing (validate image formats, JSON structure, HTML validity)
- **FR-022**: System MUST use Redis for session queue management to ensure ordered, exclusive session selection by backend processes
- **FR-023**: System MUST claim sessions atomically from Redis queue in FIFO order based on upload timestamp to prevent duplicate processing
- **FR-024**: System MUST acquire Redis-based locks on master folders before writing to prevent concurrent update conflicts from multiple backends
- **FR-025**: System MUST release Redis locks on master folders after write operations complete or if processing fails
- **FR-026**: System MUST support both local development (Redis via Docker) and production deployment (distributed Redis) without code changes
- **FR-027**: System MUST perform within-session page matching using AI similarity scoring on fact files to identify duplicate pages captured at different form-filling stages
- **FR-028**: System MUST merge prompt files for pages identified as duplicates within a session based on AI fact matching
- **FR-029**: System MUST maintain a page embeddings index in master folders for fast similarity search when matching session pages to existing master pages
- **FR-030**: System MUST update master embeddings index when new pages are added or existing page facts change
- **FR-031**: System MUST merge session page prompts with matching master pages using the embeddings index for cross-session page identification
- **FR-032**: System MUST support simple overwrite merge strategy for MVP with extensibility for advanced merge algorithms in future iterations
- **FR-033**: System MUST generate a single combined prompt file per website master after all page-level merges are complete
- **FR-034**: System MUST handle task-specific sessions (e.g., citizenship form vs work visa) that share pages from the same website without data loss

### Key Entities

- **Session**: Task-specific browser extension recording session (e.g., "citizenship form" or "work visa" task) identified by GUID. Contains multiple page captures organized as numbered file triplets. Sessions for different tasks may visit same website pages. Session is the top-level container for all related files.
- **File Triplet**: A set of three related files sharing a sequence number prefix: screenshot (visual capture), HTML (page source), and metadata (browser context). Each triplet represents one webpage snapshot during form-filling. Multiple triplets may capture the same page at different stages.
- **Fact File**: AI-generated JSON output containing page identification characteristics extracted from screenshot analysis. Includes visual headings, layout patterns, form element detection, and content keywords. Used for AI similarity-based page matching within sessions and to master.
- **Prompt File**: AI-generated JSON output (formerly called "Schema File") containing comprehensive form field definitions with type annotations, validation rules, and metadata using bracketed notation format. Multiple prompt files for same page (identified via fact matching) are merged together.
- **Master Folder**: Website-specific repository containing merged, deduplicated page data accumulated across multiple task-based sessions. One master folder per website. Contains page embeddings index, merged prompt files, and final combined prompt output.
- **Page Embeddings Index**: AI-generated vector representations of page fact files stored in master folder. Enables fast similarity search for cross-session page matching. Updated incrementally as new pages are added or facts change.
- **Processing Result**: Outcome of processing a file triplet, including success/failure status, generated output file paths, token usage, processing duration, and any error information.
- **Redis Session Queue**: Ordered queue of pending sessions (sorted by upload timestamp) ensuring FIFO processing and exclusive selection by backend processes to prevent duplicate work.
- **Redis Master Lock**: Distributed lock on master folder write operations preventing concurrent updates from multiple backends. Acquired before master merge, released after completion or failure.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: System successfully processes 95% or more of well-formed file triplets (complete screenshot, HTML, metadata sets with correct naming)
- **SC-002**: Fact file generation completes within 10 seconds per page on average (including AI API call latency)
- **SC-003**: Schema file generation completes within 15 seconds per page on average (larger prompts for comprehensive schema extraction)
- **SC-004**: Generated fact files contain meaningful data in 90% or more of cases (non-empty visual_headings, valid form_elements detection, identified layout_pattern)
- **SC-005**: Generated schema files correctly identify 85% or more of visible editable form fields (validated against manual inspection)
- **SC-006**: System correctly distinguishes required from optional fields with 80% or more accuracy based on visual indicators
- **SC-007**: Enumerated field options (dropdowns, radio buttons) are extracted with 90% or more accuracy matching visible options
- **SC-008**: System processes entire sessions (10-50 file triplets) without memory exhaustion or crashes
- **SC-009**: Processing errors include sufficient context for troubleshooting (file path, operation attempted, error details) in 100% of cases
- **SC-010**: System completes batch processing of 5 sessions (50 total file triplets) within 10 minutes
- **SC-011**: AI token usage stays within budget constraints (average 2000 tokens per fact extraction, 4000 tokens per schema extraction)
- **SC-012**: File operation failures (corrupted files, missing files) are detected and reported without terminating entire session processing
- **SC-013**: Multiple backend processes can concurrently claim and process different sessions without conflicts or duplicate processing (validated through concurrent load testing)
- **SC-014**: Redis-based session queue ensures strict FIFO ordering with zero out-of-order processing occurrences
- **SC-015**: Master folder write operations succeed without data corruption when multiple backends process sessions for the same website (zero lost updates)
- **SC-016**: Within-session page matching achieves 85% or more accuracy identifying duplicate pages captured at different form-filling stages
- **SC-017**: Cross-session page matching using embeddings index achieves 80% or more accuracy matching pages across different task sessions
- **SC-018**: Master embeddings index updates complete within 5 seconds per new/modified page
- **SC-019**: System transitions seamlessly between local (Docker Redis) and production (distributed Redis) environments with zero code changes

## Assumptions

- Browser extension creates session folders with GUIDs following a consistent format
- File naming follows strict convention: `###-descriptive-name.extension` where ### is a zero-padded 3-digit sequence number
- Each triplet contains exactly three files: one screenshot (.png or .jpg), one HTML (.html), and one metadata (.json)
- Multiple triplets may represent the same page captured at different stages during form-filling process
- Screenshots are high-quality captures suitable for AI vision analysis (minimum 800x600 resolution)
- HTML files contain actual page source code, not empty or partial content
- Metadata JSON files contain valid JSON structure with session context information and website identifier
- AI vision models are capable of extracting text and visual elements from screenshots
- AI embeddings service can generate vector representations from fact files for similarity matching
- AI API endpoints are available and responsive with predictable latency (< 5 seconds typical)
- Processing occurs server-side by one or more backend processes, not in browser extension
- Multiple backend processes may run concurrently for horizontal scaling
- Network connectivity to AI API services and Redis is stable and reliable
- Cloud storage (S3 or similar) is used for session and master folders with eventual consistency acceptable
- Redis server is available for session queue and distributed locking (local Docker or production managed service)
- Redis lock TTL is configurable and sufficient for typical session processing duration
- File storage is persistent and accessible for reading uploaded sessions and writing generated outputs
- System has sufficient compute resources to handle AI API calls and file I/O operations concurrently
- AI providers support vision-capable models for screenshot analysis
- Token usage and costs are tracked per-operation for budget management and monitoring
- Sessions are task-specific (e.g., "citizenship form" task) and may share pages with other task sessions for same website
- One master folder exists per website, accumulating data across all task-based sessions
- Simple overwrite merge strategy is acceptable for MVP with future extensibility for advanced algorithms
- No real-time processing requirement - batch/asynchronous processing is acceptable
- Session processing order by upload timestamp is acceptable (no complex priority schemes required)

## Dependencies

- AI vision API service (Anthropic Claude, OpenAI GPT-4 Vision, Google Gemini, or similar) for screenshot analysis
- AI embeddings service for generating page fact vector representations and similarity scoring
- Redis server for session queue management and distributed locking (Docker container for local development, managed service for production)
- Cloud storage service (S3 or similar) for session folders and master folders with support for large file operations
- Structured logging infrastructure for observability
- Image processing capabilities for loading and encoding screenshots
- JSON parsing and validation for metadata files and AI responses
- Error handling and retry logic for AI API interactions and Redis operations

## Out of Scope

- Browser extension implementation (file capture and upload)
- User interface for submitting sessions or viewing results
- Real-time processing or streaming results
- Session management database or storage optimization
- User authentication or authorization
- Multi-tenancy or user isolation
- Advanced merge algorithms beyond simple overwrite (deferred to future iterations)
- Conflict resolution UI for ambiguous page matches
- Page matching algorithm implementation details (algorithm selection deferred to planning phase)
- Form filling automation using generated prompt files
- Deployment infrastructure or CI/CD pipelines
- Redis cluster setup and configuration
- Cloud storage provisioning and configuration
- Performance tuning or load testing beyond basic validation
- Cost optimization strategies for AI API usage
- Migration from existing systems or backward compatibility
- Redis failure recovery and high availability configuration
- Embeddings index optimization or compression strategies
- Master folder archival or retention policies
