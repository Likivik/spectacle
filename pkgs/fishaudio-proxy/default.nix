// fishaudio-proxy.js
// Translates SillyTavern's OpenAI TTS shape → Fish Audio native TTS shape
// ST calls: POST /v1/audio/speech {input, voice, model, response_format, speed}
// Fish expects: POST /v1/tts {text, reference_id, format} + model header

const HOST = '0.0.0.0';
const PORT = 8099;
const FISH_API = 'https://api.fish.audio';

let apiKey = '';

// Load API key from env or mounted secret file
try {
  const { readFileSync } = require('fs');
  apiKey = process.env.FISH_API_KEY ||
    (process.env.FISH_API_KEY_FILE ? readFileSync(process.env.FISH_API_KEY_FILE, 'utf8').trim() : '');
} catch {}

if (!apiKey) {
  console.error('[fishaudio-proxy] No API key found. Set FISH_API_KEY or FISH_API_KEY_FILE env.');
  process.exit(1);
}

const server = require('http').createServer(async (req, res) => {
  // CORS preflight
  if (req.method === 'OPTIONS') {
    res.writeHead(204, {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization',
      'Access-Control-Max-Age': '86400',
    });
    res.end();
    return;
  }

  if (req.method !== 'POST' || req.url !== '/v1/audio/speech') {
    res.writeHead(404);
    res.end('Not found');
    return;
  }

  let body = '';
  req.on('data', chunk => body += chunk);
  req.on('end', async () => {
    try {
      const data = JSON.parse(body);
      const text = (data.input || '').slice(0, 2000);
      const reference_id = data.voice || '';
      const format = mapFormat(data.response_format);

      const fishRes = await fetch(`${FISH_API}/v1/tts`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${apiKey}`,
          'Content-Type': 'application/json',
          'model': 's2.1-pro-free',
        },
        body: JSON.stringify({ text, reference_id, format }),
      });

      if (!fishRes.ok) {
        const err = await fishRes.text();
        console.error('[fishaudio-proxy] Fish API error:', fishRes.status, err);
        res.writeHead(fishRes.status, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: err }));
        return;
      }

      res.writeHead(200, {
        'Content-Type': 'audio/mpeg',
        'Transfer-Encoding': 'chunked',
      });

      fishRes.body.pipe(res);
    } catch (err) {
      console.error('[fishaudio-proxy] Proxy error:', err.message);
      res.writeHead(500, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: err.message }));
    }
  });
});

function mapFormat(fmt) {
  // Fish supports: mp3, pcm, flac, opus, wav
  const map = { mp3: 'mp3', mpeg: 'mp3', '16bit': 'pcm', pcm: 'pcm', flac: 'flac', opus: 'opus', wav: 'wav' };
  return map[fmt] || 'mp3';
}

server.listen(PORT, HOST, () => {
  console.log(`[fishaudio-proxy] Listening on ${HOST}:${PORT}`);
});
