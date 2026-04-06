/**
 * Sweat index calculation from temperature, humidity, wind speed.
 * Index scale: 0 (comfortable) to 10 (extremely hot/humid).
 */
import type { WeatherData } from '../types/index.js';

/**
 * Calculate sweat index (0–10) from weather data.
 * Based on apparent temperature with humidity and wind adjustments.
 */
export function calculateSweatIndex(weather: WeatherData): number {
  const temp = weather.temperature ?? 25;
  const humidity = weather.humidity ?? 60;
  const wind = weather.wind_speed ?? 0;

  // Apparent temperature (simplified Steadman formula)
  const e = (humidity / 100) * 6.105 * Math.exp((17.27 * temp) / (237.7 + temp));
  const apparent = temp + 0.33 * e - 0.7 * wind - 4;

  // Convert to 0–10 index
  // <18°C → 0-2 (comfortable), 18-24 → 3-4, 24-28 → 5-6, 28-32 → 7-8, >32 → 9-10
  let index: number;
  if (apparent < 18) {
    index = Math.max(0, Math.round(apparent / 9));
  } else if (apparent < 24) {
    index = 3 + Math.round(((apparent - 18) / 6) * 2);
  } else if (apparent < 28) {
    index = 5 + Math.round(((apparent - 24) / 4));
  } else if (apparent < 32) {
    index = 7 + Math.round(((apparent - 28) / 4));
  } else {
    index = Math.min(10, 9 + Math.round((apparent - 32) / 4));
  }

  return Math.min(10, Math.max(0, index));
}

/**
 * Determine max walking distance (km) based on weather.
 * Hot / rainy → shorter radius.
 */
export function getMaxDistanceKm(
  sweatIndex: number | null,
  rainProbability: number | null,
): { maxKm: number; reason: string } {
  const si = sweatIndex ?? 5;
  const rain = rainProbability ?? 0;

  if (si >= 7 || rain >= 50) {
    const why = si >= 7
      ? `流汗指數 ${si} (不舒適)，步行5分鐘內 (400m)`
      : `降雨機率 ${rain}%，步行5分鐘內 (400m)`;
    return { maxKm: 0.4, reason: why };
  }
  if (si >= 5) {
    return { maxKm: 0.6, reason: `流汗指數 ${si} (普通)，步行8分鐘內 (600m)` };
  }
  return { maxKm: 0.8, reason: '舒適天氣，步行10分鐘內 (800m)' };
}
