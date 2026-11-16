import { createGraphql, MeetupProviderError } from './provider-transport.js';

export function createMeetupGroupResolver(options = {}) {
  const graphql = createGraphql({ timeoutMs: 5000, ...options });
  return async (urlName, controls = {}) => {
    const normalized = normalizeMeetupUrlName(urlName);
    if (!normalized) throw new MeetupProviderError('invalid_request');
    const data = await graphql('query($urlname: String!) { groupByUrlname(urlname: $urlname) { id name urlname } }', { urlname: normalized }, controls);
    if (!Object.hasOwn(data, 'groupByUrlname')) throw new MeetupProviderError('response_invalid');
    if (data.groupByUrlname === null) return null;
    if (typeof data.groupByUrlname?.id !== 'string' || data.groupByUrlname.id.length > 128) {
      throw new MeetupProviderError('response_invalid');
    }
    const group = normalizeMeetupGroupResult(data.groupByUrlname);
    if (!group || group.urlName !== normalized) throw new MeetupProviderError('response_invalid');
    return group;
  };
}

export function normalizeMeetupGroupResult(group) {
  try {
    if (!group || typeof group !== 'object' || Array.isArray(group)) return null;
    const id = optionalString(group.id);
    const urlName = normalizeMeetupUrlName(group.urlname || group.urlName || group.url_name);
    if (!id || !urlName) return null;
    return {
      id,
      name: optionalString(group.name) || '',
      urlName,
      url: normalizeMeetupGroupUrl(group.link || group.url || group.groupUrl || '', urlName)
    };
  } catch { return null; }
}

export function normalizeMeetupUrlName(value) {
  try {
    let normalized = optionalString(value)?.toLowerCase();
    if (!normalized) return '';
    if (/^https?:\/\//.test(normalized)) {
      try {
        const url = new URL(normalized);
        if (!['meetup.com', 'www.meetup.com'].includes(url.hostname) || url.username || url.password || url.port) return '';
        const parts = url.pathname.split('/').filter(Boolean);
        if (parts.length !== 1) return '';
        normalized = parts[0];
      } catch { return ''; }
    } else normalized = normalized.replace(/^\/+|\/+$/g, '');
    if (!/^[a-z0-9][a-z0-9_-]{0,99}$/.test(normalized) || ['pro', 'events', 'home'].includes(normalized)) return '';
    return normalized;
  } catch { return ''; }
}

function normalizeMeetupGroupUrl(value, urlName) {
  const text = optionalString(value);
  if (text) {
    try {
      const url = new URL(text);
      if (url.protocol === 'https:' && /(^|\.)meetup\.com$/i.test(url.hostname)
        && !url.username && !url.password && !url.port) {
        return url.toString();
      }
    } catch {
      // Fall back to the canonical public group URL below.
    }
  }
  return `https://www.meetup.com/${urlName}/`;
}

function optionalString(value) {
  if (value === undefined || value === null) return '';
  const text = String(value).trim();
  return text || '';
}
