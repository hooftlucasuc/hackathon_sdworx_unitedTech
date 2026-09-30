import { config } from '../config';
import type { DataSource } from '../types';
import { createFirestoreSource } from './firestore';
import { mockSource } from './mock';

export const source: DataSource = config.dataSource === 'firestore' ? createFirestoreSource() : mockSource;
