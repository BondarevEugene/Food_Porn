"""Responsive, read-only Release Control Center for paid Little Legend books.

The page contains no customer data. Authenticated API requests use Telegram
initData; payment and regeneration actions are deliberately absent.
"""
from __future__ import annotations

RELEASE_CONTROL_HTML = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light">
<title>Little Legend · Release Control</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
:root{font-family:system-ui,-apple-system,sans-serif;color:#28324b;background:#f5f7ff}
*{box-sizing:border-box}body{margin:0;min-height:100vh;background:radial-gradient(circle at 8% 0%,#e7e9ff,transparent 43%),linear-gradient(150deg,#faf8ff,#f2f8ff)}
main{max-width:940px;margin:auto;padding:24px 18px 72px}
header{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap}
.eyebrow{color:#6662a7;font-size:12px;font-weight:800;letter-spacing:.15em;text-transform:uppercase}
h1{font:700 clamp(29px,5vw,47px)/1.13 Georgia,serif;letter-spacing:-.04em;margin:10px 0}
h2{font-size:19px;margin:0 0 15px}.sub{color:#66718c;line-height:1.6}
.panel{background:#fff;border:1px solid #e1e6f2;border-radius:23px;padding:23px;margin-top:20px;box-shadow:0 14px 42px #323d6910}
.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}
.metric{border-radius:17px;background:#f5f6fc;padding:17px}.metric small{display:block;color:#69748e;margin-bottom:8px}.metric strong{font-size:20px;overflow-wrap:anywhere}
label{display:block;font-size:13px;font-weight:700;margin:14px 0 7px}
input{width:100%;padding:13px;border:1px solid #cbd3e6;border-radius:12px;font:inherit}
button,a.action{border:0;background:#5554b8;color:#fff;padding:13px 18px;border-radius:12px;font:700 14px system-ui;cursor:pointer;text-decoration:none;display:inline-block}
button:disabled{opacity:.55;cursor:not-allowed}.secondary{background:#eceefa;color:#3e467e}
.actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:17px}.status{display:inline-block;padding:8px 13px;border-radius:99px;background:#e9edfc;color:#404c83;font-weight:700}
.status.ready{background:#e6f7ef;color:#1d7652}.status.blocked{background:#fff0ed;color:#a34135}
.issue{border-left:3px solid #db917b;padding:12px 15px;margin:12px 0;background:#fff8f6;border-radius:10px}
.issue strong{display:block}.issue p{margin:5px 0 0;color:#65718b;font-size:13px}
.note{color:#6b748d;font-size:13px;line-height:1.6}.hidden{display:none}
@media(max-width:650px){main{padding:18px 12px 55px}.grid{grid-template-columns:1fr}.panel{padding:18px}header{align-items:flex-start}}
</style></head><body><main>
<header><div><div class="eyebrow">Little Legend / Operations</div>
<h1>Контроль выпуска</h1><p class="sub">Готовность цифровой книги, оплата и проверка PDF — в одном месте.</p></div>
<a class="action secondary" href="/little-legend">Вернуться в студию</a></header>
<section class="panel"><h2>Найти оплаченный заказ</h2>
<p class="note">Введите номер заказа (quote ID). Доступны только ваши книги с подтверждённой оплатой.</p>
<label for="quote">Номер заказа</label><input id="quote" type="number" min="1" step="1" inputmode="numeric" placeholder="Например, 125">
<div class="actions"><button id="check" type="button">Проверить выпуск</button>
<button id="refresh" class="secondary" type="button" disabled>Повторить проверку</button></div>
<p id="message" class="note" role="status" aria-live="polite">Ожидаем номер заказа.</p></section>
<section id="results" class="hidden" aria-label="Результаты проверки">
<div class="panel"><h2>Состояние выпуска</h2><span id="state" class="status">Проверка</span>
<div class="grid" style="margin-top:18px">
<div class="metric"><small>Оплата</small><strong id="payment">—</strong></div>
<div class="metric"><small>Производство</small><strong id="production">—</strong></div>
<div class="metric"><small>Доставка</small><strong id="delivery">—</strong></div></div>
<p class="note" id="explain"></p><div class="actions"><a id="download" class="action hidden" href="#">Скачать PDF</a></div></div>
<div class="panel"><h2>Диагностика PDF</h2>
<div class="grid"><div class="metric"><small>Страниц</small><strong id="pages">—</strong></div>
<div class="metric"><small>Глав обнаружено</small><strong id="chapters">—</strong></div>
<div class="metric"><small>Обложка</small><strong id="cover">—</strong></div></div>
<div id="issues" aria-live="polite"></div><p class="note">Проверка не подтверждает готовность к типографской печати. Повторная проверка не создаёт платёж и не запускает генерацию.</p></div>
</section>
<section class="panel" aria-label="Восстановление доставки">
<div class="eyebrow">Recovery / Telegram</div>
<h2>Безопасное восстановление доставки</h2>
<p class="note">Этот раздел работает по номеру истории (story ID), а не номеру заказа. Проверяет журнал отправки и статус релиза. Не отправляет PDF повторно.</p>
<label for="recoveryStory">Номер истории</label>
<input id="recoveryStory" type="number" min="1" step="1" inputmode="numeric" placeholder="Номер истории">
<div class="actions"><button id="diagnoseDelivery" type="button" class="secondary">Проверить доставку</button>
<button id="repairProjection" type="button" disabled>Восстановить подтверждённый статус</button></div>
<p id="recoveryMessage" class="note" role="status" aria-live="polite">Сначала проверьте доставку.</p>
<div id="recoveryDetails" class="grid hidden">
<div class="metric"><small>Рекомендация</small><strong id="recoveryAction">—</strong></div>
<div class="metric"><small>Журнал Telegram</small><strong id="effectStatus">—</strong></div>
<div class="metric"><small>Релиз</small><strong id="manifestStatus">—</strong></div>
</div>
<p class="note">Неопределённая отправка требует ручной проверки: повторная отправка может создать дубликат. Восстановление разрешено только при подтверждённом Telegram message ID.</p>
</section><section class="panel" aria-label="Production Operations">
<div class="eyebrow">Production / Resilience</div>
<h2>Производство и AI-бюджет</h2>
<p class="note">Проверка задания, активности воркера и неопределённых расходов. Только диагностика — повторных AI-запросов нет.</p>
<div class="actions"><button id="inspectProduction" type="button">Проверить производство по номеру заказа</button></div>
<p id="productionMessage" class="note" role="status" aria-live="polite">Введите номер заказа выше.</p>
<div id="productionDetails" class="grid hidden">
<div class="metric"><small>Рекомендация</small><strong id="productionAction">—</strong></div>
<div class="metric"><small>Аренда / попытки</small><strong id="productionLease">—</strong></div>
<div class="metric"><small>Неопределённые операции</small><strong id="productionEffects">—</strong></div>
<div class="metric"><small>Бюджет AI (USD)</small><strong id="productionBudget">—</strong></div>
<div class="metric"><small>Зарезервировано (USD)</small><strong id="productionHeld">—</strong></div>
<div class="metric"><small>Израсходовано (USD)</small><strong id="productionSpent">—</strong></div>
</div>
<p class="note" id="productionNotes"></p>
</section>
</main>
<script>
'use strict';
const $=id=>document.getElementById(id);
const auth=window.Telegram?.WebApp?.initData||'';
const labels={ready:'Готова к скачиванию',blocked:'Выдача заблокирована',not_ready:'Производство не завершено',
paid_delivery_gate_failed:'Не пройдена проверка доставки',chapter_art_missing:'Нет иллюстраций глав',
cover_art_missing:'Отсутствует иллюстрация обложки',chapter_text_missing:'Не найдены главы',
insufficient_pages:'Недостаточно страниц',pdf_content_unreadable:'Ошибка чтения PDF',
blank_or_image_only_page:'Пустая страница',editorial_notice_present:'Редакторская пометка',
invalid_pdf_bytes:'Некорректный PDF'};
function label(code){return labels[code]||code.replaceAll('_',' ')}
async function get(path){
const r=await fetch('/little-legend/api'+path,{headers:{Authorization:'tma '+auth},cache:'no-store'});
if(!r.ok)throw Error(r.status===404?'Заказ не найден или доступ запрещён':r.status===503?'Хранилище временно недоступно':'Ошибка HTTP '+r.status);
return r.json()}
async function check(){
const id=Number($('quote').value);
if(!Number.isSafeInteger(id)||id<=0){$('message').textContent='Укажите корректный номер заказа';return}
if(!auth){$('message').textContent='Откройте панель через Telegram для авторизации';return}
$('check').disabled=true;$('refresh').disabled=true;$('message').textContent='Проверяем заказ…';
$('results').classList.add('hidden');$('download').classList.add('hidden');$('download').removeAttribute('href');
try{
const status=await get('/order-quotes/'+id+'/status');
$('payment').textContent=status.payment_verified?'Подтверждена':'Ожидает подтверждения';
$('production').textContent=status.production_status||'—';
$('delivery').textContent=status.delivery_status||'—';
$('pages').textContent='—';$('chapters').textContent='—';$('cover').textContent='—';$('issues').replaceChildren();
let state='not_ready';
if(status.payment_verified&&status.production_status==='ready'){
const audit=await get('/order-quotes/'+id+'/diagnostics');
state=audit.status;
$('pages').textContent=String(audit.page_count??'—');
$('chapters').textContent=String(audit.chapter_count??'—');
$('cover').textContent=audit.cover_has_art?'Есть':'Нет';
(audit.issue_codes||[]).forEach(code=>{const item=document.createElement('div');item.className='issue';
const title=document.createElement('strong');title.textContent=label(code);
const detail=document.createElement('p');detail.textContent='Код: '+code;item.append(title,detail);$('issues').append(item)});
if(state==='ready'){$('download').href='/little-legend/api/order-quotes/'+id+'/book.pdf';$('download').classList.remove('hidden');
$('download').onclick=async event=>{event.preventDefault();try{const r=await fetch($('download').href,{headers:{Authorization:'tma '+auth},cache:'no-store'});if(!r.ok)throw Error('PDF HTTP '+r.status);const blob=await r.blob();const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='little-legend-book.pdf';a.click();setTimeout(()=>URL.revokeObjectURL(url),30000)}catch(e){$('message').textContent=e.message}}}
}
$('state').textContent=label(state);$('state').className='status '+(state==='ready'?'ready':state==='blocked'?'blocked':'');
$('explain').textContent=state==='ready'?'Цифровая книга прошла проверку сохранённого PDF.':state==='blocked'?'Найдены проблемы, требующие исправления перед выдачей.':'Книга ещё не готова к выдаче.';
$('results').classList.remove('hidden');$('message').textContent='Проверка завершена. Новых платежей не создано.';
}catch(e){$('message').textContent=e.message}
finally{$('check').disabled=false;$('refresh').disabled=false}}
const recoveryLabels={no_effect:'Отправка ещё не зарегистрирована',in_flight:'Отправка выполняется',manual_review:'Требуется ручная проверка',repair_projection:'Можно восстановить статус',consistent:'Доставка подтверждена',inconsistent:'Несоответствие данных'};
let recoverableStory=null;
async function diagnoseDelivery(){
const id=Number($('recoveryStory').value);
recoverableStory=null;$('repairProjection').disabled=true;
$('recoveryDetails').classList.add('hidden');
if(!Number.isSafeInteger(id)||id<=0){$('recoveryMessage').textContent='Укажите корректный номер истории';return}
if(!auth){$('recoveryMessage').textContent='Откройте панель через Telegram';return}
$('diagnoseDelivery').disabled=true;$('recoveryMessage').textContent='Проверяем журнал доставки…';
try{
const x=await get('/stories/'+id+'/delivery-diagnosis');
$('recoveryAction').textContent=recoveryLabels[x.action]||x.action;
$('effectStatus').textContent=x.effect_status||'Нет записи';
$('manifestStatus').textContent=x.manifest_status||'Нет записи';
$('recoveryDetails').classList.remove('hidden');
if(x.action==='repair_projection'&&Number.isSafeInteger(x.telegram_message_id)&&x.telegram_message_id>0){
recoverableStory=id;$('repairProjection').disabled=false;
$('recoveryMessage').textContent='Telegram подтвердил отправку. Можно восстановить только статус в базе.'}
else {$('recoveryMessage').textContent=x.action==='manual_review'?'Автоматический повтор запрещён: проверьте доставку вручную.':'Диагностика завершена. Повторная отправка не выполняется.'}
}catch(e){$('recoveryMessage').textContent=e.message}
finally{$('diagnoseDelivery').disabled=false}}
async function repairProjection(){
const id=Number($('recoveryStory').value);
if(recoverableStory!==id||!auth)return;
if(!window.confirm('Восстановить только подтверждённый статус доставки? PDF повторно отправлен не будет.'))return;
recoverableStory=null;$('repairProjection').disabled=true;
$('recoveryMessage').textContent='Восстанавливаем подтверждённый статус…';
try{
const r=await fetch('/little-legend/api/stories/'+id+'/delivery-reconcile',{
method:'POST',headers:{Authorization:'tma '+auth,'Content-Type':'application/json'},
body:'{}',cache:'no-store'});
if(!r.ok)throw Error('Не удалось восстановить статус: HTTP '+r.status);
const result=await r.json();
$('recoveryMessage').textContent=result.action==='consistent'?'Статус синхронизирован с подтверждённой отправкой.':'Операция завершена; проверьте актуальный статус.';
await diagnoseDelivery();
}catch(e){$('recoveryMessage').textContent=e.message}}
$('diagnoseDelivery').addEventListener('click',diagnoseDelivery);
$('repairProjection').addEventListener('click',repairProjection);
$('recoveryStory').addEventListener('input',()=>{recoverableStory=null;$('repairProjection').disabled=true});
const productionActions={wait:'Воркер активен',ready:'Книга сформирована',manual_review:'Нужна ручная проверка',queued:'В очереди',blocked:'Производство заблокировано'};
async function inspectProduction(){
const id=Number($('quote').value);
$('productionDetails').classList.add('hidden');
if(!Number.isSafeInteger(id)||id<=0){$('productionMessage').textContent='Введите корректный номер заказа выше';return}
if(!auth){$('productionMessage').textContent='Откройте панель через Telegram';return}
$('inspectProduction').disabled=true;$('productionMessage').textContent='Проверяем производственный журнал…';
try{
const x=await get('/order-quotes/'+id+'/production-operations');
const money=v=>v===null||v===undefined?'—':(v/1000000).toFixed(4);
$('productionAction').textContent=productionActions[x.recovery_action]||x.recovery_action;
$('productionLease').textContent=x.lease_diagnosis+' / '+x.lease_attempts;
$('productionEffects').textContent=String(x.unresolved_effects)+' / резервов: '+x.held_reservations;
$('productionBudget').textContent=money(x.budget_limit_micro_usd);
$('productionHeld').textContent=money(x.budget_held_micro_usd);
$('productionSpent').textContent=money(x.budget_spent_micro_usd);
$('productionNotes').textContent=(x.notes||[]).join(' · ');
$('productionDetails').classList.remove('hidden');
$('productionMessage').textContent='Проверка завершена. Повторные списания и генерация не выполнялись.';
}catch(e){$('productionMessage').textContent=e.message}
finally{$('inspectProduction').disabled=false}}
$('inspectProduction').addEventListener('click',inspectProduction);
$('check').addEventListener('click',check);$('refresh').addEventListener('click',check);
$('quote').addEventListener('keydown',e=>{if(e.key==='Enter')check()});
</script></body></html>"""
