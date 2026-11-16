"""Synthetic schema fixture ported from source test_meetup_topic_recommendations.py."""
def ref(kind, name=None, child=None):
    return {'kind': kind, 'name': name, 'ofType': child}


class SyntheticGraphQL:
    def __init__(self, supported=True):
        self.supported = supported
        self.calls = []
        self.selections = {}

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
                    {'name': 'createEvent',
                     'args': [{'name': 'input', 'type': ref('INPUT_OBJECT', 'CreateEventInput')}]},
                    {'name': 'editEvent',
                     'args': [{'name': 'input', 'type': ref('INPUT_OBJECT', 'EditEventInput')}]},
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
        raise AssertionError('Unexpected provider operation')
