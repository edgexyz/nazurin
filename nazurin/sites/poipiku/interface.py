import re

from nazurin.models import Document
from nazurin.sites import HandlerResult

from .api import Poipiku
from .config import COLLECTION

patterns = [
    # https://poipiku.com/14835419/13697781.html
    r"(?:^|(?:https?:)?//|[\s,])poipiku\.com/(\d+)/(\d+)(?:\.html)?(?:$|[?#,\s])",
    # https://poipiku.com/IllustViewPcV.jsp?ID=14835419&TD=13697781
    # https://poipiku.com/IllustViewV.jsp?ID=14835419&TD=13697781
    (
        r"(?:^|(?:https?:)?//|[\s,])poipiku\.com/Illust(?:View|Detail)(?:Pc)?V\.jsp"
        r"(?=\?(?:[^#,\s]*&)?ID=(\d+)(?:$|[&#,\s]))"
        r"(?=\?(?:[^#,\s]*&)?TD=(\d+)(?:$|[&#,\s]))"
    ),
]


async def handle(match: re.Match) -> HandlerResult:
    user_id = match.group(1)
    post_id = match.group(2)
    illust = await Poipiku().fetch(user_id, post_id)
    document = Document(id=illust.id, collection=COLLECTION, data=illust.metadata)
    return illust, document
