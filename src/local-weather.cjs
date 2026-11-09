const fs = require('node:fs');
const path = require('node:path');
const {writeJSON} = require('./core.cjs');
const MAX_AGE = 2 * 60 * 60_000;

function weatherLabel(code) {
  if (code <= 1) return '晴';
  if (code <= 3) return '多云';
  if (code <= 48) return '雾';
  if (code <= 67 || code === 80 || code === 81 || code === 82) return '下雨';
  if (code <= 86) return '下雪';
  return '雷雨';
}

async function readWeather(url, signal) {
  const response = await fetch(url, {redirect: 'error', signal: AbortSignal.any([signal, AbortSignal.timeout(10000)])});
  if (!response.ok) throw Error('暂时无法获取天气');
  const parts = [];
  let size = 0;
  for await (const part of response.body) {
    size += part.length;
    if (size > 128 * 1024) throw Error('天气响应过大');
    parts.push(Buffer.from(part));
  }
  return JSON.parse(Buffer.concat(parts).toString('utf8'));
}

class LocalWeather {
  constructor(dataRoot, changed) {
    this.file = path.join(dataRoot, 'weather.json');
    this.changed = changed;
    this.config = {enabled: false, place: null};
    this.cities = [];
    this.next = 0;
    this.current = null;
    try {
      const saved = JSON.parse(fs.readFileSync(this.file, 'utf8'));
      if (saved.place && typeof saved.place.name === 'string' &&
          Number.isFinite(saved.place.lat) && Math.abs(saved.place.lat) <= 90 &&
          Number.isFinite(saved.place.lon) && Math.abs(saved.place.lon) <= 180) {
        this.config = {enabled: saved.enabled === true, place: saved.place};
      }
    } catch {}
  }

  async search(query) {
    if (typeof query !== 'string' || query.trim().length < 2 || query.length > 60) throw Error('请输入城市名');
    this.searchJob?.abort();
    const job = this.searchJob = new AbortController();
    const url = new URL('https://geocoding-api.open-meteo.com/v1/search');
    url.search = new URLSearchParams({name: query.trim(), count: '6', language: 'zh', format: 'json'});
    const data = await readWeather(url, job.signal);
    job.signal.throwIfAborted();
    this.cities = (Array.isArray(data.results) ? data.results : []).slice(0, 6)
      .filter(place => Number.isFinite(place.latitude) && Number.isFinite(place.longitude))
      .map(place => ({id: place.id, name: [place.name, place.admin1, place.country].filter(Boolean).join(' · ').slice(0, 120),
        lat: place.latitude, lon: place.longitude}));
    return this.cities.map(({id, name}) => ({id, name}));
  }

  save({enabled, cityId}) {
    const place = cityId === undefined ? this.config.place : this.cities.find(city => city.id === cityId);
    if (enabled === true && !place) throw Error('请先选择城市');
    const config = {enabled: enabled === true, place: place || null};
    writeJSON(this.file, config);
    this.request?.abort();
    this.request = null;
    this.config = config;
    this.current = null;
    this.error = '';
    this.next = 0;
    this.changed();
    void this.tick();
    return this.status();
  }

  status() {
    const current = this.config.enabled && this.current && Date.now() - this.current.received < MAX_AGE ? this.current : null;
    return {enabled: this.config.enabled, place: this.config.place?.name || '', current, error: this.error || ''};
  }

  async tick() {
    if (!this.config.enabled || this.request || Date.now() < this.next) return;
    const {lat, lon} = this.config.place;
    const job = this.request = new AbortController();
    this.next = Date.now() + 30 * 60_000;
    try {
      const url = new URL('https://api.open-meteo.com/v1/forecast');
      url.search = new URLSearchParams({latitude: String(lat), longitude: String(lon),
        current: 'temperature_2m,is_day,weather_code,wind_speed_10m,wind_direction_10m,wind_gusts_10m',
        wind_speed_unit: 'kmh', timezone: 'auto'});
      const {current: c} = await readWeather(url, job.signal);
      job.signal.throwIfAborted();
      if (!c || ![c.temperature_2m, c.weather_code, c.wind_speed_10m, c.wind_direction_10m, c.wind_gusts_10m].every(Number.isFinite)) {
        throw Error('天气数据不完整');
      }
      this.current = {label: weatherLabel(c.weather_code), temperature: c.temperature_2m, day: c.is_day === 1,
        wind: Math.max(0, c.wind_speed_10m), gust: Math.max(0, c.wind_gusts_10m), direction: c.wind_direction_10m,
        at: String(c.time).slice(0, 30), received: Date.now()};
      this.error = '';
    } catch {
      if (!job.signal.aborted) this.error = '天气暂不可用，会稍后重试';
    } finally {
      if (this.request === job) {
        this.request = null;
        this.changed();
      }
    }
  }

  stop() {
    this.request?.abort();
    this.searchJob?.abort();
  }
}

function windFor(current) {
  if (!current) return {strength: 1, direction: 0, gust: 0};
  return {strength: .45 + .85 * Math.min(current.wind / 42, 1),
    direction: -.7 * Math.sin(current.direction * Math.PI / 180),
    gust: Math.min(.23, Math.max(0, current.gust - current.wind) / 80)};
}

module.exports = {LocalWeather, windFor};
