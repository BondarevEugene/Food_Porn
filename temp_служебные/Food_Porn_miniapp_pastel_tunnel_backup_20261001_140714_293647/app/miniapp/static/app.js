(() => {
  'use strict';
  const tg = window.Telegram?.WebApp;
  tg?.ready();
  tg?.expand();
  const app = document.querySelector('#app');
  const launchData = tg?.initData || '';
  let giftPhotoUrls = [];
  let giftPhotoSelection = 0;
  let giftPhotoCheck = Promise.resolve();
  const giftDraftKey = 'food-porn-gift-draft-v2';
  let savedLanguage = '';
  try { savedLanguage = localStorage.getItem('gift_lang') || ''; } catch (_) { /* private browsing */ }
  const state = {
    page: 'home', home: null, admin: null, job: null, menu: null, wallpaper: null, evening: null,
    style: 'dark', lang: savedLanguage || tg?.initDataUnsafe?.user?.language_code?.slice(0, 2) || 'uk',
    error: '', previewUrl: '', previewError: '', viewKey: ''
  };
  const copy = {
    ru: {
      studio: 'Мастерская подарков', hello: 'Подарок, который останется в памяти', lead: 'Ваша история — в красивом изображении или меню для особенного вечера.',
      gift: 'История желаний', giftSub: 'Фото, желания и атмосфера', food: 'Гастрономический подарок', foodSub: 'Меню, рецепты и печать',
      orders: 'Мои заказы', ordersSub: 'Все подарки и готовые файлы', empty: 'Здесь появятся ваши подарки.',
      back: 'На главную', photos: 'Фото близкого человека', photosHint: 'Добавьте от 1 до 7 фото. Сюжеты мы подберём сами.',
      photosNone: 'Фото ещё не выбраны', photosChosen: 'Выбрано фото', photosExcess: 'Можно выбрать максимум 7 фото', photosQueued: 'Отправятся при создании подарка',
      wishes: 'От 5 до 9 желаний', wishesHint: 'Напишите по одному желанию в каждом поле.', addWish: 'Добавить желание', theme: 'Атмосфера', dark: 'Тёплая тёмная', light: 'Светлая', color: 'Яркая',
      create: 'Создать подарок', foodLead: 'Расскажите, какие блюда войдут в ваше меню.', name: 'Ваше имя', phone: 'Телефон с кодом страны',
      cover: 'Фото для обложки', spread: 'Фото для разворота', dishes: 'Блюда', add: 'Добавить блюдо', send: 'Создать меню',
      status: 'Состояние заказа', preview: 'Предпросмотр', mobile: 'Изображение для телефона', desktop: 'Изображение для экрана',
      print: 'Архив для типографии', recipes: 'Рецепты и продукты', check: 'Проверить оплату', pay: 'Перейти к оплате',
      working: 'Мы создаём ваш подарок. Это займёт несколько минут.', payment: 'К оплате', setting: 'Настройки', language: 'Язык',
      vip: 'Бесплатный доступ: Telegram usernames', save: 'Сохранить', admin: 'Управление', customers: 'Клиенты', menus: 'Меню', gifts: 'Подарки', paid: 'Оплачено',
      previewMissing: 'Предпросмотр пока недоступен. Готовые файлы появятся здесь.', details: 'Детали заказа', goals: 'Ваши желания',
      ready: 'Подарок готов', generating: 'Создаём изображение', queued: 'Заказ принят', waiting_for_payment: 'Ожидает оплаты',
      payment_unavailable: 'Оплата временно недоступна', payment_status: 'Ожидает оплаты', interrupted: 'Создание прервано',
      failed: 'Не удалось завершить', blocked: 'Нужна другая фотография или формулировка', completed: 'Готово',
      sent_to_printshop: 'Передано в типографию', images_ready: 'Подготавливаем файлы', partial_success: 'Часть файлов готова',
      retry: 'Продолжить создание', openFromBot: 'Откройте мастерскую из Telegram-бота.', unpaid: 'После оплаты откроются файлы для скачивания.',
      checkLater: 'Оплата пока не подтверждена', wish: 'Желание', number: 'Заказ', noDishes: 'Блюда появятся после обработки заказа.',
      sendEmail: 'Отправить полный заказ на email', email: 'Email получателя', emailSent: 'Письмо отправлено',
      share: 'Подарить в Telegram', delivery: 'Вручение и доставка', openGift: 'Посмотреть вручение',
      evening: 'Вечер по меню', eveningLead: 'Выберите блюда для одного вечера. Мы покажем покупки, порядок готовки и время подачи.',
      eveningOld: 'Для этого заказа план вечера ещё не создан. Рецепты и покупки есть в PDF.',
      chooseDishes: 'Блюда этого вечера', shopping: 'Что купить', prepare: 'С чего начать', serve: 'Когда подавать',
      firstServe: 'Первое блюдо подать в', approx: 'Ориентировочно', minutes: 'мин', selected: 'отметить',
      progressPlan: 'Подбираем сюжеты', progressRender: 'Создаём изображение', progressQuality: 'Проверяем качество'
      ,studioLead: 'Ваши фото и мечты — наша художественная история. Сюжеты, свет и композицию подберёт ИИ.',
      photoStep: 'Ваши фотографии', wishStep: 'Ваши желания', themeStep: 'Настроение истории',
      artDirection: 'ИИ подберёт фон и сюжет для каждого желания и соединит всё в одну историю.',
      styleDark: 'Тёплый свет, глубокие тона', styleLight: 'Воздух, мягкость и свет', styleColor: 'Живые оттенки и эмоции',
      summary: 'Перед созданием', photoUnit: 'фото', wishUnit: 'желаний', readySummary: 'Всё готово — можно создавать',
      fillSummary: 'Добавьте фото и заполните желания', selectedTheme: 'Настроение',
      photoChecking: 'Проверяем качество снимков…', photoSmall: 'Снимок слишком маленький (минимум 300 × 300 px). Выберите другой.',
      photoSoft: 'Для лучшего результата добавьте снимок крупнее 800 px.', photoUnreadable: 'Не удалось прочитать снимок. Выберите другой.',
      samePhotos: 'Похоже, один снимок выбран дважды.', sameWishes: 'Два желания совпадают — разнообразие сделает историю интереснее.',
      draftSaved: 'Текст сохранён на этом устройстве. Фото после обновления нужно выбрать снова.',
      progressIntro: 'Наш художественный помощник работает над вашим подарком'
    },
    uk: {
      studio: 'Майстерня подарунків', hello: 'Подарунок, що залишиться у пам’яті', lead: 'Ваша історія — у красивому зображенні чи меню для особливого вечора.',
      gift: 'Історія бажань', giftSub: 'Фото, бажання й атмосфера', food: 'Гастрономічний подарунок', foodSub: 'Меню, рецепти й друк',
      orders: 'Мої замовлення', ordersSub: 'Усі подарунки та готові файли', empty: 'Тут з’являться ваші подарунки.',
      back: 'На головну', photos: 'Фото близької людини', photosHint: 'Додайте від 1 до 7 фото. Сюжети ми підберемо самі.',
      photosNone: 'Фото ще не вибрані', photosChosen: 'Вибрано фото', photosExcess: 'Можна вибрати щонайбільше 7 фото', photosQueued: 'Надішлються під час створення подарунка',
      wishes: 'Від 5 до 9 бажань', wishesHint: 'Напишіть по одному бажанню в кожному полі.', addWish: 'Додати бажання', theme: 'Атмосфера', dark: 'Тепла темна', light: 'Світла', color: 'Яскрава',
      create: 'Створити подарунок', foodLead: 'Розкажіть, які страви увійдуть до вашого меню.', name: 'Ваше ім’я', phone: 'Телефон із кодом країни',
      cover: 'Фото для обкладинки', spread: 'Фото для розвороту', dishes: 'Страви', add: 'Додати страву', send: 'Створити меню',
      status: 'Стан замовлення', preview: 'Попередній перегляд', mobile: 'Зображення для телефона', desktop: 'Зображення для екрана',
      print: 'Архів для друкарні', recipes: 'Рецепти та продукти', check: 'Перевірити оплату', pay: 'Перейти до оплати',
      working: 'Ми створюємо ваш подарунок. Це триватиме кілька хвилин.', payment: 'До сплати', setting: 'Налаштування', language: 'Мова',
      vip: 'Безкоштовний доступ: Telegram usernames', save: 'Зберегти', admin: 'Керування', customers: 'Клієнти', menus: 'Меню', gifts: 'Подарунки', paid: 'Оплачено',
      previewMissing: 'Попередній перегляд поки недоступний. Готові файли з’являться тут.', details: 'Деталі замовлення', goals: 'Ваші бажання',
      ready: 'Подарунок готовий', generating: 'Створюємо зображення', queued: 'Замовлення прийнято', waiting_for_payment: 'Очікує оплати',
      payment_unavailable: 'Оплата тимчасово недоступна', payment_status: 'Очікує оплати', interrupted: 'Створення перервано',
      failed: 'Не вдалося завершити', blocked: 'Потрібне інше фото чи формулювання', completed: 'Готово',
      sent_to_printshop: 'Передано до друкарні', images_ready: 'Готуємо файли', partial_success: 'Частина файлів готова',
      retry: 'Продовжити створення', openFromBot: 'Відкрийте майстерню з Telegram-бота.', unpaid: 'Після оплати відкриються файли для завантаження.',
      checkLater: 'Оплату ще не підтверджено', wish: 'Бажання', number: 'Замовлення', noDishes: 'Страви з’являться після обробки замовлення.',
      sendEmail: 'Надіслати повне замовлення на email', email: 'Email одержувача', emailSent: 'Лист надіслано',
      share: 'Подарувати в Telegram', delivery: 'Вручення та доставка', openGift: 'Переглянути вручення',
      evening: 'Вечір за меню', eveningLead: 'Оберіть страви для одного вечора. Покажемо покупки, порядок приготування та час подачі.',
      eveningOld: 'Для цього замовлення план вечора ще не створено. Рецепти й покупки є у PDF.',
      chooseDishes: 'Страви цього вечора', shopping: 'Що купити', prepare: 'З чого почати', serve: 'Коли подавати',
      firstServe: 'Першу страву подати о', approx: 'Орієнтовно', minutes: 'хв', selected: 'позначити',
      progressPlan: 'Добираємо сюжети', progressRender: 'Створюємо зображення', progressQuality: 'Перевіряємо якість'
      ,studioLead: 'Ваші фото й мрії — наша художня історія. Сюжети, світло та композицію добере ШІ.',
      photoStep: 'Ваші фотографії', wishStep: 'Ваші бажання', themeStep: 'Настрій історії',
      artDirection: 'ШІ добере тло й сюжет до кожного бажання та поєднає все в одну історію.',
      styleDark: 'Тепле світло, глибокі тони', styleLight: 'Повітря, ніжність і світло', styleColor: 'Живі відтінки та емоції',
      summary: 'Перед створенням', photoUnit: 'фото', wishUnit: 'бажань', readySummary: 'Усе готово — можна створювати',
      fillSummary: 'Додайте фото й заповніть бажання', selectedTheme: 'Настрій',
      photoChecking: 'Перевіряємо якість знімків…', photoSmall: 'Знімок замалий (щонайменше 300 × 300 px). Виберіть інший.',
      photoSoft: 'Для кращого результату додайте знімок понад 800 px.', photoUnreadable: 'Не вдалося прочитати знімок. Виберіть інший.',
      samePhotos: 'Схоже, один знімок вибрано двічі.', sameWishes: 'Два бажання збігаються — різноманіття зробить історію цікавішою.',
      draftSaved: 'Текст збережено на цьому пристрої. Фото після оновлення треба вибрати знову.',
      progressIntro: 'Наш художній помічник працює над вашим подарунком'
    },
    en: {
      studio: 'Gift atelier', hello: 'A gift they will remember', lead: 'Your story becomes a beautiful image or a menu for a special evening.',
      gift: 'A story of wishes', giftSub: 'Photos, wishes and atmosphere', food: 'A culinary gift', foodSub: 'Menu, recipes and print',
      orders: 'My orders', ordersSub: 'Your gifts and finished files', empty: 'Your gifts will appear here.',
      back: 'Home', photos: 'Photos of your loved one', photosHint: 'Add 1 to 7 photos. We will choose the scenes.',
      photosNone: 'No photos selected yet', photosChosen: 'Photos selected', photosExcess: 'Choose no more than 7 photos', photosQueued: 'They will upload when you create the gift',
      wishes: '5 to 9 wishes', wishesHint: 'Write one wish in each field.', addWish: 'Add a wish', theme: 'Atmosphere', dark: 'Warm dark', light: 'Light', color: 'Colorful',
      create: 'Create gift', foodLead: 'Tell us which dishes belong in your menu.', name: 'Your name', phone: 'Phone with country code',
      cover: 'Cover photo', spread: 'Spread photo', dishes: 'Dishes', add: 'Add dish', send: 'Create menu',
      status: 'Order status', preview: 'Preview', mobile: 'Phone image', desktop: 'Desktop image', print: 'Print archive',
      recipes: 'Recipes and shopping list', check: 'Check payment', pay: 'Pay now', working: 'We are creating your gift. This may take a few minutes.',
      payment: 'Amount due', setting: 'Settings', language: 'Language', vip: 'Free access: Telegram usernames', save: 'Save',
      admin: 'Manage', customers: 'Customers', menus: 'Menus', gifts: 'Gifts', paid: 'Paid', previewMissing: 'Preview is not ready yet. Your finished files will appear here.',
      details: 'Order details', goals: 'Your wishes', ready: 'Gift is ready', generating: 'Creating your artwork', queued: 'Order received',
      waiting_for_payment: 'Awaiting payment', payment_unavailable: 'Payment temporarily unavailable', payment_status: 'Awaiting payment',
      interrupted: 'Creation interrupted', failed: 'Could not finish', blocked: 'Please try another photo or wording', completed: 'Complete',
      sent_to_printshop: 'Sent to print shop', images_ready: 'Preparing files', partial_success: 'Some files are ready',
      retry: 'Continue creating', openFromBot: 'Open the studio from the Telegram bot.', unpaid: 'Files unlock after payment.',
      checkLater: 'Payment has not been confirmed yet', wish: 'Wish', number: 'Order', noDishes: 'Your dishes will appear here once processed.',
      sendEmail: 'Email the complete order', email: 'Recipient email', emailSent: 'Email sent',
      share: 'Gift via Telegram', delivery: 'Gift and delivery', openGift: 'Preview the reveal',
      evening: 'Your dinner plan', eveningLead: 'Choose dishes for one evening. See what to buy, when to prepare and when to serve.',
      eveningOld: 'This earlier order has no dinner plan yet. The recipes and shopping list remain in the PDF.',
      chooseDishes: 'Tonight’s dishes', shopping: 'What to buy', prepare: 'Preparation order', serve: 'Serving times',
      firstServe: 'Serve the first course at', approx: 'Approximate', minutes: 'min', selected: 'check',
      progressPlan: 'Planning scenes', progressRender: 'Creating the image', progressQuality: 'Checking quality'
      ,studioLead: 'Your photos and dreams become one artful story. AI selects the scenes, light and composition.',
      photoStep: 'Your photos', wishStep: 'Your wishes', themeStep: 'Story atmosphere',
      artDirection: 'AI will match each wish with a setting and bring the scenes together.',
      styleDark: 'Warm light and rich tones', styleLight: 'Airy, gentle and luminous', styleColor: 'Vivid colour and emotion',
      summary: 'Before we begin', photoUnit: 'photos', wishUnit: 'wishes', readySummary: 'Everything is ready to create',
      fillSummary: 'Add photos and complete your wishes', selectedTheme: 'Atmosphere',
      photoChecking: 'Checking your photos…', photoSmall: 'A photo is too small (minimum 300 × 300 px). Choose another.',
      photoSoft: 'For better results, use a photo larger than 800 px.', photoUnreadable: 'Could not read a photo. Choose another.',
      samePhotos: 'It looks like the same photo was selected twice.', sameWishes: 'Two wishes match; variety can make the story richer.',
      draftSaved: 'Your words are saved on this device. Photos need selecting again after a refresh.',
      progressIntro: 'Our art assistant is creating your gift'
    }
  };
  const t = key => copy[state.lang]?.[key] || copy.uk[key] || key;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const status = code => t(code === 'payment' ? 'payment_status' : code || 'queued');
  const button = (label, action, style = 'secondary') => `<button type="button" class="${style}" data-action="${action}">${label}</button>`;

  async function api(path, options = {}) {
    if (!launchData) throw Error(t('openFromBot'));
    const response = await fetch('/miniapp/api' + path, {
      ...options, headers: {Authorization: 'tma ' + launchData, ...(options.headers || {})}
    });
    if (!response.ok) {
      let detail;
      try { detail = (await response.json()).detail; } catch (_) { /* HTTP error without JSON */ }
      throw Error(typeof detail === 'string' ? detail : `HTTP ${response.status}`);
    }
    return response.headers.get('content-type')?.includes('application/json') ? response.json() : response.blob();
  }

  function clearPreview() {
    if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
    state.previewUrl = '';
    state.previewError = '';
  }
  function notice(message, success = false) {
    state.error = message;
    document.querySelector('main > .error')?.remove();
    const banner = document.createElement('div');
    banner.className = success ? 'success' : 'error';
    banner.setAttribute('role', 'alert');
    banner.textContent = message;
    document.querySelector('#app > main')?.prepend(banner);
    setTimeout(() => { if (state.error === message) { state.error = ''; banner.remove(); } }, 7000);
  }
  async function loadPreview(path, key) {
    try {
      const blob = await api(path);
      if (state.viewKey !== key) return;
      clearPreview();
      state.previewUrl = URL.createObjectURL(blob);
      render();
    } catch (_) {
      if (state.viewKey === key) { state.previewError = t('previewMissing'); render(); }
    }
  }
  async function download(path, name) {
    const blob = await api(path);
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = name;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  }
  function goHomeButton(target = 'home') { return `<button type="button" class="back" data-page="${target}"><span aria-hidden="true">←</span> ${target === 'orders' ? t('orders') : t('back')}</button>`; }
  function footer() {
    return `<footer class="signature" aria-label="Credits"><div class="signature-rule"><span>✦</span></div><div class="signature-monogram">F<span>✦</span>P</div><div class="signature-lines"><span>With love for you.</span><span>С любовью для Вас.</span></div><div class="signature-by"><span>OLGA VOLOSHENKO</span><i>×</i><span>BONDAREV_E</span></div><div class="signature-meta">FOOD PORN ATELIER · PERSONAL GIFTS</div></footer>`;
  }
  function layout(body) {
    return `<header class="top"><button type="button" class="brand" data-page="home"><span class="brand-mark">✦</span><span>${t('studio')}<small>THE GIFT ATELIER</small></span></button><button type="button" class="header-action" data-page="settings" aria-label="${t('setting')}">⚙</button></header><main>${state.error ? `<div class="error" role="alert">${esc(state.error)}</div>` : ''}${body}</main>${footer()}`;
  }
  function orderCount() {
    const jobs = state.home?.jobs || [];
    const linked = new Set(jobs.map(job => job.order_id).filter(Boolean));
    return jobs.length + (state.home?.menus?.length || 0) + (state.home?.wallpapers || []).filter(order => !linked.has(order.id)).length;
  }
  function orderRows() {
    const jobs = (state.home?.jobs || []).map(job => ({kind:'job', id:job.id, icon:'✧', title:t('gift'), note:job.goals?.[0] || '', status:job.status}));
    const menus = (state.home?.menus || []).map(menu => ({kind:'menu', id:menu.id, icon:'◈', title:t('food'), note:`#${menu.id}`, status:menu.status}));
    const linked = new Set((state.home?.jobs || []).map(job => job.order_id).filter(Boolean));
    const old = (state.home?.wallpapers || []).filter(order => !linked.has(order.id)).map(order => ({kind:'wallpaper', id:order.id, icon:'✧', title:t('gift'), note:`#${order.id}`, status:order.paid ? 'ready' : 'payment'}));
    const rows = [...jobs, ...menus, ...old];
    return rows.length ? rows.map(row => `<button type="button" class="order-row" data-order="${row.kind}:${esc(row.id)}"><span class="order-icon">${row.icon}</span><span class="order-copy"><strong>${row.title}</strong><small>${esc(row.note)}</small></span><span class="order-end"><em>${esc(status(row.status))}</em><b aria-hidden="true">↗</b></span></button>`).join('') : `<div class="empty">✦<p>${t('empty')}</p></div>`;
  }
  function preview() {
    return `<section class="visual"><div class="visual-head"><span>${t('preview')}</span><span>✦</span></div>${state.previewUrl ? `<img class="preview" src="${state.previewUrl}" alt="${t('preview')}">` : `<div class="visual-empty"><span>✧</span><p>${state.previewError || t('previewMissing')}</p></div>`}</section>`;
  }
  function detailHead(title, id, currentStatus) {
    return `<div class="eyebrow">${t('number')} #${esc(id)}</div><h1>${title}</h1><div class="status-pill"><span class="status-dot"></span>${esc(status(currentStatus))}</div>`;
  }
  function deliveryTools(prefix) {
    return `<section class="panel delivery-panel"><div class="panel-title">${t('delivery')}</div><button type="button" class="primary" data-action="${prefix}-share">${t('share')}</button><label class="field" for="recipient-email">${t('email')}</label><input id="recipient-email" class="input" type="email" autocomplete="email" placeholder="name@example.com"><button type="button" class="secondary" data-action="${prefix}-email">${t('sendEmail')}</button></section>`;
  }
  function giftDetail(job) {
    const current = job?.status;
    const filesReady = current === 'ready';
    const canPreview = ['payment', 'payment_unavailable', 'ready'].includes(current);
    const progress = current === 'generating' ? t('progress' + (job?.progress || 'Plan').replace(/^./, c => c.toUpperCase())) : '';
    const stages = ['Plan','Render','Quality'];
    const currentStage = Math.max(0, stages.findIndex(stage => stage.toLowerCase() === String(job?.progress || 'plan').toLowerCase()));
    const timeline = current === 'generating' ? `<section class="panel creative-progress"><div class="panel-title">${t('progressIntro')}</div><ol>${stages.map((stage,index) => `<li class="${index < currentStage ? 'done' : index === currentStage ? 'current' : ''}"><span>${String(index + 1).padStart(2,'0')}</span>${t('progress' + stage)}</li>`).join('')}</ol><p class="muted">${progress || t('working')}</p></section>` : '';
    return `<div class="page detail">${goHomeButton('orders')}${detailHead(t('gift'), job?.order_id || String(job?.id || '').slice(0, 8), current)}${canPreview ? preview() : current === 'generating' ? timeline : `<section class="panel soft"><p>${esc(job?.error || status(current))}</p></section>`}
      <section class="panel"><div class="panel-title">${t('goals')} <span>${String(job?.goals?.length || 0).padStart(2,'0')}</span></div><ol class="wishes-list">${(job?.goals || []).map(goal => `<li>${esc(goal)}</li>`).join('')}</ol></section>
      ${job?.error ? `<p class="error">${esc(job.error)}</p>` : ''}
      ${current === 'interrupted' ? button(t('retry'), 'gift-retry', 'primary') : ''}
      ${['payment','payment_unavailable'].includes(current) ? `<section class="panel action-panel"><p>${t('unpaid')}</p><strong>${t('payment')}: ${esc(job.stars || '—')} ⭐</strong>${button(t('pay'), 'gift-pay', 'primary')}${button(t('check'), 'gift-check')}</section>` : ''}
      ${filesReady ? `<section class="panel action-panel"><div class="panel-title">${t('ready')}</div>${button(t('openGift'), 'gift-open', 'primary')}${button(t('mobile'), 'gift-mobile', 'file-button')}${button(t('desktop'), 'gift-desktop', 'file-button')}${button(t('print'), 'gift-print', 'file-button')}</section>${deliveryTools('gift')}` : ''}</div>`;
  }
  function menuDetail(menu) {
    const current = menu?.status;
    const canPreview = ['waiting_for_payment','images_ready','paid','completed','sent_to_printshop'].includes(current);
    const inProgress = ['queued','images_ready','partial_success'].includes(current);
    const progress = menu?.progress;
    const progressText = inProgress && progress?.total ? `${t('generating')}: ${progress.completed} / ${progress.total}` : (menu?.error || status(current));
    const ready = menu?.paid && !['queued','images_ready','partial_success','failed'].includes(current);
    return `<div class="page detail">${goHomeButton('orders')}${detailHead(t('food'), menu?.id, current)}${canPreview ? preview() : `<section class="panel soft"><p>${esc(progressText)}</p></section>`}
      <section class="panel"><div class="panel-title">${t('dishes')} <span>${String(menu?.items?.length || 0).padStart(2,'0')}</span></div>${menu?.items?.length ? `<ol class="wishes-list">${menu.items.map(item => `<li>${esc(item.title)}</li>`).join('')}</ol>` : `<p class="muted">${t('noDishes')}</p>`}</section>
      ${menu?.error ? `<p class="error">${esc(menu.error)}</p>` : ''}
      ${current === 'waiting_for_payment' && !menu.paid ? `<section class="panel action-panel"><p>${t('unpaid')}</p><strong>${t('payment')}: ${esc(menu.stars || '—')} ⭐</strong>${button(t('pay'), 'menu-pay', 'primary')}${button(t('check'), 'menu-check')}</section>` : ''}
      ${ready ? `<section class="panel action-panel"><div class="panel-title">${t('ready')}</div>${button(t('evening'), 'menu-evening', 'primary')}${button(t('openGift'), 'menu-open', 'secondary')}${button('PDF · ' + t('print'), 'menu-pdf', 'file-button')}${button(t('recipes'), 'menu-recipes', 'file-button')}</section>${deliveryTools('menu')}` : ''}</div>`;
  }
  function wallpaperDetail(order) {
    const files = `${button(t('mobile'), 'wallpaper-mobile', 'file-button')}${button(t('desktop'), 'wallpaper-desktop', 'file-button')}${button(t('print'), 'wallpaper-print', 'file-button')}`;
    const price = order?.stars ? `${esc(order.stars)} ⭐` : `${esc(order?.amount || '—')} UAH`;
    const checkout = `<p>${t('unpaid')}</p><strong>${t('payment')}: ${price}</strong>${order?.stars ? button(t('pay'), 'wallpaper-pay', 'primary') : ''}${button(t('check'), 'wallpaper-check')}`;
    return `<div class="page detail">${goHomeButton('orders')}${detailHead(t('gift'), order?.id, order?.paid ? 'ready' : 'payment')}${preview()}<section class="panel action-panel"><div class="panel-title">${t('details')}</div>${order?.paid ? files : checkout}</section>${order?.paid ? deliveryTools('wallpaper') : ''}</div>`;
  }
  function dishRow() {
    return `<div class="dish"><select class="input" name="category"><option value="main">Основное</option><option value="appetizer">Закуска</option><option value="salad">Салат</option><option value="soup">Суп</option><option value="dessert">Десерт</option><option value="drink">Напиток</option></select><input class="input" name="title" required maxlength="180" placeholder="${t('dishes')}"><button type="button" data-action="remove-dish" aria-label="Remove dish">×</button></div>`;
  }
  function dishKey(item) { return `${item.category}:${item.position}:${item.title}`; }
  function clock(minutes) {
    const normalized = ((minutes % 1440) + 1440) % 1440;
    return `${String(Math.floor(normalized / 60)).padStart(2,'0')}:${String(normalized % 60).padStart(2,'0')}`;
  }
  function eveningPage() {
    if (!state.evening) return `<div class="page">${goHomeButton('menu')}<h1>${t('evening')}</h1><section class="panel soft"><p>${t('eveningOld')}</p></section></div>`;
    const menuId = state.eveningMenuId;
    const selections = state.eveningSelected || [];
    const selected = new Set(selections);
    const courses = state.evening.serve.filter(item => selected.has(dishKey(item)));
    const buying = new Map();
    courses.forEach(item => item.ingredients.forEach(ingredient => buying.set(ingredient, (buying.get(ingredient) || 0) + 1)));
    const time = state.eveningTime || '19:00';
    const [hours, minutes] = time.split(':').map(Number);
    const start = (Number.isFinite(hours) ? hours : 19) * 60 + (Number.isFinite(minutes) ? minutes : 0);
    const serving = courses.map((item,index) => ({item, when: start + (item.category === 'drink' ? 0 : index * 25)}));
    const cooking = state.evening.prepare.filter(item => selected.has(dishKey(item))).map(item => {
      const served = serving.find(entry => dishKey(entry.item) === dishKey(item));
      return {item, when: (served?.when ?? start) - item.prep_minutes - item.cook_minutes - 15};
    }).sort((a,b) => a.when-b.when);
    return `<div class="page dinner">${goHomeButton('menu')}<div class="eyebrow">FOOD PORN · #${esc(menuId)}</div><h1>${t('evening')}</h1><p class="sub">${t('eveningLead')}</p>
      <section class="panel"><div class="panel-title">${t('chooseDishes')}</div><div class="course-choices">${state.evening.serve.map((item,index) => `<label class="course-choice"><input type="checkbox" data-course="${index}" ${selected.has(dishKey(item)) ? 'checked' : ''}><span>${esc(item.title)}</span><small>${esc(item.prep_minutes + item.cook_minutes)} ${t('minutes')}</small></label>`).join('')}</div></section>
      <section class="panel"><label class="field" for="dinner-time">${t('firstServe')}</label><input class="input time-input" id="dinner-time" type="time" value="${esc(time)}"><p class="muted">${t('approx')}: ${t('prepare').toLowerCase()} та ${t('serve').toLowerCase()}.</p></section>
      <section class="panel"><div class="panel-title">${t('shopping')} <span>${buying.size}</span></div><div class="shopping-list">${[...buying].map(([ingredient,count]) => `<label class="shop-row"><input type="checkbox" data-ingredient="${esc(ingredient)}" ${state.eveningChecked?.[ingredient] ? 'checked' : ''}><span>${esc(ingredient)}${count > 1 ? ` ×${count}` : ''}</span></label>`).join('')}</div></section>
      <section class="panel"><div class="panel-title">${t('prepare')}</div><ol class="plan-list">${cooking.map(({item,when}) => `<li><time>${clock(when)}</time><span><strong>${esc(item.title)}</strong><small>${esc(item.prep_minutes)} + ${esc(item.cook_minutes)} ${t('minutes')}</small></span></li>`).join('')}</ol></section>
      <section class="panel"><div class="panel-title">${t('serve')}</div><ol class="plan-list">${serving.map(({item,when}) => `<li><time>${clock(when)}</time><span>${esc(item.title)}</span></li>`).join('')}</ol></section></div>`;
  }
  async function openEvening() {
    const id = state.menu?.id;
    state.eveningMenuId = id;
    state.evening = null;
    state.error = '';
    try {
      state.evening = await api(`/menus/${id}/evening`);
      const key = `food-porn-evening-${id}`;
      let saved = {};
      try { saved = JSON.parse(localStorage.getItem(key) || '{}'); } catch (_) { /* private browsing */ }
      state.eveningTime = saved.time || '19:00';
      state.eveningChecked = saved.checked || {};
      state.eveningSelected = saved.selected || null;
      if (!state.eveningSelected) {
        const courseList = state.evening.serve;
        const picks = ['appetizer','main','dessert','drink'].map(category =>
          courseList.find(item => item.category === category)).filter(Boolean);
        if (!picks.some(item => item.category === 'appetizer')) {
          const salad = courseList.find(item => item.category === 'salad' || item.category === 'soup');
          if (salad) picks.unshift(salad);
        }
        state.eveningSelected = (picks.length ? picks : courseList.slice(0, 4)).map(dishKey);
      }
    } catch (error) {
      state.error = error.message;
      state.evening = null;
    }
    state.page = 'evening'; render(); window.scrollTo(0,0);
  }
  function saveEvening() {
    try { localStorage.setItem(`food-porn-evening-${state.eveningMenuId}`, JSON.stringify({
      selected:state.eveningSelected, checked:state.eveningChecked, time:state.eveningTime
    })); } catch (_) { /* Device storage may be unavailable. */ }
  }
  function releaseGiftPhotoUrls() {
    giftPhotoUrls.forEach(url => URL.revokeObjectURL(url));
    giftPhotoUrls = [];
  }
  function readGiftDraft() {
    try {
      const draft = JSON.parse(sessionStorage.getItem(giftDraftKey) || '{}');
      return {goals:Array.isArray(draft.goals) ? draft.goals.slice(0, 9).map(value => String(value).slice(0, 280)) : [],
        style:['dark','light','color'].includes(draft.style) ? draft.style : 'dark'};
    } catch (_) { return {goals:[], style:'dark'}; }
  }
  function saveGiftDraft() {
    const form = app.querySelector('#gift-form');
    if (!form) return;
    try { sessionStorage.setItem(giftDraftKey, JSON.stringify({
      goals:[...form.querySelectorAll('#gift-goals textarea')].map(field => field.value),
      style:state.style
    })); } catch (_) { /* Private browsing may disable storage. */ }
  }
  function giftSummary() {
    const form = app.querySelector('#gift-form');
    if (!form) return;
    const photos = form.querySelector('#gift-photo-input')?.files?.length || 0;
    const fields = [...form.querySelectorAll('#gift-goals textarea')];
    const completed = fields.filter(field => field.value.trim()).length;
    const output = form.querySelector('#gift-summary');
    const hint = form.querySelector('#gift-goal-hint');
    const normalized = fields.map(field => field.value.trim().toLocaleLowerCase()).filter(Boolean);
    if (hint) hint.textContent = new Set(normalized).size < normalized.length ? t('sameWishes') : t('artDirection');
    const photosValid = photos > 0 && photos <= 7 && !form.querySelector('#gift-photo-input')?.validity?.customError;
    if (output) output.innerHTML = `<span>${photos} / 7 ${t('photoUnit')}</span><span>${completed} / ${fields.length} ${t('wishUnit')}</span><span>${t('selectedTheme')}: ${t(state.style)}</span><strong>${photosValid && completed === fields.length ? t('readySummary') : t('fillSummary')}</strong>`;
  }
  function inspectPhoto(image, file, selection) {
    return new Promise(resolve => {
      const finish = message => {
        if (selection === giftPhotoSelection) {
          const item = image.closest('.photo-thumb');
          if (message) item?.classList.add(message === 'photoSmall' || message === 'photoUnreadable' ? 'bad' : 'soft');
          resolve(message);
        } else resolve('');
      };
      image.addEventListener('load', () => {
        if (Math.min(image.naturalWidth, image.naturalHeight) < 300) finish('photoSmall');
        else if (Math.min(image.naturalWidth, image.naturalHeight) < 800) finish('photoSoft');
        else finish('');
      }, {once:true});
      image.addEventListener('error', () => finish('photoUnreadable'), {once:true});
      image.src = URL.createObjectURL(file);
      giftPhotoUrls.push(image.src);
    });
  }
  function updateGiftPhotos(input) {
    const selection = ++giftPhotoSelection;
    const files = Array.from(input.files || []);
    const count = files.length;
    const invalid = count > 7;
    const status = app.querySelector('#gift-photo-status');
    const tally = app.querySelector('#gift-photo-count');
    const progress = app.querySelector('#gift-photo-progress');
    const preview = app.querySelector('#gift-photo-preview');
    if (!status || !tally || !progress || !preview) return;
    releaseGiftPhotoUrls();
    input.setCustomValidity(invalid ? t('photosExcess') : '');
    status.textContent = invalid ? t('photosExcess') : count ? `${t('photosChosen')}: ${count} / 7` : t('photosNone');
    tally.textContent = `${String(count).padStart(2, '0')} / 07`;
    const selectionBox = app.querySelector('#gift-photo-selection');
    selectionBox.classList.toggle('has-photos', count > 0 && !invalid);
    selectionBox.classList.toggle('invalid', invalid);
    progress.replaceChildren();
    preview.replaceChildren();
    for (let index = 0; index < 7; index++) {
      const mark = document.createElement('span');
      mark.className = index < count ? 'filled' : '';
      progress.append(mark);
    }
    const checks = files.slice(0, 7).map((file, index) => {
      const item = document.createElement('div');
      item.className = 'photo-thumb';
      item.title = file.name;
      const image = document.createElement('img');
      image.alt = `${t('photos')} ${index + 1}`;
      const number = document.createElement('span');
      number.textContent = String(index + 1).padStart(2, '0');
      item.append(image, number);
      preview.append(item);
      return inspectPhoto(image, file, selection);
    });
    giftSummary();
    if (!invalid && count) status.textContent = t('photoChecking');
    giftPhotoCheck = Promise.all(checks).then(results => {
      if (selection !== giftPhotoSelection) return;
      const fatal = results.find(result => result === 'photoSmall' || result === 'photoUnreadable');
      const duplicates = new Set(files.map(file => [file.name,file.size,file.lastModified].join(':'))).size !== files.length;
      const warning = fatal || (invalid ? 'photosExcess' : duplicates ? 'samePhotos' : results.includes('photoSoft') ? 'photoSoft' : '');
      input.setCustomValidity(fatal ? t(fatal) : invalid ? t('photosExcess') : '');
      status.textContent = warning ? t(warning) : count ? `${t('photosChosen')}: ${count} / 7` : t('photosNone');
      selection && app.querySelector('#gift-photo-selection')?.classList.toggle('invalid', Boolean(fatal || invalid));
      giftSummary();
    });
  }
  function render() {
    releaseGiftPhotoUrls();
    let body = '';
    switch (state.page) {
      case 'home':
        body = `<section class="hero"><div class="hero-orbit one"></div><div class="hero-orbit two"></div><div class="eyebrow">PERSONAL GIFTS • MADE WITH LOVE</div><h1>${t('hello')}</h1><p>${t('lead')}</p><img class="hero-art" src="/miniapp/static/gift-ribbon.svg" alt="" aria-hidden="true"></section>
          <div class="section-heading"><span>01 / ${t('studio')}</span><i>✦</i></div><div class="product-grid"><button type="button" class="product-card image-card" data-page="gift"><span class="product-top">01 <span>↗</span></span><img class="product-art" src="/miniapp/static/gift-ribbon.svg" alt="" aria-hidden="true"><strong>${t('gift')}</strong><small>${t('giftSub')}</small></button><button type="button" class="product-card menu-card" data-page="food"><span class="product-top">02 <span>↗</span></span><img class="product-art" src="/miniapp/static/kitchen-cloche.svg" alt="" aria-hidden="true"><strong>${t('food')}</strong><small>${t('foodSub')}</small></button></div>
          <button type="button" class="orders-launch" data-page="orders"><span class="orders-glyph">◫</span><span><strong>${t('orders')}</strong><small>${t('ordersSub')}</small></span><em>${orderCount()}</em><b aria-hidden="true">→</b></button>${state.home?.admin ? `<button type="button" class="admin-launch" data-page="admin">✦ ${t('admin')} <span>→</span></button>` : ''}`;
        break;
      case 'gift': {
        const draft = readGiftDraft();
        state.style = draft.style;
        const count = Math.max(5, Math.min(9, draft.goals.length));
        body = `<div class="form gift-studio">${goHomeButton()}<div class="eyebrow">01 / PERSONAL STORY</div><h1>${t('gift')}</h1><p class="sub">${t('studioLead')}</p><form id="gift-form" class="panel">
          <div class="studio-section"><div class="studio-heading"><span>01</span><div><h2>${t('photoStep')}</h2><p>${t('photosHint')}</p></div></div>
          <div class="drop"><input id="gift-photo-input" name="photos" type="file" accept="image/jpeg,image/png,image/webp" aria-describedby="gift-photo-status" multiple required><div id="gift-photo-selection" class="photo-selection" role="status" aria-live="polite"><div class="photo-selection-head"><span id="gift-photo-status">${t('photosNone')}</span><strong id="gift-photo-count">00 / 07</strong></div><div id="gift-photo-progress" class="photo-progress" aria-hidden="true">${Array.from({length:7}, () => '<span></span>').join('')}</div><small>${t('photosQueued')}</small><div id="gift-photo-preview" class="photo-preview"></div></div></div></div>
          <div class="studio-section"><div class="studio-heading"><span>02</span><div><h2>${t('wishStep')}</h2><p>${t('wishesHint')}</p></div></div><div id="gift-goals">${Array.from({length:count}, (_,index) => { const i = index + 1; return `<div class="goal"><i>${String(i).padStart(2,'0')}</i><textarea name="goal${i}" required maxlength="280" aria-label="${t('wish')} ${i}" placeholder="${t('wish')} ${i}">${esc(draft.goals[index] || '')}</textarea></div>`; }).join('')}</div><p id="gift-goal-hint" class="studio-guidance">${t('artDirection')}</p>${count < 9 ? button('+ ' + t('addWish'), 'add-wish') : ''}${draft.goals.some(Boolean) ? `<p class="draft-note">${t('draftSaved')}</p>` : ''}</div>
          <div class="studio-section"><div class="studio-heading"><span>03</span><div><h2>${t('themeStep')}</h2><p>${t('theme')}</p></div></div><div class="style-cards" role="group" aria-label="${t('theme')}">${['dark','light','color'].map(style => `<button type="button" class="style-card ${state.style === style ? 'active' : ''}" data-style="${style}" aria-pressed="${state.style === style}"><span class="style-swatch ${style}" aria-hidden="true"></span><span><strong>${t(style)}</strong><small>${t('style' + style[0].toUpperCase() + style.slice(1))}</small></span><i aria-hidden="true">✓</i></button>`).join('')}</div></div>
          <div class="studio-summary"><div class="panel-title">${t('summary')}</div><div id="gift-summary"></div></div>${button(t('create'), 'submit-gift', 'primary')}</form></div>`;
        break;
      }
      case 'food':
        body = `<div class="form">${goHomeButton()}<div class="eyebrow">02 / CULINARY STORY</div><h1>${t('food')}</h1><p class="sub">${t('foodLead')}</p><form id="menu-form" class="panel">${!state.home?.customer ? `<label class="field">${t('name')}</label><input class="input" name="name" required maxlength="100"><label class="field">${t('phone')}</label><input class="input" type="tel" name="phone" required placeholder="+380…">` : ''}<label class="field">${t('cover')}</label><input class="input" name="cover" type="file" accept="image/jpeg,image/png,image/webp" required><label class="field">${t('spread')}</label><input class="input" name="spread" type="file" accept="image/jpeg,image/png,image/webp" required><label class="field">${t('dishes')}</label><div id="dishes">${dishRow()}</div>${button('+ ' + t('add'), 'add-dish')}${button(t('send'), 'submit-menu', 'primary')}</form></div>`;
        break;
      case 'orders':
        body = `<div class="page">${goHomeButton()}<div class="eyebrow">YOUR STORIES</div><h1>${t('orders')}</h1><p class="sub">${t('ordersSub')}</p><div class="orders-list">${orderRows()}</div></div>`;
        break;
      case 'evening': body = eveningPage(); break;
      case 'job': body = giftDetail(state.job); break;
      case 'menu': body = menuDetail(state.menu); break;
      case 'wallpaper': body = wallpaperDetail(state.wallpaper); break;
      case 'settings':
        body = `<div class="page">${goHomeButton()}<h1>${t('setting')}</h1><section class="panel"><label class="field">${t('language')}</label><div class="styles">${[['uk','Українська'],['ru','Русский'],['en','English']].map(([code,label]) => `<button type="button" class="chip ${code === state.lang ? 'active' : ''}" data-lang="${code}">${label}</button>`).join('')}</div></section></div>`;
        break;
      case 'admin': {
        const a = state.admin;
        body = `<div class="page">${goHomeButton()}<h1>${t('admin')}</h1><div class="admin-grid">${[['♧','customers'],['◈','menus'],['✧','gifts'],['✓','paid_gifts']].map(([icon,key]) => `<div class="stat-card"><span>${icon}</span><strong>${a?.[key] ?? '–'}</strong><small>${t(key === 'paid_gifts' ? 'paid' : key)}</small></div>`).join('')}</div><section class="panel"><div class="panel-title">${t('details')}</div><p>Telegram Stars: ${a?.stars_ready ? '✓' : '—'} · ${esc(a?.stars_revenue || 0)} ⭐</p><p>Portmone: ${a?.payment_ready ? '✓' : '—'} · ${esc(a?.revenue || '0')} UAH</p><label class="field">Menu price, UAH</label><input id="menu-price" class="input" type="number" min="1" max="100000" step="0.01" value="${esc(a?.menu_price)}">${button(t('save'), 'save-price')}<hr class="divider"><label class="field">${t('vip')}</label><textarea id="vip" placeholder="username, username">${esc((a?.vip || []).join(', '))}</textarea>${button(t('save'), 'save-vip', 'primary')}</section></div>`;
        break;
      }
    }
    app.innerHTML = layout(body);
    if (state.page === 'gift') giftSummary();
  }

  async function open(page) {
    state.page = page;
    state.error = '';
    state.viewKey = '';
    clearPreview();
    try {
      if (['home','orders','food'].includes(page)) state.home = await api('/home');
      if (page === 'admin') state.admin = await api('/admin');
    } catch (error) { state.error = error.message; }
    render();
    window.scrollTo(0, 0);
  }
  async function openOrder(kind, id) {
    clearPreview();
    state.error = '';
    const key = `${kind}:${id}`;
    const path = kind === 'job' ? `/gifts/${id}` : kind === 'menu' ? `/menus/${id}` : `/wallpapers/${id}`;
    try {
      const order = await api(path);
      state.page = kind;
      state.viewKey = key;
      state[kind] = order;
      render();
      window.scrollTo(0, 0);
      if (kind !== 'job' || ['payment','payment_unavailable','ready'].includes(order.status)) {
        await loadPreview(path + '/files/preview', key);
      }
    } catch (error) { notice(error.message); }
  }
  function openPayment(url, kind, id) {
    if (tg?.openInvoice) tg.openInvoice(url, status => {
      if (status === 'paid') setTimeout(() => openOrder(kind, id), 1200);
    });
    else if (tg?.openTelegramLink) tg.openTelegramLink(url);
    else window.open(url, '_blank');
  }
  app.addEventListener('click', async event => {
    const element = event.target.closest('button');
    if (!element) return;
    if (element.dataset.page) { await open(element.dataset.page); return; }
    if (element.dataset.order) {
      const [kind,id] = element.dataset.order.split(':');
      await openOrder(kind, id);
      return;
    }
    try {
      if (element.dataset.lang) {
        state.lang = element.dataset.lang;
        try { localStorage.setItem('gift_lang', state.lang); } catch (_) { /* private browsing */ }
        await api('/language', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({language:state.lang})});
        render(); return;
      }
      if (element.dataset.style) {
        state.style = element.dataset.style;
        document.querySelectorAll('[data-style]').forEach(chip => {
          chip.classList.toggle('active', chip.dataset.style === state.style);
          chip.setAttribute('aria-pressed', String(chip.dataset.style === state.style));
        });
        saveGiftDraft();
        giftSummary();
        return;
      }
      const action = element.dataset.action;
      if (!action) return;
      if (action === 'add-dish') {
        if (document.querySelectorAll('.dish').length < 18) document.querySelector('#dishes').insertAdjacentHTML('beforeend', dishRow());
        return;
      }
      if (action === 'remove-dish') {
        if (document.querySelectorAll('.dish').length > 1) element.closest('.dish').remove();
        return;
      }
      if (action === 'add-wish') {
        const container = document.querySelector('#gift-goals');
        const count = container.querySelectorAll('.goal').length;
        if (count < 9) {
          const next = count + 1;
          const row = document.createElement('div');
          row.className = 'goal';
          const numeral = document.createElement('i');
          numeral.textContent = String(next);
          const field = document.createElement('textarea');
          field.name = `goal${next}`;
          field.required = true;
          field.maxLength = 280;
          field.placeholder = `${t('wish')} ${next}`;
          field.setAttribute('aria-label', `${t('wish')} ${next}`);
          row.append(numeral, field);
          container.append(row);
          if (next === 9) element.remove();
        }
        saveGiftDraft();
        giftSummary();
        return;
      }
      if (action === 'submit-gift') {
        const form = document.querySelector('#gift-form');
        await giftPhotoCheck;
        if (!form.reportValidity()) return;
        const formData = new FormData(form);
        const photos = formData.getAll('photos').filter(photo => photo.size);
        if (photos.length < 1 || photos.length > 7) throw Error(t('photosHint'));
        const goals = Array.from(form.querySelectorAll('#gift-goals textarea'), field => String(formData.get(field.name)).trim());
        if (goals.some(goal => !goal)) throw Error(t('wishesHint'));
        if (goals.some(goal => goal.includes('\n'))) throw Error(t('wishesHint'));
        const payload = new FormData();
        photos.forEach(photo => payload.append('photos', photo));
        payload.append('goals', goals.join('\n'));
        payload.append('style', state.style);
        payload.append('language', state.lang);
        element.disabled = true;
        const job = await api('/gifts', {method:'POST', body:payload});
        try { sessionStorage.removeItem(giftDraftKey); } catch (_) { /* Storage may be unavailable. */ }
        state.job = job; state.page = 'job'; state.viewKey = `job:${job.id}`;
        render(); return;
      }
      if (action === 'submit-menu') {
        const form = document.querySelector('#menu-form');
        if (!form.reportValidity()) return;
        const payload = new FormData(form);
        payload.set('dishes', JSON.stringify([...form.querySelectorAll('.dish')].map(row => ({category:row.querySelector('select').value, title:row.querySelector('input').value.trim()}))));
        payload.set('language', state.lang);
        element.disabled = true;
        const menu = await api('/menus', {method:'POST', body:payload});
        state.menu = menu; state.page = 'menu'; state.viewKey = `menu:${menu.id}`;
        render(); return;
      }
      if (action === 'menu-evening') { await openEvening(); return; }
      if (action === 'gift-open' || action === 'menu-open') {
        const target = action === 'gift-open' ? `gifts/${state.job.id}` : `menus/${state.menu.id}`;
        const result = await api(`/${target}/share`, {method:'POST'});
        if (result.present_url && tg?.openLink) tg.openLink(result.present_url);
        else if (result.present_url) window.open(result.present_url, '_blank');
        return;
      }
      if (action === 'gift-retry') { state.job = await api(`/gifts/${state.job.id}/retry`, {method:'POST'}); render(); return; }
      if (['gift-pay','menu-pay','wallpaper-pay'].includes(action)) {
        const path = action === 'gift-pay' ? `/gifts/${state.job.id}` : action === 'menu-pay' ? `/menus/${state.menu.id}` : `/wallpapers/${state.wallpaper.id}`;
        const result = await api(path + '/checkout', {method:'POST'});
        openPayment(result.url, action === 'gift-pay' ? 'job' : action === 'menu-pay' ? 'menu' : 'wallpaper',
          action === 'gift-pay' ? state.job.id : action === 'menu-pay' ? state.menu.id : state.wallpaper.id);
        return;
      }
      if (['gift-check','menu-check','wallpaper-check'].includes(action)) {
        const kind = action.split('-')[0];
        const id = kind === 'gift' ? state.job.id : kind === 'menu' ? state.menu.id : state.wallpaper.id;
        const prefix = kind === 'gift' ? 'gifts' : kind === 'menu' ? 'menus' : 'wallpapers';
        const result = await api(`/${prefix}/${id}/verify`, {method:'POST'});
        if (result.paid) await openOrder(kind === 'gift' ? 'job' : kind, id);
        else notice(t('checkLater'));
        return;
      }
      if (action === 'save-price') {
        await api('/admin/menu-price', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({price:document.querySelector('#menu-price').value})});
        state.admin = await api('/admin'); render(); return;
      }
      if (action === 'save-vip') {
        await api('/admin/vip', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({names:document.querySelector('#vip').value.split(',').map(name => name.trim()).filter(Boolean)})});
        state.admin = await api('/admin'); render(); return;
      }
      if (action === 'gift-share' || action === 'menu-share' || action === 'wallpaper-share') {
        const target = action === 'gift-share' ? `gifts/${state.job.id}` : action === 'menu-share' ? `menus/${state.menu.id}` : `wallpapers/${state.wallpaper.id}`;
        const result = await api(`/${target}/share`, {method:'POST'});
        if (result.prepared_message_id && tg?.shareMessage && (!tg.isVersionAtLeast || tg.isVersionAtLeast('8.0'))) {
          tg.shareMessage(result.prepared_message_id);
          return;
        }
        const share = `https://t.me/share/url?url=${encodeURIComponent(result.url)}&text=${encodeURIComponent(t('share'))}`;
        if (tg?.openTelegramLink) tg.openTelegramLink(share);
        else window.open(share, '_blank');
        return;
      }
      if (action === 'gift-email' || action === 'menu-email' || action === 'wallpaper-email') {
        const email = document.querySelector('#recipient-email');
        if (!email?.checkValidity() || !email.value) { email?.reportValidity(); return; }
        const target = action === 'gift-email' ? `gifts/${state.job.id}` : action === 'menu-email' ? `menus/${state.menu.id}` : `wallpapers/${state.wallpaper.id}`;
        element.disabled = true;
        await api(`/${target}/email`, {method:'POST', headers:{'Content-Type':'application/json'},
          body:JSON.stringify({email:email.value.trim()})});
        element.disabled = false;
        notice(t('emailSent'), true);
        return;
      }
      for (const [prefix, kind, id] of [['gift-', 'gifts', state.job?.id], ['menu-', 'menus', state.menu?.id], ['wallpaper-', 'wallpapers', state.wallpaper?.id]]) {
        if (action.startsWith(prefix)) { await download(`/${kind}/${id}/files/${action.slice(prefix.length)}`, `${kind}-${id}-${action.slice(prefix.length)}`); return; }
      }
    } catch (error) { element.disabled = false; notice(error.message); }
  });
  app.addEventListener('change', event => {
    if (event.target.id === 'gift-photo-input') {
      updateGiftPhotos(event.target);
      return;
    }
    if (state.page !== 'evening' || !state.evening) return;
    const element = event.target;
    if (element.id === 'dinner-time') state.eveningTime = element.value;
    else if (element.dataset.course != null) {
      const dish = state.evening.serve[Number(element.dataset.course)];
      if (!dish) return;
      const key = dishKey(dish);
      const selected = new Set(state.eveningSelected);
      if (element.checked) selected.add(key); else selected.delete(key);
      state.eveningSelected = [...selected];
    } else if (element.dataset.ingredient != null) {
      state.eveningChecked[element.dataset.ingredient] = element.checked;
    } else return;
    saveEvening(); render();
  });
  app.addEventListener('input', event => {
    if (event.target.closest('#gift-goals')) { saveGiftDraft(); giftSummary(); }
  });
  if (!launchData) {
    app.innerHTML = `<main class="loading">${t('openFromBot')}</main>`;
    return;
  }
  open('home');
  setInterval(async () => {
    try {
      if (state.page === 'job' && state.job?.status === 'generating') {
        const old = state.job.status;
        state.job = await api(`/gifts/${state.job.id}`);
        render();
        if (old !== state.job.status && ['payment','payment_unavailable','ready'].includes(state.job.status)) {
          await loadPreview(`/gifts/${state.job.id}/files/preview`, state.viewKey);
        }
      }
      if (state.page === 'menu' && ['queued','images_ready','partial_success'].includes(state.menu?.status)) {
        state.menu = await api(`/menus/${state.menu.id}`);
        render();
        if (!state.previewUrl && ['waiting_for_payment','paid','completed','sent_to_printshop'].includes(state.menu.status)) {
          await loadPreview(`/menus/${state.menu.id}/files/preview`, state.viewKey);
        }
      }
    } catch (_) { /* Keep the visible order while connectivity recovers. */ }
  }, 12000);
})();
