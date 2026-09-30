import { config } from '../config';
import type { DataSource } from '../types';
import { createFirestoreSource } from './firestore';
import { mockSource } from './mock';
import { createRestSource } from './rest';

export const source: DataSource =
  config.dataSource === 'firestore'
    ? createFirestoreSource()
    : config.dataSource === 'api'
      ? createRestSource()
      : mockSource;
