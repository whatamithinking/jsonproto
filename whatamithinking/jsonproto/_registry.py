from typing import (
    Callable,
    TypeVar,
    TYPE_CHECKING,
    overload,
    ClassVar,
    Final,
)
import inspect
import weakref
from itertools import chain

if TYPE_CHECKING:
    from ._handlers.base import BaseTypeHandler

from ._errors import TypeHandlerMissingError
from ._common import (
    TypeHintValue,
    ResolvedTypeHint,
    IsTypeCallback,
    Constraints,
    Empty,
    Constraints,
    BaseConstraint,
)
from ._resolver import resolve_type_hint, TypeHintResolution, FuzzyTypeHint


T = TypeVar("T")
T_TypeHandlerRegisterCallback = Callable[
    [type["BaseTypeHandler"], ResolvedTypeHint | Empty, IsTypeCallback | Empty], None
]


class TypeRegistry:

    def __init__(self, *registries: "TypeRegistry") -> None:
        self._type_hint_handler_classes: dict[
            ResolvedTypeHint, type["BaseTypeHandler"]
        ] = {}
        self._callback_handler_classes: dict[
            IsTypeCallback, type["BaseTypeHandler"]
        ] = {}
        self._registries = list[TypeRegistry]()

        self._type_hint_to_constraints: dict[ResolvedTypeHint, Constraints] = {}
        self._callback_to_constraints: dict[ResolvedTypeHint, Constraints] = {}

        self._cache_handler_classes: dict[FuzzyTypeHint, type["BaseTypeHandler"]] = {}
        self._cache_handlers: dict[
            tuple[FuzzyTypeHint, Constraints, TypeHintValue], "BaseTypeHandler"
        ] = {}

        self._register_callbacks = list[weakref.ref[T_TypeHandlerRegisterCallback]]()
        # clear cache so we return the latest type handler class registered
        # unlikely to really be a problem in practice but because we are caching we are now
        # open late registrations potentially changing things up after the fact
        self._add_callbacks_to_registry(self)
        for registry in registries:
            self.add_registry(registry)

    def _add_callbacks_to_registry(self, registry: "TypeRegistry") -> None:
        # register this registry's callbacks with the new registry so we can clear our caches
        # whenever the new registry changes
        registry.add_register_type_handler_callback(self._cache_handler_classes.clear)
        registry.add_register_type_handler_callback(self._cache_handlers.clear)

    def add_registry(self, registry: "TypeRegistry") -> None:
        self._add_callbacks_to_registry(registry)
        self._registries.append(registry)

    def add_register_type_handler_callback(
        self, callback: T_TypeHandlerRegisterCallback, /
    ) -> None:
        if inspect.ismethod(callback):
            register_callback_ref = weakref.WeakMethod(callback)
        else:
            register_callback_ref = weakref.ref(callback)
        self._register_callbacks.append(register_callback_ref)

    def call_register_type_handler_callbacks(
        self,
        type_handler_class: type[T] | Empty,
        type_hint: ResolvedTypeHint | Empty,
        callback: IsTypeCallback | Empty,
    ) -> None:
        for i in range(len(self._register_callbacks) - 1, -1, -1):
            register_callback = self._register_callbacks[i]()
            if register_callback is None:
                del self._register_callbacks[i]
            else:
                register_callback(
                    type_handler_class=type_handler_class,
                    type_hint=type_hint,
                    callback=callback,
                )

    def register_type_constraints(
        self,
        *constraints: BaseConstraint,
        type_hint: ResolvedTypeHint | Empty = Empty,
        callback: IsTypeCallback | Empty = Empty,
    ):
        constraints = Constraints(constraints)
        if type_hint is not Empty:
            thr = resolve_type_hint(type_hint=type_hint)
            if thr.is_partial:
                raise TypeError(
                    "stringified types not supported during type handler registration"
                )
            self._type_hint_to_constraints[thr.type_hint] = constraints
        else:
            self._callback_to_constraints[callback] = constraints

    @overload
    def register_type_handler(
        self,
        type_handler_class: type[T],
        /,
        *,
        type_hint: ResolvedTypeHint | Empty = Empty,
        callback: IsTypeCallback | Empty = Empty,
    ) -> type[T]: ...

    @overload
    def register_type_handler(
        self,
        type_handler_class: Empty = Empty,
        /,
        *,
        type_hint: ResolvedTypeHint | Empty = Empty,
        callback: IsTypeCallback | Empty = Empty,
    ) -> Callable[[type[T]], type[T]]: ...

    def register_type_handler(
        self,
        type_handler_class: type[T] | Empty = Empty,
        /,
        *,
        type_hint: ResolvedTypeHint | Empty = Empty,
        callback: IsTypeCallback | Empty = Empty,
    ) -> type[T] | Callable[[type[T]], type[T]]:
        if type_hint is Empty and callback is Empty:
            raise ValueError("one of type_hint or callback must be given")
        elif type_hint is not Empty and callback is not Empty:
            raise ValueError("either type_hint or callback must be given, not both")

        def register_type_handler_wrapper(type_handler_class: type[T], /) -> type[T]:
            if type_hint is not Empty:
                thr = resolve_type_hint(type_hint=type_hint)
                if thr.is_partial:
                    raise TypeError(
                        "stringified types not supported during type handler registration"
                    )
                self._type_hint_handler_classes[thr.type_hint] = type_handler_class
            else:
                self._callback_handler_classes[callback] = type_handler_class
            self.call_register_type_handler_callbacks()
            return type_handler_class

        # if called like a function with type handler class given
        if type_handler_class is not Empty:
            return register_type_handler_wrapper(type_handler_class)
        else:  # if used as decorator, where type handler class will be empty
            return register_type_handler_wrapper

    def get_type_handler_class(
        self, type_hint_resolution: TypeHintResolution
    ) -> type["BaseTypeHandler"]:
        try:
            return self._cache_handler_classes[type_hint_resolution.type_hint]
        except KeyError:
            # note that we start by looking for handlers of the more specific type hint
            # and fallback to the less specific without the generic types, since
            # these shell types usually themselves call in this method to handle
            # generic types handling
            type_hint_options = [
                type_hint_resolution.original_type_hint,
                type_hint_resolution.type_hint,
            ]
            if (origin := type_hint_resolution.origin) is not None:
                type_hint_options.append(origin)
            type_hint_class = None
            for type_hint_option in type_hint_options:
                if type_hint_class := self._type_hint_handler_classes.get(
                    type_hint_option
                ):
                    break
                for is_type, thc in self._callback_handler_classes.items():
                    if not is_type(type_hint_option):
                        continue
                    type_hint_class = thc
                    break
                if type_hint_class:
                    break
            else:
                # we cache results from other registries as well so we can avoid searching through them
                # each time. don't think this should generally create problems as i don't see any need
                # to be changing type handlers returned on the fly from one call to the next
                for registry in self._registries:
                    try:
                        type_hint_class = registry.get_type_handler_class(
                            type_hint_resolution=type_hint_resolution
                        )
                        break
                    except TypeHandlerMissingError:
                        continue
                else:
                    raise TypeHandlerMissingError(
                        f"No type handler class found supporting {type_hint_resolution.original_type_hint!r}"
                    )
            self._cache_handler_classes[type_hint_resolution.original_type_hint] = (
                type_hint_class
            )
            self._cache_handler_classes[type_hint_option] = type_hint_class
            return type_hint_class

    def get_type_handler(
        self,
        type_hint: FuzzyTypeHint,
        constraints: Constraints = Constraints.empty,
        type_hint_value: TypeHintValue = Empty,
    ) -> "BaseTypeHandler":
        try:
            return self._cache_handlers[(type_hint, constraints, type_hint_value)]
        except KeyError:
            type_hint_resolution = resolve_type_hint(type_hint=type_hint)
            if type_hint_resolution.is_partial:
                raise TypeError("could not fully resolve type hint")
            # special case: ClassVar/Final type hints are effectively Literal with one value but
            # the value is not included in the type hint so we need to get it from the caller
            # and use it to index off of and create a new type handler for each one since the default
            # needs to be provided to each instance of the type handler
            if type_hint_resolution.origin in (ClassVar, Final):
                if type_hint_value is Empty:
                    raise ValueError(
                        "type_hint_value must be given when getting the type handler for ClassVar or Final"
                    )
            elif type_hint_value is not Empty:
                type_hint_value = (
                    Empty  # always ignore the value otherwise so instances dont explode
                )
                try:
                    return self._cache_handlers[
                        (type_hint, constraints, type_hint_value)
                    ]
                except KeyError:
                    pass

            total_constraints = Constraints(
                chain(
                    (
                        _
                        for _ in type_hint_resolution.annotations
                        if hasattr(_, "constraint_type")
                    ),
                    constraints,
                )
            )
            type_handler_class = self.get_type_handler_class(
                type_hint_resolution=type_hint_resolution
            )
            type_handler = type_handler_class(
                type_handler_registry=self,
                type_hint=type_hint_resolution.type_hint,
                constraints=total_constraints,
                type_hint_value=type_hint_value,
            )
            # index off the original input exactly in case this is given again
            self._cache_handlers[
                (
                    type_hint_resolution.original_type_hint,
                    constraints,
                    type_hint_value,
                )
            ] = type_handler
            # index off the type hint alone without any annotations and with all the constraints
            # stripped off and provided separately in case a caller provides just the type hint and
            # the same set of constraints previously provided through the annotations
            self._cache_handlers[
                (
                    type_hint_resolution.type_hint,
                    total_constraints,
                    type_hint_value,
                )
            ] = type_handler
            return type_handler


default_type_registry = TypeRegistry()
