/**
 * CWB (Central Weather Bureau) weather API integration.
 * Fetches real-time observation + 3-hour rain probability for Taiwan.
 */
import type { WeatherData } from '../types/index.js';
import { calculateSweatIndex } from './sweat-index.js';
import { cacheKey, cacheGet, cacheSet } from './cache.js';

const CWB_BASE = 'https://opendata.cwa.gov.tw/api/v1/rest/datastore';

// API configuration: city name → F-D0047 code
const CITY_CWB_CODE: Record<string, string> = {
  '宜蘭縣': '001', '桃園市': '005', '新竹縣': '009', '苗栗縣': '013',
  '彰化縣': '017', '南投縣': '021', '雲林縣': '025', '嘉義縣': '029',
  '屏東縣': '033', '臺東縣': '037', '台東縣': '037', '花蓮縣': '041',
  '澎湖縣': '045', '基隆市': '049', '新竹市': '053', '嘉義市': '057',
  '臺北市': '061', '台北市': '061', '高雄市': '065', '新北市': '069',
  '臺中市': '073', '台中市': '073', '臺南市': '077', '台南市': '077',
  '連江縣': '081', '金門縣': '085',
};

// City → main township for rain probability
const CITY_MAIN_TOWN: Record<string, string> = {
  '台北市': '中正區', '臺北市': '中正區', '新北市': '板橋區',
  '桃園市': '桃園區', '台中市': '西屯區', '臺中市': '西屯區',
  '台南市': '中西區', '臺南市': '中西區', '高雄市': '三民區',
  '基隆市': '仁愛區', '新竹市': '東區', '嘉義市': '東區',
  '宜蘭縣': '宜蘭市', '新竹縣': '竹北市', '苗栗縣': '苗栗市',
  '彰化縣': '彰化市', '南投縣': '南投市', '雲林縣': '斗六市',
  '嘉義縣': '太保市', '屏東縣': '屏東市', '花蓮縣': '花蓮市',
  '台東縣': '台東市', '臺東縣': '台東市', '澎湖縣': '馬公市',
  '金門縣': '金城鎮', '連江縣': '南竿鄉',
};

function apiKey(): string {
  return process.env.CWB_API_KEY || '';
}

interface ObsStation {
  StationName?: string;
  GeoInfo?: { Coordinates?: Array<{ CoordinateName: string; StationLatitude: string; StationLongitude: string }> };
  WeatherElement?: { AirTemperature?: string; RelativeHumidity?: string; WindSpeed?: string };
  ObsTime?: { DateTime?: string };
}

function distKm(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLng = ((lng2 - lng1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLng / 2) ** 2;
  return R * 2 * Math.asin(Math.sqrt(a));
}

async function fetchObservation(lat: number, lng: number): Promise<Partial<WeatherData>> {
  const url = `${CWB_BASE}/O-A0003-001?Authorization=${apiKey()}&elementName=TEMP,HUMD,WDSD&parameterName=LAT,LON`;
  const res = await fetch(url, { signal: AbortSignal.timeout(8000) });
  if (!res.ok) throw new Error(`CWB obs API ${res.status}`);
  const data = await res.json() as { records?: { Station?: ObsStation[] } };
  const stations = data.records?.Station ?? [];

  let minDist = Infinity;
  let best: Partial<WeatherData> | null = null;

  for (const station of stations) {
    const coords = station.GeoInfo?.Coordinates ?? [];
    const wgs = coords.find((c) => c.CoordinateName === 'WGS84');
    if (!wgs) continue;
    const sLat = parseFloat(wgs.StationLatitude);
    const sLng = parseFloat(wgs.StationLongitude);
    if (isNaN(sLat) || isNaN(sLng)) continue;

    const el = station.WeatherElement ?? {};
    const temp = parseFloat(el.AirTemperature ?? '');
    const humidity = parseFloat(el.RelativeHumidity ?? '');
    const wind = parseFloat(el.WindSpeed ?? '');

    if (isNaN(temp) || temp < -90 || isNaN(humidity) || humidity < 0) continue;

    const d = distKm(lat, lng, sLat, sLng);
    if (d < minDist && d <= 200) {
      minDist = d;
      best = {
        temperature: temp,
        humidity: humidity,
        wind_speed: isNaN(wind) || wind < -90 ? 0 : wind,
        station_name: station.StationName,
      };
    }
  }
  return best ?? {};
}

async function fetchRainProbability(cityName: string): Promise<number | null> {
  const code = CITY_CWB_CODE[cityName];
  if (!code) return null;
  const townName = CITY_MAIN_TOWN[cityName];
  if (!townName) return null;

  const url = `${CWB_BASE}/F-D0047-${code}?Authorization=${apiKey()}&format=JSON`;
  const res = await fetch(url, { signal: AbortSignal.timeout(8000) });
  if (!res.ok) return null;
  const data = await res.json() as { records?: { Locations?: Array<{ Location?: Array<{ LocationName?: string; WeatherElement?: Array<{ ElementName?: string; Time?: Array<{ StartTime?: string; ElementValue?: Array<{ ProbabilityOfPrecipitation?: string }> }> }> }> }> } };

  const locations = data.records?.Locations?.[0]?.Location ?? [];
  const loc = locations.find((l) => l.LocationName === townName);
  if (!loc) return null;

  const el = (loc.WeatherElement ?? []).find((e) => e.ElementName === '3小時降雨機率');
  if (!el?.Time?.length) return null;

  // Find closest time entry
  const now = Date.now();
  let minDiff = Infinity;
  let pop: string | null = null;
  for (const t of el.Time) {
    if (!t.StartTime) continue;
    try {
      const diff = Math.abs(new Date(t.StartTime).getTime() - now);
      if (diff < minDiff) {
        minDiff = diff;
        pop = t.ElementValue?.[0]?.ProbabilityOfPrecipitation ?? null;
      }
    } catch { /* ignore */ }
  }
  return pop && pop !== 'N/A' ? parseInt(pop, 10) : null;
}

/**
 * Get weather data for a location name.
 * Uses ArcGIS geocoding to get coordinates, then CWB API.
 */
export async function getWeather(
  location: string,
  coords?: { lat: number; lng: number } | null,
): Promise<WeatherData | null> {
  const ck = cacheKey('weather', location);
  const cached = cacheGet<WeatherData>(ck, 'weather');
  if (cached) return cached;

  const cwbKey = apiKey();
  if (!cwbKey) {
    console.warn('[weather] CWB_API_KEY not set — skipping weather');
    return null;
  }

  // Get coordinates
  let lat: number, lng: number;
  let cityName: string | null = null;

  if (coords) {
    lat = coords.lat;
    lng = coords.lng;
  } else {
    const { geocode, reverseGeocode } = await import('./geocoding.js');
    const point = await geocode(location);
    if (!point) return null;
    lat = point.lat;
    lng = point.lng;
    cityName = await reverseGeocode(lat, lng);
  }

  if (!cityName && !coords) {
    const { reverseGeocode } = await import('./geocoding.js');
    cityName = await reverseGeocode(lat, lng);
  }

  try {
    const obs = await fetchObservation(lat, lng);
    if (!obs.temperature) return null;

    let rainProb: number | null = null;
    if (cityName) {
      try {
        rainProb = await fetchRainProbability(cityName);
      } catch { /* non-fatal */ }
    }

    const weather: WeatherData = {
      temperature: obs.temperature ?? null,
      humidity: obs.humidity ?? null,
      wind_speed: obs.wind_speed ?? null,
      rain_probability: rainProb,
      station_name: obs.station_name,
    };
    weather.sweat_index = calculateSweatIndex(weather);

    cacheSet(ck, 'weather', weather);
    return weather;
  } catch (e) {
    console.warn('[weather] Failed:', e);
    return null;
  }
}
