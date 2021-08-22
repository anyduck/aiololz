import asyncio
import logging
from pathlib import Path

from aiohttp import ClientSession

import config
from aiololz.solver import TensorflowSolver
from aiololz.worker import Worker

logger = logging.getLogger(__name__)


async def _main() -> None:
    solver = TensorflowSolver(Path('models', 'quantized.tflite'), 20)
    client = ClientSession(headers=config.HEADERS, raise_for_status=True)
    client.cookie_jar.update_cookies(config.COOKIES, config.BASE_URL)

    worker = Worker(config.BASE_URL, client, solver)
    try:
        await worker.start_working()
    finally:
        await worker.close()


def main() -> None:
    loop = asyncio.get_event_loop()
    task = loop.create_task(_main())
    logger.info('Start working...')
    try:
        loop.run_until_complete(task)
    except (SystemExit, KeyboardInterrupt):
        logger.info('Detected Ctrl-C: Exiting...')
    finally:
        task.cancel()
        loop.run_until_complete(asyncio.gather(task))
        loop.close()


if __name__ == '__main__':
    main()
 