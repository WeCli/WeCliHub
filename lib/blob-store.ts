/**
 * Vercel Blob persistent storage layer.
 *
 * When running on Vercel (VERCEL=1), hub_meta.json and star_records.json are
 * stored in Vercel Blob Storage so they survive across serverless cold starts.
 *
 * Requires the BLOB_READ_WRITE_TOKEN environment variable to be set in your
 * Vercel project settings. You can create a Blob store from the Vercel
 * dashboard → Storage → Create → Blob.
 */

import { get, put } from "@vercel/blob";

const IS_VERCEL = process.env.VERCEL === "1";
const BLOB_ACCESS_ENV = process.env.CLAWCROSSHUB_BLOB_ACCESS ?? process.env.FLOWHUB_BLOB_ACCESS;
const BLOB_ACCESS: "public" | "private" = BLOB_ACCESS_ENV === "public" ? "public" : "private";

// In-memory cache to avoid redundant Blob fetches within the same invocation
const cache = new Map<string, { data: unknown; ts: number }>();
const CACHE_TTL_MS = 5_000; // 5 seconds

/**
 * Load a JSON file from Vercel Blob.
 * Returns `null` if the blob does not exist yet.
 */
export async function loadJsonFromBlob<T = unknown>(key: string): Promise<T | null> {
  if (!IS_VERCEL) return null;

  // Check in-memory cache first
  const cached = cache.get(key);
  if (cached && Date.now() - cached.ts < CACHE_TTL_MS) {
    return cached.data as T;
  }

  const tryLoad = async (access: "public" | "private"): Promise<T | null> => {
    const result = await get(key, { access, useCache: false });
    if (!result || result.statusCode !== 200 || !result.stream) {
      return null;
    }

    const raw = await new Response(result.stream).text();
    const data = JSON.parse(raw) as T;
    cache.set(key, { data, ts: Date.now() });
    return data;
  };

  try {
    const primary = await tryLoad(BLOB_ACCESS);
    if (primary) return primary;

    // Backward compatibility: migrate existing public objects to private mode.
    if (BLOB_ACCESS === "private") {
      return await tryLoad("public");
    }
    return null;
  } catch {
    return null;
  }
}

/**
 * Save a JSON value to Vercel Blob.
 * Overwrites any existing blob with the same key.
 */
export async function saveJsonToBlob(key: string, data: unknown): Promise<void> {
  if (!IS_VERCEL) return;

  const body = JSON.stringify(data, null, 2);
  await put(key, body, {
    access: BLOB_ACCESS,
    allowOverwrite: true,
    contentType: "application/json",
    addRandomSuffix: false,
  });

  // Update in-memory cache
  cache.set(key, { data, ts: Date.now() });
}

/**
 * Check if we are running on Vercel with Blob storage available.
 */
export function isBlobAvailable(): boolean {
  return IS_VERCEL && Boolean(process.env.BLOB_READ_WRITE_TOKEN);
}
