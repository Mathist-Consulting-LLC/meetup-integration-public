import { MeetupProviderError } from './provider-transport.js';

export function normalizeMeetupTokenResponse(result, now = Date.now()) {
  try {
    if (!result || typeof result !== 'object' || Array.isArray(result) ||
        !['access_token', 'refresh_token', 'expires_in'].every(key => Object.hasOwn(result, key)) ||
        !Number.isSafeInteger(now) ||
        typeof result.access_token !== 'string' || !result.access_token.trim() ||
        typeof result.refresh_token !== 'string' || !result.refresh_token.trim() ||
        !['number', 'string'].includes(typeof result.expires_in) ||
        !Number.isFinite(Number(result.expires_in)) || Number(result.expires_in) <= 60 ||
        (result.token_type !== undefined && (typeof result.token_type !== 'string' || result.token_type.toLowerCase() !== 'bearer'))) throw new MeetupProviderError('authentication_unavailable');
    const expiresAt = now + Number(result.expires_in) * 1000;
    if (!Number.isSafeInteger(expiresAt)) throw new MeetupProviderError('authentication_unavailable');
    return { accessToken: result.access_token, refreshToken: result.refresh_token, expiresAt };
  } catch {
    throw new MeetupProviderError('authentication_unavailable');
  }
}
