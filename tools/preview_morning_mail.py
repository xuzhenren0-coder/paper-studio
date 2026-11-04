"""Generate an original labelled preview; never opens a mail provider connection."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mailing.core import render
from mailing.demo import sample

root=Path(__file__).resolve().parents[1];target=root/'test-results/morning-preview';target.mkdir(parents=True,exist_ok=True)
message=render(sample(),'同学','https://example.org/demo-unsubscribe',preview=True)
(target/'morning.html').write_text(message['html'],encoding='utf-8')
(target/'morning.txt').write_text(message['text'],encoding='utf-8')
print('Created labelled local preview; no email sent: '+str(target))
