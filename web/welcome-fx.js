/* Decorative liquidity sequence. No security scan, market signal or network request. */
(function(){
 'use strict';
 const screen=document.getElementById('welcome-screen');if(!screen)return;
 const image=screen.querySelector('img'),canvas=document.createElement('canvas');canvas.className='welcome-fx';canvas.setAttribute('aria-hidden','true');screen.append(canvas);
 const ctx=canvas.getContext('2d');if(!ctx)return;
 const phases=['laser','ripple','digital','converge','liquid','grid','focus','glitch','assembly'];
 const names=['Trái sang phải','Tâm lan ra ngoài','Phải sang trái','Viền hội tụ vào tâm','Sóng chất lỏng dâng','Lưới sáng quét xuống','Bokeh lấy nét','Glitch ngắn','Hạt sáng kết tụ'];
 const motion=window.matchMedia('(prefers-reduced-motion: reduce)');
 const toggle=document.createElement('button');toggle.type='button';toggle.className='welcome-motion';toggle.textContent='Tạm dừng hiệu ứng';document.querySelector('.session-actions').prepend(toggle);
 const label=document.createElement('span');label.className='welcome-fx-label';label.textContent='Hiệu ứng trang trí · không phải quét bảo mật';screen.append(label);
 let frame=null,elapsed=0,last=0,paused=false,phaseIndex=-1,w=1,h=1;
 const style=getComputedStyle(document.documentElement),glow=style.getPropertyValue('--welcome-glow').trim(),fog=style.getPropertyValue('--welcome-fog').trim(),ice=style.getPropertyValue('--welcome-ice').trim();
 const ease=p=>p*p*(3-2*p);
 const particles=Array.from({length:window.innerWidth<700?100:240},(_,i)=>({x:((i*71)%997)/997,y:((i*137)%991)/991,a:(i%7)/7}));
 function resize(){w=screen.clientWidth||innerWidth;h=screen.clientHeight||innerHeight;const ratio=Math.min(devicePixelRatio||1,1.25);canvas.width=Math.round(w*ratio);canvas.height=Math.round(h*ratio);ctx.setTransform(ratio,0,0,ratio,0,0);}
 // A broad translucent stroke provides a halo without costly per-shape shadowBlur.
 function line(x1,y1,x2,y2,color,alpha=1,width=2){ctx.strokeStyle=color;ctx.beginPath();ctx.moveTo(x1,y1);ctx.lineTo(x2,y2);ctx.globalAlpha=alpha*.18;ctx.lineWidth=width+10;ctx.stroke();ctx.globalAlpha=alpha;ctx.lineWidth=width;ctx.stroke();}
 function draw(index,p){
  const t=ease(p),cx=w*.5,cy=h*.48,max=Math.hypot(w,h)*.6;
  ctx.clearRect(0,0,w,h);ctx.globalCompositeOperation='source-over';ctx.globalAlpha=1;
  // Smooth entry/exit prevents a hard cut at phase changes. Only this small overlay
  // changes opacity; never repaint/filter the full-resolution background each frame.
  const envelope=ease(Math.min(1,p/.1,(1-p)/.1));
  canvas.style.opacity=String(.78*envelope);
  if(index===0||index===2){
   const x=(index===0?t:1-t)*w;
   const gradient=ctx.createLinearGradient(x-90,0,x+90,0);gradient.addColorStop(0,'transparent');gradient.addColorStop(.5,fog);gradient.addColorStop(1,'transparent');ctx.fillStyle=gradient;ctx.globalAlpha=.65;ctx.fillRect(x-90,0,180,h);line(x,0,x,h,glow,.95,3);
   if(index===2)for(let i=0;i<particles.length;i++){const a=particles[i],px=x+a.a*130,py=a.y*h;ctx.globalAlpha=.35;ctx.fillStyle=i%3?glow:ice;ctx.fillRect(px,py,2,2);}
  }else if(index===1){
   if(p<.12){ctx.globalAlpha=(1-p/.12)*.6;ctx.fillStyle=glow;ctx.beginPath();ctx.arc(cx,cy,6+p*160,0,Math.PI*2);ctx.fill();}
   for(let k=0;k<5;k++){const r=(p-k*.13)*max;if(r<0)continue;ctx.beginPath();ctx.arc(cx,cy,r,0,Math.PI*2);ctx.strokeStyle=glow;ctx.globalAlpha=Math.max(0,.65-p+k*.1);ctx.lineWidth=2;ctx.stroke();}
  }else if(index===3){
   for(let i=0;i<32;i++){const angle=i/32*Math.PI*2;const r=max*(1-t);line(cx+Math.cos(angle)*r,cy+Math.sin(angle)*r,cx+Math.cos(angle)*(r+70),cy+Math.sin(angle)*(r+70),i%5?glow:ice,.5,1.5);}
   if(p>.8){ctx.globalAlpha=Math.sin((p-.8)/.2*Math.PI)**2*.3;ctx.fillStyle=glow;ctx.beginPath();ctx.arc(cx,cy,40+(p-.8)*500,0,Math.PI*2);ctx.fill();}
  }else if(index===4){
   const y=h*(1-t);
   ctx.beginPath();ctx.moveTo(0,h);for(let x=0;x<=w+20;x+=16)ctx.lineTo(x,y+Math.sin(x/90+p*10)*14);ctx.lineTo(w,h);ctx.closePath();const gradient=ctx.createLinearGradient(0,y,0,h);gradient.addColorStop(0,glow);gradient.addColorStop(1,'transparent');ctx.fillStyle=gradient;ctx.globalAlpha=.3;ctx.fill();
  }else if(index===5){
   const y=t*h;
   for(let i=0;i<16;i++)line(cx+(i-8)*w*.04,h*.15,cx+(i-8)*w*.17,h,fog,.18,1);
   for(let i=0;i<10;i++){const gy=h*.15+Math.pow(i/9,2)*h*.85;line(0,gy,w,gy,fog,.18,1);}line(0,y,w,y,glow,.8,2);
  }else if(index===6){
   // Soft glow breathing in place; never blur or defocus the background/logo.
   const gradient=ctx.createLinearGradient(cx-w*.35,0,cx+w*.35,0);gradient.addColorStop(0,'transparent');gradient.addColorStop(.5,fog);gradient.addColorStop(1,'transparent');ctx.fillStyle=gradient;ctx.globalAlpha=.25*Math.sin(p*Math.PI)**2;ctx.fillRect(0,0,w,h);
  }else if(index===7){
   // One short distortion, not repetitive flashing. Never moves the input controls.
   for(let i=0;i<5;i++){ctx.globalAlpha=.4*Math.sin(p*Math.PI)**2;ctx.fillStyle=i%2?ice:glow;ctx.fillRect((i%2)*w*.08,cy-100+i*43+Math.sin(p*Math.PI*2)*8,w*.84,2);}
  }else{
   for(let i=0;i<particles.length;i++){const a=particles[i],angle=a.x*Math.PI*2,targetX=cx+Math.cos(angle)*w*.25,targetY=cy+Math.sin(angle)*h*.13;const x=a.x*w*(1-t)+targetX*t,y=a.y*h*(1-t)+targetY*t;ctx.globalAlpha=.35;ctx.fillStyle=i%4?glow:ice;ctx.beginPath();ctx.arc(x,y,1+i%3*.3,0,Math.PI*2);ctx.fill();}
  }
  ctx.globalAlpha=1;ctx.globalCompositeOperation='source-over';
 }
 function stop(){if(frame!==null)cancelAnimationFrame(frame);frame=null;ctx.clearRect(0,0,w,h);image.style.clipPath='none';image.style.filter='none';screen.removeAttribute('data-effect');document.body.removeAttribute('data-welcome-effect');}
 function allowed(){return document.body.classList.contains('guest')&&!document.hidden&&!paused&&!motion.matches;}
 function tick(now){frame=null;if(!allowed()){stop();return;}elapsed+=Math.min(now-last,100);last=now;const index=Math.floor(elapsed/6000)%phases.length,p=(elapsed%6000)/6000;
  if(index!==phaseIndex){phaseIndex=index;screen.dataset.effect=phases[index];document.body.dataset.welcomeEffect=phases[index];label.textContent=names[index]+' · trang trí, không phải quét bảo mật';}
  draw(index,p);frame=requestAnimationFrame(tick);
 }
 function start(){if(!allowed()){stop();return;}if(frame!==null)return;resize();image.style.clipPath='none';image.style.filter='brightness(1.04)';last=performance.now();phaseIndex=-1;frame=requestAnimationFrame(tick);}
 toggle.addEventListener('click',()=>{paused=!paused;toggle.textContent=paused?'Tiếp tục hiệu ứng':'Tạm dừng hiệu ứng';if(paused)stop();else start();});
 window.addEventListener('demo-login-success',()=>{stop();toggle.hidden=true;});
 window.addEventListener('demo-guest',()=>{toggle.hidden=motion.matches;elapsed=0;start();});
 document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();else start();});
 motion.addEventListener('change',()=>{toggle.hidden=motion.matches;if(motion.matches)stop();else start();});
 window.addEventListener('resize',resize);toggle.hidden=motion.matches||!document.body.classList.contains('guest');start();
 window.WelcomeFX=Object.freeze({phases:[...phases],start,stop});
})();
