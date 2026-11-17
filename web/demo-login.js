/* Public local demo. No real credential or API authorization is provided by this UI. */
(function(){
 const q=id=>document.getElementById(id),dialog=q('demo-login'),form=q('demo-login-form');
 const open=q('demo-login-open'),account=q('demo-account'),welcome=q('welcome-screen');
 const sessionKey='liquiditylab:demo-session';
 const positionKey='liquiditylab:demo-position';
 function read(key){try{return window.sessionStorage?.getItem(key);}catch{return null;}}
 function write(key,value){try{if(value==null)window.sessionStorage?.removeItem(key);else window.sessionStorage?.setItem(key,value);}catch{}}
 function show(){q('demo-login-error').textContent='';dialog.showModal();q('demo-username').focus();}
 function guest(){document.body.classList.add('guest');open.hidden=false;account.hidden=true;welcome.hidden=false;window.dispatchEvent(new Event('demo-guest'));}
 function signedIn(){document.body.classList.remove('guest');open.hidden=true;account.hidden=false;welcome.hidden=true;}
 if(read(sessionKey)==='active'){
  signedIn();
  let saved;
  try{saved=JSON.parse(read(positionKey));}catch{}
  if(saved?.hash===window.location.hash&&Number.isFinite(saved.top)){
   const restore=()=>window.requestAnimationFrame(()=>{
    if(window.location.hash===saved.hash)window.scrollTo(0,saved.top);
   });
   window.addEventListener('eod-updated',restore,{once:true});
  }
 }else guest();
 window.addEventListener('pagehide',()=>{
  if(read(sessionKey)==='active')write(positionKey,JSON.stringify({hash:window.location.hash,top:window.scrollY}));
 });
 open.addEventListener('click',show);
 q('demo-login-close').addEventListener('click',()=>dialog.close());
 form.addEventListener('submit',event=>{
  event.preventDefault();
  if(q('demo-username').value.trim()!=='LiquidityLab'||q('demo-password').value!=='123456789'){q('demo-login-error').textContent='Nhập đúng tài khoản và mật khẩu mẫu bên dưới.';return;}
  q('demo-password').value='';dialog.close();write(sessionKey,'active');signedIn();
  window.dispatchEvent(new Event('resize'));window.dispatchEvent(new Event('hashchange'));window.dispatchEvent(new Event('demo-login-success'));
 });
 q('demo-logout').addEventListener('click',()=>{write(sessionKey,null);write(positionKey,null);form.reset();guest();});
})();
