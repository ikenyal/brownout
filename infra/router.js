// Brownout router (CloudFront Functions, cloudfront-js-2.0, viewer request).
// Reads the current alert level from CloudFront KeyValueStore and rewrites the
// request. Because this runs before the cache lookup, switching mode is just a
// KVS write: no deployment, no invalidation.
import cf from 'cloudfront';

const kvs = cf.kvs();

async function handler(event) {
  const req = event.request;
  let level = 1;
  try {
    const value = await kvs.get('level');
    level = parseInt(value, 10) || 1;
  } catch (e) {
    level = 1; // key missing: normal mode
  }
  const uri = req.uri;
  if (uri.startsWith('/level-') || uri.startsWith('/full/')) {
    return req; // direct links for demos and measurement
  }
  if (level >= 3) {
    // Every URL collapses to the one emergency page for this level.
    req.uri = '/level-' + level + '/index.html';
  } else {
    req.uri = '/full' + (uri === '/' ? '/index.html' : uri);
  }
  return req;
}
