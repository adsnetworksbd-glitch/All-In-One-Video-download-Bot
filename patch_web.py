with open("bot.py", "r", encoding="utf-8") as f:
    code = f.read()

web_server_code = '''
import os
from aiohttp import web

async def health_check(request):
    return web.Response(text="Bot is running and healthy!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Health check web server bound to port {port}")
'''

if "start_web_server" not in code:
    # Insert web server and start in post_init
    code = web_server_code + "\n\n" + code
    code = code.replace(
        "async def post_init(application):",
        "async def post_init(application):\n    asyncio.create_task(start_web_server())"
    )
    with open("bot.py", "w", encoding="utf-8") as f:
        f.write(code)
    print("Successfully patched bot.py with web server!")
else:
    print("Web server already present.")
