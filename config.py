import logging.config
from pathlib import Path
from typing import Any

import yaml
import yarl


def __load(file: str) -> Any:
    with open(Path('configs', file), encoding='utf-8') as f:
        return yaml.safe_load(f.read())

BASE_URL: yarl.URL = yarl.URL('https://lolz.guru')
HEADERS: dict[str, str] = __load('headers.yaml')
COOKIES: dict[str, str] = __load('cookies.yaml')
logging.config.dictConfig(__load('logging.yaml'))
