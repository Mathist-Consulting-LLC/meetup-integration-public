import { createGraphql, MeetupProviderError, providerErrorCode } from './provider-transport.js';
const TYPE_REF = 'kind name ofType { kind name ofType { kind name ofType { kind name } } }';

export function createMeetupTopicProvider({ clock = Date.now, ...options } = {}) {
  const graphql = createGraphql({ clock, ...options });
  return {
    probe: async (controls = {}) => {
      try {
        controls = { ...controls, deadline: Math.min(controls.deadline ?? Infinity, clock() + (options.timeoutMs ?? 15000)) };
        // Meetup rejects a single query that repeats __Type.fields many times, so
        // inspect each type independently and combine only the safe results.
        const inspect = async (name, part = 'fields') => {
          const args = part === 'fields' ? `args { name type { ${TYPE_REF} } }` : '';
          const data = await graphql(`query($name: String!) { __type(name: $name) { ${part} { name type { ${TYPE_REF} } ${args} } } }`, { name }, controls);
          if (!data.__type || !Array.isArray(data.__type[part])
            || data.__type[part].length > 1000
            || data.__type[part].some(item => !item || typeof item.name !== 'string' || !item.type
              || (item.args !== undefined && (!Array.isArray(item.args) || item.args.some(arg => !arg || typeof arg.name !== 'string' || !arg.type))))) throw new MeetupProviderError('schema_unsupported');
          return { [part]: data.__type[part] };
        };
        const [queryType, mutationType, eventType, topicType, connectionType, edgeType, createType, editType] = [
          await inspect('Query'), await inspect('Mutation'), await inspect('Event'), await inspect('Topic'),
          await inspect('TopicsConnection'), await inspect('TopicEdge'), await inspect('CreateEventInput', 'inputFields'),
          await inspect('EditEventInput', 'inputFields')
        ];
        const fields = (value, key = 'fields') => new Map((value?.[key] || []).map((item) => [item.name, item]));
        const named = (ref) => { while (ref?.ofType) { if (ref.name) return ref.name; ref = ref.ofType; } return ref?.name || ''; };
        const isListOf = (ref, name) => { while (ref?.kind === 'NON_NULL') ref = ref.ofType; return ref?.kind === 'LIST' && named(ref.ofType) === name; };
        const queryFields = fields(queryType), mutationFields = fields(mutationType);
        const eventFields = fields(eventType), topicFields = fields(topicType);
        const connectionFields = fields(connectionType), edgeFields = fields(edgeType);
        const createFields = fields(createType, 'inputFields'), editFields = fields(editType, 'inputFields');
        const topics = queryFields.get('suggestTopics');
        const topicArgs = new Map((topics?.args || []).map((item) => [item.name, item]));
        const eventArgs = new Map((queryFields.get('event')?.args || []).map((item) => [item.name, item]));
        const createArgs = new Map((mutationFields.get('createEvent')?.args || []).map((item) => [item.name, item]));
        const editArgs = new Map((mutationFields.get('editEvent')?.args || []).map((item) => [item.name, item]));
        const verified = named(topics?.type) === 'TopicsConnection' && named(topicArgs.get('query')?.type) === 'String'
          && named(queryFields.get('event')?.type) === 'Event' && named(eventArgs.get('id')?.type) === 'ID'
          && named(createArgs.get('input')?.type) === 'CreateEventInput' && named(editArgs.get('input')?.type) === 'EditEventInput'
          && named(eventFields.get('topics')?.type) === 'TopicsConnection'
          && isListOf(connectionFields.get('edges')?.type, 'TopicEdge') && named(edgeFields.get('node')?.type) === 'Topic'
          && topicFields.has('id') && topicFields.has('name')
          && isListOf(createFields.get('topics')?.type, 'ID') && isListOf(editFields.get('topics')?.type, 'ID');
        return {
          provenance: 'authenticated_introspection', searchSupported: verified, readbackSupported: verified,
          createSupported: verified, editSupported: verified, expiresAt: new Date(clock() + 240000).toISOString()
        };
      } catch (error) {
        throw new MeetupProviderError(providerErrorCode(error, 'schema_unsupported'));
      }
    },
    search: async (term, controls = {}) => {
      if (typeof term !== 'string' || term.length > 100) throw new MeetupProviderError('invalid_request');
      const data = await graphql('query($query: String!, $first: Int!) { suggestTopics(query: $query, first: $first, excludeMemberTopics: false) { edges { node { id name } } } }', { query: String(term).slice(0, 100), first: 20 }, controls);
      const edges = data.suggestTopics?.edges;
      if (!Array.isArray(edges) || edges.length > 20 || edges.some(edge => !edge?.node || typeof edge.node.id !== 'string' || !edge.node.id.trim() || edge.node.id.length > 128 || typeof edge.node.name !== 'string' || !edge.node.name.trim() || edge.node.name.length > 160)) throw new MeetupProviderError('response_invalid');
      return edges.map(edge => ({ id: edge.node.id.trim(), name: edge.node.name.trim() }));
    }
  };
}
