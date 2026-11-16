import { MeetupProviderError, providerErrorCode } from './provider-transport.js';

export function createMeetupTopicCatalog({ probe, search, ttlMs = 300_000, clock = Date.now } = {}) {
  let cached = null;
  let expiresAt = 0;
  const unavailable = (reason, extra = {}) => ({
    supported: false, manualReviewRequired: true, reason, state: 'unsupported',
    topics: [], recommendations: [],
    provenance: 'unverified', expiresAt: null, maxTopics: 5,
    ...extra
  });
  const capability = async (controls) => {
    if (!probe || !search) return { ok: false, result: unavailable('authenticated_topic_schema_not_verified') };
    if (!cached || clock() >= expiresAt) {
      cached = await probe(controls);
      expiresAt = clock() + Math.min(Math.max(1, ttlMs), 300_000);
    }
    if (cached?.provenance !== 'authenticated_introspection'
      || cached?.searchSupported !== true || cached?.readbackSupported !== true
      || cached?.createSupported !== true || cached?.editSupported !== true
      || !Number.isFinite(Date.parse(cached.expiresAt))
      || Date.parse(cached.expiresAt) <= clock()) {
      return { ok: false, result: unavailable('event_topic_schema_unsupported_or_stale') };
    }
    return { ok: true, value: cached };
  };
  const providerSearch = async (term, { groupId = '', signal, capability } = {}) => {
    const results = await search(term, { groupId: String(groupId).slice(0, 128), capability, signal });
    if (!Array.isArray(results)) throw new Error('invalid topic search result');
    return canonicalProviderTopics(results, 50);
  };
  return {
    async search(query, { groupId = '', signal, fresh = false } = {}) {
      try {
        const term = String(query || '').trim();
        if (term.length > 100) return unavailable('topic_search_query_too_long');
        if (fresh) { cached = null; expiresAt = 0; }
        const status = await capability({ signal });
        if (!status.ok) return status.result;
        const topics = await providerSearch(term, { groupId, signal, capability: status.value });
        if (Date.parse(status.value.expiresAt) <= clock()) return unavailable('event_topic_schema_unsupported_or_stale');
        return { supported: true, manualReviewRequired: false, reason: null, topics,
          state: 'ok', provenance: 'authenticated_introspection', expiresAt: status.value.expiresAt, maxTopics: 5 };
      } catch (error) {
        // Never return stale selections as if provider validation succeeded.
        cached = null;
        expiresAt = 0;
        return unavailable('topic_search_failed', {
          errorCode: providerErrorCode(error, 'response_invalid')
        });
      }
    },
    async validate(topics, { signal } = {}) {
      try {
        if (!Array.isArray(topics) || topics.length > 5
          || canonicalProviderTopics(topics, 5).length !== topics.length) {
          throw new MeetupProviderError('invalid_request');
        }
        cached = null;
        expiresAt = 0;
        const status = await capability({ signal });
        if (!status.ok) throw new MeetupProviderError('schema_unsupported');
        const canonical = canonicalProviderTopics(topics, 5);
        for (const topic of canonical) {
          const results = await providerSearch(topic.name.slice(0, 100), { signal, capability: status.value });
          if (!results.some(result => result.id === topic.id && result.name === topic.name)) {
            throw new MeetupProviderError('response_invalid');
          }
        }
        if (Date.parse(status.value.expiresAt) <= clock()) throw new MeetupProviderError('schema_unsupported');
        return canonical;
      } catch (error) {
        throw new MeetupProviderError(providerErrorCode(error, 'response_invalid'));
      }
    },
  };
}

function canonicalProviderTopics(results, maxResults) {
  const seen = new Set();
  const topics = [];
  for (const topic of results.slice(0, maxResults)) {
    const id = typeof topic?.id === 'string' ? topic.id.trim() : '';
    const name = typeof topic?.name === 'string' ? topic.name.trim() : '';
    if (!id || !name || seen.has(id) || id.length > 128 || name.length > 160) continue;
    seen.add(id);
    topics.push({ id, name });
  }
  return topics;
}
