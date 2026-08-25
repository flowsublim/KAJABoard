import json

from django.core.serializers.json import DjangoJSONEncoder


def model_snapshot(instance, *, exclude: tuple[str, ...] = ()) -> dict[str, object]:
    """Return an audit-safe snapshot of concrete model fields."""

    values = {
        field.name: getattr(instance, field.attname)
        for field in instance._meta.concrete_fields
        if field.name not in exclude
    }
    return json.loads(json.dumps(values, cls=DjangoJSONEncoder))


def changed_field_names(before: dict[str, object], after: dict[str, object]) -> list[str]:
    return sorted(key for key in before.keys() | after.keys() if before.get(key) != after.get(key))
