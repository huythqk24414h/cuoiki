/* Only filter preferences persist. Never credentials, quotes or manual financial inputs. */
(function(){
  const defaults={symbol:'',scope:'ALL',type:'ALL',range:'1M',from:'',to:'2026-11-04',resolution:'1D',source:'Historical EOD'};
  let saved={};try{saved=JSON.parse(localStorage.getItem('liquidity-market-state')||'{}');}catch(_){}
  const value={...defaults};for(const k of Object.keys(defaults))if(typeof saved?.[k]==='string')value[k]=saved[k];
  window.MarketState={value,set(patch){if(!Object.entries(patch).some(([k,v])=>value[k]!==v))return;Object.assign(value,patch);try{localStorage.setItem('liquidity-market-state',JSON.stringify(value));}catch(_){}window.dispatchEvent(new CustomEvent('market-state-change',{detail:{...value}}));}};
})();
