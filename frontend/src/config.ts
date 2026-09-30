const env = import.meta.env;

/** api = REST-API van B pollen, voor als Firebase er (nog) niet is. */
type Source = 'mock' | 'firestore' | 'api';

const envSource: Source =
  env.VITE_DATA_SOURCE === 'firestore' ? 'firestore' : env.VITE_DATA_SOURCE === 'api' ? 'api' : 'mock';

// Plan B op de demodag: ?bron=demo schakelt zonder herstart over naar demodata, ?bron=live terug.
const override = new URLSearchParams(window.location.search).get('bron');
const liveSource: Source = envSource === 'mock' ? 'firestore' : envSource;
const dataSource: Source = override === 'demo' ? 'mock' : override === 'live' ? liveSource : envSource;

export const config = {
  dataSource,
  /** Echte data (Firestore of API) in plaats van demodata. */
  live: dataSource !== 'mock',
  overridden: dataSource !== envSource,
  apiBase: (env.VITE_API_BASE ?? 'http://localhost:8080').replace(/\/$/, ''),
  /** Basis-URL van de luisteraar (scripts/segment_collector.py); leeg = geen links in de kop. */
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

/** 'demo' = demodata, null = terug naar wat .env.local zegt. Herlaadt de pagina. */
export function switchSource(bron: 'demo' | null): void {
  const url = new URL(window.location.href);
  if (bron) url.searchParams.set('bron', bron);
  else url.searchParams.delete('bron');
  window.location.assign(url.toString());
}
