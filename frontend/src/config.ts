const env = import.meta.env;

/** api = REST-API van B pollen, voor als Firebase er (nog) niet is. */
type Source = 'mock' | 'firestore' | 'api';

const envSource: Source =
  env.VITE_DATA_SOURCE === 'firestore' ? 'firestore' : env.VITE_DATA_SOURCE === 'api' ? 'api' : 'mock';

// Plan B on demo day: ?source=demo switches to demo data without a restart, ?source=live switches back.
// ?bron= (the earlier Dutch name) still works.
const params = new URLSearchParams(window.location.search);
const override = params.get('source') ?? params.get('bron');
const liveSource: Source = envSource === 'mock' ? 'firestore' : envSource;
const dataSource: Source = override === 'demo' ? 'mock' : override === 'live' ? liveSource : envSource;

export const config = {
  dataSource,
  /** Echte data (Firestore of API) in plaats van demodata. */
  live: dataSource !== 'mock',
  overridden: dataSource !== envSource,
  // docs/backend.md calls it VITE_API_URL, the Dockerfile VITE_API_BASE: accept both.
  apiBase: ((env.VITE_API_URL as string | undefined) || env.VITE_API_BASE || 'http://localhost:8080').replace(/\/$/, ''),
  /** Base URL of the listener (scripts/segment_collector.py); empty = no links in the header. */
  listenerUrl: ((env.VITE_LISTENER_URL as string | undefined) ?? '').replace(/\/$/, ''),
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
