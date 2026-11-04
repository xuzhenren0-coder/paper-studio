"""Isolated UI fixture; clearly labelled and never writes to the user's learning DB."""
import sys,tempfile,threading,json
from pathlib import Path
from http.server import ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server,discovery

def main():
    with tempfile.TemporaryDirectory(dir=server.ROOT/'test-results',prefix='discovery-ui-') as directory:
        server.DATA=Path(directory)
        def sample(*args):
            row={'key':'test','doi':'','title':'[UI TEST] Vehicle lateral control with model predictive control','abstract':'This is an isolated UI test abstract for vehicle lateral control. It is not a research result.','published':discovery.today().isoformat(),'date_label':'测试日期','source':'Vehicle System Dynamics','issns':['0042-3114'],'authors':'UI test fixture','landing_url':'https://www.tandfonline.com/toc/nvsd20/current','pdf_url':'','license':'','publication_kind':'正式出版候选','providers':['OpenAlex'],'citations':0,'review_status':'测试记录'}
            return [row],1
        discovery.openalex=sample;discovery.crossref=lambda *args:([],0);discovery.arxiv=lambda *args:([],0)
        def model(context,*args):return {'items':[{'id':r['id'],'title_zh':'【界面测试译文】基于模型预测控制的车辆横向控制','abstract_zh':'这是用于验证中文简介显示的隔离测试摘要，不是论文研究结论。可在此核对悬停提示、中文摘要和英文原文的展示。'} for r in context['items']]}
        server.discovery_model=model
        server.CONFIG.update(endpoint='http://127.0.0.1:1/v1',model='isolated-ui-test',key='test-only')
        server.DISCOVERY.search({'query':'vehicle lateral control'})
        server.DISCOVERY.save_topic({'query':'vehicle lateral control','name':'界面测试主题'})
        class FixtureHandler(server.Handler):
            def do_GET(self):
                if self.path in ('/','/index.html'):
                    html=(server.ROOT/'web/index.html').read_text(encoding='utf-8').replace('<body>','<body><p style="margin:0;padding:8px 20px;color:#875c23;background:#fff1d5;font-size:12px">隔离界面测试：论文记录与中文译文为测试样本，不会写入你的资料库。</p>')
                    return self.send(html.encode(),ctype='text/html; charset=utf-8')
                return super().do_GET()
        http=ThreadingHTTPServer(('127.0.0.1',8766),FixtureHandler)
        print('Isolated UI fixture on 127.0.0.1:8766',flush=True)
        try:http.serve_forever()
        except KeyboardInterrupt:pass
        finally:http.server_close()

if __name__=='__main__':main()
