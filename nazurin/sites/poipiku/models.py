from dataclasses import dataclass

from nazurin.models import Illust, Image

from . import config

REFERER = "https://poipiku.com/"


def get_cookies() -> dict[str, str]:
    cookies = {"POIPIKU_CONTENTS_VIEW_MODE": "1"}
    if config.TOKEN:
        cookies["POIPIKU_LK"] = config.TOKEN
    return cookies


@dataclass
class PoipikuImage(Image):
    referer: str = REFERER

    async def size(self, **kwargs):
        headers = {"Referer": self.referer, **(kwargs.pop("headers", None) or {})}
        return await super().size(headers=headers, **kwargs)


@dataclass
class PoipikuIllust(Illust):
    referer: str = REFERER

    async def download(self, **kwargs):
        headers = {"Referer": self.referer, **(kwargs.pop("headers", None) or {})}
        await super().download(headers=headers, **kwargs)
