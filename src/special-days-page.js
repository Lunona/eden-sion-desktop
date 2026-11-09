(() => {
  const api = window.sion;
  const home = document.getElementById('companion');
  if (!home) return;
  const card = document.createElement('article');
  card.className = 'workspace-card occasion-card';
  card.innerHTML = `
    <div class="card-head"><div><span class="card-eyebrow">DAYS TO REMEMBER</span><h3>特别的日子</h3></div><span class="soft-tag">只属于这段相处</span></div>
    <div id="occasion-list"></div>
    <details id="occasion-edit"><summary>记下一个日子</summary>
      <form id="occasion-form">
        <label>名称<input id="occasion-title" placeholder="例如：我们的纪念日" maxlength="60" required></label>
        <div class="two-col"><label>日期<input type="date" id="occasion-date" required></label><label>类型<select id="occasion-kind"><option value="birthday">生日</option><option value="anniversary">纪念日</option><option value="other">其他</option></select></label></div>
        <label class="switch-line"><span>每年重复</span><input type="checkbox" id="occasion-annual"></label>
        <button class="primary">记下日子</button>
      </form>
    </details>
    <p id="occasion-status" class="subtle" role="status"></p>`;
  home.querySelector('#companion-reminder-form').closest('article').after(card);
  const get = id => card.querySelector('#' + id);
  let signature = '';
  function render(items) {
    const key = JSON.stringify(items);
    if (key === signature) return;
    signature = key;
    const list = get('occasion-list');
    const openLetters = new Set(Array.from(list.querySelectorAll('.occasion-letter[open]'),
      letter => letter.dataset.cardId));
    list.replaceChildren();
    if (!items.length) {
      const empty = document.createElement('p');
      empty.className = 'subtle';
      empty.textContent = '可以把生日、纪念日或想留住的一天记在这里。';
      list.append(empty);
    }
    for (const item of items) {
      const row = document.createElement('div');
      row.className = 'occasion-row';
      const date = document.createElement('time');
      date.dateTime = item.date;
      date.textContent = item.date.slice(5).replace('-', ' / ');
      const detail = document.createElement('div');
      const title = document.createElement('strong');
      title.textContent = item.title;
      const kind = document.createElement('small');
      kind.textContent = item.kind + (item.annual ? ' · 每年重复' : '');
      detail.append(title, kind);
      const remove = document.createElement('button');
      remove.textContent = '移除';
      remove.onclick = async () => {
        try { render((await api.invoke('special-day', {action: 'remove', id: item.id})).special_days); }
        catch (error) { get('occasion-status').textContent = error.message; }
      };
      row.append(date, detail, remove);
      list.append(row);
      if (item.card) {
        const letter = document.createElement('details');
        letter.className = 'occasion-letter';
        const summary = document.createElement('summary');
        summary.textContent = '打开 ' + item.card.occasion + ' 的信笺';
        const text = document.createElement('p');
        text.textContent = item.card.letter;
        if (item.card.id) {
          letter.dataset.cardId = item.card.id;
          letter.open = openLetters.has(item.card.id);
          summary.addEventListener('click', event => {
            event.preventDefault();
            if (!letter.getClientRects().length) return;
            letter.open = !letter.open;
            if (letter.open) void api.invoke('special-card-open', {id: item.card.id}).catch(() => {});
          });
        }
        letter.append(summary, text);
        list.append(letter);
      }
    }
  }
  get('occasion-form').onsubmit = async event => {
    event.preventDefault();
    const form = event.currentTarget;
    try {
      const result = await api.invoke('special-day', {title: get('occasion-title').value,
        date: get('occasion-date').value, kind: get('occasion-kind').value, annual: get('occasion-annual').checked});
      form.reset();get('occasion-edit').open = false;
      get('occasion-status').textContent = '这一天已经记下了。';
      render(result.special_days);
    } catch (error) { get('occasion-status').textContent = error.message; }
  };
  api.subscribe(event => {
    if (event.type === 'state' && event.state.companion) render(event.state.companion.special_days || []);
  });
  api.invoke('companion-status').then(result => render(result.special_days || [])).catch(() => {});
})();
