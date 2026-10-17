"""Creation and cleanup of the application session registry."""
import asyncio
from contextlib import asynccontextmanager
from ..engine import Sessions
from ..audio import AudioHub

@asynccontextmanager
async def lifespan(app):
    app.state.sessions = Sessions()
    app.state.audio = AudioHub()
    async def cleanup():
        while True:
            await asyncio.sleep(15)
            await asyncio.to_thread(app.state.sessions.prune)
    task = asyncio.create_task(cleanup())
    try:
        yield
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await app.state.audio.close()
        await asyncio.to_thread(app.state.sessions.prune, True)
