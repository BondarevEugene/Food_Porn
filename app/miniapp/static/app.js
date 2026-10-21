(() => {
  'use strict';
  const tg = window.Telegram?.WebApp;
  tg?.ready();
  tg?.expand();
  const app = document.querySelector('#app');
  const launchData = tg?.initData || '';
  const channelToken = new URLSearchParams(window.location.search).get('channel_token') || '';
  const authorization = launchData ? 'tma ' + launchData : channelToken ? 'channel ' + channelToken : '';
  let giftPhotoUrls = [];
  let giftPhotoSelection = 0;
  let giftPhotoCheck = Promise.resolve();
  const giftDraftKey = 'food-porn-gift-draft-v2';
  let savedLanguage = '';
  try { savedLanguage = localStorage.getItem('gift_lang') || ''; } catch (_) { /* private browsing */ }
  const state = {
    page: 'home', home: null, admin: null, job: null, menu: null, wallpaper: null, evening: null,
    sceneStudio: null, studioScene: 0, studioCompare: {left:'current', right:'current'}, studioImages: {},
    style: 'dark', lang: savedLanguage || tg?.initDataUnsafe?.user?.language_code?.slice(0, 2) || 'uk',
    error: '', previewUrl: '', previewError: '', viewKey: '', cookingIndex: 0, cookingStep: 0,
    menuInputMode: 'list'
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
      menuSimple: 'Просто список', menuDetailed: 'По категориям', dishListHint: 'Одно блюдо с новой строки. Можно написать «Десерт: тирамису» или «пас».',
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
      menuSimple: 'Просто список', menuDetailed: 'За категоріями', dishListHint: 'Одна страва з нового рядка. Можна написати «Десерт: тірамісу» або «пас».',
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
      menuSimple: 'Simple list', menuDetailed: 'By category', dishListHint: 'One dish per line. You may write “Dessert: tiramisu” or “pass”.',
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
  const studioWords = () => {
    const words = {
    ru:{title:'Редактор сцен',lead:'Меняйте только одну часть коллажа и сохраняйте удачные лица.',locked:'Зафиксирована',unlock:'Разблокировать',lock:'Зафиксировать сцену',current:'Текущий вариант',newVersion:'Создать вариант',instruction:'Что изменить',placeholder:'Например: заменить фон на вечерний Париж, лицо и одежду сохранить',scene:'Вся сцена',clothing:'Одежда',background:'Фон',mood:'Настроение',apply:'Выбрать этот вариант',formats:'Форматы из одного заказа',makeFormats:'Создать 6 форматов',video:'Живой коллаж',phrase:'Финальная фраза',aiVoice:'Озвучить фразу голосом AI',voice:'Или загрузить свой голос',music:'Своя музыка (необязательно)',makeVideo:'Создать видео 10–20 сек.',legacy:'Этот заказ создан до появления редактора сцен. Форматы доступны, но для редактирования сцен нужен новый заказ.',compare:'Сравнение вариантов'},
    uk:{title:'Редактор сцен',lead:'Змінюйте лише одну частину колажу та зберігайте вдалі обличчя.',locked:'Зафіксована',unlock:'Розблокувати',lock:'Зафіксувати сцену',current:'Поточний варіант',newVersion:'Створити варіант',instruction:'Що змінити',placeholder:'Наприклад: замінити тло на вечірній Париж, обличчя й одяг зберегти',scene:'Уся сцена',clothing:'Одяг',background:'Тло',mood:'Настрій',apply:'Обрати цей варіант',formats:'Формати з одного замовлення',makeFormats:'Створити 6 форматів',video:'Живий колаж',phrase:'Фінальна фраза',aiVoice:'Озвучити фразу голосом AI',voice:'Або завантажити свій голос',music:'Своя музика (необов’язково)',makeVideo:'Створити відео 10–20 сек.',legacy:'Це замовлення створене до появи редактора сцен. Формати доступні, але для редагування сцен потрібне нове замовлення.',compare:'Порівняння варіантів'},
    en:{title:'Scene Studio',lead:'Change one part of the collage while keeping every successful face.',locked:'Locked',unlock:'Unlock',lock:'Lock scene',current:'Current version',newVersion:'Create variant',instruction:'What should change?',placeholder:'For example: use evening Paris as the background; keep face and clothes',scene:'Whole scene',clothing:'Clothing',background:'Background',mood:'Mood',apply:'Use this version',formats:'Formats from one order',makeFormats:'Create 6 formats',video:'Living collage',phrase:'Final phrase',aiVoice:'Narrate the phrase with AI',voice:'Or upload your voice',music:'Your music (optional)',makeVideo:'Create a 10–20 sec video',legacy:'This order predates Scene Studio. Formats are available, but scene editing needs a new order.',compare:'Compare variants'}
    };
    return words[state.lang] || words.uk;
  };

  async function api(path, options = {}) {
    if (!authorization) throw Error(t('openFromBot'));
    const response = await fetch('/miniapp/api' + path, {
      ...options, headers: {Authorization: authorization, ...(options.headers || {})}
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
    return `<footer class="signature" aria-label="Food Porn Atelier"><div class="signature-rule"><span>✦</span></div><div class="signature-center"><div class="signature-monogram" aria-hidden="true"><span class="sig-orbit"></span><span class="sig-heart">♥</span><b>F<span>✦</span>P</b></div><div class="signature-title">Food Porn <i>Atelier</i></div><div class="signature-subtitle">PERSONAL STORIES · INTIMATE DINNERS</div></div><div class="signature-lines"><span>With love for you.</span><span>С любовью для Вас.</span></div><div class="signature-by"><span>OLGA VOLOSHENKO</span><i>&</i><span>BONDAREV_E</span></div></footer>`;
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
    const schedule = state.lang === 'uk' ? 'Надіслати у вибраний час' : state.lang === 'ru' ? 'Отправить в выбранное время' : 'Send at a chosen time';
    return `<section class="panel delivery-panel"><div class="panel-title">${t('delivery')}</div><button type="button" class="primary" data-action="${prefix}-share">${t('share')}</button><label class="field" for="recipient-email">${t('email')}</label><input id="recipient-email" class="input" type="email" autocomplete="email" placeholder="name@example.com"><button type="button" class="secondary" data-action="${prefix}-email">${t('sendEmail')}</button><label class="field" for="delivery-time">${schedule}</label><input id="delivery-time" class="input" type="datetime-local"><button type="button" class="secondary" data-action="${prefix}-schedule">${schedule}</button></section>`;
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
      ${['payment','payment_unavailable'].includes(current) ? `<section class="panel action-panel"><p>${t('unpaid')}</p><strong>${t('payment')}: ${esc(job.stars || '—')} ⭐</strong>${button(t('pay'), 'gift-pay', 'primary')}${state.home?.wayforpay_ready ? button('💳 WayForPay', 'gift-pay-wayforpay', 'secondary') : ''}${button(t('check'), 'gift-check')}</section>` : ''}
      ${filesReady ? `<section class="panel action-panel"><div class="panel-title">${t('ready')}</div>${button('✦ Scene Studio', 'studio-open', 'primary')}${button(t('openGift'), 'gift-open', 'secondary')}${button(t('mobile'), 'gift-mobile', 'file-button')}${button(t('desktop'), 'gift-desktop', 'file-button')}${button(t('print'), 'gift-print', 'file-button')}</section>${deliveryTools('gift')}` : ''}</div>`;
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
      ${current === 'waiting_for_payment' && !menu.paid ? `<section class="panel action-panel"><p>${t('unpaid')}</p><strong>${t('payment')}: ${esc(menu.stars || '—')} ⭐</strong>${button(t('pay'), 'menu-pay', 'primary')}${state.home?.wayforpay_ready ? button('💳 WayForPay', 'menu-pay-wayforpay', 'secondary') : ''}${button(t('check'), 'menu-check')}</section>` : ''}
      ${ready ? `<section class="panel action-panel"><div class="panel-title">${t('ready')}</div>${button(t('evening'), 'menu-evening', 'primary')}${button(t('openGift'), 'menu-open', 'secondary')}${button('PDF · ' + t('print'), 'menu-pdf', 'file-button')}${button(t('recipes'), 'menu-recipes', 'file-button')}</section>${deliveryTools('menu')}` : ''}</div>`;
  }
  function wallpaperDetail(order) {
    const files = `${button('✦ Scene Studio', 'studio-open', 'primary')}${button(t('mobile'), 'wallpaper-mobile', 'file-button')}${button(t('desktop'), 'wallpaper-desktop', 'file-button')}${button(t('print'), 'wallpaper-print', 'file-button')}`;
    const price = order?.stars ? `${esc(order.stars)} ⭐` : `${esc(order?.amount || '—')} UAH`;
    const checkout = `<p>${t('unpaid')}</p><strong>${t('payment')}: ${price}</strong>${order?.stars ? button(t('pay'), 'wallpaper-pay', 'primary') : ''}${state.home?.wayforpay_ready ? button('💳 WayForPay', 'wallpaper-pay-wayforpay', 'secondary') : ''}${button(t('check'), 'wallpaper-check')}`;
    return `<div class="page detail">${goHomeButton('orders')}${detailHead(t('gift'), order?.id, order?.paid ? 'ready' : 'payment')}${preview()}<section class="panel action-panel"><div class="panel-title">${t('details')}</div>${order?.paid ? files : checkout}</section>${order?.paid ? deliveryTools('wallpaper') : ''}</div>`;
  }
  function sceneStudioDetail() {
    const studio = state.sceneStudio;
    const words = studioWords();
    if (!studio) return `<div class="page">${goHomeButton('orders')}<p class="error">Scene Studio unavailable</p></div>`;
    const index = Math.min(state.studioScene || 0, Math.max(0, studio.goals.length - 1));
    const locked = (studio.locked || []).includes(index);
    const versions = (studio.versions || []).filter(item => item.scene_index === index);
    const options = [`<option value="current">${esc(words.current)}</option>`, ...versions.map(item => `<option value="${item.id}">#${item.number} · ${esc(item.instruction)}</option>`)].join('');
    const exports = ['phone','desktop','story','instagram','a3','telegram','video'].map(kind => {
      const ready = (studio.exports || []).find(item => item.kind === kind && item.ready);
      const labels = {phone:'📱 Phone',desktop:'🖥 Desktop',story:'▯ Story',instagram:'▣ Instagram',a3:'A3 Print',telegram:'Telegram Cover',video:'▶ MP4'};
      return ready ? `<button class="file-button" data-action="studio-download" data-kind="${kind}">${labels[kind]}</button>` : `<span class="format-chip pending">${labels[kind]}</span>`;
    }).join('');
    const left = state.studioImages.left ? `<img src="${state.studioImages.left}" alt="Variant A">` : '<span>01</span>';
    const right = state.studioImages.right ? `<img src="${state.studioImages.right}" alt="Variant B">` : '<span>02</span>';
    const selectedVersion = versions.find(item => String(item.id) === String(state.studioCompare.right));
    return `<div class="page scene-studio">${goHomeButton('orders')}<div class="studio-hero"><small>PREMIUM CREATIVE SUITE</small><h1>${words.title}</h1><p>${words.lead}</p></div>
      ${!studio.editable ? `<p class="error">${words.legacy}</p>` : `<nav class="scene-tabs">${studio.goals.map((goal, scene) => `<button class="${scene===index?'active':''} ${(studio.locked||[]).includes(scene)?'locked':''}" data-action="studio-scene" data-index="${scene}"><b>${String(scene+1).padStart(2,'0')}</b><span>${esc(goal)}</span></button>`).join('')}</nav>
      <section class="panel"><div class="panel-title">${words.compare}<span>${index+1}/${studio.goals.length}</span></div><div class="compare-selects"><select id="compare-left">${options}</select><select id="compare-right">${options}</select></div><div class="scene-compare"><figure>${left}<figcaption>A</figcaption></figure><figure>${right}<figcaption>B</figcaption></figure></div>${selectedVersion && !selectedVersion.selected ? `<button class="primary" data-action="studio-select" data-version="${selectedVersion.id}">${words.apply}</button>` : ''}${button(locked ? words.unlock : words.lock, 'studio-lock', locked ? 'secondary' : 'file-button')}</section>
      <section class="panel scene-edit"><div class="panel-title">${words.newVersion}<span>1 AI request</span></div><div class="edit-modes">${['scene','clothing','background','mood'].map(mode => `<label><input type="radio" name="edit-mode" value="${mode}" ${mode==='scene'?'checked':''}><span>${words[mode]}</span></label>`).join('')}</div><label class="field">${words.instruction}</label><textarea id="scene-instruction" maxlength="500" placeholder="${esc(words.placeholder)}"></textarea>${button(words.newVersion, 'studio-generate', 'primary')}</section>`}
      <section class="panel"><div class="panel-title">${words.formats}<span>NO AI COST</span></div><div class="format-grid">${exports}</div>${button(words.makeFormats, 'studio-exports', 'secondary')}</section>
      <section class="panel video-maker"><div class="panel-title">${words.video}<span>10–20 SEC</span></div><label class="field">${words.phrase}</label><textarea id="video-phrase" maxlength="500">${esc(studio.final_phrase || '')}</textarea><label class="check-row"><input id="video-ai-voice" type="checkbox"><span>${words.aiVoice}</span></label><label class="field">${words.voice}</label><input id="video-voice" class="input" type="file" accept="audio/*"><label class="field">${words.music}</label><input id="video-music" class="input" type="file" accept="audio/*">${button(words.makeVideo, 'studio-video', 'primary')}</section></div>`;
  }
  function dishRow() {
    return `<div class="dish"><select class="input" name="category"><option value="main">Основное</option><option value="appetizer">Закуска</option><option value="salad">Салат</option><option value="soup">Суп</option><option value="dessert">Десерт</option><option value="drink">Напиток</option></select><input class="input" name="title" required maxlength="180" placeholder="${t('dishes')}"><button type="button" data-action="remove-dish" aria-label="Remove dish">×</button></div>`;
  }
  function dishKey(item) { return `${item.category}:${item.position}:${item.title}`; }
  function clock(minutes) {
    const normalized = ((minutes % 1440) + 1440) % 1440;
    return `${String(Math.floor(normalized / 60)).padStart(2,'0')}:${String(normalized % 60).padStart(2,'0')}`;
  }
  function recipeSteps(item) {
    const raw = String(item?.recipe || '').trim();
    if (!raw) return [];
    const lines = raw.split(/\n+|(?=\d+[.)]\s+)/).map(value => value.replace(/^\d+[.)]\s*/, '').trim()).filter(Boolean);
    return lines.length > 1 ? lines : raw.split(/(?<=[.!?])\s+/).filter(Boolean);
  }
  function cookingPanel(courses) {
    if (!courses.length) return '';
    state.cookingIndex = Math.min(state.cookingIndex || 0, courses.length - 1);
    const item = courses[state.cookingIndex];
    const steps = recipeSteps(item);
    state.cookingStep = Math.min(state.cookingStep || 0, Math.max(steps.length - 1, 0));
    const labels = state.lang === 'uk'
      ? {title:'Готуємо разом',prev:'Назад',next:'Далі',done:'Готово',allergens:'Алергени',equipment:'Обладнання',replace:'Заміни'}
      : state.lang === 'ru'
      ? {title:'Готовим вместе',prev:'Назад',next:'Далее',done:'Готово',allergens:'Аллергены',equipment:'Оборудование',replace:'Замены'}
      : {title:'Cook together',prev:'Back',next:'Next',done:'Done',allergens:'Allergens',equipment:'Equipment',replace:'Substitutions'};
    return `<section class="panel cooking-mode"><div class="panel-title">${labels.title} <span>${state.cookingStep + 1}/${Math.max(steps.length,1)}</span></div><div class="styles">${courses.map((dish,index)=>`<button type="button" class="chip ${index===state.cookingIndex?'active':''}" data-action="cook-dish" data-index="${index}">${esc(dish.title)}</button>`).join('')}</div><h3>${esc(item.title)}</h3>${item.equipment?.length?`<p class="muted"><b>${labels.equipment}:</b> ${esc(item.equipment.join(', '))}</p>`:''}${item.allergens?.length?`<p class="muted"><b>${labels.allergens}:</b> ${esc(item.allergens.join(', '))}</p>`:''}<div class="note" style="margin-top:14px">${esc(steps[state.cookingStep] || item.recipe)}</div>${item.substitutions?.length?`<p class="muted"><b>${labels.replace}:</b> ${esc(item.substitutions.join(' · '))}</p>`:''}<div class="actions" style="margin-top:14px"><button type="button" class="secondary" data-action="cook-prev" ${state.cookingStep<1?'disabled':''}>← ${labels.prev}</button><button type="button" class="primary" data-action="cook-next">${state.cookingStep>=steps.length-1?labels.done:labels.next+' →'}</button></div></section>`;
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
      <section class="panel"><div class="panel-title">${t('serve')}</div><ol class="plan-list">${serving.map(({item,when}) => `<li><time>${clock(when)}</time><span>${esc(item.title)}</span></li>`).join('')}</ol></section>${cookingPanel(courses)}</div>`;
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
          <div class="section-heading"><span>01 / ${t('studio')}</span><i>✦</i></div><div class="product-grid"><button type="button" class="product-card image-card" data-page="gift"><span class="product-top">01 <span>↗</span></span><span class="card-symbol dream" aria-hidden="true">✧</span><strong>${t('gift')}</strong><small>${t('giftSub')}</small></button><button type="button" class="product-card menu-card" data-page="food"><span class="product-top">02 <span>↗</span></span><span class="card-symbol dining" aria-hidden="true">◈</span><strong>${t('food')}</strong><small>${t('foodSub')}</small></button></div>
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
        body = `<div class="form">${goHomeButton()}<div class="eyebrow">02 / CULINARY STORY</div><h1>${t('food')}</h1><p class="sub">${t('foodLead')}</p><form id="menu-form" class="panel">${!state.home?.customer ? `<label class="field">${t('name')}</label><input class="input" name="name" required maxlength="100"><label class="field">${t('phone')}</label><input class="input" type="tel" name="phone" required placeholder="+380…">` : ''}<label class="field">${t('cover')}</label><input class="input" name="cover" type="file" accept="image/jpeg,image/png,image/webp" required><label class="field">${t('spread')}</label><input class="input" name="spread" type="file" accept="image/jpeg,image/png,image/webp" required><label class="field">${t('dishes')}</label><div class="styles"><button type="button" class="chip ${state.menuInputMode==='list'?'active':''}" data-action="menu-input-mode" data-mode="list">${t('menuSimple')}</button><button type="button" class="chip ${state.menuInputMode==='structured'?'active':''}" data-action="menu-input-mode" data-mode="structured">${t('menuDetailed')}</button></div>${state.menuInputMode==='list'?`<div id="dish-list-mode"><textarea class="input" name="dish_list" required maxlength="2500" placeholder="${t('dishListHint')}"></textarea><p class="muted">${t('dishListHint')}</p></div>`:`<div id="dish-structured-mode"><div id="dishes">${dishRow()}</div>${button('+ ' + t('add'), 'add-dish')}</div>`}${button(t('send'), 'submit-menu', 'primary')}</form></div>`;
        break;
      case 'orders':
        body = `<div class="page">${goHomeButton()}<div class="eyebrow">YOUR STORIES</div><h1>${t('orders')}</h1><p class="sub">${t('ordersSub')}</p><div class="orders-list">${orderRows()}</div></div>`;
        break;
      case 'evening': body = eveningPage(); break;
      case 'job': body = giftDetail(state.job); break;
      case 'menu': body = menuDetail(state.menu); break;
      case 'wallpaper': body = wallpaperDetail(state.wallpaper); break;
      case 'scene-studio': body = sceneStudioDetail(); break;
      case 'settings':
        body = `<div class="page">${goHomeButton()}<h1>${t('setting')}</h1><section class="panel"><label class="field">${t('language')}</label><div class="styles">${[['uk','Українська'],['ru','Русский'],['en','English']].map(([code,label]) => `<button type="button" class="chip ${code === state.lang ? 'active' : ''}" data-lang="${code}">${label}</button>`).join('')}</div></section></div>`;
        break;
      case 'admin': {
        const a = state.admin;
        body = `<div class="page">${goHomeButton()}<h1>${t('admin')}</h1><a class="primary" style="display:block;padding:16px;margin-bottom:18px;text-align:center;border-radius:14px" href="/crm${esc(window.location.hash)}">✦ Mini CRM · Клиенты, финансы, реклама →</a><div class="admin-grid">${[['♧','customers'],['◈','menus'],['✧','gifts'],['✓','paid_gifts']].map(([icon,key]) => `<div class="stat-card"><span>${icon}</span><strong>${a?.[key] ?? '–'}</strong><small>${t(key === 'paid_gifts' ? 'paid' : key)}</small></div>`).join('')}</div><section class="panel"><div class="panel-title">${t('details')}</div><p>Telegram Stars: ${a?.stars_ready ? '✓' : '—'} · ${esc(a?.stars_revenue || 0)} ⭐</p><p>Portmone: ${a?.payment_ready ? '✓' : '—'} · ${esc(a?.revenue || '0')} UAH</p><label class="field">Menu price, UAH</label><input id="menu-price" class="input" type="number" min="1" max="100000" step="0.01" value="${esc(a?.menu_price)}">${button(t('save'), 'save-price')}<hr class="divider"><label class="field">${t('vip')}</label><textarea id="vip" ${a?.owner ? '' : 'readonly'} placeholder="username, username">${esc((a?.vip || []).join(', '))}</textarea>${a?.owner ? button(t('save'), 'save-vip', 'primary') : ''}</section></div>`;
        break;
      }
    }
    app.innerHTML = layout(body);
    if (state.page === 'gift') giftSummary();
    if (state.page === 'scene-studio') {
      const left = app.querySelector('#compare-left');
      const right = app.querySelector('#compare-right');
      if (left) left.value = state.studioCompare.left;
      if (right) right.value = state.studioCompare.right;
    }
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
  function clearStudioImages() {
    Object.values(state.studioImages || {}).forEach(url => url && URL.revokeObjectURL(url));
    state.studioImages = {};
  }
  async function studioImage(value) {
    const orderId = state.sceneStudio.order_id;
    const scene = state.studioScene || 0;
    const path = value === 'current'
      ? `/wallpapers/${orderId}/studio/scenes/${scene}/current`
      : `/wallpapers/${orderId}/studio/versions/${value}`;
    return URL.createObjectURL(await api(path));
  }
  async function loadStudioCompare() {
    clearStudioImages();
    try {
      const [left, right] = await Promise.all([
        studioImage(state.studioCompare.left), studioImage(state.studioCompare.right)
      ]);
      state.studioImages = {left, right};
      render();
    } catch (error) { notice(error.message); }
  }
  async function openSceneStudio(orderId) {
    clearPreview();
    clearStudioImages();
    state.sceneStudio = await api(`/wallpapers/${orderId}/studio`);
    state.studioScene = 0;
    const versions = state.sceneStudio.versions.filter(item => item.scene_index === 0);
    state.studioCompare = {left:'current', right:versions.length ? String(versions[versions.length - 1].id) : 'current'};
    state.page = 'scene-studio';
    render();
    window.scrollTo(0, 0);
    if (state.sceneStudio.editable) await loadStudioCompare();
  }
  function openPayment(url, kind, id, provider='stars') {
    if (provider === 'stars' && tg?.openInvoice) tg.openInvoice(url, status => {
      if (status === 'paid') setTimeout(() => openOrder(kind, id), 1200);
    });
    else if (tg?.openLink) tg.openLink(url);
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
      if (action === 'studio-open') {
        const orderId = state.page === 'job' ? state.job?.order_id : state.wallpaper?.id;
        if (!orderId) throw Error('Order is not ready for Scene Studio');
        await openSceneStudio(orderId); return;
      }
      if (action === 'studio-scene') {
        state.studioScene = Number(element.dataset.index);
        const versions = state.sceneStudio.versions.filter(item => item.scene_index === state.studioScene);
        state.studioCompare = {left:'current', right:versions.length ? String(versions[versions.length - 1].id) : 'current'};
        render(); await loadStudioCompare(); return;
      }
      if (action === 'studio-lock') {
        const scene = state.studioScene || 0;
        const locked = !(state.sceneStudio.locked || []).includes(scene);
        await api(`/wallpapers/${state.sceneStudio.order_id}/studio/scenes/${scene}/lock`, {
          method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({locked})
        });
        state.sceneStudio.locked = locked
          ? [...new Set([...(state.sceneStudio.locked || []), scene])]
          : (state.sceneStudio.locked || []).filter(value => value !== scene);
        render(); return;
      }
      if (action === 'studio-generate') {
        const field = document.querySelector('#scene-instruction');
        if (!field.value.trim() || field.value.trim().length < 3) { field.focus(); return; }
        const mode = document.querySelector('input[name="edit-mode"]:checked')?.value || 'scene';
        element.disabled = true;
        const version = await api(`/wallpapers/${state.sceneStudio.order_id}/studio/scenes/${state.studioScene}/variants`, {
          method:'POST', headers:{'Content-Type':'application/json'},
          body:JSON.stringify({mode, instruction:field.value.trim()})
        });
        state.sceneStudio = await api(`/wallpapers/${state.sceneStudio.order_id}/studio`);
        state.studioCompare = {left:'current', right:String(version.id)};
        render(); await loadStudioCompare(); return;
      }
      if (action === 'studio-select') {
        await api(`/wallpapers/${state.sceneStudio.order_id}/studio/versions/${element.dataset.version}/select`, {method:'POST'});
        state.sceneStudio = await api(`/wallpapers/${state.sceneStudio.order_id}/studio`);
        state.studioCompare = {left:'current', right:String(element.dataset.version)};
        render(); await loadStudioCompare();
        notice(studioWords().apply, true); return;
      }
      if (action === 'studio-exports') {
        element.disabled = true;
        await api(`/wallpapers/${state.sceneStudio.order_id}/exports`, {method:'POST'});
        state.sceneStudio = await api(`/wallpapers/${state.sceneStudio.order_id}/studio`);
        render(); notice(studioWords().formats, true); return;
      }
      if (action === 'studio-download') {
        await download(`/wallpapers/${state.sceneStudio.order_id}/exports/${element.dataset.kind}`,
          `wallpaper-${state.sceneStudio.order_id}-${element.dataset.kind}`);
        return;
      }
      if (action === 'studio-video') {
        const data = new FormData();
        data.append('final_phrase', document.querySelector('#video-phrase').value.trim());
        data.append('duration_seconds', '15');
        data.append('ai_voice', String(document.querySelector('#video-ai-voice').checked));
        const voice = document.querySelector('#video-voice').files[0];
        const music = document.querySelector('#video-music').files[0];
        if (voice) data.append('voice', voice);
        if (music) data.append('music', music);
        element.disabled = true;
        await api(`/wallpapers/${state.sceneStudio.order_id}/video`, {method:'POST', body:data});
        state.sceneStudio = await api(`/wallpapers/${state.sceneStudio.order_id}/studio`);
        render(); notice(studioWords().video, true); return;
      }
      if (action === 'menu-input-mode') {
        state.menuInputMode = element.dataset.mode === 'structured' ? 'structured' : 'list';
        render(); return;
      }
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
        const dishPayload = state.menuInputMode === 'list'
          ? {mode:'list', text:String(new FormData(form).get('dish_list') || '').trim()}
          : [...form.querySelectorAll('.dish')].map(row => ({category:row.querySelector('select').value, title:row.querySelector('input').value.trim()}));
        payload.set('dishes', JSON.stringify(dishPayload));
        payload.set('language', state.lang);
        element.disabled = true;
        const menu = await api('/menus', {method:'POST', body:payload});
        state.menu = menu; state.page = 'menu'; state.viewKey = `menu:${menu.id}`;
        render(); return;
      }
      if (action === 'menu-evening') { await openEvening(); return; }
      if (action === 'cook-dish') { state.cookingIndex = Number(element.dataset.index)||0; state.cookingStep = 0; render(); return; }
      if (action === 'cook-prev') { state.cookingStep = Math.max(0,(state.cookingStep||0)-1); render(); return; }
      if (action === 'cook-next') {
        const selected = new Set(state.eveningSelected || []);
        const courses = state.evening.serve.filter(item => selected.has(dishKey(item)));
        const steps = recipeSteps(courses[state.cookingIndex]);
        if (state.cookingStep < steps.length - 1) state.cookingStep += 1;
        else if (state.cookingIndex < courses.length - 1) { state.cookingIndex += 1; state.cookingStep = 0; }
        render(); return;
      }
      if (action === 'gift-open' || action === 'menu-open') {
        const target = action === 'gift-open' ? `gifts/${state.job.id}` : `menus/${state.menu.id}`;
        const result = await api(`/${target}/share`, {method:'POST'});
        if (result.present_url && tg?.openLink) tg.openLink(result.present_url);
        else if (result.present_url) window.open(result.present_url, '_blank');
        return;
      }
      if (action === 'gift-retry') { state.job = await api(`/gifts/${state.job.id}/retry`, {method:'POST'}); render(); return; }
      if (['gift-pay','menu-pay','wallpaper-pay','gift-pay-wayforpay','menu-pay-wayforpay','wallpaper-pay-wayforpay'].includes(action)) {
        const baseAction = action.replace('-wayforpay', '');
        const path = baseAction === 'gift-pay' ? `/gifts/${state.job.id}` : baseAction === 'menu-pay' ? `/menus/${state.menu.id}` : `/wallpapers/${state.wallpaper.id}`;
        const query = action.endsWith('-wayforpay') ? '?provider=wayforpay' : '';
        const result = await api(path + '/checkout' + query, {method:'POST'});
        openPayment(result.url, baseAction === 'gift-pay' ? 'job' : baseAction === 'menu-pay' ? 'menu' : 'wallpaper',
          baseAction === 'gift-pay' ? state.job.id : baseAction === 'menu-pay' ? state.menu.id : state.wallpaper.id,
          result.provider);
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
      if (action === 'gift-schedule' || action === 'menu-schedule' || action === 'wallpaper-schedule') {
        const email = document.querySelector('#recipient-email');
        const when = document.querySelector('#delivery-time');
        if (!email?.checkValidity() || !email.value) { email?.reportValidity(); return; }
        if (!when?.value) { when?.focus(); return; }
        const kind = action.split('-')[0];
        const reference = kind === 'gift' ? state.job.id : kind === 'menu' ? state.menu.id : state.wallpaper.id;
        await api('/deliveries/schedule', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({kind,reference_id:String(reference),email:email.value.trim(),send_at:new Date(when.value).toISOString()})});
        notice(state.lang==='uk'?'Доставку заплановано':state.lang==='ru'?'Доставка запланирована':'Delivery scheduled', true);
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
    if (event.target.id === 'compare-left' || event.target.id === 'compare-right') {
      state.studioCompare[event.target.id === 'compare-left' ? 'left' : 'right'] = event.target.value;
      loadStudioCompare();
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
  if (!authorization) {
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
