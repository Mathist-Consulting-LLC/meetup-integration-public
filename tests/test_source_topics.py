"""Provider-only ports of release18 Python contracts; app tests remain source-owned."""
import unittest
from meetup_integration import MeetupTopicCatalog, Topic, TopicReviewRequired, canonical_topics
def ref(kind, name=None, child=None):
    return {'kind': kind, 'name': name, 'ofType': child}


class SyntheticGraphQL:
    def __init__(self, supported=True):
        self.supported = supported
        self.calls = []
        self.selections = {'AuDHD': [{'id': 'topic-1', 'name': 'AuDHD'}]}
        self.event_topics = [{'id': 'topic-1', 'name': 'AuDHD'}]

    def __call__(self, query, *, variables=None):
        self.calls.append((query, variables))
        if '__type' in query:
            typename = variables['typeName']
            connection = ref('OBJECT', 'TopicsConnection')
            edge_list = ref('LIST', child=ref('OBJECT', 'TopicEdge'))
            id_list = ref('LIST', child=ref('SCALAR', 'ID'))
            fields = {
                'Query': [
                    {'name': 'suggestTopics', 'type': connection,
                     'args': [{'name': 'query', 'type': ref('SCALAR', 'String')},
                              {'name': 'first', 'type': ref('SCALAR', 'Int')}]},
                    {'name': 'event', 'type': ref('OBJECT', 'Event'),
                     'args': [{'name': 'id', 'type': ref('SCALAR', 'ID')}]},
                ],
                'Mutation': [
                    {'name': 'createEvent', 'args': [{'name': 'input', 'type': ref('INPUT_OBJECT', 'CreateEventInput')}]},
                    {'name': 'editEvent', 'args': [{'name': 'input', 'type': ref('INPUT_OBJECT', 'EditEventInput')}]},
                ],
                'Event': [{'name': 'topics', 'type': connection}],
                'Topic': [{'name': 'id'}, {'name': 'name'}],
                'TopicsConnection': [{'name': 'edges', 'type': edge_list}],
                'TopicEdge': [{'name': 'node', 'type': ref('OBJECT', 'Topic')}],
                'CreateEventInput': [{'name': 'topics', 'type': id_list}],
                'EditEventInput': [{'name': 'topics', 'type': id_list}],
            }
            part = 'inputFields' if typename.endswith('Input') else 'fields'
            return {'data': {'__type': {part: fields[typename] if self.supported else []}}}
        if 'suggestTopics(' in query:
            rows = self.selections.get(variables['query'], [])
            return {'data': {'suggestTopics': {'edges': [{'node': row} for row in rows]}}}
        if 'event(id:' in query:
            if self.event_topics is None:
                return {'data': {'event': {'id': variables['id'], 'topics': None}}}
            rows = self.event_topics
            return {'data': {'event': {'id': variables['id'], 'topics': {
                'edges': [{'node': row} for row in rows]
            }}}}
        raise AssertionError('Unexpected provider operation')


class SourceTopicTests(unittest.TestCase):
    def test_schema_search_fresh_identity_and_exact_readback(self):
        graphql = SyntheticGraphQL()
        catalog = MeetupTopicCatalog(graphql)
        self.assertTrue(catalog.supported())
        self.assertEqual(catalog.search('AuDHD'), (Topic('topic-1', 'AuDHD'),))
        self.assertEqual(catalog.validate(canonical_topics([{'id': 'topic-1', 'name': 'AuDHD'}])),
                         ('topic-1',))
        self.assertEqual(catalog.readback('event-1'), ('topic-1',))
        graphql.selections['AuDHD'] = [{'id': 'topic-2', 'name': 'AuDHD'}]
        with self.assertRaisesRegex(TopicReviewRequired, r'^Provider topic identity or schema is unverified\.$'):
            catalog.validate((Topic('topic-1', 'AuDHD'),))

    def test_unverified_schema_and_bad_ids_fail_before_any_write(self):
        graphql = SyntheticGraphQL(supported=False)
        catalog = MeetupTopicCatalog(graphql)
        self.assertFalse(catalog.supported())
        with self.assertRaises(TopicReviewRequired):
            catalog.validate((Topic('topic-1', 'AuDHD'),))
        with self.assertRaises(TopicReviewRequired):
            canonical_topics([{'id': 'a', 'name': 'Name'}] * 2)
        with self.assertRaises(TopicReviewRequired):
            canonical_topics([{'id': str(i), 'name': 'Name'} for i in range(6)])
        self.assertFalse(any('suggestTopics(' in query for query, _ in graphql.calls))

    def test_cached_capability_is_revalidated_before_each_write(self):
        graphql = SyntheticGraphQL()
        catalog = MeetupTopicCatalog(graphql)
        self.assertTrue(catalog.supported())
        previous_queries = len(graphql.calls)
        graphql.supported = False
        with self.assertRaisesRegex(TopicReviewRequired, r'^Provider topic identity or schema is unverified\.$'):
            catalog.validate((Topic('topic-1', 'AuDHD'),))
        self.assertGreater(len(graphql.calls), previous_queries)
        self.assertFalse(any('suggestTopics(' in query for query, _ in graphql.calls))

    def test_partial_graphql_errors_fail_closed_even_with_data(self):
        graphql = SyntheticGraphQL()
        def partial(query, *, variables=None):
            response = graphql(query, variables=variables)
            if 'suggestTopics(' in query:
                response['errors'] = [{'message': 'synthetic partial error'}]
            return response
        catalog = MeetupTopicCatalog(partial)
        with self.assertRaisesRegex(TopicReviewRequired, r'^Provider topic identity or schema is unverified\.$'):
            catalog.validate((Topic('topic-1', 'AuDHD'),))
        self.assertNotIn('synthetic partial error', str(catalog._cache))
        def partial_schema(query, *, variables=None):
            response = graphql(query, variables=variables)
            response['errors'] = [{'message': 'synthetic schema error'}]
            return response
        self.assertFalse(MeetupTopicCatalog(partial_schema).supported())
        def partial_readback(query, *, variables=None):
            response = graphql(query, variables=variables)
            if 'event(id:' in query:
                response['errors'] = [{'message': 'synthetic partial readback'}]
            return response
        with self.assertRaisesRegex(TopicReviewRequired, r'^Provider topic identity or schema is unverified\.$'):
            MeetupTopicCatalog(partial_readback).readback('event-1')

    def test_catalog_outage_and_missing_event_readback_require_review(self):
        graphql = SyntheticGraphQL()
        catalog = MeetupTopicCatalog(graphql)
        graphql.selections['AuDHD'] = None
        with self.assertRaisesRegex(TopicReviewRequired, r'^Provider topic identity or schema is unverified\.$'):
            catalog.search('AuDHD')
        graphql.selections['AuDHD'] = [
            {'id': 'topic-1', 'name': 'AuDHD'},
            {'id': 'topic-1', 'name': 'Other'},
        ]
        with self.assertRaisesRegex(TopicReviewRequired, r'^Provider topic identity or schema is unverified\.$'):
            catalog.search('AuDHD')
        graphql.event_topics = None
        with self.assertRaisesRegex(TopicReviewRequired, r'^Provider topic identity or schema is unverified\.$'):
            catalog.readback('event-1')
