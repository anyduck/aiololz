import asyncio
import base64
import logging
import re
from http.cookies import Morsel
from typing import Optional
import aiohttp

import lxml.etree
from aiohttp import ClientSession
from bs4 import BeautifulSoup
from yarl import URL

from .retry import retry
from .solver import AbstractSolver

logger = logging.getLogger(__name__)

class CaptchaNotFoundError(Exception):
    pass

class CaptchaAnswerError(Exception):
    pass

class ContestUnavailableError(Exception):
    pass


class Worker:

    MOVING_CAPTCHA_RE = re.compile(r"sid: '(.+?)'.*url: '(.+?)'", re.DOTALL)
    CLICK_CAPTCHA_RE = re.compile(r'dotSize = (\d+);.*?imgData = "(.+?)";', re.DOTALL)
    CAPTCHA_WRONG_HASH = hash('Вы не прошли проверку CAPTCHA должным '
                              'образом. Пожалуйста, попробуйте ещё раз.')

    def __init__(self, base_url: URL, client: ClientSession, solver: AbstractSolver):
        self._base_url = base_url
        self._client = client
        self._solver = solver

    async def close(self) -> None:
        await self._client.close()

    def _make_url(self, path: str) -> URL:
        return self._base_url.join(URL(path))

    def _update_cookie(self, name: str, value: Optional[str]) -> None:
        """ . """

        cookie = Morsel()
        if value is not None:
            cookie.set(name, value, value)
        else:
            cookie['max-age'] = -1
        self._client.cookie_jar.update_cookies({name: cookie}, self._base_url)

    def _is_cookie_expired(self, name: str) -> bool:
        """ Checks that this cookie is not present in the client. """

        return all(c.key != name for c in self._client.cookie_jar)

    async def renew_df_id_cookie(self):
        """ Parses and updates the df_id cookie. """

        # Removes the old df_id to trigger script appearance
        self._update_cookie('df_id', None)

        async with self._client.get(self._base_url) as resp:
            if m := re.search(r'<script src="(.+?)">', await resp.text()):
                process_url = self._make_url(m.group(1))
            else:
                raise Exception('process script url not found')

        async with self._client.get(process_url) as resp:
            if m := re.search(r" _0x\w+=\['(.+?)'\];", await resp.text()):
                encoded_array = m.group(1).replace("'+'", "").split("','")
            else:
                raise Exception('array with df_id not found')

        df_id: str = ''
        for encoded in encoded_array:
            decoded = str(base64.b64decode(encoded), 'utf-8')
            df_id = decoded if is_md5(decoded) else df_id
        if not df_id:
            raise Exception('df_id value not found')

        self._update_cookie('df_id', df_id)

    async def get_contests_urls(self) -> list[URL]:
        """ Returns the URLs of the contests. """

        rss_url = self._make_url('forums/contests/index.rss')
        async with self._client.get(rss_url) as resp:
            logger.debug('Response from %s: %s', rss_url, await resp.read())
            root = lxml.etree.XML(await resp.read())
        urls = root.xpath('/rss/channel/item/link/text()')
        return list(map(URL, urls))

    @retry(CaptchaAnswerError, tries=-1, delay=1)
    async def participate_in_contest(self, thread_url: URL):
        """ Joins contest by given thread url. """

        # TODO - add referer header
        async with self._client.get(thread_url) as resp:
            resp = await resp.text()
        try:
            csrf, c_hash, c_image, c_grid = self._get_contest_data(resp)
        except CaptchaNotFoundError:
            raise ContestUnavailableError('Captcha not found')

        x, y = self._solver.solve(c_image, c_grid)
        if (x is None) or (y is None) or (x == 0 and y == 0):
            raise CaptchaAnswerError(f'Response from solver: {x, y}')

        logger.debug('Response from solver: (%d, %d)', x, y)

        resp = await self._send_participate(thread_url, csrf, c_hash, x, y)
        if 'error' in resp:
            if hash(resp['error'][0]) == self.CAPTCHA_WRONG_HASH:
                raise CaptchaAnswerError('Got wrong answer from solver')
            raise ContestUnavailableError(f'Contest is unavailable: {resp["error"][0]}')

    def _get_contest_data(self, html: str) -> tuple[str, str, str, int, str]:
        """ Scrapes data needed for joining contest. """

        soup = BeautifulSoup(html, 'lxml')
        try:
            csrf = soup.find('input', {'name': '_xfToken'})['value']
        except TypeError:
            logger.error(html)
            raise

        if tag := soup.find('input', {'name': 'captcha_hash'}):
            c_hash = tag['value']
        else:
            raise CaptchaNotFoundError('Captcha hash not found')

        captcha = soup.find('div', {'class': 'captchaBlock'}).script
        if m := self.CLICK_CAPTCHA_RE.search(captcha.string):
            c_grid = int(m.group(1))
            c_image = m.group(2)
        else:
            raise CaptchaNotFoundError('Captcha image not found')

        return csrf, c_hash, c_image, c_grid

    async def _send_participate(self, thread_url: URL, csrf: str, c_hash: str, x, y) -> dict:
        """ Send participate POST request with given data. """

        headers = {
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Referer': str(thread_url),
            'X-Ajax-Referer': str(thread_url),
            'X-Requested-With': 'XMLHttpRequest',
        }
        data = {
            'captcha_hash': c_hash,
            'captcha_type': 'ClickCaptcha',
            'x': x, 'y': y,
            '_xfRequestUri': thread_url.path,
            '_xfNoRedirect': '1',
            '_xfToken': csrf,
            '_xfResponseType': 'json',
        }

        join_url = thread_url / 'participate'
        async with self._client.post(join_url, data=data, headers=headers) as resp:
            logger.debug('Response from %s: %s', join_url, await resp.text())
            return await resp.json()

    async def start_working(self, delay=60, max_delay=3600, backoff=2) -> None:
        _delay = delay

        if self._is_cookie_expired('df_id'):
            await self.renew_df_id_cookie()
        if self._is_cookie_expired('xf_user'):
            raise RuntimeError('Credentials expired')
        try:
            while True:
                count_participated = 0
                try:
                    urls = await self.get_contests_urls()
                except (aiohttp.ClientConnectionError, aiohttp.ClientResponseError, asyncio.TimeoutError) as e:
                    logger.error('Connetion error %s', e)
                    urls: list[URL] = list()
                logger.info('Parsed %d url(s)', len(urls))
                for url in urls:
                    try:
                        await self.participate_in_contest(url)
                        logger.info('Participated in %s', url.human_repr())
                        count_participated += 1
                    except ContestUnavailableError:
                        logger.info('Skipped contest %s', url.human_repr())
                    except (aiohttp.ClientConnectionError, aiohttp.ClientResponseError, asyncio.TimeoutError) as e:
                        logger.error('Connetion error %s', e)
                        break
                _delay = delay if count_participated else _delay * backoff
                if max_delay is not None:
                    _delay = min(_delay, max_delay)
                logger.info(f'Waiting for %d m', _delay // 60)
                await asyncio.sleep(_delay)
        except asyncio.CancelledError:
            return logger.debug('Task cancelled')


def is_md5(string: str) -> bool:
    """ Check if string is valid md5 hash. """

    try:
        int(string, 16)
    except ValueError:
        return False
    return len(string) == 32
