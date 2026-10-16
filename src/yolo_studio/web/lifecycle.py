"""Creation and cleanup of the application session registry."""
import asyncio
from contextlib import asynccontextmanager
from ..engine import Sessions

@asynccontextmanager
async def lifespan(app):
    app.state.sessions = Sessions()
    async def cleanup():
        while True:
            await asyncio.sleep(15)
            await asyncio.to_thread(app.state.sessions.prune)
    task = asyncio.create_task(cleanup())
    yield
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    await asyncio.to_thread(app.state.sessions.prune, True)
