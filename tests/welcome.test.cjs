/* Lifecycle/logic tests with isolated DOM/canvas doubles; NOT visual browser acceptance. */
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function login(saved=new Map()){const handlers={},body=new Set(),nodes={};let opened=0,closed=0,scroll=0;const events=[];
 for(const id of ['demo-login','demo-login-form','demo-login-open','demo-account','welcome-screen','demo-username','demo-password','demo-login-error','demo-logout','demo-login-close'])nodes[id]={value:'',hidden:false,addEventListener:(e,f)=>handlers[id+':'+e]=f,focus(){}};
 nodes['demo-login'].showModal=()=>opened++;nodes['demo-login'].close=()=>closed++;nodes['demo-login-form'].reset=()=>{};
 const window={location:{hash:'#analysis'},scrollY:250,scrollTo:(_,top)=>{scroll=top;},requestAnimationFrame:f=>f(),
  sessionStorage:{getItem:key=>saved.get(key),setItem:(key,value)=>saved.set(key,value),removeItem:key=>saved.delete(key)},
  addEventListener:(e,f)=>{handlers[e]=f;},dispatchEvent:e=>events.push(e.type)};
 vm.runInNewContext(fs.readFileSync('web/demo-login.js','utf8'),{document:{getElementById:id=>nodes[id],body:{classList:{add:v=>body.add(v),remove:v=>body.delete(v)}}},window,Event});
 return {nodes,handlers,body,events,opened:()=>opened,closed:()=>closed,position:()=>scroll};}
test('welcome is first screen; login dialog opens only on click',()=>{const h=login();assert.equal(h.opened(),0);assert.ok(h.body.has('guest'));assert.equal(h.nodes['demo-account'].hidden,true);h.handlers['demo-login-open:click']();assert.equal(h.opened(),1);});
test('wrong login keeps welcome; correct login reveals account; logout returns to welcome without modal',()=>{const h=login();h.nodes['demo-username'].value='LiquidityLab';h.nodes['demo-password'].value='bad';h.handlers['demo-login-form:submit']({preventDefault(){}});assert.ok(h.body.has('guest'));h.nodes['demo-password'].value='123456789';h.handlers['demo-login-form:submit']({preventDefault(){}});assert.equal(h.body.has('guest'),false);assert.equal(h.nodes['demo-account'].hidden,false);assert.equal(h.nodes['demo-password'].value,'');assert.ok(h.events.includes('demo-login-success'));h.handlers['demo-logout:click']();assert.ok(h.body.has('guest'));assert.equal(h.nodes['welcome-screen'].hidden,false);assert.equal(h.opened(),0);});
test('reload keeps the demo session and scroll position until logout',()=>{
 const storage=new Map(),before=login(storage);
 before.nodes['demo-username'].value='LiquidityLab';before.nodes['demo-password'].value='123456789';
 before.handlers['demo-login-form:submit']({preventDefault(){}});before.handlers.pagehide();
 const after=login(storage);
 assert.equal(after.body.has('guest'),false);assert.equal(after.nodes['welcome-screen'].hidden,true);
 after.handlers['eod-updated']();assert.equal(after.position(),250);
 assert.ok(![...storage.values()].join('').includes('123456789'));
 after.handlers['demo-logout:click']();
 assert.ok(login(storage).body.has('guest'));
});
function fx(reduced=false){let callback=null,guest=true,time=0;const handlers={},docHandlers={},mediaHandlers={};const img={style:{}},body={dataset:{},classList:{contains:()=>guest},removeAttribute:k=>{if(k==='data-welcome-effect')delete body.dataset.welcomeEffect;}};
 const ctx=new Proxy({createLinearGradient:()=>({addColorStop(){}})},{get:(o,k)=>k in o?o[k]:(()=>{}),set:(o,k,v)=>(o[k]=v,true)});
 const children=[],screen={clientWidth:1000,clientHeight:600,dataset:{},querySelector:()=>img,append:(...n)=>children.push(...n),removeAttribute:k=>{if(k==='data-effect')delete screen.dataset.effect;}};
 const doc={hidden:false,body,getElementById:()=>screen,createElement:tag=>({style:{},setAttribute(){},getContext:()=>ctx,addEventListener(e,f){this[e]=f;}}),querySelector:()=>({prepend:n=>children.unshift(n)}),addEventListener:(e,f)=>docHandlers[e]=f};
 const win={innerWidth:1440,matchMedia:()=>({matches:reduced,addEventListener:(e,f)=>mediaHandlers[e]=f}),addEventListener:(e,f)=>handlers[e]=f};
 vm.runInNewContext(fs.readFileSync('web/welcome-fx.js','utf8'),{window:win,document:doc,innerWidth:1000,innerHeight:600,devicePixelRatio:1,getComputedStyle:()=>({getPropertyValue:()=> '#FF334D'}),performance:{now:()=>time},requestAnimationFrame:f=>(callback=f,1),cancelAnimationFrame:()=>callback=null,Math});
 return {win,doc,screen,img,handlers,docHandlers,children,advance(){time+=100;const f=callback;callback=null;f?.(time);},stop(){guest=false;handlers['demo-login-success']();},running:()=>callback!==null};}
test('nine light overlays keep artwork visible, loop and stop after sign-in',()=>{const h=fx();const seen=[];for(let i=0;i<541;i++){h.advance();assert.equal(h.img.style.clipPath,'none');const brightness=Number(/^brightness\(([\d.]+)\)$/.exec(h.img.style.filter)?.[1]);assert.ok(brightness>=1&&brightness<=1.1,'Never darken or blur the artwork');const p=h.screen.dataset.effect;if(p!==seen.at(-1))seen.push(p);}assert.deepEqual(seen,['laser','ripple','digital','converge','liquid','grid','focus','glitch','assembly','laser']);h.stop();assert.equal(h.running(),false);assert.equal(h.screen.dataset.effect,undefined);});
test('reduced-motion starts no animation frame',()=>{assert.equal(fx(true).running(),false);});
test('manual pause and hidden tab stop rendering',()=>{const h=fx();h.children[0].click();assert.equal(h.running(),false);h.children[0].click();assert.equal(h.running(),true);h.doc.hidden=true;h.docHandlers.visibilitychange();assert.equal(h.running(),false);});
