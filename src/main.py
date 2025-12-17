"""Main entry point for WebForms File Processor service.

Provides CLI and service entry points for processing browser extension sessions.
"""

import asyncio
from pathlib import Path
from typing import Annotated
from uuid import UUID

import typer
from dotenv import load_dotenv

from src.lib.logging import configure_logging, get_logger
from src.services.coordination import enqueue_session
from src.services.orchestrator import process_next_session, process_session

# Load environment variables from .env file in project root
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

app = typer.Typer(help="WebForms File Processor - AI-powered session analysis")

logger = get_logger(__name__)


@app.command()
def process(
    session_id: Annotated[
        str, typer.Argument(help="Session UUID to process")
    ],
    limit: Annotated[
        int | None,
        typer.Option(
            "--limit", "-l",
            help="Limit number of quartets to process (for debugging)"
        ),
    ] = None,
    debug_dir: Annotated[
        Path | None,
        typer.Option(
            "--debug-dir", "-d",
            help="Directory to write page matching debug files"
        ),
    ] = None,
) -> None:
    """Process a specific session by UUID.

    Example:
        python -m src.main process 550e8400-e29b-41d4-a716-446655440000
        python -m src.main process 550e8400-e29b-41d4-a716-446655440000 --limit 1
        python -m src.main process 550e8400-e29b-41d4-a716-446655440000 --debug-dir ./debug
    """
    configure_logging()

    logger.info(
        "cli_process_session",
        session_id=session_id,
        quartet_limit=limit,
        debug_dir=str(debug_dir) if debug_dir else None,
    )

    try:
        uuid = UUID(session_id)
        result = asyncio.run(process_session(uuid, quartet_limit=limit, debug_dir=debug_dir))

        typer.echo("\n✅ Session processed successfully!")
        typer.echo(f"   Quartets: {result.quartets_processed}")
        typer.echo(f"   Success: {result.success_count}")
        typer.echo(f"   Failed: {result.failure_count}")
        typer.echo(f"   Success Rate: {result.success_rate():.1f}%")
        typer.echo(f"   Duration: {result.total_duration_ms/1000:.2f}s")
        typer.echo(f"   Total Tokens: {result.total_tokens:,}")

    except ValueError as e:
        typer.echo(f"❌ Invalid UUID: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"❌ Processing failed: {e}", err=True)
        logger.error("cli_process_failed", error=str(e), exc_info=True)
        raise typer.Exit(1)


@app.command()
def worker() -> None:
    """Run as continuous worker, processing sessions from queue.

    Example:
        python -m src.main worker
    """
    configure_logging()

    logger.info("worker_starting")
    typer.echo("🚀 Worker started - processing sessions from queue")
    typer.echo("   Press Ctrl+C to stop")

    async def worker_loop() -> None:
        """Continuous worker loop."""
        while True:
            try:
                result = await process_next_session()

                if result:
                    typer.echo(
                        f"\n✅ Session {result.session_id} complete "
                        f"({result.success_count}/{result.quartets_processed} quartets success)"
                    )
                else:
                    # Queue empty, wait before trying again
                    await asyncio.sleep(5)

            except KeyboardInterrupt:
                logger.info("worker_stopping", reason="KeyboardInterrupt")
                typer.echo("\n👋 Worker stopped")
                break
            except Exception as e:
                logger.error("worker_error", error=str(e), exc_info=True)
                typer.echo(f"⚠️  Error: {e}", err=True)
                await asyncio.sleep(10)  # Wait before retry

    try:
        asyncio.run(worker_loop())
    except KeyboardInterrupt:
        typer.echo("\n👋 Worker stopped")


@app.command()
def enqueue(
    session_id: Annotated[str, typer.Argument(help="Session UUID to enqueue")],
    timestamp: Annotated[
        float,
        typer.Option(help="Upload timestamp (UNIX timestamp)"),
    ] = None,
) -> None:
    """Add a session to the processing queue.

    Example:
        python -m src.main enqueue 550e8400-e29b-41d4-a716-446655440000
    """
    configure_logging()

    import time

    if timestamp is None:
        timestamp = time.time()

    try:
        uuid = UUID(session_id)

        async def enqueue_async() -> bool:
            return await enqueue_session(uuid, timestamp)

        added = asyncio.run(enqueue_async())

        if added:
            typer.echo(f"✅ Session {session_id} added to queue")
        else:
            typer.echo(f"⚠️  Session {session_id} already in queue")

    except ValueError as e:
        typer.echo(f"❌ Invalid UUID: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"❌ Failed to enqueue: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def merge(
    session_id: Annotated[
        str, typer.Argument(help="Session UUID to merge schemas for")
    ],
    form_threshold: Annotated[
        float,
        typer.Option(
            "--form-threshold", "-f",
            help="Form similarity threshold (0.0-1.0) - are pages from same form?"
        ),
    ] = 0.8,
    page_threshold: Annotated[
        float,
        typer.Option(
            "--page-threshold", "-p",
            help="Page similarity threshold (0.0-1.0) - are pages the same within form?"
        ),
    ] = 0.5,
    debug_dir: Annotated[
        Path | None,
        typer.Option(
            "--debug-dir", "-d",
            help="Directory to write page matching debug files"
        ),
    ] = None,
) -> None:
    """Merge schemas within a session by two-stage page similarity.

    Two-stage matching:
    1. Form Similarity: Are these pages from the same multi-page form?
       (Based on URL, page_headings, structure, navigation)
    2. Page Similarity: Are these the same page within that form?
       (Based on form_headings - section titles unique to each page)

    Pages match if they pass BOTH thresholds.

    Example:
        python -m src.main merge 550e8400-e29b-41d4-a716-446655440000
        python -m src.main merge 550e8400-e29b-41d4-a716-446655440000 --form-threshold 0.9
        python -m src.main merge 550e8400-e29b-41d4-a716-446655440000 --page-threshold 0.6
        python -m src.main merge 550e8400-e29b-41d4-a716-446655440000 --debug-dir ./debug
    """
    from src.services.pipeline.session_merger import merge_session_schemas

    configure_logging()

    logger.info(
        "cli_merge_session",
        session_id=session_id,
        form_threshold=form_threshold,
        page_threshold=page_threshold,
        debug_dir=str(debug_dir) if debug_dir else None,
    )

    try:
        uuid = UUID(session_id)
        result = asyncio.run(
            merge_session_schemas(
                uuid,
                form_similarity_threshold=form_threshold,
                page_similarity_threshold=page_threshold,
                debug_dir=debug_dir,
            )
        )

        if result.success:
            typer.echo("\n✅ Session schemas merged successfully!")
            metadata = result.metadata or {}
            typer.echo(f"   Source schemas: {metadata.get('source_schema_count', 0)}")
            typer.echo(f"   Page groups: {metadata.get('page_groups_count', 0)}")
            typer.echo(f"   Merged saved: {metadata.get('merged_schemas_saved', 0)}")
            typer.echo(f"   Duration: {result.duration_ms/1000:.2f}s")
            if debug_dir:
                typer.echo(f"   Debug output: {debug_dir}")
        else:
            typer.echo(f"❌ Merge failed: {result.error_message}", err=True)
            raise typer.Exit(1)

    except ValueError as e:
        typer.echo(f"❌ Invalid UUID: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"❌ Merge failed: {e}", err=True)
        logger.error("cli_merge_failed", error=str(e), exc_info=True)
        raise typer.Exit(1)


@app.command()
def version() -> None:
    """Show version information."""
    typer.echo("WebForms File Processor v0.1.0")
    typer.echo("AI-powered browser extension session analysis")


if __name__ == "__main__":
    app()
