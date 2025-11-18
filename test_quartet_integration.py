#!/usr/bin/env python3
"""Integration test for quartet processor with real session files.

This script processes a real session using the quartet_processor to verify
the implementation works end-to-end with actual files.
"""

import asyncio
import json
from pathlib import Path
from uuid import UUID

from src.models.session import FileQuartet
from src.services.pipeline.quartet_processor import process_quartet


async def main() -> None:
    """Run quartet processor integration test."""
    # Session details
    session_id = UUID("eab3d762-e1aa-425e-a13c-fa37c2ea4645")

    # Use relative paths for security (storage layer requires paths starting with sessions/)
    base_path = f"sessions/{session_id}"

    # Create FileQuartet for sequence 001
    quartet_001 = FileQuartet(
        sequence_number=1,
        screenshot_path=f"{base_path}/001-session_1763417342931_113181906_capture-2025-11-17T22-09-02-931Z-ai-capture-start.png",
        html_path=f"{base_path}/001-session_1763417342931_113181906_capture-2025-11-17T22-09-02-931Z-ai-capture-start.html",
        metadata_path=f"{base_path}/001-session_1763417342931_113181906_capture-2025-11-17T22-09-02-931Z-ai-capture-start.json",
        scraped_facts_path=f"{base_path}/001-session_1763417342931_113181906_capture-2025-11-17T22-09-02-931Z-ai-capture-start_scraped_facts.txt",
    )

    print(f"🔄 Processing quartet 001 from session {session_id}...")
    print(f"   Screenshot: {Path(quartet_001.screenshot_path).name}")
    print(f"   HTML: {Path(quartet_001.html_path).name}")
    print(f"   Metadata: {Path(quartet_001.metadata_path).name}")
    print(f"   Scraped Facts: {Path(quartet_001.scraped_facts_path).name}")
    print()

    # Note: Files have been copied to this project's storage location
    # and scraped_facts.txt has been converted to .json format

    try:
        result = await process_quartet(session_id, quartet_001)

        if result.success:
            print("✅ Quartet processing succeeded!")
            print(f"   Duration: {result.duration_ms:.2f}ms")
            print(f"   Schema file: {result.schema_file_path}")
            print(f"   AI tokens: {result.ai_metrics.total_tokens if result.ai_metrics else 'N/A'}")
            print(f"   Schema sections: {result.metadata.get('schema_sections_count', 'N/A')}")
        else:
            print("❌ Quartet processing failed!")
            print(f"   Error type: {result.error_type}")
            print(f"   Error message: {result.error_message}")

    except Exception as e:
        print(f"❌ Exception during processing: {type(e).__name__}")
        print(f"   Message: {str(e)}")


if __name__ == "__main__":
    asyncio.run(main())
