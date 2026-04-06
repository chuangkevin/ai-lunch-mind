// Shared TypeScript types for AI Lunch Mind

export interface Budget {
  min?: number | null;
  max?: number | null;
  currency: string;
}

export interface SocialProof {
  platforms: string[];
  mentions: Array<{ platform: string; url: string }>;
  count: number;
}

/** Snake_case to match existing frontend field names */
export interface Restaurant {
  name: string;
  address: string;
  rating: number | null;
  rating_count?: number | null;
  price_level: string | null;
  estimated_price?: string | null;
  maps_url: string;
  food_type: string;
  source: 'google_maps' | 'uber_eats';
  open_now: boolean | null;
  hours_status: string;
  distance_km: number | null;
  walking_distance: string;
  walking_minutes: number | null;
  uber_eats_url?: string;
  uber_eats_eta?: string;
  uber_eats_rating?: number | null;
  ai_reason?: string;
  social_proof?: SocialProof | null;
  relevance_score?: number;
  _coords?: [number, number];
}

export interface Intent {
  location: string | null;
  primary_keywords: string[];
  secondary_keywords: string[];
  budget: Budget | null;
  estimated_price_range: string;
  search_radius_hint: string;
  intent: string;
  weather_hints: string[];
  raw_input: string;
  _source: string;
}

export interface WeatherData {
  temperature: number | null;
  humidity: number | null;
  wind_speed: number | null;
  rain_probability: number | null;
  sweat_index?: number | null;
  station_name?: string;
}

export interface SweatIndexResult {
  sweat_index: number;
  weather: WeatherData;
  location: string;
}

export interface GeoPoint {
  lat: number;
  lng: number;
}

export interface CacheEntry<T> {
  value: T;
  expires_at: number;
}
