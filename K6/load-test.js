import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

const errorRate = new Rate('error_rate');
const throttled = new Counter('throttled_429');
const loadLatency = new Trend('load_latency_ms', true);

const BASE_URL = __ENV.BASE_URL || 'https://rag-backend-235944902030.us-central1.run.app';
const LOAD_ROWS = __ENV.LOAD_ROWS || 800;
const LOAD_ITER = __ENV.LOAD_ITER || 120;
const LOAD_MS = __ENV.LOAD_MS || 12000;
const LOAD_FAIL = __ENV.LOAD_FAIL || 10;
const QUICK = __ENV.QUICK === '1';

export const options = {
  scenarios: {
    warmup: {
      executor: 'constant-vus',
      vus: 1,
      duration: QUICK ? '5s' : '20s',
      exec: 'warmup',
      tags: { scenario: 'warmup' },
    },
    browse: {
      executor: 'ramping-vus',
      startTime: QUICK ? '5s' : '20s',
      startVUs: 0,
      stages: QUICK
        ? [{ duration: '10s', target: 10 }, { duration: '5s', target: 0 }]
        : [
            { duration: '30s', target: 20 },
            { duration: '60s', target: 20 },
            { duration: '20s', target: 0 },
          ],
      exec: 'browse',
      tags: { scenario: 'browse' },
    },
    breach: {
      executor: 'ramping-vus',
      startTime: QUICK ? '20s' : '140s',
      startVUs: 0,
      stages: QUICK
        ? [{ duration: '10s', target: 10 }, { duration: '10s', target: 0 }]
        : [
            { duration: '20s', target: 20 },
            { duration: '180s', target: 20 },
            { duration: '20s', target: 0 },
          ],
      exec: 'breach',
      tags: { scenario: 'breach' },
    },
  },
  thresholds: {
    'http_req_duration{scenario:browse}': ['p(95)<8000'],
    'http_req_failed{scenario:browse}': ['rate<0.01'],
    'error_rate{scenario:browse}': ['rate<0.01'],
  },
};

export function warmup() {
  const r = http.get(`${BASE_URL}/`);
  check(r, { 'health 200': (res) => res.status === 200 });
  sleep(1);
}

export function browse() {
  const r1 = http.get(`${BASE_URL}/`);
  check(r1, { 'root 200': (res) => res.status === 200 });
  errorRate.add(r1.status >= 500 || r1.status === 0);
  if (r1.status === 429) throttled.add(1);
  sleep(0.5);

  const r2 = http.get(`${BASE_URL}/api/courses`);
  check(r2, { 'courses 200': (res) => res.status === 200 });
  errorRate.add(r2.status >= 500 || r2.status === 0);
  if (r2.status === 429) throttled.add(1);
  sleep(1);
}

export function breach() {
  const url = `${BASE_URL}/api/load?rows=${LOAD_ROWS}&iterations=${LOAD_ITER}&ms=${LOAD_MS}&fail=${LOAD_FAIL}`;
  const r = http.get(url);
  loadLatency.add(r.timings.duration);
  if (r.status === 429) throttled.add(1);
  errorRate.add(r.status >= 500 || r.status === 0);
  sleep(0.3);
}
