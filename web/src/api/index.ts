/**
 * The API layer. Feature code imports from '@/api':
 *   - hooks (useRecordings, useRoutes, …) for reads and mutations
 *   - fetch functions (fetchAudioLink, fetchExportMarkdown, …) for one-off calls
 *   - types (Recording, Transcript, …) and schemas
 *   - errorMessage(err, fallback) to turn any failure into user words
 * See src/api/README.md.
 */
export * from './client';
export * from './types';
export * from './keys';
export * from './token';
export * from './hooks';
export { createQueryClient } from './queryClient';
