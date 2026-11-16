import contextlib
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from meetup_integration import MeetupClient, MeetupApiError, Result, EventCreateRequest
from meetup_integration.contract_check import check_snapshot, synthetic_snapshot
import test_provider as base


def corpus():
    local = Path(__file__).with_name("provider-faults.json")
    return json.loads((local if local.exists() else
                       Path(__file__).parents[1] / "contracts/provider-faults.json").read_text())


class ContractSuite(unittest.TestCase):
    def test_review_input_and_response_counterexamples(self):
        def field(s, owner, key, part="fields"):
            return next(f for t in s["data"]["__schema"]["types"] if t["name"] == owner
                        for f in t[part] if f["name"] == key)
        def required(row):
            row["type"] = {"kind": "NON_NULL", "ofType": row["type"]}
        def wrapped(row):
            row["type"] = {"kind": "LIST", "ofType": row["type"]}
        def input_field(s, owner, key):
            return field(s, owner, key, "inputFields")
        mutations = [
            ("F2-title", lambda s: required(input_field(s, "EditEventInput", "title"))),
            ("F3-scalar", lambda s: input_field(s, "EditEventInput", "rsvpSettings").update(
                type={"kind": "SCALAR", "name": "String"})),
            ("F4-group", lambda s: wrapped(field(s, "Event", "group"))),
            ("F4-id", lambda s: field(s, "Event", "id").update(
                type={"kind": "LIST", "ofType": {"kind": "SCALAR", "name": "ID"}})),
        ]
        for owner, key in (("CreateEventInput", "question"), ("CreateEventInput", "topics"),
                           ("CreateEventInput", "featuredPhotoId"),
                           ("CreateEventInput", "proNetworkEvents"),
                           ("EditEventInput", "rsvpSurvey"), ("EditEventInput", "rsvpSettings"),
                           ("RsvpSettings", "rsvpOpenTime"), ("RsvpSettings", "rsvpLimit")):
            mutations.append((owner + key, lambda s, o=owner, k=key: required(input_field(s, o, k))))
        for label, mutate in mutations:
            with self.subTest(label=label):
                s = synthetic_snapshot()
                mutate(s)
                self.assertFalse(check_snapshot(s)["supported"])
        for owner, key in (("CreateEventInput", "rsvpSettings"),
                           ("CreateEventInput", "proNetworkEvents"),
                           ("EditEventInput", "rsvpSurvey")):
            s = synthetic_snapshot()
            wrapped(input_field(s, owner, key))
            self.assertFalse(check_snapshot(s)["supported"])
        # Every actually consumed filter/input reference rejects a new omitted requirement.
        from meetup_integration.contract_check import ARG_INPUTS
        for root, path, arg, _ in ARG_INPUTS:
            s = synthetic_snapshot()
            owner = root
            for key in path.split("."):
                row = field(s, owner, key)
                owner = row["type"]["name"]
            ref = next(a for a in row["args"] if a["name"] == arg)["type"]
            target = next(t for t in s["data"]["__schema"]["types"] if t["name"] == ref["name"])
            extra = {"name": "newRequired", "type": {"kind": "NON_NULL",
                     "ofType": {"kind": "SCALAR", "name": "String"}}}
            target["inputFields"].append(extra)
            self.assertFalse(check_snapshot(s)["supported"], path)
            extra["defaultValue"] = '"default"'
            self.assertTrue(check_snapshot(s)["supported"], path)
        # Required always-supplied members and required optional members with defaults are safe.
        for owner, key in (("EditEventInput", "eventId"), ("RsvpSurvey", "enabled"),
                           ("ProNetworkEventsInput", "timezone"), ("CreateEventInput", "title")):
            s = synthetic_snapshot()
            required(input_field(s, owner, key))
            self.assertTrue(check_snapshot(s)["supported"])
        s = synthetic_snapshot()
        row = input_field(s, "EditEventInput", "title")
        required(row)
        row["defaultValue"] = '"untitled"'
        self.assertTrue(check_snapshot(s)["supported"])
        # Follow renamed nested objects, not detached correctly named definitions.
        s = synthetic_snapshot()
        nested = copy.deepcopy(next(t for t in s["data"]["__schema"]["types"] if t["name"] == "RsvpSettings"))
        nested["name"] = "ProviderSettings"
        s["data"]["__schema"]["types"].append(nested)
        input_field(s, "EditEventInput", "rsvpSettings")["type"]["name"] = nested["name"]
        self.assertTrue(check_snapshot(s)["supported"])
        required(next(f for f in nested["inputFields"] if f["name"] == "rsvpLimit"))
        self.assertFalse(check_snapshot(s)["supported"])
        next(f for f in nested["inputFields"] if f["name"] == "rsvpLimit")["defaultValue"] = "100"
        self.assertTrue(check_snapshot(s)["supported"])
        # No correctly named detached type is needed to satisfy either parent.
        input_field(s, "CreateEventInput", "rsvpSettings")["type"]["name"] = nested["name"]
        s["data"]["__schema"]["types"] = [t for t in s["data"]["__schema"]["types"]
                                         if t["name"] != "RsvpSettings"]
        self.assertTrue(check_snapshot(s)["supported"])
        nested["inputFields"].append({"name": "newRequired", "type": {
            "kind": "NON_NULL", "ofType": {"kind": "SCALAR", "name": "Boolean"}}})
        self.assertFalse(check_snapshot(s)["supported"])
        for owner, key in (("Event", "group"), ("Event", "id"), ("Event", "rsvpQuestions"),
                           ("TopicsConnection", "edges")):
            s = synthetic_snapshot()
            wrapped(field(s, owner, key))
            self.assertFalse(check_snapshot(s)["supported"])
        s = synthetic_snapshot()
        field(s, "Event", "id")["type"] = {"kind": "SCALAR", "name": "UnknownIdentityScalar"}
        self.assertTrue(check_snapshot(s)["supported"])
    def test_exact_operation_shapes_and_malformed_mutation_results(self):
        local = Path(__file__).with_name("provider-operations.json")
        fixture = json.loads((local if local.exists() else
                             Path(__file__).parents[1] / "contracts/provider-operations.json").read_text())
        for case in fixture["cases"]:
            with self.subTest(operation=case["method"]):
                calls = []
                def transport(request, token):
                    calls.append(json.loads(request.body))
                    return Result(200, json.dumps(case["responses"][len(calls) - 1]).encode())
                client = MeetupClient(token_supplier=lambda: "synthetic-token", transport=transport)
                def invoke():
                    if case["method"] == "create_event":
                        return client.create_event(EventCreateRequest(**fixture["create_request"]))
                    return getattr(client, case["method"])(*case["args"], **case["kwargs"])
                invoke()
                self.assertEqual(calls, case["requests"])
                if case["method"] in ("create_event", "update_event", "cancel_event",
                                      "_create_group_event_photo_placeholder"):
                    original = copy.deepcopy(case["responses"][-1])
                    for payload in ({}, {"event": {}}, {"event": {"id": 42}},
                                    {"errors": [{"message": "PRIVATE"}]}):
                        root = next(iter(original["data"]))
                        case["responses"][-1] = {"data": {root: payload}}
                        calls.clear()
                        with self.assertRaises(MeetupApiError) as caught:
                            invoke()
                        self.assertTrue(caught.exception.outcome_unknown)
                        self.assertNotIn("PRIVATE", str(caught.exception))
                        self.assertEqual(len(calls), len(case["requests"]))
                    case["responses"][-1] = original
    def test_shared_schema_drives_real_capability_probe_without_writes(self):
        local = Path(__file__).with_name("provider-schema.json")
        snapshot = json.loads((local if local.exists() else
                              Path(__file__).parents[1] / "contracts/provider-schema.json").read_text())
        calls = []
        def transport(request, token):
            payload = json.loads(request.body)
            calls.append(payload)
            self.assertTrue(payload["query"].startswith("query"))
            name = payload["variables"]["typeName"]
            row = next(t for t in snapshot["data"]["__schema"]["types"] if t["name"] == name)
            return Result(200, json.dumps({"data": {"__type": row}}).encode())
        client = MeetupClient(token_supplier=lambda: "synthetic-token", transport=transport)
        self.assertTrue(check_snapshot(snapshot)["supported"])
        self.assertTrue(client.inspect_event_topic_contract()["supported"])
        self.assertEqual(len(calls), 8)
        create = next(t for t in snapshot["data"]["__schema"]["types"] if t["name"] == "CreateEventInput")
        next(f for f in create["inputFields"] if f["name"] == "topics")["type"] = {"kind": "SCALAR", "name": "ID"}
        client = MeetupClient(token_supplier=lambda: "synthetic-token", transport=transport)
        self.assertFalse(client.inspect_event_topic_contract()["supported"])
    def test_shared_read_faults_are_redacted_and_never_retried(self):
        for case in corpus()["cases"]:
            with self.subTest(case=case["id"]):
                calls = []
                def transport(request, token):
                    calls.append(json.loads(request.body))
                    if case.get("throw"):
                        raise TimeoutError("PRIVATE")
                    body = case["body"]
                    return Result(case["status"], (body if isinstance(body, str)
                                  else json.dumps(body)).encode())
                client = MeetupClient(token_supplier=lambda: "synthetic-token", transport=transport)
                with self.assertRaises(MeetupApiError) as caught:
                    client._group_id_from_urlname("synthetic")
                self.assertEqual(caught.exception.code, case["code"])
                self.assertNotIn("PRIVATE", str(caught.exception))
                self.assertIsNone(caught.exception.__cause__)
                self.assertEqual(len(calls), 1)

    def test_write_submission_boundary_and_shared_faults(self):
        calls = []
        def token():
            raise TimeoutError("PRIVATE before submission")
        client = MeetupClient(token_supplier=token, transport=lambda *a: calls.append(a))
        with self.assertRaises(MeetupApiError) as caught:
            client.create_event(base.request())
        self.assertFalse(caught.exception.outcome_unknown)
        self.assertEqual(caught.exception.code, "authentication_unavailable")
        self.assertEqual(calls, [])
        for case in corpus()["cases"]:
            calls = []
            def submitted(request, token):
                calls.append(json.loads(request.body))
                if case.get("throw"):
                    raise TimeoutError("PRIVATE after remote success")
                body = case["body"]
                return Result(case["status"], (body if isinstance(body, str)
                              else json.dumps(body)).encode())
            client = MeetupClient(token_supplier=lambda: "synthetic-token", transport=submitted)
            with self.assertRaises(MeetupApiError) as caught:
                client.create_event(base.request())
            self.assertTrue(caught.exception.outcome_unknown)
            self.assertEqual(len(calls), 1)
            self.assertNotIn("PRIVATE", str(caught.exception))

    def test_schema_negative_mutations(self):
        snapshot = synthetic_snapshot()
        self.assertTrue(check_snapshot(snapshot)["supported"])
        def field(s, name, part, key):
            return next(x for x in next(t for t in s["data"]["__schema"]["types"]
                                       if t["name"] == name)[part] if x["name"] == key)
        mutations = [
            lambda s: s["data"]["__schema"]["types"].pop(0),
            lambda s: field(s, "Query", "fields", "event").update(type={"kind": "SCALAR", "name": "String"}),
            lambda s: field(s, "Query", "fields", "event").update(args=[]),
            lambda s: field(s, "Query", "fields", "event")["args"][0].update(type={"kind": "SCALAR", "name": "Int"}),
            lambda s: field(s, "CreateEventInput", "inputFields", "topics").update(type={"kind": "SCALAR", "name": "ID"}),
            lambda s: field(s, "Query", "fields", "event")["args"].append(
                {"name": "PRIVATE", "type": {"kind": "NON_NULL", "ofType": {"kind": "SCALAR", "name": "ID"}}}),
            lambda s: field(s, "Event", "fields", "id").update(type={}),
            lambda s: field(s, "Query", "fields", "event").update(type={"kind": "SCALAR", "name": "Event"}),
            lambda s: next(t for t in s["data"]["__schema"]["types"] if t["name"] == "DeleteEventInput")["inputFields"].append(
                {"name": "PRIVATE", "type": {"kind": "NON_NULL", "ofType": {"kind": "SCALAR", "name": "ID"}}}),
        ]
        for mutate in mutations:
            candidate = copy.deepcopy(snapshot)
            mutate(candidate)
            result = check_snapshot(candidate)
            self.assertFalse(result["supported"])
            self.assertNotIn("PRIVATE", json.dumps(result))
        # Traverse returned schema references rather than guessing payload names.
        for path in (("Query", "groupByUrlname", "events", "pageInfo", "hasNextPage"),
                     ("Mutation", "createEvent", "event", "id"),
                     ("Mutation", "deleteEvent", "errors", "message")):
            candidate = copy.deepcopy(snapshot)
            name = path[0]
            for key in path[1:]:
                row = field(candidate, name, "fields", key)
                ref = row["type"]
                while ref.get("ofType"):
                    ref = ref["ofType"]
                name = ref["name"]
            row["name"] = "PRIVATE-removed"
            self.assertFalse(check_snapshot(candidate)["supported"])
        for value in (None, [], {}, {"errors": [{"message": "PRIVATE"}]}):
            self.assertFalse(check_snapshot(value)["supported"])
        candidate = copy.deepcopy(snapshot)
        query = field(candidate, "Query", "fields", "eventSearch")
        input_name = next(a for a in query["args"] if a["name"] == "filter")["type"]["name"]
        field(candidate, input_name, "inputFields", "lat")["type"] = {"kind": "SCALAR", "name": "String"}
        self.assertFalse(check_snapshot(candidate)["supported"])

    def test_command_is_offline_and_does_not_disclose_inputs(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "PRIVATE.json"
            path.write_text(json.dumps(synthetic_snapshot()))
            for args, expected in (([], 0), (["--snapshot", str(path)], 0)):
                result = subprocess.run([sys.executable, "-I", "-m",
                    "meetup_integration.contract_check", *args], capture_output=True, text=True)
                self.assertEqual(result.returncode, expected, result.stderr)
                self.assertNotIn("PRIVATE", result.stdout + result.stderr)
            path.write_text("{PRIVATE")
            result = subprocess.run([sys.executable, "-I", "-m",
                "meetup_integration.contract_check", "--snapshot", str(path)],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertNotIn("PRIVATE", result.stdout + result.stderr)
        from meetup_integration.contract_check import main
        with patch("socket.socket", side_effect=AssertionError("network forbidden")), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main([]), 0)
