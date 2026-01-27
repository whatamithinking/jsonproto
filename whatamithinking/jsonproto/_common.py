from typing import (
    TypeVar,
    Literal,
    get_args,
    get_origin,
    Mapping,
    Any,
    Callable,
    Union,
    ClassVar,
    TYPE_CHECKING,
    Iterable,
    Iterator,
    Self,
)
from collections import deque
from types import MappingProxyType

from lru import LRU

if TYPE_CHECKING:
    from ._constraints import T_ConstraintType, T_ConstraintId

__all__ = ["Empty"]


class EmptyMeta(type):
    def __repr__(cls):
        return "<Empty>"

    def __bool__(cls):
        return False


class Empty(metaclass=EmptyMeta): ...


T = TypeVar("T")
T_Key = TypeVar("T_Key")
T_Value = TypeVar("T_Value")
ExtrasMode = Literal["forbid", "roundtrip", "drop"]
TypeHandlerFormat = Literal["json", "unstruct", "struct"]
ResolvedTypeHint = type
UnresolvedTypeHint = type
StringTypeHint = str
FuzzyTypeHint = ResolvedTypeHint | UnresolvedTypeHint | StringTypeHint
TypeHintValue = Any | Empty
CodecSerializationFormat = Literal["jsonstr", "jsonbytes", "binstream", "textstream"]
CodecFormat = CodecSerializationFormat | TypeHandlerFormat
IsTypeCallback = Callable[[ResolvedTypeHint], bool]
JsonScalarType = float | int | bool | str | None
JsonArrayType = list[Union[JsonScalarType, "JsonArrayType", "JsonObjectType"]]
JsonObjectType = dict[str, Union[JsonScalarType, "JsonArrayType", "JsonObjectType"]]
JsonType = JsonScalarType | JsonArrayType | JsonObjectType


class Metadata(Mapping):
    __slots__ = "_mapping", "_hash", "_len"

    def __init__(self, *args, **kwargs) -> None:
        self._mapping = dict(*args, **kwargs)

    def __iter__(self) -> Iterator:
        return iter(self._mapping)

    def __len__(self) -> int:
        try:
            return self._len
        except AttributeError:
            self._len = len(self._mapping)
            return self._len

    def __getitem__(self, key):
        return self._mapping[key]

    def __hash__(self) -> int:
        try:
            return self._hash
        except AttributeError:
            self._hash = hash(tuple(sorted(self._mapping.items())))
            return self._hash


def identity(value: T) -> T:
    return value


class _ConstraintCache(type):
    _cache: dict[type["BaseConstraint"], dict[Any, "BaseConstraint"]] = {}

    def __call__(cls, *args, **kwargs):
        key = make_cache_key(args=args, kwargs=kwargs)
        try:
            instance = cls._cache[cls][key]
        except KeyError:
            cls._cache.setdefault(cls, {})[key] = instance = super().__call__(
                *args, **kwargs
            )
        return instance


class BaseConstraint(metaclass=_ConstraintCache):
    constraint_type: ClassVar["T_ConstraintType"]
    constraint_id: ClassVar["T_ConstraintId"]


class Constraints:
    __slots__ = "_mapping", "_hash", "_values"
    empty: "Constraints" = None

    def __new__(cls, constraints: Iterable[BaseConstraint] | None = None) -> Self:
        if not constraints:
            raise ValueError("Use Constraints.empty instead")
        self = super().__new__(cls)
        self._mapping: dict["T_ConstraintId", BaseConstraint | deque[BaseConstraint]] = {}  # type: ignore
        self._extend(constraints)
        return self

    def __repr__(self) -> str:
        return f"Constraints({list(self)!r})"

    def __hash__(self) -> int:
        try:
            return self._hash
        except AttributeError:
            self._hash = hash(tuple(sorted(self._mapping.items())))
            return self._hash

    def __bool__(self) -> bool:
        return bool(self._mapping)

    def _build_values(self) -> list[BaseConstraint]:
        self._values = []
        append = self._values.append
        extend = self._values.extend
        for value in self._mapping.values():
            if value.__class__ is deque:
                extend(value)
            else:
                append(value)
        return self._values

    def __iter__(self) -> Iterator[BaseConstraint]:
        try:
            return iter(self._values)
        except AttributeError:
            return iter(self._build_values())

    def __reversed__(self) -> Iterator[BaseConstraint]:
        try:
            return reversed(self._values)
        except AttributeError:
            return reversed(self._build_values())

    def get(
        self, constraint_id: "T_ConstraintId", default: T = None
    ) -> BaseConstraint | deque[BaseConstraint] | T:
        return self._mapping.get(constraint_id, default)

    def append(self, constraint: BaseConstraint) -> None:
        match constraint.constraint_id:
            # handle constraints we allow multiple instances of
            case "example":
                try:
                    self._mapping[constraint.constraint_id].append(constraint)
                except KeyError:
                    self._mapping[constraint.constraint_id] = deque((constraint,))
            # handle constraints we allow just one instance of, with latest always taking precedence
            case _:
                self._mapping[constraint.constraint_id] = constraint
                # can only allow one or the other, either static default or a default factory, but not both
                if constraint.constraint_id == "default":
                    self._mapping.pop("default_factory", None)
                elif constraint.constraint_id == "default_factory":
                    self._mapping.pop("default", None)

    def _extend(self, constraints: Iterable[BaseConstraint]) -> None:
        for constraint in constraints:
            self.append(constraint)

    def extendleft(self, constraints: Iterable[BaseConstraint]) -> None:
        for constraint in constraints:
            # if constraint already in mapping current value should take precedence over these prepend values
            if constraint.constraint_id in self._mapping:
                continue
            self.append(constraint)


class _EmptyConstraints(Constraints):
    _hash = hash(())
    _iter = iter(())

    def __bool__(self):
        return False

    def __iter__(self):
        return self._iter

    def __reversed__(self):
        return self._iter

    def get(self, constraint_id, default=None):
        return default


Constraints.empty = object.__new__(_EmptyConstraints)


def get_alias(name: str):
    parts = name.split("_")
    return f"{parts[0].lower()}{''.join(map(str.title, parts[1:]))}"


_empty_annotations = MappingProxyType({})


def get_annotations(obj: type):
    if isinstance(obj, type):
        try:
            return type.__dict__["__annotations__"].__get__(obj)
        except AttributeError:
            return _empty_annotations
    else:
        return getattr(obj, "__annotations__", _empty_annotations)


_get_origin_cache = LRU(1024)


def cached_get_origin(tp: type) -> type | None:
    try:
        return _get_origin_cache[tp]
    except KeyError:
        _get_origin_cache[tp] = result = get_origin(tp)
        return result


_get_args_cache = LRU(1024)


def cached_get_args(tp: type) -> tuple:
    try:
        return _get_args_cache[tp]
    except KeyError:
        _get_args_cache[tp] = result = get_args(tp)
        return result


# shameless copy from functools
class _HashedSeq(list):
    """This class guarantees that hash() will be called no more than once
    per element.  This is important because the lru_cache() will hash
    the key multiple times on a cache miss.

    """

    __slots__ = "hashvalue"

    def __init__(self, tup, hash=hash):
        self[:] = tup
        self.hashvalue = hash(tup)

    def __hash__(self):
        return self.hashvalue


# shameless copy from functools
def make_cache_key(
    args=(),
    kwargs=None,
    kwd_mark=(object(),),
    fasttypes={int, str},
    tuple=tuple,
    type=type,
    len=len,
):
    key = args
    if kwargs:
        key += (kwd_mark,) + tuple(kwargs.items())
    if len(key) == 1 and key[0].__class__ in fasttypes:
        return key[0]
    elif key:
        return _HashedSeq(key)
    return key
