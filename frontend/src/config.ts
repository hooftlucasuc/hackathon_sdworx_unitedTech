const env = import.meta.env;

type Source = 'mock' | 'firestore';

const envSource: Source = env.VITE_DATA_SOURCE === 'firestore' ? 'firestore' : 'mock';

// Plan B op de demodag: ?bron=demo schakelt zonder herstart over naar demodata, ?bron=live terug.
const override = new URLSearchParams(window.location.search).get('bron');
const dataSource: Source = override === 'demo' ? 'mock' : override === 'live' ? 'firestore' : envSource;

export const config = {
  dataSource,
  overridden: dataSource !== envSource,
  apiBase: (env.VITE_API_BASE ?? 'http://localhost:8080').replace(/\/$/, ''),
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
