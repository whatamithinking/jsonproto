from typing import Annotated, Literal, Self
import re
from urllib.parse import urlparse
import ipaddress

from ._struct import struct
from ._constraints import Value

__all__ = [
    "Port",
    "IPAddress",
    "EmptyModel",
    "Url",
    "Email",
]


Port = Annotated[int, Value("ge", 0), Value("le", 65_535)]
IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


@struct
class EmptyModel: ...


class Url(str):
    _regex = re.compile(
        r"""(?x)^https?:\\/\\/(?:www\\.)?
        [-a-zA-Z0-9@:%._\\+~#=]{1,256}
        \\.[a-zA-Z0-9()]{1,6}
        \\b(?:[-a-zA-Z0-9()@:%_
        \\+.~#?&\\/=]*)$"""
    )
    scheme: Literal["http", "https"]
    host: str
    port: int
    path: str
    query: dict[str, str]
    fragment: str

    def __new__(cls, value) -> Self:
        match = cls._regex.match(value)
        if match is None:
            raise ValueError("Value is not in valid url format.")
        parsed = urlparse(value)
        self = str.__new__(cls, value)
        self.scheme = parsed.scheme
        netlocparts = parsed.netloc.split(":")
        self.host = netlocparts[0]
        self.port = int(netlocparts[1]) if len(netlocparts) >= 2 else 80
        self.path = parsed.path
        self.query = dict(_.split("=", 1) for _ in parsed.query.split("&"))  # type: ignore
        self.fragment = parsed.fragment
        return self


class Email(str):
    regex = re.compile(
        r"""(?x)
        ^(?P<username>[a-zA-Z0-9._%+-]+)
        @(?P<domain>[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})$
        """
    )
    username: str
    domain: str

    def __new__(cls, value) -> Self:
        match = cls.regex.match(value)
        if match is None:
            raise ValueError("Value is not in valid email format.")
        self = str.__new__(cls, value)
        gdict = match.groupdict()
        self.username = gdict["username"]
        self.domain = gdict["domain"]
        return self
