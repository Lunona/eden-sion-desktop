(() => {
  const api = window.sion;
  const home = document.getElementById('companion');
  if (!home) return;
  const card = document.createElement('article');
  card.className = 'workspace-card weather-card';
  card.innerHTML = `
    <div class="card-head"><div><span class="card-eyebrow">LOCAL WEATHER</span><h3>此刻的天气</h3></div><span class="soft-tag" id="weather-location">未选择地点</span></div>
    <div class="weather-values"><div><small>天气</small><strong id="weather-condition">—</strong></div><div><small>风速</small><strong id="weather-wind">—</strong></div><div><small>光线</small><strong id="weather-daylight">—</strong></div></div>
    <p id="weather-result" class="subtle" role="status"></p>
    <details><summary>设置天气联动</summary>
      <form id="weather-search-form"><label>城市<input id="weather-query" placeholder="输入城市名" maxlength="60" required></label><button type="submit">查找城市</button></form>
      <label>选择地点<select id="weather-cities"><option value="">保留当前地点</option></select></label>
      <label class="switch-line"><span>跟随当地天气</span><input id="weather-enabled" type="checkbox"></label>
      <button type="button" id="weather-save" class="primary">保存天气设置</button>
      <p class="subtle">风速与阵风会调整衣发摆动。日夜改变面板色调，雨雪偶尔会出现在主动问候里。数据由 Open-Meteo 提供。</p>
    </details>`;
  home.querySelector('.companion-main').append(card);
  const get = id => card.querySelector('#' + id);
  let dirty = false;
  function render(state) {
    const weather = state.weather;
    if (!weather) return;
    const c = weather.current;
    get('weather-location').textContent = weather.place || '未选择地点';
    get('weather-condition').textContent = c ? c.label + ' ' + Math.round(c.temperature) + '°' : '—';
    get('weather-wind').textContent = c ? Math.round(c.wind) + ' km/h' : '—';
    get('weather-daylight').textContent = c ? c.day ? '日间' : '夜间' : '—';
    if (!dirty) get('weather-enabled').checked = weather.enabled;
    if (!dirty) get('weather-result').textContent = weather.error || (c ? '更新于 ' + c.at.replace('T', ' ') : weather.enabled ? '正在获取当地天气…' : '开启后，风力和日夜随选定地点变化。');
    document.body.dataset.daylight = c && !c.day ? 'night' : 'day';
  }
  get('weather-enabled').onchange = () => { dirty = true; };
  get('weather-search-form').onsubmit = async event => {
    event.preventDefault();
    dirty = true;
    const form = event.currentTarget;
    const button = form.querySelector('button');
    button.disabled = true;
    try {
      const cities = await api.invoke('weather-search', {query: get('weather-query').value});
      const select = get('weather-cities');
      select.replaceChildren(new Option('保留当前地点', ''));
      for (const city of cities) select.add(new Option(city.name, String(city.id)));
      if (cities.length) {
        select.selectedIndex = 1;
        get('weather-enabled').checked = true;
      }
      get('weather-result').textContent = cities.length ? '选好地点后保存。' : '没有找到这个城市。';
    } catch (error) {
      get('weather-result').textContent = error.message;
    } finally { button.disabled = false; }
  };
  get('weather-save').onclick = async () => {
    const button = get('weather-save');
    button.disabled = true;
    try {
      const city = get('weather-cities').value;
      const result = await api.invoke('weather-config', {enabled: get('weather-enabled').checked, ...(city ? {cityId: Number(city)} : {})});
      dirty = false;render({weather: result});
      get('weather-cities').value = '';
    } catch (error) { get('weather-result').textContent = error.message; }
    finally { button.disabled = false; }
  };
  api.subscribe(event => { if (event.type === 'state') render(event.state); });
  api.invoke('state').then(render).catch(() => {});
})();
