const env = import.meta.env;

type Source = 'mock' | 'firestore';

const envSource: Source = env.VITE_DATA_SOURCE === 'firestore' ? 'firestore' : 'mock';

// Plan B on demo day: ?source=demo switches to demo data without a restart, ?source=live switches back.
// ?bron= (the earlier Dutch name) still works.
const params = new URLSearchParams(window.location.search);
const override = params.get('source') ?? params.get('bron');
const dataSource: Source = override === 'demo' ? 'mock' : override === 'live' ? 'firestore' : envSource;

export const config = {
  dataSource,
  overridden: dataSource !== envSource,
  // docs/backend.md calls it VITE_API_URL, the Dockerfile VITE_API_BASE: accept both.
  apiBase: ((env.VITE_API_URL as string | undefined) || env.VITE_API_BASE || 'http://localhost:8080').replace(/\/$/, ''),
  demoMode: env.VITE_DEMO_MODE === 'true',
  anonAuth: env.VITE_FIREBASE_ANON_AUTH === 'true',
  firebase: {
    apiKey: env.VITE_FIREBASE_API_KEY as string | undefined,
    authDomain: env.VITE_FIREBASE_AUTH_DOMAIN as string | undefined,
    projectId: env.VITE_FIREBASE_PROJECT_ID as string | undefined,
    appId: env.VITE_FIREBASE_APP_ID as string | undefined,
  },
};

/** 'demo' = demo data, null = back to what .env.local says. Reloads the page. */
export function switchSource(source: 'demo' | null): void {
  const url = new URL(window.location.href);
  url.searchParams.delete('bron');
  if (source) url.searchParams.set('source', source);
  else url.searchParams.delete('source');
  window.location.assign(url.toString());
}
