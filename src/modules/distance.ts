/**
 * Distance calculations using Haversine formula.
 * Walking distance = straight-line × 1.3 (Taiwan urban alley factor).
 */
import type { GeoPoint, Restaurant } from '../types/index.js';
import { geocode } from './geocoding.js';

const EARTH_RADIUS_KM = 6371;

/** Straight-line distance between two points in km. */
export function haversine(a: GeoPoint, b: GeoPoint): number {
  const dLat = ((b.lat - a.lat) * Math.PI) / 180;
  const dLng = ((b.lng - a.lng) * Math.PI) / 180;
  const sinDLat = Math.sin(dLat / 2);
  const sinDLng = Math.sin(dLng / 2);
  const h =
    sinDLat * sinDLat +
    Math.cos((a.lat * Math.PI) / 180) *
      Math.cos((b.lat * Math.PI) / 180) *
      sinDLng *
      sinDLng;
  return EARTH_RADIUS_KM * 2 * Math.asin(Math.sqrt(h));
}

/** Extract (lat, lng) from a Google Maps place URL like /@25.061,121.433,17z/ */
function extractCoordsFromMapsUrl(url: string): GeoPoint | null {
  const m = url.match(/@(-?\d+\.\d+),(-?\d+\.\d+)/);
  if (!m) return null;
  const lat = parseFloat(m[1]);
  const lng = parseFloat(m[2]);
  // Sanity: Taiwan range
  if (lat >= 21.5 && lat <= 26.5 && lng >= 119 && lng <= 122.5) {
    return { lat, lng };
  }
  return null;
}

/**
 * Calculate distances for all restaurants from userLocation.
 * Priority: GPS user_coords > ArcGIS geocoding.
 * Restaurant coords: Maps URL > ArcGIS geocoding.
 */
export async function calculateDistances(
  restaurants: Restaurant[],
  userLocation: string,
  userCoords?: { lat: number; lng: number } | null,
): Promise<Restaurant[]> {
  // Resolve user coordinates
  let userPoint: GeoPoint | null = null;

  if (userCoords) {
    userPoint = { lat: userCoords.lat, lng: userCoords.lng };
  } else {
    userPoint = await geocode(userLocation);
    if (!userPoint) {
      console.warn('[distance] Cannot geocode user location:', userLocation);
      return restaurants;
    }
  }

  const results: Restaurant[] = [];

  for (const r of restaurants) {
    // Priority 1: extract from Maps URL
    let restPoint: GeoPoint | null = r.maps_url
      ? extractCoordsFromMapsUrl(r.maps_url)
      : null;

    // Priority 2: geocode address
    if (!restPoint) {
      let addr = r.address || '';
      if (!addr || addr.endsWith('附近')) {
        addr = `${r.name} ${userLocation} 台灣`;
      } else if (!/[市縣區鎮鄉]/.test(addr)) {
        addr = `${addr} ${userLocation} 台灣`;
      }
      try {
        restPoint = await geocode(addr);
        // Reject geocoding results too far from user (>50 km → likely wrong city)
        if (restPoint && haversine(userPoint, restPoint) > 50) {
          restPoint = null;
        }
      } catch {
        restPoint = null;
      }
    }

    if (!restPoint) {
      results.push(r);
      continue;
    }

    const distKm = haversine(userPoint, restPoint);

    // Skip if distance < 20m (geocode hit the same point as user)
    if (distKm < 0.02) {
      results.push(r);
      continue;
    }

    const walkingKm = distKm * 1.3; // Taiwan urban alley factor
    const walkingMinutes = Math.max(1, Math.round((walkingKm / 4) * 60)); // 4 km/h

    results.push({
      ...r,
      distance_km: Math.round(distKm * 100) / 100,
      walking_distance:
        walkingKm < 1
          ? `${Math.round(walkingKm * 1000)}m`
          : `${walkingKm.toFixed(1)}km`,
      walking_minutes: walkingMinutes,
      _coords: [restPoint.lat, restPoint.lng],
    });
  }

  return results;
}
