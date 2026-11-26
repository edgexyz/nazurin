import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import aiofiles.os
import aiohttp
from PIL import Image as PILImage

from nazurin.models import Illust, Image
from nazurin.utils import Request
from nazurin.utils.decorators import async_wrap

from . import config

if TYPE_CHECKING:
    from nazurin.utils.network import NazurinRequestSession

FORMAT_EXTENSIONS: ClassVar[dict[str, str]] = {
    "JPEG": ".jpg",
    "PNG": ".png",
    "WEBP": ".webp",
    "GIF": ".gif",
}


def get_cookies() -> dict[str, str]:
    if config.SESSION:
        return {"xfolio_session": config.SESSION}
    return {}


@async_wrap
def detect_image_extension(path: str | os.PathLike) -> str | None:
    try:
        with PILImage.open(path) as image:
            return FORMAT_EXTENSIONS.get(image.format or "")
    except OSError:
        return None


class XfolioRequest(Request):
    def __init__(self, referers: dict[str, str] | None = None, **kwargs):
        super().__init__(**kwargs)
        self._referers = referers or {}

    def get(self, url, **kwargs):
        referer = self._referers.get(str(url))
        if referer:
            headers = {"Referer": referer, **(kwargs.get("headers") or {})}
            kwargs["headers"] = headers
        return super().get(url, **kwargs)


@dataclass
class XfolioImage(Image):
    referer: str | None = None

    async def size(self, **kwargs):
        headers = dict(kwargs.pop("headers", None) or {})
        if self.referer:
            headers.setdefault("Referer", self.referer)
        cookies = {**get_cookies(), **(kwargs.pop("cookies", None) or {})}
        return await super().size(headers=headers, cookies=cookies, **kwargs)

    async def download(self, session: aiohttp.ClientSession):
        await super().download(session)
        real_ext = await detect_image_extension(self.path)
        stem, current_ext = os.path.splitext(self.name)
        if real_ext and real_ext.lower() != current_ext.lower():
            old_path = self.path
            self.name = stem + real_ext
            if await aiofiles.os.path.exists(old_path):
                await aiofiles.os.replace(old_path, self.path)


@dataclass
class XfolioIllust(Illust):
    async def download(
        self,
        *,
        request_class: "type[NazurinRequestSession]" = XfolioRequest,
        **kwargs,
    ):
        cookies = {**get_cookies(), **(kwargs.pop("cookies", None) or {})}
        if issubclass(request_class, XfolioRequest):
            referers = {
                file.url: file.referer
                for file in self.all_files
                if isinstance(file, XfolioImage) and file.url and file.referer
            }
            kwargs.setdefault("referers", referers)
        await super().download(
            request_class=request_class,
            cookies=cookies,
            **kwargs,
        )
