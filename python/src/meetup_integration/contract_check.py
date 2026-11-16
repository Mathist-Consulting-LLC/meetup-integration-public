"""Narrow consumer constraints, not a provider schema or live compatibility proof.

Source-declared names and consumer scalar/object/list shapes are asserted.
Required-input compatibility follows actual omission paths, not inferred schema
nullability; precise unknown leaf scalar names remain unverified.
This module never constructs clients, mutations, refresh operations or transports.
"""
import argparse
import json
from pathlib import Path


# (type, part, field, type shape, consumed argument shapes).
# None means presence-only: source selection does not establish a schema type.
PROFILE = (
    ("Query", "fields", "self", None, {}),
    ("Query", "fields", "groupByUrlname", None, {"urlname": "String"}),
    ("Query", "fields", "proNetwork", None, {"urlname": "String"}),
    ("Query", "fields", "event", "Event", {"id": "ID"}),
    ("Query", "fields", "eventSearch", None, {"first": "Int", "filter": None}),
    ("Query", "fields", "suggestTopics", "TopicsConnection",
     {"query": "String", "first": "Int", "excludeMemberTopics": None}),
    ("Mutation", "fields", "createEvent", None, {"input": "CreateEventInput"}),
    ("Mutation", "fields", "editEvent", None, {"input": "EditEventInput"}),
    ("Mutation", "fields", "deleteEvent", None, {"input": "DeleteEventInput"}),
    ("Mutation", "fields", "createGroupEventPhoto", None,
     {"input": "GroupEventPhotoCreateInput"}),
    ("Event", "fields", "topics", "TopicsConnection", {}),
    ("TopicsConnection", "fields", "edges", "[TopicEdge]", {}),
    ("TopicEdge", "fields", "node", "Topic", {}),
    ("Topic", "fields", "id", None, {}),
    ("Topic", "fields", "name", None, {}),
) + tuple(
    (name, "inputFields", field, shape, {})
    for name, fields in {
        "CreateEventInput": {
            "groupUrlname": None, "title": None, "description": None,
            "startDateTime": None, "duration": None, "venueId": None,
            "howToFindUs": None, "publishStatus": None, "question": None,
            "rsvpSettings": None, "featuredPhotoId": None, "topics": "[ID]",
            "proNetworkEvents": None,
        },
        "EditEventInput": {
            "eventId": None, "title": None, "description": None,
            "startDateTime": None, "duration": None, "venueId": None,
            "howToFindUs": None, "question": None, "rsvpSettings": None,
            "rsvpSurvey": None, "featuredPhotoId": None, "topics": "[ID]",
        },
        "DeleteEventInput": {
            "eventId": None, "removeFromCalendar": None, "updateSeries": None,
        },
        "GroupEventPhotoCreateInput": {
            "groupId": None, "photoType": None, "contentType": None, "setAsMain": None,
        },
        "RsvpSettings": {"rsvpLimit": None, "rsvpOpenTime": None},
        "RsvpSurvey": {"enabled": None},
        "ProNetworkEventsInput": {"fromEventId": None, "timezone": None},
    }.items() for field, shape in fields.items()
) + tuple(("Event", "fields", field, None, {}) for field in (
    "id", "title", "eventUrl", "dateTime", "endTime", "duration", "status",
    "createdTime", "group", "venue", "howToFindUs", "description", "networkEvent",
    "maxTickets", "rsvpSettings", "rsvpQuestions", "rsvpSurveySettings",
    "featuredEventPhoto",
))


def _shape(ref, depth=0):
    if depth > 12 or not isinstance(ref, dict):
        raise ValueError()
    kind = ref.get("kind")
    if kind == "NON_NULL":
        return _shape(ref.get("ofType"), depth + 1)
    if kind == "LIST":
        return "[" + _shape(ref.get("ofType"), depth + 1) + "]"
    if kind not in ("SCALAR", "OBJECT", "INPUT_OBJECT", "ENUM", "INTERFACE", "UNION"):
        raise ValueError()
    if not isinstance(ref.get("name"), str) or not ref["name"]:
        raise ValueError()
    name = ref["name"]
    if name in ("String", "Int", "Float", "Boolean", "ID", "DateTime") and kind != "SCALAR":
        raise ValueError()
    if name in ("Event", "Topic", "TopicsConnection", "TopicEdge") and kind != "OBJECT":
        raise ValueError()
    if name.endswith("Input") and kind != "INPUT_OBJECT":
        raise ValueError()
    return ref["name"]


def _index(rows):
    if not isinstance(rows, list) or len(rows) > 10000:
        raise ValueError()
    result = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str):
            raise ValueError()
        if row["name"] in result:
            raise ValueError()
        result[row["name"]] = row
    return result


# Traverse actual referenced type names rather than guessing Group/Connection or
# mutation payload names. A terminal None asserts presence, not scalar identity.
PATHS = (
    ("Query", "self.id", None, {}),
    ("Query", "self.name", None, {}),
    ("Query", "groupByUrlname.id", None, {}),
    ("Query", "groupByUrlname.name", None, {}),
    ("Query", "groupByUrlname.urlname", None, {}),
    ("Query", "groupByUrlname.lat", None, {}),
    ("Query", "groupByUrlname.lon", None, {}),
    ("Query", "groupByUrlname.events", None,
     {"first": "Int", "after": "String", "sort": None, "filter": None}),
    ("Query", "groupByUrlname.venues", None, {"first": "Int", "after": "String"}),
    ("Query", "proNetwork.id", None, {}),
    ("Query", "proNetwork.eventsSearch", None, {"input": None}),
    ("Query", "proNetwork.groupsSearch", None, {"input": None}),
) + tuple(
    ("Query", connection + "." + tail, shape, {})
    for connection in ("groupByUrlname.events", "groupByUrlname.venues")
    for tail, shape in (("pageInfo.endCursor", None), ("pageInfo.hasNextPage", "Boolean"),
                        ("edges.node.id", None))
) + tuple(
    ("Query", connection + ".edges.node." + field, None, {})
    for connection, fields in (
        ("proNetwork.eventsSearch", ("id",)),
        ("proNetwork.groupsSearch", ("id", "name", "urlname")),
        ("eventSearch", ("venue.id", "venue.name", "venue.address", "venue.city",
                         "venue.state", "venue.postalCode")),
        ("groupByUrlname.venues", ("name", "address", "city", "state", "postalCode")),
    ) for field in fields
) + tuple(
    ("Event", path, None, {}) for path in (
        "group.id", "group.name", "group.urlname", "venue.id", "venue.name",
        "venue.address", "networkEvent.id", "networkEvent.groupCount",
        "rsvpSettings.rsvpOpenTime", "rsvpQuestions.questionId", "rsvpQuestions.text",
        "rsvpSurveySettings.requiresProQuestionnaire", "featuredEventPhoto.id",
        "featuredEventPhoto.baseUrl",
    )
) + tuple(
    ("Mutation", operation + "." + path, shape, {})
    for operation in ("createEvent", "editEvent", "deleteEvent")
    for path, shape in (("errors.message", None), ("errors.code", None), ("errors.field", None))
) + (
    ("Query", "groupByUrlname.events.edges.node", "Event", {}),
    ("Query", "proNetwork.eventsSearch.edges.node", "Event", {}),
    ("Mutation", "createEvent.event", "Event", {}),
    ("Mutation", "editEvent.event", "Event", {}),
    ("Mutation", "createGroupEventPhoto.uploadUrl", None, {}),
    ("Mutation", "createGroupEventPhoto.photo.id", None, {}),
    ("Mutation", "createGroupEventPhoto.photo.baseUrl", None, {}),
    ("Mutation", "createGroupEventPhoto.imagePath", None, {}),
)
ARG_INPUTS = (
    ("Query", "groupByUrlname.events", "filter",
     {"afterDateTime": "DateTime", "beforeDateTime": "DateTime", "status": "[*]"}),
    ("Query", "eventSearch", "filter",
     {"query": "String", "lat": "Float", "lon": "Float", "radius": None}),
    ("Query", "proNetwork.eventsSearch", "input", {"first": None, "sort": None}),
    ("Query", "proNetwork.groupsSearch", "input", {"first": None}),
)

# Guaranteed members of each actual request, not a union of all possible writes.
# Conditional objects are validated when present; their parent may be omitted.
GUARANTEED = {
    "CreateEventInput": {"groupUrlname", "title", "description", "startDateTime",
                         "duration", "venueId", "howToFindUs", "publishStatus"},
    "EditEventInput": {"eventId"},
    "DeleteEventInput": {"eventId", "removeFromCalendar", "updateSeries"},
    "GroupEventPhotoCreateInput": {"groupId", "photoType", "contentType", "setAsMain"},
    "RsvpSettings": set(),
    "RsvpSurvey": {"enabled"},
    "ProNetworkEventsInput": {"fromEventId", "timezone"},
}
NESTED_INPUTS = {
    ("CreateEventInput", "rsvpSettings"): "RsvpSettings",
    ("EditEventInput", "rsvpSettings"): "RsvpSettings",
    ("EditEventInput", "rsvpSurvey"): "RsvpSurvey",
    ("CreateEventInput", "proNetworkEvents"): "ProNetworkEventsInput",
}
RESPONSE_LISTS = {"edges", "errors", "rsvpQuestions"}
EVENT_OBJECTS = {"group", "venue", "networkEvent", "rsvpSettings",
                 "rsvpSurveySettings", "featuredEventPhoto", "topics"}


def _base_ref(ref):
    _shape(ref)
    while ref.get("kind") == "NON_NULL":
        ref = ref["ofType"]
    return ref


def _structure(ref, *, object_value=False, list_value=False, input_value=False):
    ref = _base_ref(ref)
    if list_value:
        if ref["kind"] != "LIST":
            raise ValueError()
        ref = _base_ref(ref["ofType"])
    if ref["kind"] == "LIST":
        raise ValueError()
    kinds = (("INPUT_OBJECT",) if input_value else ("OBJECT", "INTERFACE")) if object_value else ("SCALAR", "ENUM")
    if ref["kind"] not in kinds:
        raise ValueError()
    return ref["name"]


def _input_contract(types, ref, fields, guaranteed, profile=None):
    name = _structure(ref, object_value=True, input_value=True)
    inputs = _index(types[name]["inputFields"])
    for field, expected in fields.items():
        row = inputs[field]
        nested = NESTED_INPUTS.get((profile, field))
        if nested:
            members = {key: shape for owner, part, key, shape, _ in PROFILE
                       if owner == nested and part == "inputFields"}
            _input_contract(types, row["type"], members, GUARANTEED[nested], nested)
        else:
            _structure(row["type"], list_value=bool(expected and expected.startswith("[")))
            if expected not in (None, "[*]") and _shape(row["type"]) != expected:
                raise ValueError()
    for field, row in inputs.items():
        if (field not in guaranteed and row["type"].get("kind") == "NON_NULL"
                and row.get("defaultValue") is None):
            raise ValueError()

def _field(types, name, path):
    for key in path.split("."):
        row = _index(types[name]["fields"])[key]
        name = _shape(row["type"]).strip("[]")
    return row


def check_snapshot(snapshot):
    """Return only fixed summary diagnostics; never return untrusted schema text."""
    try:
        if not isinstance(snapshot, dict) or snapshot.get("errors"):
            raise ValueError()
        types = _index(snapshot["data"]["__schema"]["types"])
        entries = []
        for name, part, field, shape, args in PROFILE:
            if part == "inputFields" and name in NESTED_INPUTS.values():
                continue  # These profiles apply through actual parent references.
            entries.append((_index(types[name][part])[field], shape, args, part))
            if part == "fields":
                object_value = (name == "Event" and field in EVENT_OBJECTS) or (
                    name in ("Query", "Mutation") or field in ("edges", "node"))
                _structure(entries[-1][0]["type"], object_value=object_value or field in RESPONSE_LISTS,
                           list_value=field in RESPONSE_LISTS)
        for name, path, shape, args in PATHS:
            segments = path.split(".")
            for index, field in enumerate(segments):
                entry = _index(types[name]["fields"])[field]
                actual = _shape(entry["type"])
                object_value = index < len(segments) - 1 or shape in ("Event", "TopicsConnection")
                if path in ("groupByUrlname.events", "groupByUrlname.venues",
                            "proNetwork.eventsSearch", "proNetwork.groupsSearch"):
                    object_value = True
                _structure(entry["type"], object_value=object_value,
                           list_value=field in RESPONSE_LISTS)
                if index < len(segments) - 1:
                    ref = entry["type"]
                    while ref.get("kind") in ("NON_NULL", "LIST"):
                        ref = ref["ofType"]
                    if ref["kind"] not in ("OBJECT", "INTERFACE"):
                        raise ValueError()
                name = actual.strip("[]")
            if path in ("groupByUrlname.events", "groupByUrlname.venues"):
                cursor = _index(entry["args"])["after"]
                if cursor["type"].get("kind") == "NON_NULL":
                    raise ValueError()
            entries.append((entry, shape, args, "fields"))
        for entry, shape, args, part in entries:
            actual = _shape(entry["type"])
            if shape is not None and actual != shape:
                raise ValueError()
            if part == "fields":
                arguments = _index(entry["args"])
                for arg, expected in args.items():
                    actual = _shape(arguments[arg]["type"])
                    if expected is not None and actual != expected:
                        raise ValueError()
                # New required arguments break existing requests, even if unused.
                for arg, value in arguments.items():
                    if arg not in args and value["type"].get("kind") == "NON_NULL":
                        if value.get("defaultValue") is None:
                            raise ValueError()
        for operation, profile in (("createEvent", "CreateEventInput"),
                                   ("editEvent", "EditEventInput"),
                                   ("deleteEvent", "DeleteEventInput"),
                                   ("createGroupEventPhoto", "GroupEventPhotoCreateInput")):
            row = _index(_field(types, "Mutation", operation)["args"])["input"]
            fields = {field: shape for owner, part, field, shape, _ in PROFILE
                      if owner == profile and part == "inputFields"}
            _input_contract(types, row["type"], fields, GUARANTEED[profile], profile)
        for name, path, arg, fields in ARG_INPUTS:
            row = _index(_field(types, name, path)["args"])[arg]
            _input_contract(types, row["type"], fields, set(fields))
        return {"supported": True, "scope": "bounded-consumer-profile",
                "checks": len(PROFILE) + len(PATHS) + len(ARG_INPUTS)}
    except (KeyError, TypeError, ValueError, AttributeError, RecursionError):
        return {"supported": False, "scope": "bounded-consumer-profile",
                "code": "schema_unsupported"}


def synthetic_snapshot():
    """Generated consumer model; explicitly NOT observed provider introspection."""
    def ref(shape):
        if shape and shape.startswith("["):
            return {"kind": "LIST", "ofType": ref(shape[1:-1])}
        name = "Unobserved" if shape in (None, "*") else shape
        kind = ("SCALAR" if name in ("String", "Int", "Float", "Boolean", "ID", "DateTime", "Unobserved")
                else "INPUT_OBJECT" if name.endswith("Input") else "OBJECT")
        return {"kind": kind, "name": name}
    types = {}
    for name, part, field, shape, args in PROFILE:
        row = {"name": field, "type": ref(shape)}
        if part == "fields":
            row["args"] = [{"name": arg, "type": ref(value)} for arg, value in args.items()]
        types.setdefault(name, {"name": name}).setdefault(part, []).append(row)
    for root, path, shape, args in PATHS:
        name = root
        segments = path.split(".")
        for index, field in enumerate(segments):
            rows = types.setdefault(name, {"name": name}).setdefault("fields", [])
            entry = next((row for row in rows if row["name"] == field), None)
            if entry is None:
                entry = {"name": field, "type": ref(None), "args": []}
                rows.append(entry)
            if index < len(segments) - 1:
                if _shape(entry["type"]) == "Unobserved":
                    target = "Synthetic" + name + field.title()
                    entry["type"] = ref("[" + target + "]" if field in RESPONSE_LISTS else target)
                name = _shape(entry["type"]).strip("[]")
            else:
                if shape is not None:
                    entry["type"] = ref(shape)
                entry["args"] = [{"name": arg, "type": ref(value)} for arg, value in args.items()]
    for root, path, arg, fields in ARG_INPUTS:
        row = _index(_field(types, root, path)["args"])[arg]
        name = "Synthetic" + root + path.replace(".", "") + arg.title() + "Input"
        row["type"] = ref(name)
        types[name] = {"name": name, "inputFields": [
            {"name": field, "type": ref(shape)} for field, shape in fields.items()
        ]}
    for (owner, field), target in NESTED_INPUTS.items():
        _index(types[owner]["inputFields"])[field]["type"] = {
            "kind": "INPUT_OBJECT", "name": target}
    return {"data": {"__schema": {"types": list(types.values())}}}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline bounded schema check; no live compatibility claim.")
    parser.add_argument("--snapshot", type=Path, help="Caller-provided introspection JSON; never fetched.")
    args = parser.parse_args(argv)
    try:
        if args.snapshot:
            with args.snapshot.open("rb") as stream:
                raw = stream.read(4 * 1024 * 1024 + 1)
            if len(raw) > 4 * 1024 * 1024:
                raise ValueError()
            def unique(pairs):
                value = {}
                for key, item in pairs:
                    if key in value:
                        raise ValueError()
                    value[key] = item
                return value
            snapshot = json.loads(raw, object_pairs_hook=unique)
        else:
            snapshot = synthetic_snapshot()
        result = check_snapshot(snapshot)
    except (OSError, ValueError, RecursionError):
        result = {"supported": False, "code": "snapshot_invalid"}
    result["provenance"] = "caller_snapshot" if args.snapshot else "generated_synthetic"
    print(json.dumps(result, sort_keys=True))
    return 0 if result["supported"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
