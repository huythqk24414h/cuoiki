'use strict';
const $ = selector => document.querySelector(selector);
const calculator = window.LiquidityCalculator;
let lastResult = null;
let toastTimer;
let inputMode = 'visual';
let draftVersion = 0;

function toast(message) {
  $('#toast').textContent = message;
  $('#toast').classList.add('visible');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $('#toast').classList.remove('visible'), 6000);
}
function navigate() {
  // A skip link moves focus within the current page; it is not a route change.
  if (location.hash === '#main' && document.querySelector('nav a[aria-current="page"]')) return;
  const allowed = ['monitor', 'analysis', 'book', 'calculator', 'alerts', 'method'];
  const page = allowed.includes(location.hash.slice(1)) ? location.hash.slice(1) : 'monitor';
  document.querySelectorAll('.page').forEach(el => { el.hidden = el.id !== page; });
  document.querySelectorAll('nav a').forEach(el => {
    el.classList.toggle('active', el.dataset.page === page);
    if (el.dataset.page === page) el.setAttribute('aria-current', 'page');
    else el.removeAttribute('aria-current');
  });
  document.title = `${{monitor:'Tổng quan', analysis:'Phân tích thanh khoản', book:'Sổ lệnh', alerts:'Cảnh báo', calculator:'Kiểm tra công thức', method:'Phương pháp & nguồn'}[page]} — Liquidity Lab`;
}
window.addEventListener('hashchange', navigate);
navigate();

async function request(url, options = {}) {
  const target=new URL(url,location.href);
  if(target.origin!==location.origin)throw new Error('Ứng dụng chỉ cho phép gọi máy chủ local cùng nguồn.');
  const {signal:callerSignal,timeoutMs=target.pathname.includes('coverage')?30000:15000,...settings}=options;
  const controller=new AbortController();
  const abort=()=>controller.abort(callerSignal.reason);
  if(callerSignal?.aborted)abort();else callerSignal?.addEventListener('abort',abort,{once:true});
  let timedOut=false;const timer=setTimeout(()=>{timedOut=true;controller.abort();},timeoutMs);
  try{
    const response=await fetch(target.href,{...settings,signal:controller.signal});
    const body=await response.json();
    if(!response.ok){const error=new Error(body.error||'Máy chủ không xử lý được yêu cầu.');error.httpStatus=response.status;throw error;}
    return body;
  }catch(error){
    if(timedOut){const e=new Error('Máy chủ local phản hồi quá chậm. Dữ liệu cũ được giữ lại; thử đọc lại.');e.code='LOCAL_TIMEOUT';throw e;}
    if(error.name==='TypeError'){const e=new Error('Không kết nối được chương trình local. Kiểm tra cửa sổ chạy ứng dụng.');e.code='LOCAL_OFFLINE';throw e;}
    throw error;
  }finally{clearTimeout(timer);callerSignal?.removeEventListener('abort',abort);}
}

function resetResult() {
  draftVersion += 1;
  lastResult = null;
  window.dispatchEvent(new CustomEvent('manual-book-updated',{detail:null}));
  for (const id of ['result','snapshot','insight','calc-error']) $(`#${id}`).hidden = true;
  for (const id of ['result-empty','snapshot-empty','insight-empty']) $(`#${id}`).hidden = false;
  $('#snapshot-empty').textContent = 'Biểu đồ chỉ xuất hiện sau phép tính hợp lệ.';
  document.querySelectorAll('[aria-invalid="true"]').forEach(input => {input.removeAttribute('aria-invalid');input.removeAttribute('aria-errormessage');});
}
function chooseInputMode(mode, focus = false) {
  inputMode = mode;
  resetResult();
  for (const id of ['visual','json']) {
    const active = id === mode;
    $(`#${id}-panel`).hidden = !active;
    $(`#${id}-tab`).setAttribute('aria-selected', String(active));
    $(`#${id}-tab`).tabIndex = active ? 0 : -1;
  }
  if (focus) $(`#${mode}-tab`).focus();
}
for (const mode of ['visual','json']) {
  $(`#${mode}-tab`).addEventListener('click', () => chooseInputMode(mode));
  $(`#${mode}-tab`).addEventListener('keydown', event => {
    if (['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) {
      event.preventDefault();
      chooseInputMode(event.key === 'Home' ? 'visual' : event.key === 'End' ? 'json' : mode === 'visual' ? 'json' : 'visual', true);
    }
  });
}
$('#book-form').addEventListener('input', resetResult);
$('#template').addEventListener('click', () => {
  resetResult();
  $('#payload').value = JSON.stringify({contract_version:'1.0',source:'manual',symbol:'',price_unit:'VND',quantity_unit:'share',session:'continuous',event_time:'',received_at:'',bids:[{price:null,quantity:null}],asks:[{price:null,quantity:null}]}, null, 2);
  toast('Đã điền cấu trúc trống. Bạn tự cung cấp mã, thời gian, giá và khối lượng.');
});
$('#clear').addEventListener('click', () => {
  $('#book-form').reset();
  resetResult();
  (inputMode === 'visual' ? $('#manual-symbol') : $('#payload')).focus();
  toast('Đã xóa cả hai bản nháp và kết quả trong phiên.');
});

function readManualForm() {
  const form = {symbol:$('#manual-symbol').value,time:$('#manual-time').value,receivedTime:$('#manual-received').value};
  for (const side of ['bids','asks']) {
    form[side] = [0,1,2].map(level => ({
      price:document.querySelector(`[data-side="${side}"][data-level="${level}"][data-field="price"]`).value,
      quantity:document.querySelector(`[data-side="${side}"][data-level="${level}"][data-field="quantity"]`).value
    }));
  }
  const nowVietnam = new Date(Date.now()+7*60*60*1000).toISOString().slice(0,-1)+'+07:00';
  return calculator.buildManualPayload(form, nowVietnam);
}

function renderSnapshot(payload, result) {
  const series = calculator.cumulativeLevels(payload);
  const max = Math.max(...series.bids.map(x => x.cumulativeValue), ...series.asks.map(x => x.cumulativeValue));
  const outer = $('#snapshot-bars');
  outer.replaceChildren();
  if (!(max > 0) || !Number.isFinite(max)) {
    $('#snapshot-empty').textContent = 'Giá trị vượt độ chính xác biểu đồ. Xem kết quả và JSON từ engine; không vẽ thanh thay thế.';
    return false;
  }
  $('#snapshot').hidden=false;
  const figure=document.createElement('div');
  outer.append(figure);window.LiquidityDepthChart.render(figure,payload,'MANUAL');
  const details=document.createElement('details'),summary=document.createElement('summary'),container=document.createElement('div');
  summary.textContent='Xem giá trị lũy kế theo từng mức';details.append(summary,container);outer.append(details);
  const ns = 'http://www.w3.org/2000/svg';
  for (let i = 0; i < Math.max(series.bids.length, series.asks.length); i += 1) {
    const row = document.createElement('div'); row.className = 'snapshot-level';
    const label = document.createElement('p'); label.textContent = `Lũy kế đến mức ${i+1}`; row.append(label);
    const bars = document.createElement('div'); bars.className = 'snapshot-row';
    for (const side of ['bids','asks']) {
      const entry = series[side][i];
      const cell = document.createElement('div');
      const caption = document.createElement('p');
      caption.className = side === 'bids' ? 'bid-mark' : 'ask-mark';
      caption.textContent = entry ? `${side === 'bids' ? 'Mua' : 'Bán'}: ≈ ${calculator.formatDecimal(String(entry.cumulativeValue),0)} VND` : `${side === 'bids' ? 'Mua' : 'Bán'}: không nhập mức này`;
      const svg = document.createElementNS(ns,'svg');
      svg.setAttribute('viewBox','0 0 200 20'); svg.setAttribute('aria-hidden','true');
      const track = document.createElementNS(ns,'rect'); track.setAttribute('width','200'); track.setAttribute('height','16'); track.setAttribute('rx','4'); track.setAttribute('class','snapshot-track'); svg.append(track);
      if (entry) {
        const bar = document.createElementNS(ns,'rect');
        bar.setAttribute('width',String(entry.cumulativeValue/max*200)); bar.setAttribute('height','16'); bar.setAttribute('rx','4');
        bar.setAttribute('class',side === 'bids' ? 'snapshot-bid' : 'snapshot-ask'); svg.append(bar);
      }
      cell.append(caption,svg); bars.append(cell);
    }
    row.append(bars); container.append(row);
  }
  const total = document.createElement('p'); total.className = 'helper';
  total.textContent = `Tổng chính xác từ engine: mua ${calculator.formatDecimal(result.bid_depth_vnd,4)} VND; bán ${calculator.formatDecimal(result.ask_depth_vnd,4)} VND. Hình học và nhãn lũy kế của biểu đồ được làm tròn.`;
  container.append(total);
  return true;
}

function renderResult(result, payload) {
  const sweepOutput = $('#sweep-result');
  sweepOutput.textContent = '';
  $('#sweep-run').onclick = () => {
    try {
      const sweep = calculator.simulateSweep(payload, $('#sweep-side').value, $('#sweep-quantity').value);
      const format = value => value.toLocaleString('vi-VN', {maximumFractionDigits: 4});
      const slippage = sweep.slippageBps == null ? 'Chưa đủ khối lượng để tính trượt giá toàn lệnh'
        : 'Trượt giá so với giá giữa ' + format(sweep.slippageBps) + ' bps';
      sweepOutput.textContent = 'Khớp mô phỏng ' + format(sweep.filled) + '/' + format(sweep.requested) +
        ' cp (' + format(sweep.fillRatio * 100) + '%) · Còn thiếu ' + format(sweep.remaining) +
        ' cp · VWAP phần khớp ' + (sweep.vwap == null ? '—' : format(sweep.vwap) + ' VND/cp') + ' · ' + slippage + '.';
    } catch (error) {
      sweepOutput.textContent = error.message;
    }
  };
  $('#result-values').replaceChildren();
  const fmt = calculator.formatDecimal;
  const values = [['Độ sâu mua', `${fmt(result.bid_depth_vnd,4)} VND`], ['Độ sâu bán', `${fmt(result.ask_depth_vnd,4)} VND`],
    ['Spread tuyệt đối', `${fmt(result.spread_vnd_per_share,4)} VND/cp`],
    ['Spread tương đối', `${fmt(result.spread_bps,4)} bps`], ['Imbalance theo giá trị', fmt(result.imbalance,6)],
    ['Tổng độ sâu hai phía', `${fmt(result.total_depth_vnd,4)} VND`],
    ['Số mức mua / bán', `${result.levels.bid} / ${result.levels.ask}`]];
  values.forEach(([name,value]) => {
    const group=document.createElement('div'), dt=document.createElement('dt'), dd=document.createElement('dd');
    dt.textContent=name; dd.textContent=value; group.append(dt,dd); $('#result-values').append(group);
  });
  $('#result-json').textContent=JSON.stringify(result,null,2);
  $('#insight-list').replaceChildren();
  calculator.describeResult(result).forEach(text => { const li=document.createElement('li');li.textContent=text;$('#insight-list').append(li); });
  const hasChart = renderSnapshot(payload,result);
  for (const id of ['result','insight']) $(`#${id}`).hidden=false;
  for (const id of ['result-empty','insight-empty']) $(`#${id}`).hidden=true;
  $('#snapshot').hidden = !hasChart;
  $('#snapshot-empty').hidden = hasChart;
}

$('#book-form').addEventListener('submit', async event => {
  event.preventDefault();
  resetResult();
  const version=draftVersion, button=$('#calculate');
  button.disabled=true;button.textContent='Đang tính…';
  try {
    let payload;
    if (inputMode === 'visual') payload=readManualForm();
    else {
      try {payload=JSON.parse($('#payload').value);} catch {throw new Error('JSON chưa hợp lệ. Kiểm tra dấu ngoặc, dấu phẩy và các trường bắt buộc.');}
    }
    const result=await request('/api/calculate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    if (draftVersion !== version) return;
    renderResult(result,payload);
    lastResult=result;
    window.dispatchEvent(new CustomEvent('manual-book-updated',{detail:{payload,result}}));
    toast('Đã tính từ dữ liệu nhập tay. Kết quả không được đưa vào màn hình thị trường.');
  } catch(error) {
    if (draftVersion !== version) return;
    if(inputMode==='visual' && (error.httpStatus==null||error.httpStatus===422) && !['TimeoutError','AbortError','TypeError'].includes(error.name)){
      const targets=[];
      const row=/Bên (mua|bán), mức (\d)/.exec(error.message);
      if(row){
        const side=row[1]==='mua'?'bids':'asks';
        document.querySelectorAll(`[data-side="${side}"][data-level="${Number(row[2])-1}"]`).forEach(input=>targets.push(input));
      }else if(/mã/i.test(error.message))targets.push($('#manual-symbol'));
      else if(/thời gian|ngày giờ/i.test(error.message))targets.push($('#manual-time'),$('#manual-received'));
      else document.querySelectorAll('#visual-panel .input-row input').forEach(input=>{if(input.value)targets.push(input);});
      targets.forEach(input=>{input.setAttribute('aria-invalid','true');input.setAttribute('aria-errormessage','calc-error');});
    }
    $('#calc-error').textContent=error.name === 'TimeoutError' ? 'Ứng dụng phản hồi quá lâu. Hãy thử lại.' : error.message;
    $('#calc-error').hidden=false;
    $('#calc-error').focus();
  } finally {button.disabled=false;button.textContent='Tính toán';}
});
$('#download').addEventListener('click', () => {
  if (!lastResult) return;
  const url=URL.createObjectURL(new Blob([JSON.stringify(lastResult,null,2)],{type:'application/json'}));
  const link=document.createElement('a');link.href=url;link.download='kiem-tra-cong-thuc-nhap-tay.json';link.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
});
