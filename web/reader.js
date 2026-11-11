import * as pdfjs from '/vendor/pdf.mjs';
import {matchQuote,selectionLocator} from '/evidence-anchor.js';
pdfjs.GlobalWorkerOptions.workerSrc='/vendor/pdf.worker.mjs';

// Continuous PDF reader. Canvas uses device pixels; textLayer uses CSS coordinates.
export class PaperReader {
 constructor(scroll,pages,{onPosition,onSelection,onStatus,onOutline,onNavigation=()=>{}}){
  Object.assign(this,{scroll,pages,onPosition,onSelection,onStatus,onOutline,onNavigation});
  this.navigation=[];this.activeCitation=null;this.locateSerial=0;
  this.column = null;
  this.records=[];this.generation=0;this.scale=1;this.fit=true;this.doc=null;this.active=0;this.jobs=new Map();this.queue=[];this.working=0;
  this.observer=new IntersectionObserver(entries=>{for(const e of entries)if(e.isIntersecting)this.enqueue(Number(e.target.dataset.page));},{root:scroll,rootMargin:'900px 500px'});
  scroll.addEventListener('scroll',()=>{this.hideMenu();if(this.scrollRAF)return;this.scrollRAF=requestAnimationFrame(()=>{this.scrollRAF=null;this.reportPosition();this.evict();});},{passive:true});
  this.hideMenu=()=>this.onSelection(null);
  document.addEventListener('selectionchange',()=>{clearTimeout(this.selectionTimer);this.selectionTimer=setTimeout(()=>this.readSelection(),160);});
  this.resizeObserver=new ResizeObserver(()=>{
   clearTimeout(this.resizeTimer);
   if (!this.resizePaused) this.resizeTimer=setTimeout(()=>this.reflowIfWidthChanged(),160);
  });
  this.resizeObserver.observe(scroll);
 }
 async load(url,position={},identity=null){
  this.identity=identity;this.navigation=[];this.activeCitation=null;++this.locateSerial;this.onNavigation(false);
  ++this.generation;this.cancelJobs();this.observer.disconnect();this.queue=[];
  if(this.loading){await this.loading.destroy();this.loading=null;}
  if(this.doc){await this.doc.destroy();this.doc=null;}
  this.records=[];this.pages.replaceChildren();this.onStatus('正在打开论文…');
  this.loading=pdfjs.getDocument({url,cMapUrl:'/vendor/cmaps/',cMapPacked:true,standardFontDataUrl:'/vendor/standard_fonts/',wasmUrl:'/vendor/wasm/',iccUrl:'/vendor/iccs/'});const loading=this.loading;
  const doc=await loading.promise;if(this.loading!==loading){await doc.destroy();return;}
  this.doc=doc;this.loading=null;this.fit=position.fit!==false;this.scale=Number(position.scale)||1;
  this.column = ['left', 'right'].includes(position.column) ? position.column : null;
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
  return{page:selected.n,fraction:Math.max(0,Math.min(.99,(this.scroll.scrollTop-selected.slot.offsetTop)/selected.slot.offsetHeight)),scale:this.scale,fit:this.fit,scrollLeft:this.scroll.scrollLeft,column:this.column};
 }
 reportPosition(){if(!this.resizePaused)this.onPosition(this.position());}
 pauseResize() {
  clearTimeout(this.resizeTimer);
  this.resizePaused = true;
 }
 settleResize() {
  if (!this.resizePaused) return;
  this.resizePaused = false;
  this.reflowIfWidthChanged(true);
  this.reportPosition();
 }
 reflowIfWidthChanged(keepFrame = false) {
  const width = this.scroll.clientWidth;
  if (!this.resizePaused && this.doc && this.records.length && (this.fit || this.column) && width > 0 && Math.abs(this.lastWidth - width) > 3) {
   this.reflow(true, null, keepFrame);
  }
 }
 async reflow(preserve=true,restore=null,keepFrame=false){
  if(!this.doc)return;const position=restore||(preserve?this.position():{page:1,fraction:0});
  ++this.generation;this.cancelJobs();this.queue=[];this.observer.disconnect();this.lastWidth=this.scroll.clientWidth;
  if(this.fit)this.scale=Math.min(2,Math.max(.25,(this.scroll.clientWidth-48)/this.records[0].width));
  if (this.column) this.scale = Math.min(3, Math.max(.35, (this.scroll.clientWidth - 32) / (this.records[0].width * .46)));
  for(const r of this.records){
   const preview = keepFrame && Math.abs(r.n - position.page) <= 1 && r.paper.querySelector(r.rendered ? 'canvas' : '.page-preview');
   r.rendered=false;r.failed=false;delete r.paper.dataset.ready;
   if (preview) {
    preview.classList.add('page-preview');
    r.paper.replaceChildren(preview);
   } else r.paper.replaceChildren();
   r.paper.style.width=`${r.width*this.scale}px`;r.paper.style.height=`${r.height*this.scale}px`;r.slot.style.width=`${r.width*this.scale}px`;
   r.paper.style.setProperty('--total-scale-factor',String(this.scale));r.paper.style.setProperty('--scale-round-x','1px');r.paper.style.setProperty('--scale-round-y','1px');this.observer.observe(r.slot);}
  this.jump(position.page,position.fraction||0);this.scroll.scrollLeft=position.scrollLeft||0;this.reportPosition();
  if (this.column) this.alignColumn();
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
   const preview = r.paper.querySelector('.page-preview');
   if (preview) {
    canvas.style.visibility = 'hidden';
    layer.style.visibility = 'hidden';
    r.paper.append(canvas, layer);
   } else r.paper.replaceChildren(canvas,layer);
   job.render=page.render({canvasContext:canvas.getContext('2d'),viewport,transform:dpr===1?null:[dpr,0,0,dpr,0,0]});
   job.text=new pdfjs.TextLayer({textContentSource:page.streamTextContent({includeMarkedContent:true,disableNormalization:true}),container:layer,viewport});
   await Promise.all([job.render.promise,job.text.render()]);
   if(generation!==this.generation)return;
   if (preview) {
    preview.remove();
    canvas.style.visibility = '';
    layer.style.visibility = '';
   }
   r.rendered=true;r.paper.dataset.ready='true';
   if(this.activeCitation?.page===r.n)this.highlight(r,this.activeCitation);
  }finally{if(this.jobs.get(r.n)===job)this.jobs.delete(r.n);}
 }
 evict(){const current=this.position().page;for(const r of this.records){if(r.rendered&&Math.abs(r.n-current)>5&&!r.paper.contains(window.getSelection()?.anchorNode)){r.paper.querySelectorAll('canvas').forEach(c=>{c.width=0;c.height=0;});r.paper.replaceChildren();r.rendered=false;delete r.paper.dataset.ready;}}}
 jump(n,fraction=0){const r=this.records[Math.max(1,Math.min(this.records.length,Number(n)||1))-1];if(!r)return;this.scroll.scrollTop=r.slot.offsetTop+fraction*r.slot.offsetHeight;this.enqueue(r.n);this.reportPosition();}
 zoom(delta){this.column=null;this.fit=false;this.scale=Math.max(.35,Math.min(3,this.scale+delta));return this.reflow(true);}
 fitWidth(){this.column=null;this.fit=true;return this.reflow(true);}
 async fitColumn(side) {
  this.column = side;
  this.fit = false;
  await this.reflow(true);
 }
 alignColumn() {
  const record = this.records[this.position().page - 1];
  if (!record) return;
  const bounds = record.paper.getBoundingClientRect();
  const viewport = this.scroll.getBoundingClientRect();
  const fraction = this.column === 'right' ? .51 : .06;
  this.scroll.scrollLeft += bounds.left - viewport.left + bounds.width * fraction - 12;
  this.reportPosition();
 }
 textNodes(layer){const nodes=[];const walk=document.createTreeWalker(layer,NodeFilter.SHOW_TEXT);let node,text='';while(node=walk.nextNode()){nodes.push({node,start:text.length});text+=node.textContent;}return{nodes,text};}
 highlight(r,item){
  r.paper.querySelectorAll('.source-highlight').forEach(n=>n.remove());
  const layer=r.paper.querySelector('.textLayer');if(!layer)return null;
  const {nodes,text}=this.textNodes(layer),match=matchQuote(text,item.quote||item.text||'',item.anchor);if(!match)return null;
  const first=nodes.find(x=>x.start+x.node.length>match.start),last=[...nodes].reverse().find(x=>x.start<match.end);if(!first||!last)return null;
  const range=document.createRange();range.setStart(first.node,match.start-first.start);range.setEnd(last.node,match.end-last.start);
  const rects=[...range.getClientRects()].filter(x=>x.width>.1&&x.height>.1),base=r.paper.getBoundingClientRect();
  for(const rect of rects){const box=document.createElement('div');box.className='source-highlight';box.setAttribute('aria-hidden','true');Object.assign(box.style,{left:(rect.left-base.left)+'px',top:(rect.top-base.top)+'px',width:rect.width+'px',height:rect.height+'px'});r.paper.append(box);}
  return rects[0]||null;
 }
 async locate(item){
  const ticket=++this.locateSerial;
  for(let i=0;i<200&&this.loading;i++){if(ticket!==this.locateSerial)return null;await new Promise(resolve=>setTimeout(resolve,50));}
  if(ticket!==this.locateSerial)return null;
  const page=Number(item.page),r=this.records[page-1];if(!r)return false;
  const doc=this.doc;
  this.navigation.push(this.position());if(this.navigation.length>30)this.navigation.shift();this.onNavigation(true);
  this.pages.querySelectorAll('.source-highlight').forEach(n=>n.remove());this.activeCitation=null;this.jump(page);
  if(item.anchor?.document&&this.identity&&item.anchor.document!==this.identity)return false;
  for(let i=0;i<200&&!r.rendered&&!r.failed;i++){if(ticket!==this.locateSerial||doc!==this.doc)return null;await new Promise(resolve=>setTimeout(resolve,50));this.enqueue(page);}
  if(ticket!==this.locateSerial||doc!==this.doc)return null;
  if(!r.rendered)return false;
  this.activeCitation={...item,page};const rect=this.highlight(r,this.activeCitation);
  if(!rect){this.activeCitation=null;return false;}
  const bounds=this.scroll.getBoundingClientRect();this.scroll.scrollTop+=rect.top-bounds.top-90;
  if(rect.left<bounds.left+12||rect.right>bounds.right-12)this.scroll.scrollLeft+=rect.left-bounds.left-24;
  this.reportPosition();return true;
 }
 async returnToReading(){
  const position=this.navigation.pop();if(!position)return;
  ++this.locateSerial;this.activeCitation=null;this.pages.querySelectorAll('.source-highlight').forEach(n=>n.remove());this.onNavigation(this.navigation.length>0);
  const changed = this.fit !== position.fit || this.scale !== position.scale || this.column !== (position.column || null);
  this.column = position.column || null;
  if(changed){this.fit=position.fit;this.scale=position.scale;await this.reflow(false,position);}else{this.jump(position.page,position.fraction);this.scroll.scrollLeft=position.scrollLeft||0;this.reportPosition();}
 }
 readSelection(){
  const sel=window.getSelection();if(!sel||sel.isCollapsed||!sel.rangeCount){this.onSelection(null);return;}
  const asElement=n=>n?.nodeType===1?n:n?.parentElement;
  const start=asElement(sel.anchorNode)?.closest('.textLayer');const end=asElement(sel.focusNode)?.closest('.textLayer');
  if(!start||!end||!this.pages.contains(start)||!this.pages.contains(end)){this.onSelection(null);return;}
  const text=sel.toString().trim();if(text.length<2){this.onSelection(null);return;}
  const range=sel.getRangeAt(0);const rect=range.getBoundingClientRect();
  if(rect.bottom<100||rect.top>innerHeight){this.onSelection(null);return;}
  let locator=null;
  if(start===end){const before=document.createRange();before.selectNodeContents(start);before.setEnd(range.startContainer,range.startOffset);const through=document.createRange();through.selectNodeContents(start);through.setEnd(range.endContainer,range.endOffset);locator=selectionLocator(start.textContent,before.toString().length,through.toString().length);}
  this.onSelection({text,page:Number(start.dataset.page),endPage:Number(end.dataset.page),locator,rect:{left:rect.left,right:rect.right,top:rect.top,bottom:rect.bottom}});
 }
}
