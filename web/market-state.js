/* Persist filter preferences and follow the Vietnam calendar by default. */
(function(){
  const today=()=>new Date(Date.now()+7*3600000).toISOString().slice(0,10);
  const defaults={symbol:'',scope:'ALL',type:'ALL',period:'recent',range:'1M',from:'',to:today(),followToday:true,resolution:'1D',source:'Historical EOD'};
  let saved={};try{saved=JSON.parse(localStorage.getItem('liquidity-market-state')||'{}');}catch(_){}
  const value={...defaults};
  for(const k of Object.keys(defaults))if(typeof saved?.[k]===typeof defaults[k])value[k]=saved[k];
  if(value.followToday)value.to=today();
  function set(patch){
    patch={...patch};
    if('to' in patch && !('followToday' in patch))patch.followToday=patch.to===today();
    if(patch.followToday===true)patch.to=today();
    if(!Object.entries(patch).some(([k,v])=>value[k]!==v))return;
    Object.assign(value,patch);
    try{localStorage.setItem('liquidity-market-state',JSON.stringify(value));}catch(_){}
    window.dispatchEvent(new CustomEvent('market-state-change',{detail:{...value}}));
  }
  window.MarketState={value,set};
  const advance=()=>{if(value.followToday&&value.to!==today())set({to:today(),followToday:true});};
  if(typeof setInterval==='function')setInterval(advance,30000);
  if(typeof document!=='undefined')document.addEventListener('visibilitychange',advance);
})();
