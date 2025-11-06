# Pipeline Stage Contracts

**Feature**: Browser Extension File Processing System
**Date**: 2025-01-06
**Purpose**: Define internal contracts for processing pipeline stages

## Overview

The processing pipeline follows constitution Principle V: Ingest → Analyze → Transform → Validate → Output

**Pipeline Stages**:
1. **Triplet Processing**: Process individual file triplets (fact + prompt extraction)
2. **Session Merging**: Merge prompts within session using AI similarity
3. **Master Merging**: Merge session to master using embeddings index
4. **Combined Generation**: Generate final combined prompt per website

**Key Principles**:
- Each stage has defined input/output contracts
- Stages are independently testable
- Error handling at stage boundaries
- Logging and observability at transitions
- Stages are composable and reusable

## Stage 1: Triplet Processing

**Purpose**: Process one file triplet (screenshot, HTML, metadata) to generate fact and prompt files

### Input Contract

```python
class TripletProcessingInput(BaseModel):
    """Input for triplet processing stage"""
    session_id: UUID = Field(..., description="Parent session ID")
    sequence_number: int = Field(..., ge=1, le=999, description="Triplet sequence number")
    screenshot_path: str = Field(..., description="Path to screenshot file")
    html_path: str = Field(..., description="Path to HTML file")
    metadata_path: str = Field(..., description="Path to metadata file")
```

### Output Contract

```python
class TripletProcessingOutput(BaseModel):
    """Output from triplet processing stage"""
    session_id: UUID
    sequence_number: int

    # Generated outputs
    fact_file: FactFile = Field(..., description="Extracted page facts")
    prompt_file: PromptFile = Field(..., description="Generated prompt schema")
    fact_file_path: str = Field(..., description="Path where fact file was written")
    prompt_file_path: str = Field(..., description="Path where prompt file was written")

    # Processing metrics
    processing_result: ProcessingResult = Field(..., description="Metrics and status")
```

### Processing Logic

```python
async def process_triplet(input: TripletProcessingInput) -> TripletProcessingOutput:
    """
    Process a single file triplet.

    Pipeline:
        1. Load files from storage (screenshot, HTML, metadata)
        2. Validate files (size, type, format)
        3. Extract facts using AI vision
        4. Generate prompt using AI vision
        5. Write fact and prompt files to storage
        6. Return results with metrics

    Raises:
        ValidationError: Invalid input files
        StorageError: File I/O failures
        AIOperationError: AI processing failures
    """
    start_time = datetime.utcnow()

    try:
        # Step 1: Load files
        screenshot_bytes = await storage.read_screenshot(input.session_id, input.sequence_number)
        html_content = await storage.read_html(input.session_id, input.sequence_number)
        metadata = await storage.read_metadata(input.session_id, input.sequence_number)

        # Step 2: Extract facts
        fact_start = datetime.utcnow()
        fact_file = await ai_service.extract_facts(
            screenshot_base64=base64.b64encode(screenshot_bytes).decode(),
            screenshot_format="png",  # or from metadata
            page_url=metadata.get("url", "unknown")
        )
        fact_latency = (datetime.utcnow() - fact_start).total_seconds() * 1000

        # Step 3: Generate prompt
        prompt_start = datetime.utcnow()
        prompt_file = await ai_service.generate_prompt(
            screenshot_base64=base64.b64encode(screenshot_bytes).decode(),
            screenshot_format="png",
            html_snippet=html_content[:5000],  # First 5000 chars for context
            fact_file=fact_file
        )
        prompt_latency = (datetime.utcnow() - prompt_start).total_seconds() * 1000

        # Step 4: Write outputs
        fact_path = await storage.write_fact_file(input.session_id, input.sequence_number, fact_file)
        prompt_path = await storage.write_prompt_file(input.session_id, input.sequence_number, prompt_file)

        # Step 5: Build result
        total_duration = (datetime.utcnow() - start_time).total_seconds() * 1000

        processing_result = ProcessingResult(
            triplet_sequence=input.sequence_number,
            session_id=input.session_id,
            success=True,
            fact_file_path=fact_path,
            prompt_file_path=prompt_path,
            processing_duration_ms=int(total_duration),
            ai_fact_latency_ms=int(fact_latency),
            ai_prompt_latency_ms=int(prompt_latency),
            ai_tokens_used=fact_file.ai_tokens + prompt_file.ai_tokens,  # If tracked
            started_at=start_time,
            completed_at=datetime.utcnow()
        )

        return TripletProcessingOutput(
            session_id=input.session_id,
            sequence_number=input.sequence_number,
            fact_file=fact_file,
            prompt_file=prompt_file,
            fact_file_path=fact_path,
            prompt_file_path=prompt_path,
            processing_result=processing_result
        )

    except Exception as e:
        # Build error result
        total_duration = (datetime.utcnow() - start_time).total_seconds() * 1000

        processing_result = ProcessingResult(
            triplet_sequence=input.sequence_number,
            session_id=input.session_id,
            success=False,
            error_message=str(e),
            error_context={"input": input.model_dump(), "stage": "triplet_processing"},
            processing_duration_ms=int(total_duration),
            started_at=start_time,
            completed_at=datetime.utcnow()
        )

        logger.error("triplet_processing_failed", **processing_result.model_dump())
        raise
```

### Test Contract

```python
async def test_triplet_processing():
    """Contract test: Triplet processing produces valid outputs"""
    input_data = TripletProcessingInput(
        session_id=test_session_id,
        sequence_number=1,
        screenshot_path="sessions/test/001-screenshot.png",
        html_path="sessions/test/001-page.html",
        metadata_path="sessions/test/001-metadata.json"
    )

    output = await process_triplet(input_data)

    assert output.session_id == test_session_id
    assert output.sequence_number == 1
    assert isinstance(output.fact_file, FactFile)
    assert isinstance(output.prompt_file, PromptFile)
    assert output.processing_result.success is True
    assert output.processing_result.processing_duration_ms > 0
```

## Stage 2: Session Merging

**Purpose**: Merge prompts within session by identifying duplicate pages using AI similarity on facts

### Input Contract

```python
class SessionMergingInput(BaseModel):
    """Input for session merging stage"""
    session_id: UUID = Field(..., description="Session to merge")
    triplet_outputs: List[TripletProcessingOutput] = Field(..., description="All triplet processing results")
    similarity_threshold: float = Field(default=0.85, ge=0.0, le=1.0, description="AI similarity threshold")
```

### Output Contract

```python
class PageGroup(BaseModel):
    """Group of triplets representing the same page"""
    page_hash: str = Field(..., description="Unique page identifier")
    representative_fact: FactFile = Field(..., description="Fact file representing the page")
    merged_prompt: PromptFile = Field(..., description="Merged prompt from all triplets")
    source_triplets: List[int] = Field(..., description="Sequence numbers of merged triplets")

class SessionMergingOutput(BaseModel):
    """Output from session merging stage"""
    session_id: UUID
    page_groups: List[PageGroup] = Field(..., description="Merged page groups")
    total_triplets: int = Field(..., description="Total triplets processed")
    unique_pages: int = Field(..., description="Number of unique pages identified")
    merge_duration_ms: int = Field(..., description="Merge processing time")
```

### Processing Logic

```python
async def merge_session(input: SessionMergingInput) -> SessionMergingOutput:
    """
    Merge prompts within session using AI similarity on facts.

    Pipeline:
        1. Build fact-to-prompt mapping from triplet outputs
        2. Compare all fact pairs using AI similarity scoring
        3. Group triplets by page similarity (threshold-based)
        4. Merge prompts within each page group (simple overwrite for MVP)
        5. Assign unique page hash to each group
        6. Return merged page groups

    Algorithm:
        - Start with each triplet as separate group
        - Compare facts pairwise
        - Merge groups if similarity >= threshold
        - Continue until no more merges possible (stable)
    """
    start_time = datetime.utcnow()

    # Step 1: Build initial groups (one per triplet)
    groups: List[List[TripletProcessingOutput]] = [[triplet] for triplet in input.triplet_outputs]

    # Step 2: Iteratively merge similar groups
    merged = True
    while merged:
        merged = False

        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                # Compare representative facts
                fact_i = groups[i][0].fact_file
                fact_j = groups[j][0].fact_file

                similarity = await ai_service.score_similarity(fact_i, fact_j)

                if similarity.similarity_score >= input.similarity_threshold:
                    # Merge group j into group i
                    groups[i].extend(groups[j])
                    groups.pop(j)
                    merged = True
                    break  # Restart comparison

            if merged:
                break

    # Step 3: Create page groups with merged prompts
    page_groups = []
    for group_triplets in groups:
        # Representative fact (from first triplet)
        representative_fact = group_triplets[0].fact_file

        # Generate page hash
        page_hash = hashlib.sha256(
            json.dumps(representative_fact.model_dump(), sort_keys=True).encode()
        ).hexdigest()[:16]

        # Merge prompts (MVP: simple overwrite with most recent)
        # Future: Advanced merge algorithms
        merged_prompt = group_triplets[-1].prompt_file  # Take last/most recent

        # Create page group
        page_group = PageGroup(
            page_hash=page_hash,
            representative_fact=representative_fact,
            merged_prompt=merged_prompt,
            source_triplets=[t.sequence_number for t in group_triplets]
        )

        page_groups.append(page_group)

    # Step 4: Build output
    duration = (datetime.utcnow() - start_time).total_seconds() * 1000

    return SessionMergingOutput(
        session_id=input.session_id,
        page_groups=page_groups,
        total_triplets=len(input.triplet_outputs),
        unique_pages=len(page_groups),
        merge_duration_ms=int(duration)
    )
```

### Test Contract

```python
async def test_session_merging():
    """Contract test: Session merging identifies duplicate pages"""
    # Create 3 triplets: 2 similar (same page), 1 different
    triplet1 = create_triplet_output(sequence=1, page_type="login")
    triplet2 = create_triplet_output(sequence=2, page_type="login")  # Same page
    triplet3 = create_triplet_output(sequence=3, page_type="registration")  # Different

    input_data = SessionMergingInput(
        session_id=test_session_id,
        triplet_outputs=[triplet1, triplet2, triplet3],
        similarity_threshold=0.85
    )

    output = await merge_session(input_data)

    # Should identify 2 unique pages (login merged, registration separate)
    assert output.unique_pages == 2
    assert output.total_triplets == 3

    # Find login page group
    login_group = [g for g in output.page_groups if len(g.source_triplets) == 2][0]
    assert set(login_group.source_triplets) == {1, 2}
```

## Stage 3: Master Merging

**Purpose**: Merge session page groups to master folder using embeddings index for cross-session matching

### Input Contract

```python
class MasterMergingInput(BaseModel):
    """Input for master merging stage"""
    session_id: UUID
    website_id: str
    page_groups: List[PageGroup] = Field(..., description="Session page groups to merge")
    similarity_threshold: float = Field(default=0.80, description="Embeddings similarity threshold")
```

### Output Contract

```python
class MasterMergingOutput(BaseModel):
    """Output from master merging stage"""
    website_id: str
    session_id: UUID
    pages_added: int = Field(..., description="New pages added to master")
    pages_updated: int = Field(..., description="Existing pages updated")
    embeddings_updated: int = Field(..., description="Embeddings index entries updated")
    merge_duration_ms: int
```

### Processing Logic

```python
async def merge_to_master(input: MasterMergingInput) -> MasterMergingOutput:
    """
    Merge session pages to master folder using embeddings index.

    Pipeline:
        1. Acquire master folder lock (Redis)
        2. Load embeddings index from master
        3. For each session page group:
           a. Generate embedding from fact file
           b. Search for similar pages in index (threshold)
           c. If match found: Update existing page (overwrite for MVP)
           d. If no match: Add as new page
        4. Update embeddings index
        5. Update master metadata (page count, last updated)
        6. Release master folder lock
        7. Return merge statistics

    CRITICAL: Must hold master lock for entire operation (FR-024, FR-025)
    """
    start_time = datetime.utcnow()
    pages_added = 0
    pages_updated = 0

    # Step 1: Acquire lock with context manager
    async with master_lock_context(input.website_id):

        # Step 2: Load embeddings index
        embeddings_index = await storage.read_embeddings_index(input.website_id)

        # Step 3: Process each page group
        for page_group in input.page_groups:
            # Generate embedding from fact file
            embedding_result = await ai_service.generate_embeddings(
                fact_file=page_group.representative_fact
            )

            # Search for similar pages
            similar_pages = embeddings_index.find_similar(
                query_embedding=embedding_result.embedding_vector,
                threshold=input.similarity_threshold,
                top_k=1  # Find best match
            )

            if similar_pages:
                # Update existing page
                existing_page_hash = similar_pages[0][0]  # (page_hash, similarity_score)

                # Overwrite prompt (MVP merge strategy)
                await storage.write_merged_prompt(
                    website_id=input.website_id,
                    page_hash=existing_page_hash,
                    prompt=page_group.merged_prompt
                )

                # Update embedding entry (new source triplets)
                for embedding in embeddings_index.embeddings:
                    if embedding.page_hash == existing_page_hash:
                        embedding.source_triplets.extend([
                            (input.session_id, seq) for seq in page_group.source_triplets
                        ])
                        embedding.embedding_vector = embedding_result.embedding_vector  # Update
                        break

                pages_updated += 1

            else:
                # Add new page
                await storage.write_merged_prompt(
                    website_id=input.website_id,
                    page_hash=page_group.page_hash,
                    prompt=page_group.merged_prompt
                )

                # Add embedding entry
                new_embedding = PageEmbedding(
                    page_hash=page_group.page_hash,
                    fact_file_hash=hashlib.sha256(
                        json.dumps(page_group.representative_fact.model_dump()).encode()
                    ).hexdigest(),
                    embedding_vector=embedding_result.embedding_vector,
                    source_triplets=[
                        (input.session_id, seq) for seq in page_group.source_triplets
                    ]
                )
                embeddings_index.embeddings.append(new_embedding)

                pages_added += 1

        # Step 4: Write updated embeddings index
        embeddings_index.last_updated = datetime.utcnow()
        await storage.write_embeddings_index(input.website_id, embeddings_index)

        # Lock automatically released by context manager

    # Step 5: Build output
    duration = (datetime.utcnow() - start_time).total_seconds() * 1000

    return MasterMergingOutput(
        website_id=input.website_id,
        session_id=input.session_id,
        pages_added=pages_added,
        pages_updated=pages_updated,
        embeddings_updated=pages_added + pages_updated,
        merge_duration_ms=int(duration)
    )
```

### Test Contract

```python
async def test_master_merging():
    """Contract test: Master merging updates embeddings and writes prompts"""
    # Create session with 2 pages
    page_groups = [
        create_page_group(page_hash="abc123", page_type="login"),
        create_page_group(page_hash="def456", page_type="registration")
    ]

    input_data = MasterMergingInput(
        session_id=test_session_id,
        website_id="test.com",
        page_groups=page_groups
    )

    output = await merge_to_master(input_data)

    # Should add 2 new pages (assuming empty master)
    assert output.pages_added == 2
    assert output.pages_updated == 0
    assert output.embeddings_updated == 2

    # Verify embeddings index was updated
    index = await storage.read_embeddings_index("test.com")
    assert len(index.embeddings) == 2
```

## Stage 4: Combined Generation

**Purpose**: Generate final combined prompt file for entire website

### Input Contract

```python
class CombinedGenerationInput(BaseModel):
    """Input for combined prompt generation"""
    website_id: str
    include_metadata: bool = Field(default=True, description="Include page metadata")
```

### Output Contract

```python
class CombinedGenerationOutput(BaseModel):
    """Output from combined generation stage"""
    website_id: str
    combined_prompt_path: str = Field(..., description="Path to combined prompt file")
    page_count: int = Field(..., description="Number of pages included")
    generation_duration_ms: int
```

### Processing Logic

```python
async def generate_combined_prompt(input: CombinedGenerationInput) -> CombinedGenerationOutput:
    """
    Generate final combined prompt for entire website.

    Pipeline:
        1. Acquire master lock
        2. List all merged prompt files in master folder
        3. Load each prompt file
        4. Combine into single structure
        5. Write combined prompt file
        6. Release lock
        7. Return result

    Combined prompt structure:
        {
            "website_id": "uscis.gov",
            "generated_at": "2025-01-06T15:00:00Z",
            "page_count": 15,
            "pages": {
                "page_hash_1": { ... prompt data ... },
                "page_hash_2": { ... prompt data ... }
            }
        }
    """
    start_time = datetime.utcnow()

    async with master_lock_context(input.website_id):
        # Step 1: List all prompt files
        prompt_files = await storage.list_files(
            prefix=f"masters/{input.website_id}/",
            pattern="*.prompt.json"
        )

        # Step 2: Load and combine prompts
        combined = {
            "website_id": input.website_id,
            "generated_at": datetime.utcnow().isoformat(),
            "page_count": len(prompt_files),
            "pages": {}
        }

        for prompt_path in prompt_files:
            # Extract page hash from filename
            page_hash = Path(prompt_path).stem.replace(".prompt", "")

            # Load prompt
            content = await storage.read_file(prompt_path)
            prompt_data = json.loads(content.decode('utf-8'))

            combined["pages"][page_hash] = prompt_data

        # Step 3: Write combined file
        combined_path = await storage.write_combined_prompt(input.website_id, combined)

    # Step 4: Build output
    duration = (datetime.utcnow() - start_time).total_seconds() * 1000

    return CombinedGenerationOutput(
        website_id=input.website_id,
        combined_prompt_path=combined_path,
        page_count=len(prompt_files),
        generation_duration_ms=int(duration)
    )
```

### Test Contract

```python
async def test_combined_generation():
    """Contract test: Combined generation creates single file with all pages"""
    # Assuming master has 3 pages
    input_data = CombinedGenerationInput(website_id="test.com")

    output = await generate_combined_prompt(input_data)

    assert output.page_count == 3
    assert output.combined_prompt_path.endswith("combined.prompt.json")

    # Verify combined file exists and has correct structure
    combined_content = await storage.read_file(output.combined_prompt_path)
    combined_data = json.loads(combined_content.decode('utf-8'))

    assert combined_data["website_id"] == "test.com"
    assert combined_data["page_count"] == 3
    assert len(combined_data["pages"]) == 3
```

## Pipeline Orchestration

**Purpose**: Orchestrate all stages for complete session processing

```python
async def process_session_pipeline(session_id: UUID) -> Dict[str, Any]:
    """
    Complete pipeline orchestration for one session.

    Pipeline flow:
        1. Claim session from Redis queue
        2. Load session metadata
        3. Process all triplets (Stage 1) - parallel execution
        4. Merge within session (Stage 2)
        5. Merge to master (Stage 3)
        6. Generate combined prompt (Stage 4)
        7. Return comprehensive results

    Returns:
        Dictionary with results from all stages
    """
    logger.info("pipeline_start", session_id=str(session_id))

    try:
        # Load session
        session = await load_session(session_id)

        # Stage 1: Process all triplets (parallel)
        triplet_inputs = [
            TripletProcessingInput(
                session_id=session_id,
                sequence_number=triplet.sequence_number,
                screenshot_path=triplet.screenshot_path,
                html_path=triplet.html_path,
                metadata_path=triplet.metadata_path
            )
            for triplet in session.triplets
        ]

        triplet_outputs = await asyncio.gather(*[
            process_triplet(input_data) for input_data in triplet_inputs
        ], return_exceptions=True)

        # Filter out failures
        successful_outputs = [o for o in triplet_outputs if isinstance(o, TripletProcessingOutput)]

        # Stage 2: Session merging
        session_merge_output = await merge_session(SessionMergingInput(
            session_id=session_id,
            triplet_outputs=successful_outputs
        ))

        # Stage 3: Master merging
        master_merge_output = await merge_to_master(MasterMergingInput(
            session_id=session_id,
            website_id=session.website_id,
            page_groups=session_merge_output.page_groups
        ))

        # Stage 4: Combined generation
        combined_output = await generate_combined_prompt(CombinedGenerationInput(
            website_id=session.website_id
        ))

        logger.info("pipeline_complete", session_id=str(session_id))

        return {
            "session_id": str(session_id),
            "triplets_processed": len(successful_outputs),
            "triplets_failed": len(triplet_outputs) - len(successful_outputs),
            "unique_pages": session_merge_output.unique_pages,
            "pages_added_to_master": master_merge_output.pages_added,
            "pages_updated_in_master": master_merge_output.pages_updated,
            "combined_prompt_path": combined_output.combined_prompt_path
        }

    except Exception as e:
        logger.error("pipeline_failed", session_id=str(session_id), error=str(e))
        raise
```

## Next Steps

1. Implement each pipeline stage with contracts
2. Write contract tests for all stages
3. Implement pipeline orchestration
4. Add comprehensive logging at stage boundaries
5. Set up metrics collection for each stage
6. Implement error recovery and retry logic
7. Create integration tests for complete pipeline
