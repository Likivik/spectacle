// fishaudio-proxy
// SillyTavern → Fish Audio API proxy
// Translates OpenAI TTS shape (input, voice, model) → Fish native shape (text, reference_id, format)
//
// Usage: FISH_API_KEY=<key> node fishaudio-proxy.js
// Or set FISH_API_KEY_FILE path to a file containing the key.

const HOST = '0.0.0.0';
const PORT = 8099;
const FISH_API = 'https://api.fish.audio';

const apiKey = process.env.FISH_API_KEY ||
  (process.env.FISH_API_KEY_FILE && require('fs').readFileSync(process.env.FISH_API_KEY_FILE, 'utf8').trim()) ||
  '';

if (!apiKey) {
  console.error('[fishaudio-proxy] No API key. Set FISH_API_KEY or FISH_API_KEY_FILE');
  process.exit(1);
}

const server = require('http').createServer(async (req, res) => {
  if (req.method === 'OPTIONS') {
    res.writeHead(204, {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization',
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
  req.on('data', c => body += c);
  req.on('end', async () => {
    try {
      const d = JSON.parse(body);
      const text = (d.input || '').slice(0, 2000);
      const reference_id = d.voice || '';
      const format = formatMap[d.response_format] || 'mp3';

      const fr = await fetch(`${FISH_API}/v1/tts`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${apiKey}`,
          'Content-Type': 'application/json',
          'model': 's2.1-pro-free',
        },
        body: JSON.stringify({ text, reference_id, format }),
      });

      if (!fr.ok) {
        const err = await fr.text();
        res.writeHead(fr.status, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: err }));
        return;
      }

      res.writeHead(200, { 'Content-Type': 'audio/mpeg', 'Transfer-Encoding': 'chunked' });
      fr.body.pipe(res);
    } catch (e) {
      res.writeHead(500, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: e.message }));
    }
  });
});

const formatMap = { mp3: 'mp3', mpeg: 'mp3', pcm: 'pcm', '16bit': 'pcm', flac: 'flac', opus: 'opus', wav: 'wav' };

server.listen(PORT, HOST, () => console.log(`[fishaudio-proxy] ${HOST}:${PORT}`));
