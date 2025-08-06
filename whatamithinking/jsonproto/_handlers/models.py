from typing import (
    Any,
    TYPE_CHECKING,
)

if TYPE_CHECKING:
    from .._codec import Config

from .._errors import ConstraintError
from .._struct import (
    get_fields,
    get_unsetted,
    get_constraints,
    is_struct_class,
    is_struct_instance,
    get_computed,
    set_extras,
    get_required,
    get_names,
)
from .._common import MISSING, get_alias
from .._resolver import resolve_type_hint
from .._pointers import JsonPointer
from .._common import MISSING_TYPE, MISSING
from .._issues import (
    JsonTypeIssue,
    BaseIssue,
    PythonTypeIssue,
    ExtraFieldIssue,
    DependentIssue,
    DisjointIssue,
    MissingFieldIssue,
)

from .base import TypeHandler, register_default_type_handler

__all__ = ["ModelHandler"]


@register_default_type_handler(callback=is_struct_class)
class ModelHandler(TypeHandler):
    __slots__ = (
        "constraints",
        "_dependent_groups_names",
        "_disjoint_groups_names",
        "_dependent_groups_aliases",
        "_disjoint_groups_aliases",
        "_required_names",
        "_required_aliases",
        "_computed_names",
        "_field_type_handlers",
    )

    data_type = "object"
    media_type = "application/json"
    json_class = dict
    python_class = dict

    def build(self) -> None:
        # use constraints defined at model level as base which are extended by any constraints
        # defined at the type annotation level where the model is being referenced
        if model_constraints := get_constraints(self.type_hint):
            self.constraints.extendleft(model_constraints)

        # merge dependent groups of fields which are transitively related
        # i.e. if we have a,b b,c c,d as separate groups, we can collapse that to a,b,c,d
        # since as soon as any one of those is given, all must given in order for the constraints to hold
        depgrps: list[frozenset[str]] = [
            _.field_names for _ in self.constraints if _.constraint_type == "dependent"
        ]
        self._dependent_groups_names = set[frozenset[str]]()
        for i, idepgrp in enumerate(depgrps):
            depgrp = set(idepgrp)
            for jdepgrp in depgrps[i + 1 :]:
                if not depgrp.intersection(jdepgrp):
                    continue
                depgrp.update(jdepgrp)
            self._dependent_groups_names.add(frozenset(depgrp))

        self._disjoint_groups_names = set[frozenset[str]](
            _.field_names for _ in self.constraints if _.constraint_type == "disjoint"
        )

        # make sure satisfying each of the dependent groups is possible without conflicting
        # with any of the disjoint groups at the same time
        for depgrp in self._dependent_groups_names:
            for disgrp in self._disjoint_groups_names:
                if len(depgrp.intersection(disgrp)) <= 1:
                    continue
                raise ConstraintError(
                    f"Transitively dependent field group, {depgrp!r}, "
                    f"conflicts with disjoint field group, {disgrp}"
                )

        name_to_alias = dict[str, str]()
        self._required_names = get_required(self.type_hint)
        self._computed_names = get_computed(self.type_hint)
        self._field_type_handlers = {}
        for name, field in get_fields(self.type_hint).items():
            # resolve type hint here instead of in get_type_handler so we can pass in this model as the
            # owner and handle any forward ref resolution based on that, context which we would otherwise
            # need to provide to get_type_handler
            type_hint_resolution = resolve_type_hint(
                type_hint=field.type_hint,
                resolve_forward_refs=True,
                owner=self.type_hint,
            )
            # fool-proofing in case i forget these constraints should only be used at the model level
            # not the field level
            if any(
                getattr(_, "constraint_type", None) in ("disjoint", "dependent")
                for _ in type_hint_resolution.annotations
            ):
                raise ConstraintError(
                    "Disjoint/dependent constraints can only be used in the model decorator "
                    "and not in the field annotations."
                )
            type_handler = self.get_type_handler(
                type_hint=type_hint_resolution.type_hint,
                constraints=field.constraints,
                type_hint_value=field.default,
            )
            alias: str | None = field.constraints.get("alias")
            if not alias:
                alias = get_alias(name)
            name_to_alias[name] = alias
            field_info = (name, alias, field.default, type_handler)
            self._field_type_handlers[name] = field_info
            self._field_type_handlers[alias] = field_info

        self._required_aliases = frozenset[str](
            name_to_alias[n] for n in self._required_names
        )
        self._dependent_groups_aliases = set[frozenset[str]](
            frozenset(name_to_alias[n] for n in depgrp)
            for depgrp in self._dependent_groups_names
        )
        self._disjoint_groups_aliases = set[frozenset[str]](
            frozenset(name_to_alias[n] for n in disgrp)
            for disgrp in self._disjoint_groups_names
        )

    def coerce(self, value: Any, pointer: JsonPointer, config: "Config") -> Any:
        # override in subclass to handle coercion to specific structure or changing fields across the
        # entire model and not just a specific type. use self.type_hint to get specific model class
        return value

    def handle(
        self,
        value: Any,
        pointer: JsonPointer,
        included: bool,
        excluded: bool,
        config: "Config",
    ) -> tuple[Any | MISSING_TYPE, list[BaseIssue]]:
        issues = []
        cvalue = value
        if config.coerce:
            cvalue = self.coerce(value=cvalue, pointer=pointer, config=config)
        if config.validate:
            match config.source:
                case "json":
                    if cvalue.__class__ is not self.json_class:
                        return cvalue, [
                            JsonTypeIssue(
                                value=cvalue,
                                pointer=pointer,
                                expected_type="object",
                            )
                        ]
                case "unstruct":
                    # if coercion allowed and this is mapping like or an iterable with two objects for
                    # each item we can accept it and convert to a mapping below
                    if config.coerce and (
                        hasattr(cvalue, "items")
                        or (
                            hasattr(cvalue, "__iter__")
                            and cvalue
                            and len(cvalue[0]) == 2
                        )
                    ):
                        pass
                    elif cvalue.__class__ is not self.python_class:
                        return cvalue, [
                            PythonTypeIssue(
                                value=cvalue,
                                pointer=pointer,
                                expected_type=self.python_class,
                            )
                        ]
                case "struct":
                    # if coercion allowed and this is a mapping or iterable of k/v pairs or another model
                    # we can work with it as-is. otherwise, we are gonna need this to be the exact model
                    # we are looking for
                    if config.coerce and (
                        hasattr(cvalue, "items")
                        or (
                            hasattr(cvalue, "__iter__")
                            and cvalue
                            and len(cvalue[0]) == 2
                        )
                        or is_struct_instance(cvalue)
                    ):
                        pass
                    elif cvalue.__class__ is not self.type_hint:
                        return cvalue, [
                            PythonTypeIssue(
                                value=cvalue,
                                pointer=pointer,
                                expected_type=self.type_hint,
                            )
                        ]
        source_key_patches = config.patches.have_for("source", "key")
        source_value_patches = config.patches.have_for("source", "value")
        # patches to target keys do not make sense in this context since we do not use the keys
        # from the original data in the model or reference them in any way to make decisions
        target_value_patches = config.patches.have_for("target", "value")
        extras = {}
        computed_mapping = {}
        field_mapping = (
            self.json_class() if config.target == "json" else self.python_class()
        )
        if is_struct_instance(cvalue):
            # unset names is for filtering purposes so we can apply exclude_unset field
            # only works when using a model because models keep track of this
            unset_names = get_unsetted(cvalue)
            items = ((name, getattr(cvalue, name)) for name in get_names(cvalue))
        else:
            unset_names = frozenset()
            items = getattr(cvalue, "items", getattr(cvalue, "__iter__"))()
        set_vnames = set[str]()
        for vname, vvalue in items:
            field_pointer = pointer.join(vname)
            if source_key_patches:
                vname = config.patches.patch("source", "key", field_pointer, vname)
            if source_value_patches:
                vvalue = config.patches.patch("source", "value", field_pointer, vvalue)
            if config.exclude_none and vvalue is None:
                continue
            if field_excluded := config.exclude.matches(field_pointer):
                continue
            type_handler_info = self._field_type_handlers.get(vname)
            if type_handler_info is not None:
                name, alias, default, type_handler = type_handler_info
            else:
                name = alias = default = type_handler = MISSING
            if config.exclude_unset and name in unset_names:
                continue
            if type_handler is MISSING:
                match config.extras_mode:
                    case "drop":
                        pass
                    case "forbid":
                        issues.append(
                            ExtraFieldIssue(
                                extra=vname, value=vvalue, pointer=field_pointer
                            )
                        )
                    case "roundtrip":
                        if config.target == "struct":
                            extras[vname] = vvalue
                        else:
                            field_mapping[vname] = vvalue
                continue
            if config.exclude_default and default is not MISSING and vvalue == default:
                continue
            vvalue, vvalue_issues = type_handler.handle(
                value=vvalue,
                pointer=field_pointer,
                included=included or config.include.matches(field_pointer),
                excluded=field_excluded,
                config=config,
            )
            if vvalue is MISSING:
                continue
            issues.extend(vvalue_issues)
            if target_value_patches:
                vvalue = config.patches.patch("target", "value", field_pointer, vvalue)
            set_vnames.add(vname)
            match config.target:
                case "json":
                    field_mapping[alias] = vvalue
                case "unstruct":
                    field_mapping[name] = vvalue
                case "struct":
                    if name in self._computed_names:
                        computed_mapping[name] = vvalue
                    else:
                        field_mapping[name] = vvalue

        # out of the fields which made it past all the filters, make sure we do not violate
        # any of the dependent/disjoint field group constraints
        missing_fields = None
        if config.validate:
            # only need to validate we got all the fields when we need to convert to the model
            if config.target == "struct":
                # be sure to use aliases if data is json so camelCasing matches with their data
                if config.source == "json":
                    missing_fields = self._required_aliases - set_vnames
                else:
                    missing_fields = self._required_names - set_vnames
                if missing_fields:
                    issues.extend(
                        MissingFieldIssue(value=missing_vname, pointer=pointer)
                        for missing_vname in missing_fields
                    )
            depgrps = (
                self._dependent_groups_aliases
                if config.source == "json"
                else self._dependent_groups_names
            )
            for depgrp in depgrps:
                overlap = depgrp.intersection(set_vnames)
                if overlap and len(overlap) != len(depgrp):
                    issues.append(
                        DependentIssue(
                            value=cvalue,
                            pointer=pointer,
                            dependent=depgrp,
                            # show only the fields part of the dependent group which were given so we don't
                            # spray them with every field, muddying the meaning
                            setted=overlap,
                        )
                    )
            disgrps = (
                self._disjoint_groups_aliases
                if config.source == "json"
                else self._disjoint_groups_names
            )
            for disgrp in disgrps:
                overlap = disgrp.intersection(set_vnames)
                if overlap and len(overlap) > 1:
                    issues.append(
                        DisjointIssue(
                            value=cvalue,
                            pointer=pointer,
                            disjoint=disgrp,
                            # only show what was setted which was part of the disjoint group. they should only have
                            # provided just one of the fields and no more.
                            setted=overlap,
                        )
                    )

        if (included and not excluded) or field_mapping:
            if config.target in ("json", "unstruct"):
                if config.convert or config.coerce:
                    return field_mapping, issues
                else:
                    return value, issues
            else:
                if config.convert or config.coerce:
                    if missing_fields:
                        return field_mapping, issues
                    # NOTE: be aware that accessing this model from inside the debugger while
                    # we are still setting it up here may break the repr/hash on frozen models
                    # since they may be called before we finish and then we change field values
                    # but they are not recalculated. only a problem if specifically debugging this
                    # section of code
                    model = self.type_hint(**field_mapping)
                    if extras:
                        set_extras(model, extras)
                    # if values given for computed fields, we cannot pass to constructor and dont
                    # want to recalculate so we need to override the computed field on the instance
                    # with the value given. object.setattr in case model is frozen
                    if computed_mapping:
                        for cn, cv in computed_mapping.items():
                            object.__setattr__(model, cn, cv)
                    return model, issues
                else:
                    return value, issues
        return MISSING, issues
