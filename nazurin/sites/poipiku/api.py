import os
import re
from http import HTTPStatus
from urllib.parse import urlparse

import aiohttp
from bs4 import BeautifulSoup

from nazurin.models import Caption
from nazurin.utils import Request, logger
from nazurin.utils.decorators import network_retry
from nazurin.utils.exceptions import NazurinError

from . import config
from .models import REFERER, PoipikuIllust, PoipikuImage, get_cookies

ORIGIN = "https://poipiku.com"
DETAIL_API = f"{ORIGIN}/f/ShowIllustDetailF.jsp"
APPEND_API = f"{ORIGIN}/f/ShowAppendFileF.jsp"

CDN_HOSTS = {"cdn.poipiku.com", "img.poipiku.com"}
PLACEHOLDER_PREFIXES = (
    "https://cdn.poipiku.com/img/",
    "//cdn.poipiku.com/img/",
    "https://img.poipiku.com/img/",
    "//img.poipiku.com/img/",
    "/img/",
)

DETAIL_OK = 1
DETAIL_SESSION_ERRORS = {-1, -2}
DETAIL_POIPASS_ERROR = -11

APPEND_GATE_MESSAGES: dict[int, str] = {
    -2: "Password is required or incorrect for this post",
    -3: "Login is required to view this post, please configure POIPIKU_TOKEN",
    -4: "This post is restricted to Poipiku followers",
    -5: "This post is restricted to X (Twitter) followers",
    -6: "This post is restricted by X (Twitter) follow settings",
    -7: "This post is restricted to mutual X (Twitter) followers",
    -8: "This post is restricted to an X (Twitter) list",
    -9: "This post is private",
    -11: "Poipass age verification is required to view this R18+ post",
    -20: "Retweet (RP) on X (Twitter) is required to view this post",
}

PREVIEW_SUFFIX_RE = re.compile(r"\.[A-Za-z0-9]+_640$")
BACKGROUND_URL_RE = re.compile(r"url\(['\"]?([^'\")]+)['\"]?\)")
LOGIN_STATE_RE = re.compile(r"['\"]login_state['\"]\s*:\s*['\"]([^'\"]+)['\"]")
BOOKMARK_UID_RE = re.compile(r"UpdateBookmark\(\s*(-?\d+)\s*,")
ORIGINAL_SIZE_RE = re.compile(r"(\d+)\s*x\s*(\d+)")


class Poipiku:
    @network_retry
    async def get_post(
        self,
        user_id: str | int,
        post_id: str | int,
        password: str = "",
    ) -> dict:
        """Fetch a Poipiku post and resolve its metadata and image URLs."""
        uid = int(user_id)
        pid = int(post_id)
        url = f"{ORIGIN}/{uid}/{pid}.html"

        async with Request(
            headers={"Referer": REFERER},
            cookies=get_cookies(),
        ) as session:
            async with session.get(url) as response:
                if response.status == HTTPStatus.NOT_FOUND:
                    raise NazurinError("Post not found")
                response.raise_for_status()
                html = await response.text()

            post, main_thumbs, has_append = self.parse_html(html, uid, pid, url)
            if config.TOKEN and not post["is_logged_in"]:
                logger.warning("POIPIKU_TOKEN is invalid or expired")
                raise NazurinError("POIPIKU_TOKEN is invalid or expired")

            if config.TOKEN:
                images = await self._fetch_auth_images(
                    session,
                    post,
                    password=password,
                )
            else:
                images = await self._fetch_public_images(
                    session,
                    post,
                    main_thumbs,
                    has_append=has_append,
                    password=password,
                )

            post["images"] = images
            return post

    async def fetch(
        self,
        user_id: str | int,
        post_id: str | int,
        password: str = "",
    ) -> PoipikuIllust:
        post = await self.get_post(user_id, post_id, password=password)
        imgs = self.get_images(post)
        caption = self.build_caption(post)
        return PoipikuIllust(
            int(post["id"]),
            imgs,
            caption,
            post,
            referer=post["url"],
        )

    async def _fetch_auth_images(
        self,
        session: Request,
        post: dict,
        *,
        password: str = "",
    ) -> list[dict]:
        """Fetch signed full-scale original image URLs via ShowIllustDetailF.jsp."""
        detail = await self._post_json(
            session,
            DETAIL_API,
            data={
                "ID": str(post["user"]["id"]),
                "TD": str(post["id"]),
                "AD": "-1",
                "PAS": password,
            },
            referer=post["url"],
        )
        error_code = detail.get("error_code")
        if error_code is not None:
            error_code = int(error_code)
        if error_code in DETAIL_SESSION_ERRORS:
            logger.warning("POIPIKU_TOKEN is invalid or expired")
            raise NazurinError("POIPIKU_TOKEN is invalid or expired")
        if error_code == DETAIL_POIPASS_ERROR:
            raise NazurinError(APPEND_GATE_MESSAGES[DETAIL_POIPASS_ERROR])

        if detail.get("result") != DETAIL_OK or error_code:
            append = await self._request_append(session, post, password=password)
            self._raise_append_error(append)
            raise NazurinError("Failed to fetch full-size images")

        detail_html = detail.get("html", "")
        urls = self.extract_img_urls(
            detail_html,
            selector="img.DetailIllustItemImage",
        ) or self.extract_img_urls(detail_html)
        if not urls:
            raise NazurinError("No image found")

        orig_width, orig_height = post.get("original_size") or (0, 0)
        images = []
        for index, raw_url in enumerate(urls):
            full_url = self.normalize_url(raw_url)
            parsed = urlparse(full_url)
            filename = os.path.basename(parsed.path)
            base_url = full_url.split("?", 1)[0]
            thumbnail = (
                f"{base_url}_640.jpg"
                if parsed.hostname in CDN_HOSTS and os.path.splitext(filename)[1]
                else None
            )
            images.append(
                {
                    "url": full_url,
                    "thumbnail": thumbnail,
                    "filename": filename,
                    "width": orig_width if index == 0 else 0,
                    "height": orig_height if index == 0 else 0,
                },
            )
        post["original"] = True
        return images

    async def _fetch_public_images(
        self,
        session: Request,
        post: dict,
        main_thumbs: list[str],
        *,
        has_append: bool,
        password: str = "",
    ) -> list[dict]:
        """Fetch display (_640.jpg) image URLs without login."""
        urls = list(main_thumbs)
        if not urls or has_append:
            append = await self._request_append(session, post, password=password)
            result_num = int(append.get("result_num") or 0)
            if result_num <= 0:
                self._raise_append_error(append)
            append_urls = self.extract_img_urls(
                append.get("html", ""),
                selector="img.IllustItemThumbImg",
            )
            if not append_urls:
                self._raise_append_error(append)
            urls.extend(append_urls)

        if not urls:
            raise NazurinError("No image found")

        post["original"] = False
        return [
            {
                "url": self.normalize_url(u),
                "thumbnail": None,
                "filename": os.path.basename(urlparse(u).path),
                "width": 0,
                "height": 0,
            }
            for u in urls
        ]

    async def _request_append(
        self,
        session: Request,
        post: dict,
        *,
        password: str = "",
    ) -> dict:
        return await self._post_json(
            session,
            APPEND_API,
            data={
                "UID": str(post["user"]["id"]),
                "IID": str(post["id"]),
                "PAS": password,
                "MD": "0",
                "TWF": "-1",
            },
            referer=post["url"],
        )

    @staticmethod
    async def _post_json(
        session: Request,
        api_url: str,
        *,
        data: dict[str, str],
        referer: str,
    ) -> dict:
        async with session.post(
            api_url,
            data=data,
            headers={
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Origin": ORIGIN,
                "Referer": referer,
                "X-Requested-With": "XMLHttpRequest",
            },
        ) as response:
            response.raise_for_status()
            try:
                payload = await response.json(content_type=None)
            except (ValueError, aiohttp.ContentTypeError) as error:
                raise NazurinError("Invalid response from Poipiku API") from error
            if not isinstance(payload, dict):
                raise NazurinError("Invalid response from Poipiku API")
            return payload

    @staticmethod
    def _raise_append_error(append: dict) -> None:
        result_num = int(append.get("result_num") or 0)
        if result_num in APPEND_GATE_MESSAGES:
            raise NazurinError(APPEND_GATE_MESSAGES[result_num])
        raw_html = append.get("html") or ""
        msg = BeautifulSoup(raw_html, "html.parser").get_text(" ", strip=True)
        if msg:
            raise NazurinError(msg)
        raise NazurinError("Access to this post is restricted")

    @staticmethod
    def detect_logged_in(html: str) -> bool:
        login_match = LOGIN_STATE_RE.search(html)
        if login_match:
            return login_match.group(1) != "guest"
        uid_match = BOOKMARK_UID_RE.search(html)
        if uid_match:
            return int(uid_match.group(1)) > 0
        return False

    @staticmethod
    def parse_html(
        html: str,
        user_id: int,
        post_id: int,
        url: str,
    ) -> tuple[dict, list[str], bool]:
        """Parse post metadata, visible thumbnails, and expand state from HTML."""
        is_logged_in = Poipiku.detect_logged_in(html)
        soup = BeautifulSoup(html, "html.parser")
        item = soup.select_one(f"#IllustItem_{post_id}")
        if not item:
            if config.TOKEN and not is_logged_in:
                logger.warning("POIPIKU_TOKEN is invalid or expired")
                raise NazurinError("POIPIKU_TOKEN is invalid or expired")
            raise NazurinError("Post not found")

        item_classes = set(item.get("class") or [])
        if "Text" in item_classes:
            raise NazurinError("Text post contains no images")

        cat_el = item.select_one(".IllustItemCategory a")
        category = cat_el.get_text(strip=True) if cat_el else ""

        desc_el = item.select_one(".IllustItemDesc")
        description = ""
        if desc_el:
            for br in desc_el.find_all("br"):
                br.replace_with("\n")
            description = desc_el.get_text().strip()

        tags: list[str] = []
        for tag_el in item.select(".IllustItemTag .TagName"):
            tag = tag_el.get_text(strip=True).lstrip("#")
            if tag and tag not in tags:
                tags.append(tag)

        original_size = None
        tap_el = item.select_one(".TapToFull")
        if tap_el:
            size_match = ORIGINAL_SIZE_RE.search(tap_el.get_text())
            if size_match:
                original_size = (int(size_match.group(1)), int(size_match.group(2)))

        main_thumbs = [
            src
            for img in item.select("a.IllustItemThumb img.IllustItemThumbImg")
            if (src := img.get("src")) and not Poipiku.is_placeholder(src)
        ]
        has_append = bool(
            item.select_one('[onclick*="ShowAppendFile"]'),
        )

        user = Poipiku.parse_user(soup, item, user_id)
        post = {
            "id": post_id,
            "url": url,
            "category": category,
            "description": description,
            "tags": tags,
            "user": user,
            "original": False,
            "original_size": original_size,
            "is_logged_in": is_logged_in,
        }
        return post, main_thumbs, has_append

    @staticmethod
    def parse_user(soup: BeautifulSoup, item: BeautifulSoup, user_id: int) -> dict:
        """Extract creator metadata from post page DOM."""
        user_url = f"{ORIGIN}/{user_id}/"
        name_el = soup.select_one(".UserInfoUserName a") or item.select_one(
            ".IllustItemUserName a",
        )
        name = name_el.get_text(strip=True) if name_el else str(user_id)

        profile = ""
        profile_el = soup.select_one(".UserInfoProfile")
        if profile_el:
            for br in profile_el.find_all("br"):
                br.replace_with("\n")
            profile = profile_el.get_text().strip()

        avatar = ""
        thumb_el = soup.select_one(".UserInfoUserThumb") or item.select_one(
            ".IllustItemUserThumb",
        )
        if thumb_el and thumb_el.get("style"):
            bg_match = BACKGROUND_URL_RE.search(thumb_el["style"])
            if bg_match:
                avatar = Poipiku.normalize_url(bg_match.group(1))

        posts_num = 0
        num_el = soup.select_one(".UserInfoState .UserInfoStateItemNum")
        if num_el:
            num_text = num_el.get_text(strip=True).replace(",", "")
            if num_text.isdigit():
                posts_num = int(num_text)

        follow_el = item.select_one(".UserInfoCmdFollow") or soup.select_one(
            ".UserInfo .UserInfoCmdFollow",
        )
        is_following = bool(
            follow_el and "Selected" in (follow_el.get("class") or []),
        )

        return {
            "id": user_id,
            "name": name,
            "profile": profile,
            "avatar": avatar,
            "url": user_url,
            "posts_num": posts_num,
            "is_following": is_following,
        }

    @staticmethod
    def extract_img_urls(html: str, selector: str = "img") -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        return [
            src
            for img in soup.select(selector)
            if (src := img.get("src"))
            and "Twemoji" not in (img.get("class") or [])
            and not Poipiku.is_placeholder(src)
        ]

    @staticmethod
    def is_placeholder(src: str) -> bool:
        return src.startswith(PLACEHOLDER_PREFIXES)

    @staticmethod
    def normalize_url(url: str) -> str:
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("/"):
            return ORIGIN + url
        return url

    @staticmethod
    def get_images(post: dict) -> list[PoipikuImage]:
        """Build PoipikuImage list from parsed post data."""
        images = post.get("images", [])
        if not images:
            raise NazurinError("No image found")

        imgs = []
        for index, img in enumerate(images):
            destination, filename = Poipiku.get_storage_dest(post, img, index)
            imgs.append(
                PoipikuImage(
                    filename,
                    img["url"],
                    destination,
                    thumbnail=img.get("thumbnail"),
                    width=img.get("width", 0),
                    height=img.get("height", 0),
                    referer=post["url"],
                ),
            )
        return imgs

    @staticmethod
    def get_storage_dest(
        post: dict,
        img: dict,
        index: int = 0,
    ) -> tuple[str, str]:
        """Format destination and filename."""
        stem, extension = os.path.splitext(img["filename"])
        clean_filename = PREVIEW_SUFFIX_RE.sub("", stem)
        context = {
            **post,
            # Original filename stem without preview suffix or extension
            "filename": clean_filename,
            "extension": extension,
            "index": index,
        }
        return (
            config.DESTINATION.format_map(context),
            config.FILENAME.format_map(context) + extension,
        )

    @staticmethod
    def build_caption(post: dict) -> Caption:
        user = post["user"]
        tags = post.get("tags", [])
        tag_string = " ".join(["#" + tag for tag in tags])
        return Caption(
            {
                "author": f"{user['name']} #{user['id']}",
                "category": post.get("category", ""),
                "url": post["url"],
                "text": post.get("description", ""),
                "tags": tag_string,
            },
        )
