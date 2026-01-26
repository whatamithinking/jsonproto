from typing import Protocol


class Readable(Protocol):
    def read(size: int = -1, /): ...


class Base