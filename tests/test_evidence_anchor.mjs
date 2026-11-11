import test from 'node:test';
import assert from 'node:assert/strict';
import {matchQuote,textKey,selectionLocator} from '../web/evidence-anchor.js';
test('ligatures, wrapped words and original offsets',()=>{
 const text='Before efﬁcient non-\nlinear control. After';const m=matchQuote(text,'efficient nonlinear control.');
 assert.equal(text.slice(m.start,m.end),'efﬁcient non-\nlinear control.');
});
test('numbers and ranges cannot normalize into false evidence',()=>assert.equal(matchQuote('controls 1-2 vehicles','controls 12 vehicles'),null));
test('repeated source is ambiguous without context',()=>assert.equal(matchQuote('A same quote. B same quote. C','same quote.'),null));
test('verified surroundings identify the second occurrence',()=>{
 const text='A same quote. B same quote. C',start=text.lastIndexOf('same quote.'),anchor=selectionLocator(text,start,start+11);
 assert.equal(matchQuote(text,'same quote.',anchor).start,start);
});
test('stale surroundings fail safely',()=>assert.equal(matchQuote('A same quote. C','same quote.',{prefix:'wrong'}),null));
test('source-side ambiguity cannot select an arbitrary visual match',()=>assert.equal(matchQuote('one quote','quote',{ambiguous:true}),null));
test('whitespace and soft hyphens preserve UTF-16 offsets',()=>{
 const text='🚗 A soft\u00adhyphen word';const match=matchQuote(text,'A softhyphen');assert.equal(text.slice(match.start,match.end),'A soft\u00adhyphen');
});
test('normalization preserves a technical negative sign before a number',()=>assert.notEqual(textKey('error -2'),textKey('error 2')));
