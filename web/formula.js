/* KaTeX parser, native MathML output: no CDN, unsafe HTML or inline-style CSP exception. */
(function(){
 'use strict';
 const equations={
  return:{latex:String.raw`r_t=\left(\frac{C_t}{C_{t-1}}-1\right)\times100\%`,note:'Lợi suất %, cần giá đóng cửa phiên trước hợp lệ.'},
  mean:{latex:String.raw`\mathrm{TB20}_t=\frac{1}{20}\sum_{k=1}^{20}V_{t-k}`,note:'Đúng 20 quan sát phiên trước t, loại phiên hiện tại.'},
  relative:{latex:String.raw`\mathrm{RV20}_t=\frac{V_t}{\mathrm{TB20}_t}`,note:'Đơn vị lần; — nếu thiếu 20 quan sát trước hoặc TB20 bằng 0.'},
  volatility:{latex:String.raw`\sigma_{20,t}=\sqrt{\frac{\sum_{i=1}^{20}(r_i-\bar r)^2}{19}}`,note:'Độ lệch chuẩn mẫu của 20 lợi suất (%), cần 21 giá; không thường niên hóa.'},
  depth:{latex:String.raw`D_t^{\mathrm{side}}=\sum_{i=1}^{K}P_{i,t}^{\mathrm{side}}Q_{i,t}^{\mathrm{side}}`,note:'VND chỉ khi P đã xác minh là VND/cp và Q là cp. Manual nhập VND; SSI quy đổi theo contract, không mặc định ×1.000.'},
  mid:{latex:String.raw`\mathrm{Mid}_t=\frac{\mathrm{Ask}_{1,t}+\mathrm{Bid}_{1,t}}{2}`,note:'Cần báo giá hai phía hợp lệ trong phiên phù hợp.'},
  spread:{latex:String.raw`\mathrm{Spread}_{\mathrm{bps},t}=\frac{\mathrm{Ask}_{1,t}-\mathrm{Bid}_{1,t}}{\mathrm{Mid}_t}\times10^4`,note:'Một bps = 0,01%. Không tính chỉ báo executable từ giá khóa/chéo hoặc giá đấu giá.'},
  imbalance:{latex:String.raw`I_t=\frac{D_t^B-D_t^A}{D_t^B+D_t^A}\in[-1,1]`,note:'— nếu tổng hai phía bằng 0; thiếu bản tin khác với phía cầu rỗng đã được xác minh.'}
 };
 function identify(text){if(/^r[ₜ_]/.test(text))return 'return';if(text.startsWith('TB20'))return 'mean';if(text.startsWith('RV20')||text.startsWith('Relative'))return 'relative';if(text.startsWith('D'))return 'depth';if(text.startsWith('I ')||text.startsWith('Imbalance'))return 'imbalance';return 'spread';}
 function render(target,key){
  const equation=equations[key];target.replaceChildren();target.dataset.formula=key;
  const tools=document.createElement('span');tools.className='formula-tools';
  const math=document.createElement('span');math.className='formula-math';
  try{katex.render(equation.latex,math,{throwOnError:true,trust:false,output:'mathml',displayMode:true});}catch(_){math.textContent=equation.latex;}
  const copy=document.createElement('button');copy.type='button';copy.className='button secondary formula-copy';copy.textContent='Chép LaTeX';copy.setAttribute('aria-label','Chép LaTeX: '+key);
  copy.onclick=async()=>{try{await navigator.clipboard.writeText(equation.latex);copy.textContent='Đã chép';}catch(_){copy.textContent='Không chép được';}setTimeout(()=>copy.textContent='Chép LaTeX',1500);};
  tools.append(math,copy);const note=document.createElement('span');note.className='formula-note';note.textContent=equation.note;target.append(tools,note);
 }
 document.querySelectorAll('.formula').forEach(n=>render(n,identify(n.textContent.trim())));
 const card=[...document.querySelectorAll('#method .card')].find(n=>n.querySelector('h2')?.textContent==='Công thức EOD');
 if(card){const n=document.createElement('div');n.className='formula';card.append(n);render(n,'volatility');}
 const book=[...document.querySelectorAll('#method .card')].find(n=>n.querySelector('h2')?.textContent==='Sổ lệnh nhập tay');
 if(book){const n=document.createElement('div');n.className='formula';book.append(n);render(n,'mid');}
 document.querySelectorAll('.global-market select').forEach(n=>{const update=()=>n.title=n.selectedOptions[0]?.textContent||'';n.addEventListener('change',update);update();new MutationObserver(update).observe(n,{childList:true});});
})();
