import asyncio

import pytest
from aiololz.retry import retry


@pytest.mark.asyncio
async def test_retry(monkeypatch):
    mock_sleep_time = [0]

    async def mock_sleep(seconds):
        mock_sleep_time[0] += seconds

    monkeypatch.setattr(asyncio, 'sleep', mock_sleep)

    hit = [0]

    tries = 5
    delay = 1
    backoff = 2

    @retry(tries=tries, delay=delay, backoff=backoff)
    async def f():
        hit[0] += 1
        1 / 0

    with pytest.raises(ZeroDivisionError):
        await f()
    assert hit[0] == tries
    assert mock_sleep_time[0] == sum(delay * backoff ** i for i in range(tries - 1))

@pytest.mark.asyncio
async def test_tries_inf():
    hit = [0]
    target = 10

    @retry(tries=float('inf'))
    async def f():
        hit[0] += 1
        if hit[0] == target:
            return target
        else:
            raise ValueError
    assert await f() == target

@pytest.mark.asyncio
async def test_tries_minus1():
    hit = [0]
    target = 10

    @retry(tries=-1)
    async def f():
        hit[0] += 1
        if hit[0] == target:
            return target
        else:
            raise ValueError
    assert await f() == target

@pytest.mark.asyncio
async def test_max_delay(monkeypatch):
    mock_sleep_time = [0]

    async def mock_sleep(seconds):
        mock_sleep_time[0] += seconds

    monkeypatch.setattr(asyncio, 'sleep', mock_sleep)

    hit = [0]

    tries = 5
    delay = 1
    backoff = 2
    max_delay = delay  # Never increase delay

    @retry(tries=tries, delay=delay, max_delay=max_delay, backoff=backoff)
    async def f():
        hit[0] += 1
        1 / 0

    with pytest.raises(ZeroDivisionError):
        await f()
    assert hit[0] == tries
    assert mock_sleep_time[0] == delay * (tries - 1)
