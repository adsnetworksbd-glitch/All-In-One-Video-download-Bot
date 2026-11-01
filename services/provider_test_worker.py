import asyncio, time
from database.firebase import firebase_manager
from logger import logger
from providers.http_api import GenericHttpApiAdapter

class ProviderTestWorker:
    def __init__(self): self.is_running = False

    async def start(self):
        self.is_running = True
        logger.info("ProviderTestWorker started.")
        while self.is_running:
            try: await self._process_tests()
            except Exception as e: logger.error(f"ProviderTest error: {e}")
            await asyncio.sleep(4.0)

    def stop(self): self.is_running = False

    async def _process_tests(self):
        tasks = firebase_manager.safe_get("provider_test_tasks")
        if not tasks or not isinstance(tasks, dict): return
        for task_id, task in tasks.items():
            if not isinstance(task, dict) or task.get("status") != "QUEUED": continue
            provider_id = task.get("provider_id")
            p_config = firebase_manager.safe_get(f"api_providers/{provider_id}/config") or {}
            adapter = GenericHttpApiAdapter(provider_id, p_config)
            t0 = time.time()
            check_result = await adapter.health_check()
            duration_ms = int((time.time() - t0) * 1000)
            health_payload = {
                "status": check_result.get("status", "down"),
                "checked_at": int(time.time() * 1000),
                "response_time_ms": duration_ms,
                "message": check_result.get("error") or f"HTTP {check_result.get('code', 200)}"
            }
            firebase_manager.safe_update(f"api_providers/{provider_id}/last_health_check", health_payload)
            firebase_manager.safe_update(f"provider_test_tasks/{task_id}", {
                "status": "COMPLETED", "result": health_payload, "completed_at": int(time.time() * 1000)
            })