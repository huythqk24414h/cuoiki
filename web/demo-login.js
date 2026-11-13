/* Public local demo. No real credential or API authorization is provided by this UI. */
(function(){
 const q=id=>document.getElementById(id),dialog=q('demo-login'),form=q('demo-login-form');
 const open=q('demo-login-open'),account=q('demo-account'),welcome=q('welcome-screen');
 function show(){q('demo-login-error').textContent='';dialog.showModal();q('demo-username').focus();}
 function guest(){document.body.classList.add('guest');open.hidden=false;account.hidden=true;welcome.hidden=false;window.dispatchEvent(new Event('demo-guest'));}
 // Always start at the welcome screen; no automatic modal or restored login.
 guest();
 open.addEventListener('click',show);
 q('demo-login-close').addEventListener('click',()=>dialog.close());
 form.addEventListener('submit',event=>{
  event.preventDefault();
  if(q('demo-username').value.trim()!=='LiquidityLab'||q('demo-password').value!=='123456789'){q('demo-login-error').textContent='Nhập đúng tài khoản và mật khẩu mẫu bên dưới.';return;}
  q('demo-password').value='';dialog.close();document.body.classList.remove('guest');open.hidden=true;account.hidden=false;welcome.hidden=true;
  window.dispatchEvent(new Event('resize'));window.dispatchEvent(new Event('hashchange'));window.dispatchEvent(new Event('demo-login-success'));
 });
 q('demo-logout').addEventListener('click',()=>{form.reset();guest();});
})();
