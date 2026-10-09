// Lit sur stdin une page HTML rendue par Nuxt et écrit sur stdout son état initial (window.__NUXT__) en JSON.
// Le script est exécuté dans un bac à sable vm sans accès au système (pas de require, pas de process).
const vm = require('vm');
let html = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', (c) => { html += c; });
process.stdin.on('end', () => {
  const m = html.match(/<script>window\.__NUXT__=([\s\S]*?)<\/script>/);
  if (!m) { process.stderr.write('pas de __NUXT__\n'); process.exit(2); }
  const ctx = { window: {} };
  vm.runInNewContext('window.__NUXT__=' + m[1], ctx, { timeout: 5000 });
  process.stdout.write(JSON.stringify(ctx.window.__NUXT__));
});
