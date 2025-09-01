from typing import (
    TypeVar,
    dataclass_transform,
    Callable,
    Protocol,
    ClassVar,
    Optional,
    Self,
    Any,
    TypeIs,
    Iterable,
    ParamSpec,
    Annotated,
    Literal,
)
from types import (
    FunctionType,
    MappingProxyType,
    new_class
)
import sys

from lru import LRU

from ._common import (
    MISSING,
    get_annotations,
    Constraints,
    BaseConstraint,
    cached_get_origin,
    cached_get_args,
    T_FuzzyTypeHint,
)

__all__ = [
    "StructProto",
    "is_struct_class",
    "is_struct_instance",
    "field",
    "FrozenInstanceError",
    "get_fields",
    "get_setted",
    "get_unsetted",
    "get_required",
    "get_optional",
    "get_computed",
    "set_extras",
    "get_extras",
    "get_constraints",
    "struct",
    "create_struct",
]

T = TypeVar("T")
P = ParamSpec("P")
_POST_INIT = "_post_init_"
_PARAMS = "_params_"
_FIELDS = "_fields_"
_COMPUTED = "_computed_"
_CONSTRAINTS = "_constraints_"
_SETTED = "_setted_"
_EXTRAS = "_extras_"
_FROZEN_HASH = "_frozen_hash_"
_FROZEN_REPR = "_frozen_repr_"
_CLASS_ATTRS_DEFAULTS = {
    _PARAMS: None,
    _FIELDS: None,
    _COMPUTED: None,
    _CONSTRAINTS: None,
}
_INSTANCE_ATTRS = (
    _SETTED,
    _EXTRAS,
    _FROZEN_HASH,
    _FROZEN_REPR,
)


T_FieldName = str
T_FieldValue = Any


class StructProto(Protocol):
    """Represents the structure of a struct for use in type hints.

    All fields are private implementation details and may change over time.
    Either use this class or use the functions present in this module to determine
    if something is a struct, but do not rely on any of this private info remaining
    the same in the future.
    """

    _fields_: ClassVar[dict[T_FieldName, "field"]]
    _setted_: ClassVar[set[T_FieldName]]
    _computed_: Optional[set[T_FieldName]]
    _post_init_: Optional[Callable[[Any], None]]
    _constraints_: Optional[tuple["BaseConstraint"]]
    _params_: Optional[tuple[str]]
    _extras_: Optional[dict]


class FrozenInstanceError(AttributeError):
    pass


class field:
    # NOTE: tested using slots but it slows down setting all the field values, requiring
    # a ton of setattr calls slowing down initial model creation
    name = None
    type_hint = None
    default = MISSING
    default_factory = MISSING
    slots = False
    init = False
    repr = False
    hash = False
    order = False
    eq = False
    frozen = False
    kw_only = False
    constraints: Constraints = Constraints.empty
    fget = None
    is_computed = False
    is_cached = None

    def __init__(self, fget=None, /, *, cache=None):
        if fget is not None:
            self.fget = fget
            self.is_computed = True
        if cache is not None:
            self.is_cached = cache

    @property
    def is_required(self):
        return (
            not self.is_computed
            and self.default is MISSING
            and self.default_factory is MISSING
        )

    def __repr__(self):
        return (
            f"{self.__class__.__name__}("
            f"name={self.name!r},"
            f"type_hint={self.type_hint!r},"
            f"slots={self.slots!r},"
            f"init={self.init!r},"
            f"repr={self.repr!r},"
            f"eq={self.eq!r},"
            f"order={self.order!r},"
            f"frozen={self.frozen!r},"
            f"kw_only={self.kw_only!r},"
            f"hash={self.hash!r},"
            f"default={self.default!r},"
            f"default_factory={self.default_factory!r},"
            f"is_computed={self.is_computed!r},"
            f"constraints={self.constraints!r},"
            f"is_cached={self.is_cached!r}"
            ")"
        )

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name
        if setname := getattr(self.fget, "__set_name__", None):
            setname(owner, name)
        if (computed := getattr(owner, _COMPUTED, None)) is None:
            computed = set()
            setattr(owner, _COMPUTED, computed)
        computed.add(name)

    def __get__(self, instance: Any, owner: type | None = None, /) -> Any:
        if instance is None:
            return self
        if callable(self.fget):
            value = self.fget(instance)
        # this handles case where this is used as a decorator on top of a property
        # or maybe another arbitrary descriptor
        else:
            value = self.fget.__get__(instance)
        # if cached, we can bypass this Field descriptor entirely next time
        # the field instance will still be referenced by the _FIELDS attr of the class
        # same trick used by functools.cached_property to reduce runtime overhead
        if self.is_cached:
            object.__setattr__(instance, self.name, value)
        return value

    def __call__(self, obj: Any) -> Self:
        # this is called when @field used as decorator with arguments, such as
        # @field(cached=True), in which case the Field object is created but then
        # because this is a decorator the Field object is called itself and must act like a dec
        self.fget = obj
        self.is_computed = True
        return self


# TODO: comb through these helper functions and think through how they are used, if caching can be used, do we need them, etc.
# decide when to use function internally vs copying code

# OPTIMIZATION: skip isinstance check to determine if instance or class
# and use separate function depending on caller context. fine for internal
# use in hot paths since the input type is usually known


def is_struct_instance(obj) -> TypeIs[StructProto]:
    return is_struct_class(obj.__class__)


_is_struct_class_cache = LRU(2048)


def is_struct_class(cls) -> TypeIs[StructProto]:
    try:
        return _is_struct_class_cache[cls]
    except KeyError:
        _is_struct_class_cache[cls] = result = hasattr(cls, _FIELDS)
        return result


_empty_fields: MappingProxyType = MappingProxyType({})


def get_fields(obj: type[StructProto] | StructProto) -> MappingProxyType[str, "field"]:
    """Return a mapping of field name and Field object.

    Accepts a model or an instance of one.
    """
    try:
        return MappingProxyType(getattr(obj, _FIELDS))
    except AttributeError:
        return _empty_fields


def get_names(obj: type[StructProto] | StructProto) -> tuple[str]:
    """Return a collection of the field names"""
    return tuple(get_fields(obj))


_empty_computed = frozenset()


def get_computed(obj: type[StructProto] | StructProto) -> frozenset[str]:
    """Return a set of field names on the model which are computed"""
    try:
        result = getattr(obj, _COMPUTED)
    except (
        AttributeError,
        TypeError,
    ):  # not set unless there is at least one computed field on regular class
        return _empty_computed
    else:
        if result is None:  # slotted class has this set to None by default
            return _empty_computed
        return frozenset(result)


def get_required(obj: type[StructProto] | StructProto) -> frozenset[str]:
    """Return a set of field names on the model which are required
    (i.e. their values must be given on init)"""
    return frozenset(
        name for name, field in get_fields(obj).items() if field.is_required
    )


def get_optional(obj: type[StructProto] | StructProto) -> frozenset[str]:
    """Return a set of field names on the model which are optional
    (i.e. they have default values or are computed so they dont have to be given on init)
    """
    return frozenset(
        name for name, field in get_fields(obj).items() if not field.is_required
    )


_default_setted = frozenset()


def get_setted(obj: StructProto) -> frozenset[str]:
    """Return set of field names which were set in the model constructor."""
    try:
        return frozenset(getattr(obj, _SETTED))
    except AttributeError:
        return _default_setted


def get_unsetted(obj: StructProto) -> frozenset[str]:
    """Return set of field names which were not set in the model constructor."""
    return frozenset(getattr(obj, _FIELDS).keys() - get_setted(obj))


def set_extras(obj: StructProto, extras: dict) -> None:
    object.__setattr__(obj, _EXTRAS, extras)


_extra_empty: MappingProxyType = MappingProxyType({})


def get_extras(obj: StructProto) -> MappingProxyType:
    try:
        # extras not present a lot of the time so fallback to empty instead of using AttributeError
        # to cut down on exception handling costs
        return MappingProxyType(getattr(obj, _EXTRAS, _extra_empty))
    except AttributeError:
        return _extra_empty


def get_constraints(obj) -> Constraints:
    try:
        result = getattr(obj, _CONSTRAINTS)
    except AttributeError:  # regular class, constraints attr not set unless defined
        return Constraints.empty
    else:
        if result is None:  # slotted class has this set to None by default
            return Constraints.empty
        return result


def __replace__(self, **changes):
    # we exclude fields which were unset in the original model unless they
    # are part of the changes so the new one does not look like every field
    # was initialized with a value from the caller
    changes.update(
        dict(
            (name, getattr(self, name)) for name in (get_setted(self) - changes.keys())
        )
    )
    return self.__class__(**changes)


# cls is a global which is passed in when model defined. used to freeze setting anything
# on that class instance, not just field names. this "resets" when it is subclassed and instead
# only applies the constraint to the fields
def __frozen_setattr__(self, name, value):
    if self.__class__ is cls or name in getattr(self, _FIELDS):  # type: ignore
        raise FrozenInstanceError(f"cannot assign to field {name!r}")
    return super(cls, self).__setattr__(name, value)  # type: ignore


def __frozen_delattr__(self, name):
    if self.__class__ is cls or name in getattr(self, _FIELDS):  # type: ignore
        raise FrozenInstanceError(f"cannot delete field {name!r}")
    return super(cls, self).__delattr__(name)  # type: ignore


def __getitem__(self, name):
    try:
        result = self.__dict__[name]
    except KeyError:
        raise KeyError(
            f"Item, {name}, is not a valid field name for this struct."
        ) from None
    else:
        if name not in getattr(self, _FIELDS):
            raise KeyError(f"Item, {name}, is not a valid field name for this struct.")
        return result


def __setitem__(self, name, value):
    if name not in getattr(self, _FIELDS):
        raise KeyError(f"Item, {name}, is not a valid field name for this struct.")
    self.__dict__[name] = value


class _LazyDescriptor:
    __slots__ = ("name", "method", "args")

    def __init__(self, name: str, method: str, args: tuple = ()) -> None:
        self.name = name
        self.method = method
        self.args = args

    def __get__(self, instance, owner):
        model_gen, params = owner.__dict__[_PARAMS]
        getattr(model_gen, self.method)(owner, *(self.args + params))
        if instance is None:
            return owner.__dict__[self.name]
        else:
            return getattr(instance, self.name)


_lazy_fields = _LazyDescriptor(_FIELDS, "_create_fields")
_lazy_eq = _LazyDescriptor("__eq__", "_create_comparator", ("__eq__",))
_lazy_gt = _LazyDescriptor("__gt__", "_create_comparator", ("__gt__",))
_lazy_ge = _LazyDescriptor("__ge__", "_create_comparator", ("__ge__",))
_lazy_le = _LazyDescriptor("__le__", "_create_comparator", ("__le__",))
_lazy_lt = _LazyDescriptor("__lt__", "_create_comparator", ("__lt__",))
_lazy_repr = _LazyDescriptor("__repr__", "_create_repr")
_lazy_frozen_setattr = _LazyDescriptor("__setattr__", "_create_frozen")
_lazy_frozen_delattr = _LazyDescriptor("__delattr__", "_create_frozen")
_lazy_hash = _LazyDescriptor("__hash__", "_create_hash")
_lazy_init = _LazyDescriptor("__init__", "_create_init")
_lazy_replace = _LazyDescriptor("__replace__", "_create_replace")


class StructGenerator:
    # NOTE: skipping getstate/setstate as not needed presently
    _comparators = {
        "__eq__": "==",
        "__gt__": ">",
        "__ge__": ">=",
        "__le__": "<=",
        "__lt__": "<",
    }

    def __init__(self) -> None:
        self._cache_init_exact: dict[
            tuple[type, tuple[str], tuple, tuple, bool], FunctionType
        ] = {}
        self._cache_init: dict[tuple[int, bool, bool, bool], FunctionType] = {}
        self._cache_repr_exact: dict[tuple[tuple[str], bool], FunctionType] = {}
        self._cache_repr: dict[tuple[int, bool], FunctionType] = {}
        self._cache_hash_exact: dict[tuple[tuple[str], bool], FunctionType] = {}
        self._cache_hash: dict[tuple[int, bool], FunctionType] = {}
        self._cache_cmp_exact: dict[tuple[str, tuple[str]], FunctionType] = {}
        self._cache_cmp: dict[tuple[str, int], FunctionType] = {}

    def _create_fields(
        self,
        cls,
        init: bool,
        repr: bool,
        eq: bool,
        order: bool,
        frozen: bool,
        kw_only: bool,
        hash: bool,
        replace: bool,
        slots: bool,
        getitem: bool,
        setitem: bool,
    ) -> dict[str, field]:
        fields_dict = {}
        for k in cls.__mro__[-1:0:-1]:
            if k_fields := get_fields(k):
                fields_dict.update(k_fields)

        common_field_attrs = dict(
            init=init,
            repr=repr,
            eq=eq,
            order=order,
            frozen=frozen,
            kw_only=kw_only,
            hash=hash,
            slots=slots,
        )

        cls_dict_get = cls.__dict__.get

        # pickup fields defined as attributes on the class
        for fn, type_hint in get_annotations(cls).items():
            field_attrs = common_field_attrs.copy()
            field_attrs.update(
                {
                    "name": fn,
                    "type_hint": type_hint,
                    "default": cls_dict_get(fn, MISSING),
                }
            )
            constraints = Constraints.empty
            if cached_get_origin(type_hint) is Annotated:
                args = cached_get_args(type_hint)
                field_attrs["type_hint"] = type_hint = args[0]
                constraints_args = [
                    arg for arg in args[1:] if hasattr(arg, "constraint_type")
                ]
                if constraints_args:
                    constraints = Constraints(constraints_args)
                    if field_attrs.get("default", MISSING) is MISSING:
                        if (
                            default := constraints.get("default", MISSING)
                        ) is not MISSING:
                            field_attrs["default"] = default.value
                        if (
                            default_factory := constraints.get(
                                "default_factory", MISSING
                            )
                        ) is not MISSING:
                            field_attrs["default_factory"] = default_factory.value
            field_attrs["constraints"] = constraints
            f = field()
            f.__dict__.update(field_attrs)
            fields_dict[fn] = f

        # update each of the computed fields with the settings for the model
        for fn in getattr(cls, _COMPUTED, ()):
            f = cls_dict_get(fn)
            is_cached = f.is_cached
            if frozen and f.is_cached is None:
                is_cached = True
            type_hint = get_annotations(f.fget).get("return")
            if not type_hint:
                raise TypeError(
                    f"computed field, {fn!r}, missing return type hint in model, {cls!r}"
                )
            constraints = Constraints.empty
            if cached_get_origin(type_hint) is Annotated:
                args = cached_get_args(type_hint)
                type_hint = args[0]
                constraints_args = [
                    arg for arg in args[1:] if hasattr(arg, "constraint_type")
                ]
                if constraints_args:
                    constraints = Constraints(constraints_args)
            f.__dict__.update(common_field_attrs)
            f.__dict__.update(
                dict(
                    name=fn,
                    is_cached=is_cached,
                    type_hint=type_hint,
                    constraints=constraints,
                )
            )
            fields_dict[fn] = f

        setattr(cls, _FIELDS, fields_dict)
        return fields_dict

    def _create_comparator(
        self,
        cls,
        op: Literal["__eq__", "__gt__", "__ge__", "__le__", "__lt__"],
        init: bool,
        repr: bool,
        eq: bool,
        order: bool,
        frozen: bool,
        kw_only: bool,
        hash: bool,
        replace: bool,
        slots: bool,
        getitem: bool,
        setitem: bool,
    ) -> None:
        field_names: tuple[str] = get_names(cls)
        exact_key = (op, field_names)
        try:
            func = self._cache_cmp_exact[exact_key]
        except KeyError:
            field_count = len(field_names)
            key = (op, field_count)
            try:
                template_function = self._cache_cmp[key]
            except KeyError:
                cmp = self._comparators[op]
                if field_count == 0:
                    code_str = (
                        f"def {op}(self, other):\n"
                        "    if self.__class__ is not other.__class__:\n"
                        "        return NotImplemented\n"
                        "    return True"
                    )
                else:
                    # doing it this way for eq is slightly faster than making the tuple
                    if op == "__eq__":
                        code_str = (
                            f"def {op}(self, other):\n"
                            + "    if self.__class__ is not other.__class__:\n"
                            + "        return NotImplemented\n"
                            + "    return (\n"
                            + " and\n".join(
                                f"        self._field_{i} {cmp} other._field_{i}"
                                for i in range(field_count)
                            )
                            + "\n    )"
                        )
                    # NOTE: have to use tuples for comparisons since for ordering purposes
                    # we dont need all fields in one object to be >/</etc. than all of those in the other
                    # ex: (1,2) < (2,1) is True, but (1<2 and 2<1) would be False and provide the wrong sort
                    else:
                        code_str = (
                            f"def {op}(self, other):\n"
                            + "    if self.__class__ is not other.__class__:\n"
                            + "        return NotImplemented\n"
                            + "    return (\n"
                            + ",\n".join(
                                f"        self._field_{i}" for i in range(field_count)
                            )
                            + f"\n    ) {cmp} (\n"
                            + ",\n".join(
                                f"        other._field_{i}" for i in range(field_count)
                            )
                            + f"\n    )"
                        )
                exec(code_str, {}, l := {})  # type: ignore
                self._cache_cmp[key] = template_function = l.pop(op)
            if field_count == 0:
                func = template_function
            else:
                func = template_function.__class__(
                    template_function.__code__.replace(
                        co_names=(
                            "__class__",
                            "NotImplemented",
                        )
                        + field_names,
                    ),
                    template_function.__globals__,
                )
            self._cache_cmp_exact[exact_key] = func
        setattr(cls, op, func)

    def _create_replace(
        self,
        cls,
        init: bool,
        repr: bool,
        eq: bool,
        order: bool,
        frozen: bool,
        kw_only: bool,
        hash: bool,
        replace: bool,
        slots: bool,
        getitem: bool,
        setitem: bool,
    ) -> None:
        cls.__replace__ = __replace__

    def _create_repr(
        self,
        cls: type[T],
        init: bool,
        repr: bool,
        eq: bool,
        order: bool,
        frozen: bool,
        kw_only: bool,
        hash: bool,
        replace: bool,
        slots: bool,
        getitem: bool,
        setitem: bool,
    ) -> None:
        field_names: tuple[str] = get_names(cls)
        exact_key = (field_names, frozen)
        try:
            func = self._cache_repr_exact[exact_key]
        except KeyError:
            field_count = len(field_names)
            key = (field_count, frozen)
            try:
                template_function = self._cache_repr[key]
            except KeyError:
                if field_count == 0:
                    code_str = (
                        "def __repr__(self):\n"
                        '    return f"{self.__class__.__name__}()"'
                    )
                else:
                    if frozen:
                        # optimization: use fact attribute not set yet as indicator of when to set instead
                        # of handling overhead of is None check on every call, cutting relative time by ~50%
                        code_str = (
                            f"def __repr__(self):\n"
                            + f"    try:\n"
                            + f"        return self.{_FROZEN_REPR}\n"
                            + f"    except AttributeError:\n"
                            + f'        obj_setattr(self, "{_FROZEN_REPR}", (f"{{self.__class__.__name__}}("\n'
                            + "\n".join(
                                f'            f"_field_{i}={{self._field_{i}!r}}{"" if i == field_count - 1 else ","}"'
                                for i in range(field_count)
                            )
                            + f'\n        ")"))\n'
                            + f"        return self.{_FROZEN_REPR}"
                        )
                    else:
                        code_str = (
                            f"def __repr__(self):\n"
                            + f'    return (f"{{self.__class__.__name__}}("\n'
                            + "\n".join(
                                f'            f"_field_{i}={{self._field_{i}!r}}{"" if i == field_count - 1 else ","}"'
                                for i in range(field_count)
                            )
                            + f'\n        ")")\n'
                        )
                exec(
                    code_str,
                    {
                        "obj_setattr": object.__setattr__,
                        "AttributeError": AttributeError,
                    },
                    l := {},
                )
                self._cache_repr[key] = template_function = l.pop(f"__repr__")
                if field_count == 0:
                    self._cache_repr[(field_count, not frozen)] = template_function
            if field_count == 0:
                func = template_function
            else:
                if frozen:
                    func = template_function.__class__(
                        template_function.__code__.replace(
                            co_names=(
                                _FROZEN_REPR,
                                "AttributeError",
                                "obj_setattr",
                                "__class__",
                                "__name__",
                            )
                            + field_names,
                            co_consts=(
                                None,
                                _FROZEN_REPR,
                                f"({field_names[0]}=",
                                *tuple(
                                    f",{field_name}=" for field_name in field_names[1:]
                                ),
                                ")",
                            ),
                        ),
                        template_function.__globals__,
                    )
                else:
                    func = template_function.__class__(
                        template_function.__code__.replace(
                            co_names=("__class__", "__name__") + field_names,
                            co_consts=(
                                None,
                                f"({field_names[0]}=",
                                *tuple(
                                    f",{field_name}=" for field_name in field_names[1:]
                                ),
                                ")",
                            ),
                        ),
                        template_function.__globals__,
                    )
            self._cache_repr_exact[exact_key] = func
        cls.__repr__ = func

    def _create_frozen(
        self,
        cls,
        init: bool,
        repr: bool,
        eq: bool,
        order: bool,
        frozen: bool,
        kw_only: bool,
        hash: bool,
        replace: bool,
        slots: bool,
        getitem: bool,
        setitem: bool,
    ) -> None:
        cls.__setattr__ = __frozen_setattr__.__class__(  # type: ignore
            __frozen_setattr__.__code__,
            {
                "cls": cls,
                "_FIELDS": _FIELDS,
                "FrozenInstanceError": FrozenInstanceError,
            },
        )
        cls.__delattr__ = __frozen_delattr__.__class__(  # type: ignore
            __frozen_delattr__.__code__,
            {
                "cls": cls,
                "_FIELDS": _FIELDS,
                "FrozenInstanceError": FrozenInstanceError,
            },
        )

    def _create_hash(
        self,
        cls: type[T],
        init: bool,
        repr: bool,
        eq: bool,
        order: bool,
        frozen: bool,
        kw_only: bool,
        hash: bool,
        replace: bool,
        slots: bool,
        getitem: bool,
        setitem: bool,
    ) -> None:
        field_names: tuple[str] = get_names(cls)
        exact_key = (field_names, frozen)
        try:
            func = self._cache_hash_exact[exact_key]
        except KeyError:
            field_count = len(field_names)
            key = (field_count, frozen)
            try:
                template_function = self._cache_hash[key]
            except KeyError:
                if field_count == 0:
                    const = hash(())
                    code_str = f"def __hash__(self):\n" f"    return {const}"
                else:
                    if frozen:
                        # optimization: use fact attribute not set yet as indicator of when to set instead
                        # of handling overhead of is None check on every call, cutting relative time by ~50%
                        code_str = (
                            f"def __hash__(self):\n"
                            + f"    try:\n"
                            + f"        return self.{_FROZEN_HASH}\n"
                            + f"    except AttributeError:\n"
                            + f"        obj_setattr(self, '{_FROZEN_HASH}', hash((\n"
                            + "\n".join(
                                f"            self._field_{i},"
                                for i in range(field_count)
                            )
                            + f"\n        )))\n    return self.{_FROZEN_HASH}"
                        )
                    else:
                        code_str = (
                            f"def __hash__(self):\n"
                            + "    return hash((\n"
                            + "\n".join(
                                f"        self._field_{i}," for i in range(field_count)
                            )
                            + "\n    ))"
                        )
                exec(
                    code_str,
                    {
                        "obj_setattr": object.__setattr__,
                        "AttributeError": AttributeError,
                    },
                    l := {},
                )
                self._cache_hash[key] = template_function = l.pop(f"__hash__")
                if field_count == 0:
                    self._cache_hash[(field_count, not frozen)] = template_function
            if field_count == 0:
                func = template_function
            else:
                if frozen:
                    func = template_function.__class__(
                        template_function.__code__.replace(
                            co_names=(
                                _FROZEN_HASH,
                                "AttributeError",
                                "obj_setattr",
                                "hash",
                            )
                            + field_names,
                        ),
                        template_function.__globals__,
                    )
                else:
                    func = template_function.__class__(
                        template_function.__code__.replace(
                            co_names=("hash",) + field_names,
                        ),
                        template_function.__globals__,
                    )
            self._cache_hash_exact[exact_key] = func
        cls.__hash__ = func

    def _create_init_no_fields_template(
        self, kw_only: bool, field_count: int, has_defaults: bool
    ) -> FunctionType:
        code_str = "def __init__(self): pass"
        exec(code_str, {}, l := {})
        self._cache_init[(field_count, kw_only, has_defaults, True)] = (
            template_function
        ) = l.pop("__init__")
        self._cache_init[(field_count, kw_only, has_defaults, False)] = (
            template_function
        )
        self._cache_init[(field_count, not kw_only, has_defaults, True)] = (
            template_function
        )
        self._cache_init[(field_count, not kw_only, has_defaults, False)] = (
            template_function
        )
        return template_function

    def _create_init_has_defaults_frozen_template(
        self, kw_only: bool, field_count: int, has_defaults: bool
    ) -> FunctionType:
        code_str = (
            f"def __init__(self, {'*, ' if kw_only else ''}{', '.join(f'_field_{i}' for i in range(field_count))}):\n"
            + "    setted = set()\n"
            + f'    obj_setattr(self, "{_SETTED}", setted)\n'
            + "\n".join(
                f"    if _field_{i} is MISSING:\n"
                f"        if _field_{i}_default is not MISSING:\n"
                f'            obj_setattr(self, "_field_{i}", _field_{i}_default)\n'
                f"        else:\n"
                f'            obj_setattr(self, "_field_{i}", _field_{i}_default_factory())\n'
                f"    else:\n"
                f'        setted.add("_field_{i}")\n'
                f'        obj_setattr(self, "_field_{i}", _field_{i})'
                for i in range(field_count)
            )
            + "\n"
            + (
                f"    if post_init := getattr(self, '{_POST_INIT}', None):\n"
                "        post_init()"
            )
        )
        exec(
            code_str,
            {"MISSING": MISSING, "obj_setattr": object.__setattr__},
            l := {},  # type: ignore
        )
        self._cache_init[(field_count, kw_only, has_defaults, True)] = (
            template_function
        ) = l.pop("__init__")
        return template_function

    def _create_init_has_defaults_not_frozen_template(
        self, kw_only: bool, field_count: int, has_defaults: bool
    ) -> FunctionType:
        code_str = (
            f"def __init__(self, {'*, ' if kw_only else ''}{', '.join(f'_field_{i}' for i in range(field_count))}):\n"
            + "    setted = set()\n"
            + f"    self.{_SETTED} = setted\n"
            + "\n".join(
                f"    if _field_{i} is MISSING:\n"
                f"        if _field_{i}_default is not MISSING:\n"
                f"            self._field_{i} = _field_{i}_default\n"
                f"        else:\n"
                f"            self._field_{i} = _field_{i}_default_factory()\n"
                f"    else:\n"
                f'        setted.add("_field_{i}")\n'
                f"        self._field_{i} = _field_{i}"
                for i in range(field_count)
            )
            + "\n"
            + (
                f"    if post_init := getattr(self, '{_POST_INIT}', None):\n"
                "        post_init()"
            )
        )
        exec(code_str, {"MISSING": MISSING}, l := {})
        self._cache_init[(field_count, kw_only, has_defaults, False)] = (
            template_function
        ) = l.pop("__init__")
        return template_function

    def _create_init_no_defaults_frozen_template(
        self, kw_only: bool, field_count: int, has_defaults: bool
    ) -> FunctionType:
        code_str = (
            f"def __init__(self, {'*, ' if kw_only else ''}{', '.join(f'_field_{i}' for i in range(field_count))}):\n"
            + "\n".join(
                f'    obj_setattr(self, "_field_{i}", _field_{i})'
                for i in range(field_count)
            )
            + "\n"
            + (
                f"    if post_init := getattr(self, '{_POST_INIT}', None):\n"
                "        post_init()"
            )
        )
        exec(code_str, {"obj_setattr": object.__setattr__}, l := {})
        self._cache_init[(field_count, kw_only, has_defaults, True)] = (
            template_function
        ) = l.pop("__init__")
        return template_function

    def _create_init_no_defaults_not_frozen_template(
        self, kw_only: bool, field_count: int, has_defaults: bool
    ) -> FunctionType:
        code_str = (
            f"def __init__(self, {'*, ' if kw_only else ''}{', '.join(f'_field_{i}' for i in range(field_count))}):\n"
            + "\n".join(f"    self._field_{i} = _field_{i}" for i in range(field_count))
            + "\n"
            + (
                f"    if post_init := getattr(self, '{_POST_INIT}', None):\n"
                "        post_init()"
            )
        )
        exec(code_str, {}, l := {})
        self._cache_init[(field_count, kw_only, has_defaults, False)] = (
            template_function
        ) = l.pop("__init__")
        return template_function

    def _fill_init_has_defaults_frozen_template(
        self,
        init_exact_key: tuple,
        template_function: FunctionType,
        field_names: tuple[str],
        field_defaults: tuple,
        field_default_factories: tuple,
        kw_only: bool,
    ) -> FunctionType:
        func = template_function.__class__(  # type: ignore
            template_function.__code__.replace(  # type: ignore
                co_varnames=(
                    "self",
                    *field_names,
                    "setted",
                    "post_init",
                ),
                co_consts=(
                    None,
                    _SETTED,
                    *field_names,
                    _POST_INIT,
                ),
            ),
            template_function.__globals__  # type: ignore
            | dict((f"_field_{i}_default", d) for i, d in enumerate(field_defaults))
            | dict(
                (f"_field_{i}_default_factory", df)
                for i, df in enumerate(field_default_factories)
            ),
        )
        if kw_only:
            func.__kwdefaults__ = (  # type: ignore
                dict(
                    (k, MISSING)
                    for k, d, df in zip(
                        field_names, field_defaults, field_default_factories
                    )
                    if d is not MISSING or df is not MISSING
                )
                or None
            )
        else:
            func.__defaults__ = (  # type: ignore
                tuple(
                    MISSING
                    for d, df in zip(field_defaults, field_default_factories)
                    if d is not MISSING or df is not MISSING
                )
                or None
            )
        self._cache_init_exact[init_exact_key] = func
        return func

    def _fill_init_has_defaults_not_frozen_template(
        self,
        init_exact_key: tuple,
        template_function: FunctionType,
        field_names: tuple[str],
        field_defaults: tuple,
        field_default_factories: tuple,
        kw_only: bool,
    ) -> FunctionType:
        func = template_function.__class__(  # type: ignore
            template_function.__code__.replace(  # type: ignore
                co_names=(
                    "set",
                    _SETTED,
                    "MISSING",
                    f"_field_0_default",
                    field_names[0],
                    f"_field_0_default_factory",
                    "add",
                    *tuple(
                        con
                        for i, field_name in enumerate(field_names[1:])
                        for con in (
                            f"_field_{i+1}_default",
                            field_name,
                            f"_field_{i+1}_default_factory",
                        )
                    ),
                    "getattr",
                ),
                co_varnames=(
                    "self",
                    *field_names,
                    "setted",
                    "post_init",
                ),
                co_consts=(None, *field_names, _POST_INIT),
            ),
            template_function.__globals__  # type: ignore
            | dict((f"_field_{i}_default", d) for i, d in enumerate(field_defaults))
            | dict(
                (f"_field_{i}_default_factory", df)
                for i, df in enumerate(field_default_factories)
            ),
        )
        if kw_only:
            func.__kwdefaults__ = (  # type: ignore
                dict(
                    (k, MISSING)
                    for k, d, df in zip(
                        field_names, field_defaults, field_default_factories
                    )
                    if d is not MISSING or df is not MISSING
                )
                or None
            )
        else:
            func.__defaults__ = (  # type: ignore
                tuple(
                    MISSING
                    for d, df in zip(field_defaults, field_default_factories)
                    if d is not MISSING or df is not MISSING
                )
                or None
            )
        self._cache_init_exact[init_exact_key] = func
        return func

    def _fill_init_no_defaults_frozen_template(
        self,
        init_exact_key: tuple,
        template_function: FunctionType,
        field_names: tuple[str],
    ) -> FunctionType:
        func = template_function.__class__(  # type: ignore
            template_function.__code__.replace(  # type: ignore
                co_varnames=(
                    "self",
                    *field_names,
                    "post_init",
                ),
                co_consts=(None, *field_names, _POST_INIT),
            ),
            template_function.__globals__,
        )
        self._cache_init_exact[init_exact_key] = func
        return func

    def _fill_init_no_defaults_not_frozen_template(
        self,
        init_exact_key: tuple,
        template_function: FunctionType,
        field_names: tuple[str],
    ) -> FunctionType:
        func = template_function.__class__(  # type: ignore
            template_function.__code__.replace(  # type: ignore
                co_names=(
                    *field_names,
                    "getattr",
                ),
                co_varnames=("self", *field_names, "post_init"),
            ),
            template_function.__globals__,
        )
        self._cache_init_exact[init_exact_key] = func
        return func

    def _create_init(
        self,
        cls,
        init: bool,
        repr: bool,
        eq: bool,
        order: bool,
        frozen: bool,
        kw_only: bool,
        hash: bool,
        replace: bool,
        slots: bool,
        getitem: bool,
        setitem: bool,
    ) -> None:
        fields_dict = get_fields(cls)
        field_names: tuple[str] = tuple(
            f.name for f in fields_dict.values() if not f.is_computed
        )
        field_defaults = tuple(fields_dict[fn].default for fn in field_names)
        field_default_factories = tuple(
            fields_dict[fn].default_factory for fn in field_names
        )
        init_exact_key = (
            field_names,
            field_defaults,
            field_default_factories,
            kw_only,
            frozen,
        )
        try:
            # if we have two models with the exact same names and defaults, we dont have to change anything
            # saving a relatively large amount of time
            func = self._cache_init_exact[init_exact_key]
        except KeyError:
            # obligatory check to avoid impossible init definition. may consider changing later
            # to use kwargs or something in init so this is not an issue, but should generally just
            # stick to keyword only when possible anyway
            if not kw_only:
                defaulted = None
                for f in fields_dict.values():
                    if f.is_computed:
                        continue
                    if f.default is not MISSING or f.default_factory is not MISSING:
                        defaulted = f.name
                    elif defaulted:
                        raise TypeError(
                            f"non-default argument, {f.name!r}, "
                            f"follows default argument, {defaulted!r}, in model, {cls!r}"
                        )
            has_defaults = any(_ is not MISSING for _ in field_defaults) or any(
                _ is not MISSING for _ in field_default_factories
            )
            field_count = len(field_names)
            try:
                template_function = self._cache_init[
                    (field_count, kw_only, has_defaults, frozen)
                ]
            except KeyError:
                # special case: cannot use * for kw only if nothing follows it
                if field_count == 0:
                    template_function = self._create_init_no_fields_template(
                        kw_only=kw_only,
                        field_count=field_count,
                        has_defaults=has_defaults,
                    )
                elif has_defaults:
                    if frozen:
                        template_function = (
                            self._create_init_has_defaults_frozen_template(
                                kw_only=kw_only,
                                field_count=field_count,
                                has_defaults=has_defaults,
                            )
                        )
                    else:
                        template_function = (
                            self._create_init_has_defaults_not_frozen_template(
                                kw_only=kw_only,
                                field_count=field_count,
                                has_defaults=has_defaults,
                            )
                        )
                else:
                    if frozen:
                        template_function = (
                            self._create_init_no_defaults_frozen_template(
                                kw_only=kw_only,
                                field_count=field_count,
                                has_defaults=has_defaults,
                            )
                        )
                    else:
                        template_function = (
                            self._create_init_no_defaults_not_frozen_template(
                                kw_only=kw_only,
                                field_count=field_count,
                                has_defaults=has_defaults,
                            )
                        )
            # NOTE: should maybe technically replace _field_{x}_default_factory with field_name_default_factory
            # but this works as-is and no one will see it so skipping
            if field_count == 0:
                func = template_function
            elif has_defaults:
                if frozen:
                    func = self._fill_init_has_defaults_frozen_template(
                        init_exact_key=init_exact_key,
                        template_function=template_function,
                        field_names=field_names,
                        field_defaults=field_defaults,
                        field_default_factories=field_default_factories,
                        kw_only=kw_only,
                    )
                else:
                    func = self._fill_init_has_defaults_not_frozen_template(
                        init_exact_key=init_exact_key,
                        template_function=template_function,
                        field_names=field_names,
                        field_defaults=field_defaults,
                        field_default_factories=field_default_factories,
                        kw_only=kw_only,
                    )
            else:
                if frozen:
                    func = self._fill_init_no_defaults_frozen_template(
                        init_exact_key=init_exact_key,
                        template_function=template_function,
                        field_names=field_names,
                    )
                else:
                    func = self._fill_init_no_defaults_not_frozen_template(
                        init_exact_key=init_exact_key,
                        template_function=template_function,
                        field_names=field_names,
                    )
        cls.__init__ = func

    def _iter_slots(self, cls: type[T]):
        slots = cls.__dict__.get("__slots__")
        if slots is None:
            # No explicit slots, check for implicit ones
            if getattr(cls, "__weakrefoffset__", -1) != 0:
                yield "__weakref__"
            if getattr(cls, "__dictoffset__", -1) != 0:
                yield "__dict__"
        elif isinstance(slots, str):
            # Single slot as string
            yield slots
        elif hasattr(slots, "__iter__") and not hasattr(slots, "__next__"):
            # Iterable but not an iterator (tuple, list, etc.)
            yield from slots
        else:
            raise TypeError(f"Slots of '{cls.__qualname__}' cannot be determined")

    def _create_slotted_class(self, cls: type[T]) -> type[T]:
        if "__slots__" in cls.__dict__:
            raise TypeError(f"{cls.__name__} already specifies __slots__")
        field_names = get_names(cls)
        cls_dict = cls.__dict__

        # Early exit for common case: no inheritance slots
        slot_options = list(_INSTANCE_ATTRS)
        slot_options.extend(field_names)
        if len(cls.__mro__) <= 2:  # Only self and object
            slots = slot_options
            if "__weakref__" not in cls_dict:
                slots.append("__weakref__")
        else:
            inherited_slots = set()
            for base in cls.__mro__[1:-1]:  # Skip self and object
                inherited_slots.update(self._iter_slots(base))
            slots = [
                slot_option
                for slot_option in slot_options
                if slot_option not in inherited_slots
            ]
            if "__weakref__" not in inherited_slots:
                slots.append("__weakref__")

        excluded_keys = {"__dict__", "__weakref__"}
        cls_dict_new = _CLASS_ATTRS_DEFAULTS.copy()
        cls_dict_new.update(
            {
                k: v
                for k, v in cls_dict.items()
                if k not in field_names and k not in excluded_keys
            }
        )
        cls_dict_new["__slots__"] = tuple(slots)
        qualname = getattr(cls, "__qualname__", None)
        new_cls = cls.__class__(cls.__name__, cls.__bases__, cls_dict_new)

        if qualname is not None:
            new_cls.__qualname__ = qualname

        return new_cls

    def __call__(
        self,
        cls: type[T],
        init: bool,
        repr: bool,
        eq: bool,
        order: bool,
        frozen: bool,
        kw_only: bool,
        hash: bool,
        replace: bool,
        slots: bool,
        getitem: bool,
        setitem: bool,
        constraints: Iterable["BaseConstraint"],
    ) -> type[T]:
        # NOTE: lazy building model to minimize import costs. separate fields from methods
        # since during building of codec we only need the fields and can skip building the methods
        # which are a bit slower due to dynamic code generation
        if constraints:
            setattr(cls, _CONSTRAINTS, Constraints(constraints))
        setattr(
            cls,
            _PARAMS,
            (
                self,
                (
                    init,
                    repr,
                    eq,
                    order,
                    frozen,
                    kw_only,
                    hash,
                    replace,
                    slots,
                    getitem,
                    setitem,
                ),
            ),
        )
        setattr(cls, _FIELDS, _lazy_fields)
        if slots:
            # __slots__ must be defined when the class is created or it has no effect
            # using a proxy to do lazy loading would defeat perf gains and create problems when importing
            # so we have to materialize the class with slots immediately
            cls = self._create_slotted_class(cls)
        if init:
            cls.__init__ = _lazy_init
        if repr:
            cls.__repr__ = _lazy_repr
        if eq:
            cls.__eq__ = _lazy_eq
        if order:
            cls.__gt__ = _lazy_gt
            cls.__ge__ = _lazy_ge
            cls.__le__ = _lazy_le
            cls.__lt__ = _lazy_lt
        if frozen:
            cls.__setattr__ = _lazy_frozen_setattr
            cls.__delattr__ = _lazy_frozen_delattr
        if hash:
            cls.__hash__ = _lazy_hash
        if replace:
            cls.__replace__ = _lazy_replace
        if getitem:
            cls.__getitem__ = __getitem__
        if setitem:
            cls.__setitem__ = __setitem__
        return cls


_model_gen = StructGenerator()


# adding this function in order to get IDE type hinting to work properly
# did not seem to work when using __call__ on the class instance directly
@dataclass_transform(
    eq_default=True,
    order_default=True,
    kw_only_default=True,
    frozen_default=False,
    field_specifiers=(field,),
)
def struct(
    cls: type[T] | None = None,
    /,
    *,
    init: bool = True,
    repr: bool = True,
    eq: bool = True,
    order: bool = True,
    frozen: bool = False,  # perf: faster setting of attrs on init if False
    kw_only: bool = True,
    hash: bool = True,
    replace: bool = True,
    slots: bool = False,  # defaults to off due to significant overhead added in building class
    getitem: bool = False,
    setitem: bool = False,
    constraints: Iterable["BaseConstraint"] = (),
) -> type[T] | Callable[[type[T]], type[T]]:
    def wrap_model(cls):
        return _model_gen(
            cls,
            init=init,
            repr=repr,
            eq=eq,
            order=order,
            frozen=frozen,
            kw_only=kw_only,
            hash=hash,
            replace=replace,
            slots=slots,
            getitem=getitem,
            setitem=setitem,
            constraints=constraints,
        )

    if cls:
        return wrap_model(cls)
    return wrap_model


def create_struct(
    name: str,
    fields: dict[str, T_FuzzyTypeHint | field],
    /,
    *,
    bases: tuple[type, ...] = (),
    namespace: dict | None = None,
    module: str | None = None,
    init: bool = True,
    repr: bool = True,
    eq: bool = True,
    order: bool = True,
    frozen: bool = False,  # perf: faster setting of attrs on init if False
    kw_only: bool = True,
    hash: bool = True,
    replace: bool = True,
    slots: bool = False,  # defaults to off due to significant overhead added in building class
    getitem: bool = True,  # defaults to True because that is usually main way fields worked with for these structs
    setitem: bool = True,  # defaults to True because that is usually main way fields worked with for these structs
    constraints: Iterable["BaseConstraint"] = (),
) -> type[StructProto]:
    def _setup(cls_ns: dict):
        cls_ns.update(namespace or {})
        cls_ns["__annotations__"] = {
            field_name: value
            for field_name, value in fields.items()
            if value.__class__ is not field
        }

    cls = new_class(name=name, bases=bases, exec_body=_setup)

    if module is None:
        try:
            module = sys._getframemodulename(1) or '__main__'
        except AttributeError:
            try:
                module = sys._getframe(1).f_globals.get('__name__', '__main__')
            except (AttributeError, ValueError):
                pass
    if module is not None:
        cls.__module__ = module

    return struct(
        cls,
        init=init,
        repr=repr,
        eq=eq,
        order=order,
        frozen=frozen,
        kw_only=kw_only,
        hash=hash,
        replace=replace,
        slots=slots,
        getitem=getitem,
        setitem=setitem,
        constraints=constraints,
    )
