import * as pdfjs from '/vendor/pdf.mjs';
pdfjs.GlobalWorkerOptions.workerSrc='/vendor/pdf.worker.mjs';

// Continuous PDF reader. Canvas uses device pixels; textLayer uses CSS coordinates.
export class PaperReader {
 constructor(scroll,pages,{onPosition,onSelection,onStatus,onOutline}){
  Object.assign(this,{scroll,pages,onPosition,onSelection,onStatus,onOutline});
  this.records=[];this.generation=0;this.scale=1;this.fit=true;this.doc=null;this.active=0;this.jobs=new Map();this.queue=[];this.working=0;
  this.observer=new IntersectionObserver(entries=>{for(const e of entries)if(e.isIntersecting)this.enqueue(Number(e.target.dataset.page));},{root:scroll,rootMargin:'900px 500px'});
  scroll.addEventListener('scroll',()=>{this.hideMenu();if(this.scrollRAF)return;this.scrollRAF=requestAnimationFrame(()=>{this.scrollRAF=null;this.reportPosition();this.evict();});},{passive:true});
  this.hideMenu=()=>this.onSelection(null);
  document.addEventListener('selectionchange',()=>{clearTimeout(this.selectionTimer);this.selectionTimer=setTimeout(()=>this.readSelection(),160);});
  this.resizeObserver=new ResizeObserver(()=>{clearTimeout(this.resizeTimer);this.resizeTimer=setTimeout(()=>{if(this.doc&&this.fit&&this.scroll.clientWidth>0&&Math.abs(this.lastWidth-this.scroll.clientWidth)>3)this.reflow(true);},160);});
  this.resizeObserver.observe(scroll);
 }
 async load(url,position={}){
  ++this.generation;this.cancelJobs();this.observer.disconnect();this.queue=[];
  if(this.loading){await this.loading.destroy();this.loading=null;}
  if(this.doc){await this.doc.destroy();this.doc=null;}
  this.records=[];this.pages.replaceChildren();this.onStatus('正在打开论文…');
  this.loading=pdfjs.getDocument({url,cMapUrl:'/vendor/cmaps/',cMapPacked:true,standardFontDataUrl:'/vendor/standard_fonts/',wasmUrl:'/vendor/wasm/',iccUrl:'/vendor/iccs/'});const loading=this.loading;
  const doc=await loading.promise;if(this.loading!==loading){await doc.destroy();return;}
  this.doc=doc;this.loading=null;this.fit=position.fit!==false;this.scale=Number(position.scale)||1;
  const first=await doc.getPage(1);const base=first.getViewport({scale:1});
  for(let n=1;n<=doc.numPages;n++){
   const slot=document.createElement('article');slot.className='pdf-page';slot.dataset.page=n;slot.setAttribute('aria-label',`PDF 第 ${n} 页`);
   const label=document.createElement('div');label.className='page-number';label.textContent=`${n} / ${doc.numPages}`;slot.append(label);
   const paper=document.createElement('div');paper.className='page-sheet';slot.append(paper);
   const placeholder=document.createElement('span');placeholder.className='page-placeholder';placeholder.textContent='正在准备原文…';paper.append(placeholder);
   this.pages.append(slot);this.records.push({n,slot,paper,width:base.width,height:base.height,rendered:false});
  }
  await this.reflow(false,position);
  this.onStatus('可直接选择原文文字');
  this.loadOutline(doc).catch(()=>this.onOutline([]));
 }
 async loadOutline(doc){
  const outline=await doc.getOutline()||[];const items=[];
  const walk=async(nodes,depth=0)=>{for(const node of nodes){let dest=node.dest;if(typeof dest==='string')dest=await doc.getDestination(dest);let page=null;if(Array.isArray(dest)){try{page=typeof dest[0]==='number'?dest[0]+1:(await doc.getPageIndex(dest[0]))+1;}catch{}}
   if(page)items.push({title:node.title,page,depth});if(node.items?.length)await walk(node.items,depth+1);}};
  await walk(outline);if(doc===this.doc)this.onOutline(items);
 }
 position(){
  if(!this.records.length)return{page:1,fraction:0};
  const top=this.scroll.scrollTop+16;let selected=this.records[0];for(const r of this.records){if(r.slot.offsetTop<=top)selected=r;else break;}
  return{page:selected.n,fraction:Math.max(0,Math.min(.99,(this.scroll.scrollTop-selected.slot.offsetTop)/selected.slot.offsetHeight)),scale:this.scale,fit:this.fit};
 }
 reportPosition(){const p=this.position();this.onPosition(p);}
 async reflow(preserve=true,restore=null){
  if(!this.doc)return;const position=restore||(preserve?this.position():{page:1,fraction:0});
  ++this.generation;this.cancelJobs();this.queue=[];this.observer.disconnect();this.lastWidth=this.scroll.clientWidth;
  if(this.fit)this.scale=Math.min(2,Math.max(.25,(this.scroll.clientWidth-48)/this.records[0].width));
  for(const r of this.records){r.rendered=false;r.failed=false;r.paper.replaceChildren();r.paper.style.width=`${r.width*this.scale}px`;r.paper.style.height=`${r.height*this.scale}px`;r.slot.style.width=`${r.width*this.scale}px`;
   r.paper.style.setProperty('--total-scale-factor',String(this.scale));r.paper.style.setProperty('--scale-round-x','1px');r.paper.style.setProperty('--scale-round-y','1px');this.observer.observe(r.slot);}
  this.jump(position.page,position.fraction||0);this.reportPosition();
  // Render the target first rather than wait for an observer callback.
  this.enqueue(Math.max(1,Math.min(this.records.length,position.page||1)));
 }
 cancelJobs(){for(const job of this.jobs.values()){job.render?.cancel();job.text?.cancel();}this.jobs.clear();}
 enqueue(n){const r=this.records[n-1];if(!r||r.rendered||r.failed||this.jobs.has(n)||this.queue.includes(n))return;this.queue.push(n);this.pump();}
 pump(){while(this.working<2&&this.queue.length){const n=this.queue.shift();const r=this.records[n-1];if(!r||r.rendered||this.jobs.has(n))continue;const generation=this.generation;this.working++;this.render(r,generation).catch(e=>{if(e.name!=='RenderingCancelledException'&&e.name!=='AbortException'&&generation===this.generation){r.failed=true;r.paper.textContent='此页载入失败。请重新打开论文。';this.onStatus('部分页载入失败，请重新打开论文');}}).finally(()=>{this.working--;this.pump();});}}
 async render(r,generation){
  const job={};this.jobs.set(r.n,job);const doc=this.doc;
  try{
   const page=await doc.getPage(r.n);if(generation!==this.generation)return;
   const viewport=page.getViewport({scale:this.scale});const dpr=Math.min(devicePixelRatio||1,2);
   r.width=page.getViewport({scale:1}).width;r.height=page.getViewport({scale:1}).height;
   r.paper.style.width=viewport.width+'px';r.paper.style.height=viewport.height+'px';r.slot.style.width=viewport.width+'px';
   r.paper.style.setProperty('--total-scale-factor',String(viewport.scale*viewport.userUnit));
   const canvas=document.createElement('canvas');canvas.setAttribute('aria-label',`第 ${r.n} 页原文画面`);canvas.width=Math.floor(viewport.width*dpr);canvas.height=Math.floor(viewport.height*dpr);canvas.style.width=viewport.width+'px';canvas.style.height=viewport.height+'px';
   const layer=document.createElement('div');layer.className='textLayer';layer.dataset.page=r.n;
   r.paper.replaceChildren(canvas,layer);
   job.render=page.render({canvasContext:canvas.getContext('2d'),viewport,transform:dpr===1?null:[dpr,0,0,dpr,0,0]});
   job.text=new pdfjs.TextLayer({textContentSource:page.streamTextContent({includeMarkedContent:true,disableNormalization:true}),container:layer,viewport});
   await Promise.all([job.render.promise,job.text.render()]);
   if(generation!==this.generation)return;r.rendered=true;r.paper.dataset.ready='true';
  }finally{if(this.jobs.get(r.n)===job)this.jobs.delete(r.n);}
 }
 evict(){const current=this.position().page;for(const r of this.records){if(r.rendered&&Math.abs(r.n-current)>5&&!r.paper.contains(window.getSelection()?.anchorNode)){r.paper.querySelectorAll('canvas').forEach(c=>{c.width=0;c.height=0;});r.paper.replaceChildren();r.rendered=false;delete r.paper.dataset.ready;}}}
 jump(n,fraction=0){const r=this.records[Math.max(1,Math.min(this.records.length,Number(n)||1))-1];if(!r)return;this.scroll.scrollTop=r.slot.offsetTop+fraction*r.slot.offsetHeight;this.enqueue(r.n);this.reportPosition();}
 zoom(delta){this.fit=false;this.scale=Math.max(.35,Math.min(3,this.scale+delta));return this.reflow(true);}
 fitWidth(){this.fit=true;return this.reflow(true);}
 readSelection(){
  const sel=window.getSelection();if(!sel||sel.isCollapsed||!sel.rangeCount){this.onSelection(null);return;}
  const asElement=n=>n?.nodeType===1?n:n?.parentElement;
  const start=asElement(sel.anchorNode)?.closest('.textLayer');const end=asElement(sel.focusNode)?.closest('.textLayer');
  if(!start||!end||!this.pages.contains(start)||!this.pages.contains(end)){this.onSelection(null);return;}
  const text=sel.toString().trim();if(text.length<2){this.onSelection(null);return;}
  const range=sel.getRangeAt(0);const rect=range.getBoundingClientRect();
  if(rect.bottom<100||rect.top>innerHeight){this.onSelection(null);return;}
  this.onSelection({text,page:Number(start.dataset.page),endPage:Number(end.dataset.page),rect:{left:rect.left,right:rect.right,top:rect.top,bottom:rect.bottom}});
 }
}
