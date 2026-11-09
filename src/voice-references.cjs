const fs = require('node:fs');
const path = require('node:path');
const {createHash} = require('node:crypto');
const {japaneseLine} = require('./live-companion.cjs');

const REFERENCE_BY_EMOTION = {
  calm: 'acoustic_cluster_0', thoughtful: 'acoustic_cluster_0', sleepy: 'acoustic_cluster_0',
  warm: 'baseline_warm', shy: 'baseline_warm', care: 'sio-C007-0201',
  joy: 'sio-C011-0059', playful: 'sio-C011-0059',
  curious: 'sio-C002-0133', surprise: 'sio-C002-0133',
  sad: 'sad_context_candidate'
};

function loadVoiceReferences({
  manifest = process.env.SION_VOICE_REFERENCE_MANIFEST || '',
  audioRoots = (process.env.SION_VOICE_REFERENCE_ROOTS || '').split(path.delimiter).filter(Boolean)
} = {}) {
  const references = new Map();
  try {
    if (fs.statSync(manifest).size > 128 * 1024) return references;
    const roots = audioRoots.filter(root => fs.existsSync(root)).map(root => fs.realpathSync(root));
    const data = JSON.parse(fs.readFileSync(manifest, 'utf8').replace(/^\uFEFF/, ''));
    if (!Array.isArray(data)) return references;
    for (const item of data.slice(0, 40)) {
      if (!item || !item.audio_text_checked || item.clipped_samples !== 0 ||
          !(item.phonetic_similarity >= 0.95) || !(item.duration >= 3 && item.duration <= 10) ||
          !japaneseLine(item.text) || typeof item.id !== 'string' || typeof item.audio !== 'string') continue;
      try {
        const audio = fs.realpathSync(item.audio);
        const approved = roots.some(root => {
          const relative = path.relative(root, audio);
          return relative && !relative.startsWith('..') && !path.isAbsolute(relative);
        });
        if (!approved || !/\.wav$/i.test(audio)) continue;
        if (fs.statSync(audio).size > 2 * 1024 * 1024) continue;
        const hash = createHash('sha256').update(fs.readFileSync(audio)).digest('hex');
        if (hash !== item.source_sha256) continue;
        references.set(item.id, {id: item.id, audio, text: item.text, category: String(item.category), name: String(item.name)});
      } catch {}
    }
  } catch {}
  return references;
}

function selectVoiceReference(references, config, visual) {
  if (!visual || config.emotionalReferences === false || config.textLang !== 'ja') return null;
  const url = new URL(config.endpoint);
  if (!['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname) || url.port !== '9880' || url.pathname !== '/tts') return null;
  const current = path.resolve(config.refAudio).toLowerCase();
  if (![...references.values()].some(entry => entry.audio.toLowerCase() === current)) return null;
  const kind = visual.intensity < .22 ? 'calm' : visual.emotion;
  return references.get(REFERENCE_BY_EMOTION[kind]) || null;
}

module.exports = {loadVoiceReferences, selectVoiceReference};
