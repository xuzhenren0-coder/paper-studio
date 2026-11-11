// Normalized text retains original UTF-16 offsets for DOM Range highlighting.
export function indexedText(text){
 const chars=[],starts=[],ends=[];let offset=0;
 for(const char of text){for(const c of char.normalize('NFKC').toLowerCase().replaceAll('ß','ss').replaceAll('ς','σ')){if(!/\s/u.test(c)&&c!=='\u00ad'){for(let j=0;j<c.length;j++){chars.push(c[j]);starts.push(offset);ends.push(offset+char.length);}}}offset+=char.length;}
 const keep=chars.map((c,i)=>!('-‐‑'.includes(c)&&i>0&&i+1<chars.length&&/[a-z]/.test(chars[i-1])&&/[a-z]/.test(chars[i+1])));
 return {key:chars.filter((_,i)=>keep[i]).join(''),starts:starts.filter((_,i)=>keep[i]),ends:ends.filter((_,i)=>keep[i])};
}
export const textKey=text=>indexedText(text).key;
export function matchQuote(text,quote,anchor){
 const indexed=indexedText(text),q=textKey(quote);if(!q||anchor?.ambiguous)return null;
 const matches=[];for(let at=0;(at=indexed.key.indexOf(q,at))!==-1;at++)matches.push(at);
 let found=matches;
 if(anchor?.prefix||anchor?.suffix)found=found.filter(i=>(!anchor.prefix||indexed.key.slice(0,i).endsWith(anchor.prefix))&&(!anchor.suffix||indexed.key.slice(i+q.length).startsWith(anchor.suffix)));
 if(found.length!==1)return null;
 const i=found[0];return {start:indexed.starts[i],end:indexed.ends[i+q.length-1],offset:i};
}
export function selectionLocator(text,start,end){
 const before=textKey(text.slice(0,start)),selected=textKey(text.slice(start,end)),after=textKey(text.slice(end));
 return {prefix:before.slice(-80),suffix:after.slice(0,80),selected};
}
