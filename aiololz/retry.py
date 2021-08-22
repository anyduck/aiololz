import asyncio
import functools
import logging


# def decorator(caller):
#     """ Turns caller into a decorator.
#     Unlike decorator module, function signature is not preserved.
#     :param caller: caller(f, *args, **kwargs)
#     """
#     def decor(f):
#         @functools.wraps(f)
#         def wrapper(*args, **kwargs):
#             return caller(f, *args, **kwargs)
#         return wrapper
#     return decor

logger = logging.getLogger(__name__)


async def __retry_internal(func, exceptions=Exception, tries=-1,
                           delay=0, max_delay=None, backoff=1):
    """
    Executes a function and retries it if it failed.

    :param func: the function to execute.
    :param exceptions: an exception or a tuple of exceptions to catch. default: Exception.
    :param tries: the maximum number of attempts. default: -1 (infinite).
    :param delay: initial delay between attempts. default: 0.
    :param max_delay: the maximum value of delay. default: None (no limit).
    :param backoff: multiplier applied to delay between attempts. default: 1 (no backoff).
    :returns: the result of the f function.
    """
    _tries, _delay = tries, delay
    while _tries:
        try:
            return await func()
        except exceptions as e:
            _tries -= 1
            if not _tries:
                raise

            logger.debug('%s, retrying in %s seconds...', e, _delay)

            await asyncio.sleep(_delay)
            _delay *= backoff

            if max_delay is not None:
                _delay = min(_delay, max_delay)


# def retry(exceptions=Exception, tries=-1, delay=0, max_delay=None, backoff=1):
#     """Returns a retry decorator.

#     :param exceptions: an exception or a tuple of exceptions to catch. default: Exception.
#     :param tries: the maximum number of attempts. default: -1 (infinite).
#     :param delay: initial delay between attempts. default: 0.
#     :param max_delay: the maximum value of delay. default: None (no limit).
#     :param backoff: multiplier applied to delay between attempts. default: 1 (no backoff).
#     :returns: a retry decorator.
#     """

#     @decorator
#     async def retry_decorator(f, *fargs, **fkwargs):
#         args = fargs if fargs else list()
#         kwargs = fkwargs if fkwargs else dict()
#         return await __retry_internal(
#             functools.partial(f, *args, **kwargs),
#             exceptions, tries, delay, max_delay, backoff
#         )

#     return retry_decorator

def retry(exceptions=Exception, tries=-1, delay=0, max_delay=None, backoff=1):
    """Returns a retry decorator.

    :param exceptions: an exception or a tuple of exceptions to catch. default: Exception.
    :param tries: the maximum number of attempts. default: -1 (infinite).
    :param delay: initial delay between attempts. default: 0.
    :param max_delay: the maximum value of delay. default: None (no limit).
    :param backoff: multiplier applied to delay between attempts. default: 1 (no backoff).
    :returns: a retry decorator.
    """

    def retry_decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            return await __retry_internal(
                functools.partial(func, *args, **kwargs),
                exceptions, tries, delay, max_delay, backoff
            )
        return wrapper
    return retry_decorator
