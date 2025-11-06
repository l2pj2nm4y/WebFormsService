"""Main entry point for WebForms File Processor service.

Provides CLI and service entry points for processing browser extension sessions.
"""

import asyncio
from pathlib import Path
from uuid import UUID

import typer
from dotenv import load_dotenv
from typing_extensions import Annotated

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
) -> None:
    """Process a specific session by UUID.

    Example:
        python -m src.main process 550e8400-e29b-41d4-a716-446655440000
    """
    configure_logging()

    logger.info("cli_process_session", session_id=session_id)

    try:
        uuid = UUID(session_id)
        result = asyncio.run(process_session(uuid))

        typer.echo(f"\n✅ Session processed successfully!")
        typer.echo(f"   Triplets: {result.triplets_processed}")
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
                        f"({result.success_count}/{result.triplets_processed} success)"
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
def version() -> None:
    """Show version information."""
    typer.echo("WebForms File Processor v0.1.0")
    typer.echo("AI-powered browser extension session analysis")


if __name__ == "__main__":
    app()
