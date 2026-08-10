{ den, lib, pkgs, ... }:

{
  sops.secrets = {
    "fishaudio/api-key" = {
      sopsFile = den.lib.sopsFileForHost "erebus";
      owner = "hermes";
      group = "hermes";
      mode = "0600";
    };
  };

  systemd.services.fishaudio-proxy = {
    description = "Fish Audio API proxy — translates OpenAI TTS shape to Fish native /v1/tts";
    wantedBy = [ "multi-user.target" ];
    after = [ "network.target" ];

    serviceConfig = {
      Type = "simple";
      User = "hermes";
      Group = "hermes";
      Restart = "always";
      RestartSec = "5s";
      EnvironmentFile = "/run/secrets/fishaudio-api-key";
      ExecStart = lib.getExe (pkgs.writeScript "fishaudio-proxy.js" ''
        #!${lib.getExe pkgs.nodejs}
        // Fish Audio proxy — translates SillyTavern OpenAI TTS → Fish native /v1/tts
        const HOST = '0.0.0.0';
        const PORT = 8099;
        const FISH_API = 'https://api.fish.audio';

        const apiKey = process.env.FISH_API_KEY ||
          (process.env.FISH_API_KEY_FILE &&
           require('fs').readFileSync(process.env.FISH_API_KEY_FILE, 'utf8').trim()) || '';

        if (!apiKey) { console.error('[fishaudio-proxy] No API key'); process.exit(1); }

        const server = require('http').createServer(async (req, res) => {
          if (req.method === 'OPTIONS') {
            res.writeHead(204, {
              'Access-Control-Allow-Origin': '*',
              'Access-Control-Allow-Methods': 'POST, OPTIONS',
              'Access-Control-Allow-Headers': 'Content-Type, Authorization',
            });
            res.end(); return;
          }
          if (req.method !== 'POST' || req.url !== '/v1/audio/speech') {
            res.writeHead(404); res.end('Not found'); return;
          }

          let body = '';
          req.on('data', c => body += c);
          req.on('end', async () => {
            try {
              const d = JSON.parse(body);
              const text = (d.input || '').slice(0, 2000);
              const reference_id = d.voice || '';
              const fmt = { mp3: 'mp3', mpeg: 'mp3', pcm: 'pcm', flac: 'flac', opus: 'opus', wav: 'wav' }[d.response_format] || 'mp3';

              const fr = await fetch(`${FISH_API}/v1/tts`, {
                method: 'POST',
                headers: {
                  'Authorization': `Bearer ${apiKey}`,
                  'Content-Type': 'application/json',
                  'model': 's2.1-pro-free',
                },
                body: JSON.stringify({ text, reference_id, format: fmt }),
              });

              if (!fr.ok) {
                const err = await fr.text();
                res.writeHead(fr.status, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: err })); return;
              }
              res.writeHead(200, { 'Content-Type': 'audio/mpeg', 'Transfer-Encoding': 'chunked' });
              fr.body.pipe(res);
            } catch (e) {
              res.writeHead(500, { 'Content-Type': 'application/json' });
              res.end(JSON.stringify({ error: e.message }));
            }
          });
        });

        server.listen(PORT, HOST, () => console.log(`[fishaudio-proxy] ${HOST}:${PORT}`));
      '');
    };
  };

  networking.firewall.interfaces.tailscale0.allowedTCPPorts = [ 8099 ];
}
