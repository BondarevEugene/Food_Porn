(() => {
  'use strict';
  const root = document.querySelector('#present');
  const token = location.pathname.match(/^\/miniapp\/open\/([A-Za-z0-9_-]{32})$/)?.[1];
  const base = `/miniapp/open/${token}`;
  const tg = window.Telegram?.WebApp;
  tg?.ready(); tg?.expand();
  let gift;
  let step = 0;
  const words = {
    uk: {forYou:'Це — для тебе',open:'Відкрити конверт',wait:'Твоя історія',next:'Далі',back:'Назад',
      end:'Зберегти подарунок',sorry:'Не вдалося відкрити подарунок. Попросіть відправника надіслати нове посилання.',
      letter:'Цей вечір я склав із простих речей, у яких живе моя любов до тебе: смаку, тепла і часу разом. Кожна страва — знак уваги до того, що ти любиш. Сьогодні відпочинь і відчуй мою турботу. Ти для мене особливий — і цей вечір належить тобі.',
      wish:'Бажання',menu:'Вечір для тебе',inside:'Те, що всередині'},
    ru: {forYou:'Это — для тебя',open:'Открыть конверт',wait:'Твоя история',next:'Дальше',back:'Назад',
      end:'Сохранить подарок',sorry:'Не удалось открыть подарок. Попросите отправителя прислать новую ссылку.',
      letter:'Этот вечер я сложил из простых вещей, в которых живёт моя любовь к тебе: вкуса, тепла и времени вместе. Каждое блюдо — знак внимания к тому, что ты любишь. Сегодня отдохни и почувствуй мою заботу. Ты для меня особенный — и этот вечер принадлежит тебе.',
      wish:'Желание',menu:'Вечер для тебя',inside:'То, что внутри'},
    en: {forYou:'This is for you',open:'Open the envelope',wait:'Your story',next:'Next',back:'Back',
      end:'Save your gift',sorry:'We could not open this gift. Please ask the sender for a fresh link.',
      letter:'I made this evening from simple things that hold my love for you: good food, warmth, and time together. Every dish shows that I notice what you love. Tonight, rest and feel how much I care. You are precious to me, and this evening is yours.',
      wish:'Wish',menu:'An evening for you',inside:'What is inside'}
  };
  const tr = key => (words[gift?.language] || words.uk)[key];
  const make = (tag, className, value) => {
    const element = document.createElement(tag);
    element.className = className;
    if (value != null) element.textContent = value;
    return element;
  };
  const media = key => `${base}/media/${key}`;

  function envelope() {
    root.replaceChildren();
    const wrap = make('section', 'opening');
    wrap.append(make('p', 'overline', 'FOOD PORN ATELIER'), make('h1', 'opening-title', tr('forYou')));
    const envelope = make('div', 'envelope');
    envelope.append(make('div','envelope-flap'), make('div','envelope-sheet'));
    envelope.append(make('div','seal','✦'));
    wrap.append(envelope, make('p','opening-note',tr('wait')));
    const button = make('button','gold-button',tr('open'));
    button.type = 'button';
    button.onclick = () => { envelope.classList.add('unfold'); setTimeout(() => { step = 0; story(); }, 500); };
    wrap.append(button);
    root.append(wrap);
  }

  function story() {
    const isMenu = gift.kind === 'menu';
    const slides = isMenu ? ['cover', ...(gift.has_inside ? ['inside'] : []), 'letter']
                          : ['cover', ...(gift.goals || []).map((_, index) => String(index))];
    root.replaceChildren();
    const wrap = make('section','story');
    const bar = make('div','story-top');
    bar.append(make('span','brand','F ✦ P'),make('span','counter',`${String(step+1).padStart(2,'0')} / ${String(slides.length).padStart(2,'0')}`));
    wrap.append(bar);
    const card = make('article','story-card');
    const current = slides[step];
    if (current === 'cover' || current === 'inside') {
      const photo = make('img','artwork');
      photo.src = media(current);
      photo.alt = isMenu ? tr(current === 'cover' ? 'menu' : 'inside') : tr('wait');
      card.append(photo);
      card.append(make('p','artwork-caption',isMenu ? tr(current === 'cover' ? 'menu' : 'inside') : tr('wait')));
    } else if (current === 'letter') {
      card.classList.add('letter');
      card.append(make('span','letter-mark','♡'), make('h2','letter-title',tr('forYou')),
                  make('p','letter-body',tr('letter')));
      if (gift.items?.length) {
        const list = make('div','menu-list');
        gift.items.forEach((title,index) => list.append(make('p','menu-line',`${String(index+1).padStart(2,'0')}  ${title}`)));
        card.append(list);
      }
    } else {
      card.classList.add('wish');
      const photo = make('img','wish-art');
      photo.src = media('cover'); photo.alt = tr('wait');
      card.append(photo);
      const wish = make('div','wish-copy');
      wish.append(make('span','wish-index',`${tr('wish')} ${String(Number(current)+1).padStart(2,'0')}`),
                  make('h2','wish-title',gift.goals[Number(current)]));
      card.append(wish);
    }
    wrap.append(card);
    const controls = make('nav','story-controls');
    if (step) {
      const back = make('button','quiet-button',tr('back'));
      back.onclick = () => { step--; story(); };
      controls.append(back);
    }
    if (step < slides.length - 1) {
      const next = make('button','gold-button',tr('next'));
      next.onclick = () => { step++; story(); };
      controls.append(next);
    } else {
      const filename = gift.kind === 'menu' ? 'menu.pdf' : 'gift.png';
      const save = make(tg?.downloadFile && tg?.isVersionAtLeast?.('8.0') ? 'button' : 'a',
                        'gold-button',tr('end'));
      if (save.tagName === 'BUTTON') save.onclick = () => tg.downloadFile({url:location.origin + media('download'),file_name:filename});
      else { save.href = media('download'); save.download = filename; }
      controls.append(save);
    }
    wrap.append(controls, make('footer','signature','WITH LOVE · FOOD PORN ATELIER'));
    root.append(wrap);
  }

  if (!token) { root.textContent = words.uk.sorry; return; }
  fetch(`${base}/data`,{cache:'no-store'}).then(async response => {
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    gift = await response.json();
    document.documentElement.lang = gift.language in words ? gift.language : 'uk';
    envelope();
  }).catch(() => { root.replaceChildren(make('p','problem',words.uk.sorry)); });
})();
