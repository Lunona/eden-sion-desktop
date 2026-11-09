const {addAbortListener}=require('node:events');

function japaneseLine(text) {
  return typeof text === 'string' && text.length <= 1400 && /[ぁ-ゖァ-ヺ]/u.test(text) && !/```/.test(text);
}

function isEcho(text, line) {
  if (!line) return false;
  const letters = value => value.normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{N}]/gu, '');
  const said = letters(text);
  return [line.text, line.subtitle].filter(Boolean).some(value => {
    const spoken = letters(value);
    return said && (spoken === said || (said.length >= 5 && spoken.includes(said)));
  });
}

class ScreenConversation {
  constructor({providers, settings, getDisplays, getSources}) {
    Object.assign(this, {providers, settings, getDisplays, getSources});
    this.session = null;
  }
  route() {
    if (this.providers.has('vision')) return this.providers.resolve('vision');
    if (!this.providers.has('dialogue') && this.settings().mode !== 'api') return null;
    const route = this.providers.resolve('dialogue');
    const cfg = route.config;
    if (cfg.baseUrl && new URL(cfg.baseUrl).hostname === 'api.deepseek.com' &&
        /^deepseek-(flash|v4-flash(?:-vision-exp)?)$/.test(cfg.name)) return route;
    return null;
  }
  status() {
    const route = this.route();
    return {enabled: !!this.session, displayId: this.session?.displayId ?? null,
      model: route ? route.config.name : '', provider: route ? new URL(route.config.baseUrl).host : '',
      displays: this.getDisplays().map((d, index) => ({id: d.id, label: d.label || '显示器 ' + (index + 1)}))};
  }
  enable(displayId) {
    const route = this.route();
    if (!route) throw Error('请在「模型与语音」为屏幕理解选择支持图片的模型。');
    if (!this.getDisplays().some(display => display.id === displayId)) throw Error('这块显示器已离线。');
    this.stop();
    this.session = {displayId, route, controller: new AbortController()};
  }
  stop() {
    this.session?.controller.abort(new Error('屏幕共享已关闭。'));
    this.session = null;
  }
  async capture(session, turnSignal, {maxDimension=1600, acceptFrame}={}) {
    const sharing = session.controller.signal;
    const deadline = AbortSignal.timeout(5000);
    const signal = AbortSignal.any(turnSignal ? [sharing, turnSignal, deadline] : [sharing, deadline]);
    signal.throwIfAborted();
    const display = this.getDisplays().find(d => d.id === session.displayId);
    if (!display) {
      this.stop();
      throw Error('共享的显示器已经离线。');
    }
    if (this.captureInFlight) throw Error('上一次截图仍在等待系统返回，请稍后重试。');
    const scale = Math.min(1, maxDimension / Math.max(display.size.width, display.size.height));
    const thumbnailSize = {width: Math.round(display.size.width * scale), height: Math.round(display.size.height * scale)};
    const request = this.captureInFlight = Promise.resolve(
      this.getSources({types: ['screen'], thumbnailSize, fetchWindowIcons: false}));
    const clear = () => {if (this.captureInFlight === request) this.captureInFlight = null;};
    void request.then(clear, clear);
    let listener, sources;
    const aborted = new Promise((_, reject) => {
      listener = addAbortListener(signal, () => reject(signal.reason));
    });
    try {
      sources = await Promise.race([request, aborted]);
      signal.throwIfAborted();
    } catch (error) {
      if (deadline.aborted && error === deadline.reason) {
        throw new DOMException('屏幕截图等待超时，请确认屏幕可见后重试。', 'TimeoutError');
      }
      throw error;
    } finally {
      listener[Symbol.dispose]();
    }
    const source = sources.find(s => s.display_id === String(display.id));
    if (!source || source.thumbnail.isEmpty()) throw Error('\u8fd9\u5757\u5c4f\u5e55\u6682\u65f6\u65e0\u6cd5\u8bfb\u53d6\u3002');
    if (acceptFrame && !acceptFrame(source.thumbnail)) return null;
    const jpeg = source.thumbnail.toJPEG(84);
    if (!jpeg.length || jpeg.length > 2 * 1024 * 1024) throw Error('屏幕图片大小异常。');
    return 'data:image/jpeg;base64,' + jpeg.toString('base64');
  }
}

module.exports = {japaneseLine, isEcho, ScreenConversation};
