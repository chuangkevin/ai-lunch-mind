/**
 * ArcGIS geocoding — converts place names / addresses to lat/lng.
 * Replaces Python's geopy.geocoders.ArcGIS usage.
 */
import { cacheKey, cacheGet, cacheSet } from './cache.js';
import type { GeoPoint } from '../types/index.js';

const ARCGIS_GEOCODE_URL =
  'https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates';
const ARCGIS_REVERSE_URL =
  'https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/reverseGeocode';

interface ArcGISCandidate {
  address: string;
  location: { x: number; y: number };
  score: number;
  attributes?: Record<string, string>;
}

interface ArcGISResponse {
  candidates?: ArcGISCandidate[];
}

interface ArcGISReverseResponse {
  address?: {
    City?: string;
    Region?: string;
    Subregion?: string;
    CountryCode?: string;
  };
}

/** Geocode a place name / address to [lat, lng]. Returns null if not found. */
export async function geocode(
  address: string,
  countryCode = 'TWN',
): Promise<GeoPoint | null> {
  const key = cacheKey('geocode', address);
  const cached = cacheGet<GeoPoint>(key, 'geocoding');
  if (cached) return cached;

  const variants = [
    address,
    `${address} 台灣`,
    `${address} Taiwan`,
  ];

  for (const variant of variants) {
    const params = new URLSearchParams({
      SingleLine: variant,
      f: 'json',
      outFields: 'City,Region,Country',
      outSR: '4326',
      countryCode,
      maxLocations: '1',
    });
    try {
      const res = await fetch(`${ARCGIS_GEOCODE_URL}?${params}`, { signal: AbortSignal.timeout(5000) });
      if (!res.ok) continue;
      const data = (await res.json()) as ArcGISResponse;
      const candidate = data.candidates?.[0];
      if (candidate && candidate.score >= 50) {
        const point: GeoPoint = { lat: candidate.location.y, lng: candidate.location.x };
        // Sanity: Taiwan range
        if (point.lat >= 21 && point.lat <= 26.5 && point.lng >= 118 && point.lng <= 122.5) {
          cacheSet(key, 'geocoding', point);
          return point;
        }
      }
    } catch {
      // Try next variant
    }
  }
  return null;
}

/** Reverse geocode lat/lng to a city name (Chinese). */
export async function reverseGeocode(lat: number, lng: number): Promise<string | null> {
  const key = cacheKey('rgeocode', lat.toFixed(3), lng.toFixed(3));
  const cached = cacheGet<string>(key, 'geocoding');
  if (cached) return cached;

  try {
    const params = new URLSearchParams({
      location: `${lng},${lat}`,
      f: 'json',
      featureTypes: 'City,Subregion,Region',
    });
    const res = await fetch(`${ARCGIS_REVERSE_URL}?${params}`, { signal: AbortSignal.timeout(5000) });
    if (!res.ok) return null;
    const data = (await res.json()) as ArcGISReverseResponse;
    const city = data.address?.City || data.address?.Subregion || data.address?.Region || null;
    if (city) {
      cacheSet(key, 'geocoding', city);
      return city;
    }
  } catch {
    // ignore
  }
  return null;
}
