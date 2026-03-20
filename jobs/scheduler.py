import asyncio

# Background job scheduler (skeleton)
# TODO: Integrate with reminders and periodic tasks

class Scheduler:
    def __init__(self):
        self.tasks = []

    def add_task(self, coro, interval):
        self.tasks.append((coro, interval))

    async def start(self):
        for coro, interval in self.tasks:
            asyncio.create_task(self._run_periodic(coro, interval))

    async def _run_periodic(self, coro, interval):
        while True:
            await coro()
            await asyncio.sleep(interval)
