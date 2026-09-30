import { useEffect, useState } from 'react';
import type { Call, Caller, Company, Solution, Unsub } from '../types';
import { source } from './index';

/** undefined = still loading (or no id). */
function useWatch<T>(make: ((cb: (v: T) => void) => Unsub) | null, key: string): T | undefined {
  const [value, setValue] = useState<T | undefined>(undefined);
  useEffect(() => {
    setValue(undefined);
    if (!make) return;
    return make(setValue);
    // key sums up what make depends on
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return value;
}

export const useRecentCalls = (n: number) =>
  useWatch<Call[]>((cb) => source.watchRecentCalls(n, cb), `recent:${n}`);

export const useCall = (id: string | null) =>
  useWatch<Call | null>(id ? (cb) => source.watchCall(id, cb) : null, `call:${id}`);

export const useCaller = (id: string | null | undefined) =>
  useWatch<Caller | null>(id ? (cb) => source.watchCaller(id, cb) : null, `caller:${id}`);

export const useCompany = (id: string | null | undefined) =>
  useWatch<Company | null>(id ? (cb) => source.watchCompany(id, cb) : null, `company:${id}`);

export const useCallsBy = (field: 'caller_id' | 'company_id', id: string | null | undefined) =>
  useWatch<Call[]>(id ? (cb) => source.watchCallsBy(field, id, cb) : null, `${field}:${id}`);

export const useSolutions = (ids: string[]) =>
  useWatch<Record<string, Solution>>(
    ids.length ? (cb) => source.watchSolutions(ids, cb) : null,
    `solutions:${ids.join('|')}`,
  );
