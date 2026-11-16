
import json, time, math, threading
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
import requests
import pandas as pd
import numpy as np
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse

BASE = "https://api.toobit.com"
STATE_FILE = Path("scanner_state.json")
TIMEOUT = 12
CACHE_TTL = 240
_cache = {"at": 0, "key": None, "value": None}
_scan_lock = threading.Lock()
app = FastAPI(title="Toobit Scanner V9 Integrated", version="9.0.0")

# UI is embedded in this file; no static directory is required.
INDEX_HTML = '<!doctype html>\n<html lang="fa" dir="rtl">\n<head>\n<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">\n<title>Toobit Futures Scanner V9 Integrated</title>\n<style>\n:root{font-family:Tahoma,Arial,sans-serif;color:#e8edf5;background:#101722}\n*{box-sizing:border-box}body{margin:0;padding:16px;max-width:1250px;margin:auto}\nh1{font-size:1.45rem;margin:8px 0}.muted{color:#9eacbd;font-size:.86rem;line-height:1.8}\n.panel,.card{background:#192536;border:1px solid #2b3b50;border-radius:14px;padding:14px;margin:12px 0}\n.controls{display:grid;grid-template-columns:repeat(4,minmax(130px,1fr));gap:10px}\nlabel{font-size:.8rem;color:#b9c7d8}input{width:100%;padding:10px;margin-top:6px;border-radius:8px;border:1px solid #43546a;background:#101a28;color:white}\nbutton{padding:11px 16px;border:0;border-radius:9px;background:#2878d0;color:white;font-weight:bold;cursor:pointer;margin-top:12px}\nbutton:disabled{opacity:.5}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:9px}\n.stat{background:#101a28;border-radius:10px;padding:12px}.stat b{display:block;font-size:1.25rem;margin-top:7px}\n.tabs{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0}.tabs button{margin:0;background:#34465c}.tabs button.active{background:#2878d0}\n.cardhead{display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;font-weight:bold}\n.score{font-size:1.05rem}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px;margin-top:10px}\n.cell{background:#101a28;border-radius:8px;padding:8px;overflow-wrap:anywhere}.cell small{display:block;color:#9eacbd;margin-bottom:5px}\n.reasons{font-size:.82rem;line-height:1.8;margin-top:10px;color:#cbd6e4}\n.long{color:#51d69b}.short{color:#ff7c86}.badge{font-size:.76rem;padding:4px 8px;border-radius:8px;background:#293b50}\n.tablewrap{overflow:auto}table{border-collapse:collapse;width:100%;font-size:.78rem;white-space:nowrap}td,th{padding:8px;border-bottom:1px solid #34465c;text-align:right}\n.error{color:#ff9b9b}.hidden{display:none}\n@media(max-width:700px){body{padding:10px}.controls{grid-template-columns:repeat(2,minmax(0,1fr))}.stats{grid-template-columns:repeat(2,1fr)}h1{font-size:1.2rem}}\n</style>\n</head>\n<body>\n<h1>Toobit Futures | Pump & Dump Scanner — V9 Integrated</h1>\n<div class="muted">اسکنر پژوهشی بازار USDT-M | دو موتور مستقل کشف پامپ/دامپ و تأیید ورود | ۱h / ۱۵m / ۵m / ۱m | EMA25/50 + MACD + Volume + OI + Funding + Order Book + Bollinger</div>\n<section class="panel">\n <div class="controls">\n  <label>حداقل گردش ۲۴ ساعته (USDT)<input id="volume" type="number" min="0" step="50000" value="100000"></label>\n  <label>تعداد ارزهای پُرحجم<input id="universe" type="number" min="15" max="100" step="5" value="40"></label>\n  <label>تعداد بررسی OI و دفتر سفارش<input id="oi" type="number" min="0" max="40" step="5" value="20"></label>\n  <label>حداقل امتیاز نمایش<input id="score" type="number" min="0" max="100" step="5" value="50"></label>\n </div>\n <button id="scanBtn" onclick="scan(true)">اسکن مجدد همین حالا</button>\n <label style="display:inline-block;margin-right:12px">به\u200cروزرسانی خودکار\n <select id="refresh" style="padding:9px;border-radius:8px;background:#101a28;color:white"><option value="300000">۵ دقیقه</option><option value="600000">۱۰ دقیقه</option><option value="900000">۱۵ دقیقه</option></select></label>\n <div id="status" class="muted">آماده دریافت داده…</div>\n</section>\n<section class="panel">\n <div class="stats">\n  <div class="stat">ارزهای تحلیل\u200cشده<b id="n">—</b></div><div class="stat">نامزدهای LONG ≥ 70<b id="lc">—</b></div>\n  <div class="stat">نامزدهای SHORT ≥ 70<b id="sc">—</b></div><div class="stat">آخرین بررسی UTC<b id="last" style="font-size:.85rem">—</b></div>\n </div>\n</section>\n<div class="tabs">\n <button class="active" data-tab="long">فرصت\u200cهای LONG</button><button data-tab="short">فرصت\u200cهای SHORT</button><button data-tab="all">همه داده\u200cها</button>\n</div>\n<div id="long"></div><div id="short" class="hidden"></div><div id="all" class="hidden"></div>\n<div class="muted">امتیاز Pump/Dump برای کشف فرصت و Entry برای زمان‌بندی ورود مستقل‌اند؛ هیچ‌کدام احتمال آماری یا سیگنال قطعی نیستند. OI با snapshot قبلی برنامه مقایسه می\u200cشود و در اجرای اول ممکن است خالی باشد. نسبت Bid/Ask فقط عمق ۲۰ سطح دفتر سفارش است. اهرم پیشنهادی صرفاً سقف محافظه\u200cکارانه و حداکثر 3x است؛ سفارش واقعی ثبت نمی\u200cشود.</div>\n<script>\nlet latest=null,timer=null,active=\'long\';\nconst $=id=>document.getElementById(id);\nfunction esc(v){return String(v??\'\').replace(/[&<>"\']/g,c=>({\'&\':\'&amp;\',\'<\':\'&lt;\',\'>\':\'&gt;\',\'"\':\'&quot;\',"\'":\'&#39;\'}[c]));}\nfunction num(v,d=2){return Number.isFinite(Number(v))?Number(v).toFixed(d):\'—\'}\nfunction card(r,dir){\n const L=dir===\'LONG\', p=L?\'Long\':\'Short\', status=L?r[\'Signal status LONG\']:r[\'Signal status SHORT\'];\n const cells=[\n [\'وضعیت سیگنال\',status],[\'قیمت مبنا\',num(r.Price,8)],[\'محرک قیمت\',num(r[p+\' trigger\'],8)],\n [\'فاصله از محرک\',num(r[p+\' distance %\'])+\'%\'],[\'حد ضرر\',num(r[p+\' SL*\'],8)+\' (\'+num(r[p+\' SL %\'])+\'% زیان)\'],\n [\'اهرم پیشنهادی\',r[p+\' Leverage\']],[\'امتیاز کشف\',num(r[L?\'Pump Score\':\'Dump Score\'],0)+\'/100\'],[\'امتیاز ورود\',num(r[L?\'Entry LONG Score\':\'Entry SHORT Score\'],0)+\'/100\'],[\'روند ۱h\',r[\'1h Trend\']],[\'تغییر ۱۵ دقیقه\',num(r[\'15m %\'])+\'%\'],\n [\'RSI ۱m / ۵m\',num(r[\'1m RSI\'],1)+\' / \'+num(r[\'5m RSI\'],1)],[\'جهش حجم\',num(r[\'Vol x\'])+\'×\'],[\'تغییر OI\',num(r[\'OI Δ %\'])+\'%\']\n ];\n for(let i=1;i<=4;i++)cells.push([\'هدف TP\'+i,num(r[p+\' TP\'+i+\'*\'],8)+\' (+\'+num(r[p+\' TP\'+i+\' %\'])+\'%)\']);\n return `<article class="card"><div class="cardhead"><span>${esc(r.Symbol)}</span><span class="score ${L?\'long\':\'short\'}">${dir} · ${r[p]}/100</span></div><div class="grid">${cells.map(c=>`<div class="cell"><small>${esc(c[0])}</small>${esc(c[1])}</div>`).join(\'\')}</div><div class="reasons">دلایل: ${esc(r[p+\' reasons\']||\'هنوز تأیید کافی ثبت نشده\')}</div></article>`;\n}\nfunction render(){\n if(!latest)return;\n const rows=latest.rows||[], min=Number($(\'score\').value);\n const longs=rows.filter(r=>Math.max(r.Long??0,r[\'Pump Score\']??0)>=min).sort((a,b)=>Math.max(b.Long??0,b[\'Pump Score\']??0)-Math.max(a.Long??0,a[\'Pump Score\']??0));\n const shorts=rows.filter(r=>Math.max(r.Short??0,r[\'Dump Score\']??0)>=min).sort((a,b)=>Math.max(b.Short??0,b[\'Dump Score\']??0)-Math.max(a.Short??0,a[\'Dump Score\']??0));\n $(\'long\').innerHTML=longs.length?longs.slice(0,10).map(r=>card(r,\'LONG\')).join(\'\'):\'<div class="panel muted">در این چرخه نامزدی با این حداقل امتیاز پیدا نشد.</div>\';\n $(\'short\').innerHTML=shorts.length?shorts.slice(0,10).map(r=>card(r,\'SHORT\')).join(\'\'):\'<div class="panel muted">در این چرخه نامزدی با این حداقل امتیاز پیدا نشد.</div>\';\n const cols=[\'Symbol\',\'Price\',\'15m %\',\'1m RSI\',\'5m RSI\',\'Long\',\'Short\',\'Signal status LONG\',\'Signal status SHORT\',\'Long trigger\',\'Short trigger\',\'LONG SL*\',\'SHORT SL*\',\'LONG TP1*\',\'SHORT TP1*\',\'Vol x\',\'OI Δ %\'];\n $(\'all\').innerHTML=`<div class="panel tablewrap"><table><thead><tr>${cols.map(c=>`<th>${esc(c)}</th>`).join(\'\')}</tr></thead><tbody>${rows.map(r=>`<tr>${cols.map(c=>`<td>${esc(typeof r[c]===\'number\'?num(r[c],5):r[c])}</td>`).join(\'\')}</tr>`).join(\'\')}</tbody></table></div>`;\n}\nasync function scan(force=false){\n const btn=$(\'scanBtn\');btn.disabled=true;$(\'status\').textContent=\'در حال دریافت اطلاعات و تحلیل بازار…\';\n const q=new URLSearchParams({min_quote_volume:$(\'volume\').value,top_universe:$(\'universe\').value,oi_count:$(\'oi\').value,min_score:$(\'score\').value,force:String(force)});\n try{\n  const res=await fetch(\'/api/scan?\'+q.toString());const data=await res.json();\n  if(data.busy){$(\'status\').textContent=data.message||\'اسکن در حال اجراست\';return;}\n  if(data.error)throw new Error(data.error);\n  latest=data;$(\'n\').textContent=data.scanned??data.rows.length;$(\'lc\').textContent=data.long_candidates??0;$(\'sc\').textContent=data.short_candidates??0;\n  $(\'last\').textContent=data.last_scan_utc||\'—\';\n  $(\'status\').textContent=`بررسی ${data.universe} قرارداد | داده معتبر ${data.scanned} | خطاهای جزئی ${data.errors?.length||0}`;\n  render();\n }catch(e){$(\'status\').innerHTML=\'<span class="error">خطا: \'+esc(e.message)+\'</span>\';}\n finally{btn.disabled=false;}\n}\ndocument.querySelectorAll(\'[data-tab]\').forEach(b=>b.addEventListener(\'click\',()=>{\n active=b.dataset.tab;document.querySelectorAll(\'[data-tab]\').forEach(x=>x.classList.toggle(\'active\',x===b));\n [\'long\',\'short\',\'all\'].forEach(id=>$(id).classList.toggle(\'hidden\',id!==active));\n}));\n$(\'score\').addEventListener(\'change\',render);\nfunction schedule(){if(timer)clearInterval(timer);timer=setInterval(()=>scan(false),Number($(\'refresh\').value));}\n$(\'refresh\').addEventListener(\'change\',schedule);\nscan(false);schedule();\n</script>\n</body></html>'

session = requests.Session()
session.headers.update({"User-Agent": "ToobitResearchScanner/9.0"})

def get(path, params=None):
    r = session.get(BASE + path, params=params or {}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

def as_float(x, default=np.nan):
    try: return float(x)
    except (TypeError, ValueError): return default

def rows_from_payload(x, key=None):
    if isinstance(x, list): return x
    if isinstance(x, dict):
        if key and isinstance(x.get(key), list): return x[key]
        if isinstance(x.get("data"), list): return x["data"]
    return []

def load_state():
    try: return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception: return {}

def save_state(state):
    try: STATE_FILE.write_text(json.dumps(state), encoding="utf-8")
    except Exception: pass

def candle_frame(payload):
    cols = ["open_time","open","high","low","close","volume","close_time","quote_volume","trades","taker_buy_base","taker_buy_quote"]
    if not isinstance(payload, list) or not payload: return None
    df = pd.DataFrame(payload)
    if df.shape[1] < 6: return None
    df = df.iloc[:, :min(len(cols), df.shape[1])]
    df.columns = cols[:df.shape[1]]
    for c in ["open_time", "close_time", "open","high","low","close","volume","quote_volume","taker_buy_base","taker_buy_quote"]:
        if c in df: df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["open","high","low","close","volume"])
    if "open_time" in df.columns:
        df = df.sort_values("open_time", ascending=True, kind="stable")
        df = df.drop_duplicates(subset=["open_time"], keep="last")
    return df.reset_index(drop=True)

def rsi(s, period=14):
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1/period, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1/period, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100/(1+rs)

def analyze_candles(df):
    """Analyze only closed candles; return indicators, fresh crosses and setup clues."""
    if df is None or len(df) < 60: return None
    d = df.iloc[:-1].copy()
    if len(d) < 55: return None
    close, vol = d.close, d.volume
    ema25 = close.ewm(span=25, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    ef, es = close.ewm(span=12, adjust=False).mean(), close.ewm(span=26, adjust=False).mean()
    macd = ef-es; signal = macd.ewm(span=9, adjust=False).mean(); hist=macd-signal
    rr=rsi(close)
    rv=float(vol.iloc[-1]/max(float(vol.iloc[-21:-1].mean()),1e-12))
    mid=close.rolling(20).mean(); sd=close.rolling(20).std(ddof=0)
    width=((mid+2*sd)-(mid-2*sd))/mid.replace(0,np.nan)
    width_now=float(width.iloc[-1]); width_avg=float(width.iloc[-20:-1].mean())
    squeeze=bool(np.isfinite(width_avg) and width_now < width_avg*0.80)
    resistance=float(d.high.iloc[-21:-1].max()); support=float(d.low.iloc[-21:-1].min())
    price=float(close.iloc[-1]); e25=float(ema25.iloc[-1]); e50=float(ema50.iloc[-1])
    h0,h1=float(hist.iloc[-1]),float(hist.iloc[-2])
    m0,m1=float(macd.iloc[-1]),float(macd.iloc[-2]); s0,s1=float(signal.iloc[-1]),float(signal.iloc[-2])
    tr=pd.concat([d.high-d.low,(d.high-d.close.shift()).abs(),(d.low-d.close.shift()).abs()],axis=1).max(axis=1)
    atr=float(tr.rolling(14).mean().iloc[-1])
    candle=d.iloc[-1]; body=abs(float(candle.close-candle.open)); rng=max(float(candle.high-candle.low),1e-12)
    lower_wick=min(float(candle.open),float(candle.close))-float(candle.low)
    upper_wick=float(candle.high)-max(float(candle.open),float(candle.close))
    bull_engulf=bool(candle.close>candle.open and d.close.iloc[-2]<d.open.iloc[-2] and candle.close>=d.open.iloc[-2] and candle.open<=d.close.iloc[-2])
    bear_engulf=bool(candle.close<candle.open and d.close.iloc[-2]>d.open.iloc[-2] and candle.open>=d.close.iloc[-2] and candle.close<=d.open.iloc[-2])
    hammer=bool(lower_wick>body*1.8 and upper_wick<max(body,1e-12)*0.8 and candle.close>candle.open)
    shooting=bool(upper_wick>body*1.8 and lower_wick<max(body,1e-12)*0.8 and candle.close<candle.open)
    recent_high=float(d.high.iloc[-6:-1].max()); recent_low=float(d.low.iloc[-6:-1].min())
    pullback_long=bool(e25>e50 and float(d.low.iloc[-4:].min())<=e25+0.35*(atr if np.isfinite(atr) else price*.005) and price>e25)
    pullback_short=bool(e25<e50 and float(d.high.iloc[-4:].max())>=e25-0.35*(atr if np.isfinite(atr) else price*.005) and price<e25)
    return dict(price=price,rsi=float(rr.iloc[-1]),volume_ratio=rv,squeeze=squeeze,
      ema25=e25,ema50=e50,trend_up=e25>e50 and price>e25,trend_dn=e25<e50 and price<e25,
      ema_cross_up=float(ema25.iloc[-2])<=float(ema50.iloc[-2]) and e25>e50,
      ema_cross_dn=float(ema25.iloc[-2])>=float(ema50.iloc[-2]) and e25<e50,
      macd_up=m0>s0 and h0>h1,macd_dn=m0<s0 and h0<h1,
      macd_cross_up=m1<=s1 and m0>s0,macd_cross_dn=m1>=s1 and m0<s0,
      hist_rising=h0>h1,hist_falling=h0<h1,
      breakout_up=price>resistance,breakout_dn=price<support,
      resistance=resistance,support=support,atr=atr,
      bull_pattern=bull_engulf or hammer,bear_pattern=bear_engulf or shooting,
      candle_pattern=('Bullish Engulfing' if bull_engulf else 'Hammer' if hammer else 'Bearish Engulfing' if bear_engulf else 'Shooting Star' if shooting else '—'),
      pullback_long=pullback_long,pullback_short=pullback_short,
      ret15=(price/float(d.close.iloc[-2])-1)*100,candle_time=int(d.open_time.iloc[-1]))

def score_row(a, funding, oi_change, book_ratio):
    """Pump/dump discovery score, independent from entry confirmation."""
    long=short=0; lr=[]; sr=[]
    if a['volume_ratio']>=3: long+=15; short+=15; lr.append('جهش شدید حجم'); sr.append('جهش شدید حجم')
    elif a['volume_ratio']>=2: long+=10; short+=10; lr.append('افزایش غیرعادی حجم'); sr.append('افزایش غیرعادی حجم')
    if np.isfinite(oi_change):
        if oi_change>=1.5: long+=15; short+=15; lr.append('افزایش OI'); sr.append('افزایش OI')
        elif oi_change<=-1.5: lr.append('کاهش OI؛ احتمال بستن موقعیت‌ها'); sr.append('کاهش OI؛ احتمال بستن موقعیت‌ها')
    if a['breakout_up']: long+=20; lr.append('شکست مقاومت ۲۰ کندلی')
    if a['breakout_dn']: short+=20; sr.append('شکست حمایت ۲۰ کندلی')
    if a['macd_cross_up']: long+=12; lr.append('تقاطع تازه MACD صعودی')
    elif a['macd_up']: long+=6; lr.append('شتاب MACD صعودی')
    if a['macd_cross_dn']: short+=12; sr.append('تقاطع تازه MACD نزولی')
    elif a['macd_dn']: short+=6; sr.append('شتاب MACD نزولی')
    if a['rsi']>=52 and a['rsi']<=72: long+=8; lr.append('RSI مومنتوم صعودی')
    if a['rsi']<=48 and a['rsi']>=28: short+=8; sr.append('RSI مومنتوم نزولی')
    if a['squeeze']: long+=8; short+=8; lr.append('فشردگی بولینگر'); sr.append('فشردگی بولینگر')
    if np.isfinite(book_ratio):
        if book_ratio>=1.20: long+=10; lr.append('غلبه عمق سفارش خرید')
        elif book_ratio<=1/1.20: short+=10; sr.append('غلبه عمق سفارش فروش')
    if np.isfinite(funding):
        if funding < -0.0002: long+=7; lr.append('Funding منفی؛ احتمال فشار شورت')
        elif funding > 0.0002: short+=7; sr.append('Funding مثبت؛ احتمال فشار لانگ')
    if a['ema_cross_up']: long+=5; lr.append('تقاطع تازه EMA25/50 صعودی')
    if a['ema_cross_dn']: short+=5; sr.append('تقاطع تازه EMA25/50 نزولی')
    if a['bull_pattern']: long+=5; lr.append('الگوی کندلی صعودی: '+a['candle_pattern'])
    if a['bear_pattern']: short+=5; sr.append('الگوی کندلی نزولی: '+a['candle_pattern'])
    return min(long,100),min(short,100),lr,sr

def combine_timeframes(a1h,a15,a5,a1):
    """Entry score /100. 1h is a soft bias filter, never suppresses early pump alerts."""
    ls=ss=0; lr=[]; sr=[]
    # 1H directional score: max 20
    if a1h['trend_up']: ls+=14; lr.append('روند ۱h صعودی؛ EMA25 بالای EMA50')
    elif a1h['ema25']>a1h['ema50']: ls+=7; lr.append('چرخش اولیه ۱h صعودی')
    if a1h['macd_up']: ls+=4; lr.append('MACD یک‌ساعته صعودی')
    if a1h['rsi']>50: ls+=2
    if a1h['trend_dn']: ss+=14; sr.append('روند ۱h نزولی؛ EMA25 زیر EMA50')
    elif a1h['ema25']<a1h['ema50']: ss+=7; sr.append('چرخش اولیه ۱h نزولی')
    if a1h['macd_dn']: ss+=4; sr.append('MACD یک‌ساعته نزولی')
    if a1h['rsi']<50: ss+=2
    # 15m: max 25
    if a15['trend_up']: ls+=12; lr.append('جهت ۱۵m صعودی')
    elif a15['ema_cross_up']: ls+=8; lr.append('تقاطع تازه EMA در ۱۵m')
    if a15['macd_cross_up']: ls+=8; lr.append('تقاطع MACD در ۱۵m')
    elif a15['macd_up']: ls+=5
    if a15['trend_dn']: ss+=12; sr.append('جهت ۱۵m نزولی')
    elif a15['ema_cross_dn']: ss+=8; sr.append('تقاطع تازه EMA در ۱۵m')
    if a15['macd_cross_dn']: ss+=8; sr.append('تقاطع MACD در ۱۵m')
    elif a15['macd_dn']: ss+=5
    # 5m setup: max 35
    if a5['trend_up']: ls+=10; lr.append('چیدمان EMA صعودی در ۵m')
    if a5['ema_cross_up']: ls+=8; lr.append('تقاطع تازه EMA در ۵m')
    if a5['breakout_up']: ls+=8; lr.append('شکست مقاومت در ۵m')
    if a5['pullback_long']: ls+=5; lr.append('پولبک صعودی به EMA25')
    if a5['bull_pattern']: ls+=4; lr.append('الگوی کندلی صعودی ۵m')
    if a5['trend_dn']: ss+=10; sr.append('چیدمان EMA نزولی در ۵m')
    if a5['ema_cross_dn']: ss+=8; sr.append('تقاطع تازه EMA در ۵m')
    if a5['breakout_dn']: ss+=8; sr.append('شکست حمایت در ۵m')
    if a5['pullback_short']: ss+=5; sr.append('پولبک نزولی به EMA25')
    if a5['bear_pattern']: ss+=4; sr.append('الگوی کندلی نزولی ۵m')
    # 1m trigger: max 20; must be based on closed candle
    long_trigger=(a1['macd_cross_up'] or (a1['bull_pattern'] and a1['price']>a1['ema25']) or (a1['breakout_up'] and a1['hist_rising']))
    short_trigger=(a1['macd_cross_dn'] or (a1['bear_pattern'] and a1['price']<a1['ema25']) or (a1['breakout_dn'] and a1['hist_falling']))
    if long_trigger and (a5['trend_up'] or a5['pullback_long']): ls+=20; lr.append('تریگر بسته‌شده ۱m؛ تأیید ورود LONG')
    elif long_trigger: ls+=8; lr.append('تریگر ۱m دیده شد؛ منتظر تأیید ۵m')
    if short_trigger and (a5['trend_dn'] or a5['pullback_short']): ss+=20; sr.append('تریگر بسته‌شده ۱m؛ تأیید ورود SHORT')
    elif short_trigger: ss+=8; sr.append('تریگر ۱m دیده شد؛ منتظر تأیید ۵m')
    # Soft countertrend penalty; preserve early discovery.
    if a1h['trend_dn']: ls=max(0,ls-8); lr.append('هشدار: خلاف روند یک‌ساعته')
    if a1h['trend_up']: ss=max(0,ss-8); sr.append('هشدار: خلاف روند یک‌ساعته')
    atr5=a5['atr'] if np.isfinite(a5['atr']) and a5['atr']>0 else a5['price']*.005
    ext_l=max(0,a1['price']-a5['resistance'])/atr5
    ext_s=max(0,a5['support']-a1['price'])/atr5
    expired_l=ext_l>1.2; expired_s=ext_s>1.2
    if expired_l: ls=max(0,ls-25); lr.append('ورود دیرهنگام؛ فاصله بیش از ۱.۲ ATR')
    if expired_s: ss=max(0,ss-25); sr.append('ورود دیرهنگام؛ فاصله بیش از ۱.۲ ATR')
    status_l='ورود تأییدشده' if long_trigger and (a5['trend_up'] or a5['pullback_long']) and not expired_l else ('منتظر تأیید ورود' if ls>=35 else 'هشدار زودهنگام / بدون ورود')
    status_s='ورود تأییدشده' if short_trigger and (a5['trend_dn'] or a5['pullback_short']) and not expired_s else ('منتظر تأیید ورود' if ss>=35 else 'هشدار زودهنگام / بدون ورود')
    return min(ls,100),min(ss,100),status_l,status_s,'، '.join(lr),'، '.join(sr),a1['price'],atr5

def get_oi(symbol):
    try:
        x = get("/quote/v1/openInterest", {"symbol": symbol})
        arr = rows_from_payload(x, "openInterestList")
        return as_float(arr[0].get("size")) if arr else np.nan
    except Exception: return np.nan

def get_book_ratio(symbol):
    try:
        x = get("/quote/v1/depth", {"symbol": symbol, "limit": 20})
        bids, asks = x.get("b", []), x.get("a", [])
        bv = sum(as_float(z[0],0)*as_float(z[1],0) for z in bids)
        av = sum(as_float(z[0],0)*as_float(z[1],0) for z in asks)
        return bv/av if av > 0 else np.nan
    except Exception: return np.nan

def fetch_market(min_quote_volume, top_universe):
    info = get("/api/v1/exchangeInfo")
    contracts = [c for c in info.get("contracts", []) if c.get("status") == "TRADING"
                 and c.get("inverse") is False and c.get("symbol","").endswith("-SWAP-USDT")]
    tickers = rows_from_payload(get("/quote/v1/contract/ticker/24hr"))
    funds = rows_from_payload(get("/api/v1/futures/fundingRate"))
    tmap = {x.get("s"): x for x in tickers}
    fmap = {x.get("symbol"): as_float(x.get("rate")) for x in funds}
    valid = []
    for c in contracts:
        sym = c["symbol"]
        t = tmap.get(sym)
        if not t: continue
        qv = as_float(t.get("qv"), 0)
        if qv >= min_quote_volume:
            valid.append((sym, qv, t, fmap.get(sym, np.nan)))
    valid.sort(key=lambda x: x[1], reverse=True)
    return valid[:top_universe]

def suggest_leverage(stop_pct, score, status):
    if "منقضی" in str(status) or score < 50 or not np.isfinite(stop_pct) or stop_pct <= 0:
        return "عدم ورود / 1x حداکثر", 1
    if stop_pct >= 2.5: lev = 1
    elif stop_pct >= 1.5: lev = 2
    else: lev = 3
    if score < 70: lev = min(lev, 1)
    return f"{lev}x (محافظه‌کارانه)", lev

def clean_json(value):
    if isinstance(value, dict):
        return {str(k): clean_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean_json(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value

def run_scan(min_quote_volume=100000,top_universe=40,oi_count=20,min_score=50):
    if not _scan_lock.acquire(blocking=False): return {'busy':True,'message':'اسکن قبلی هنوز در حال اجراست.'}
    errors=[]; rows=[]
    try:
        universe=fetch_market(min_quote_volume,top_universe)
        if not universe: return {'busy':False,'error':'فهرست قراردادهای قابل اسکن خالی است؛ پاسخ API را بررسی کن.','rows':[]}
        state=load_state()
        for i,(sym,qv,ticker,funding) in enumerate(universe):
            try:
                analyses=[]
                for tf in ('1h','15m','5m','1m'):
                    raw=get('/quote/v1/klines',{'symbol':sym,'interval':tf,'limit':120})
                    analyses.append(analyze_candles(candle_frame(raw)))
                    time.sleep(0.035)
                a1h,a15,a5,a1=analyses
                if any(x is None for x in analyses):
                    errors.append(f'{sym}: داده کندل ناکافی در یکی از تایم‌فریم‌ها'); continue
                oi_delta=np.nan; book=np.nan; oi=np.nan
                if i<oi_count:
                    oi=get_oi(sym); old=state.get(sym,{}).get('oi')
                    if np.isfinite(oi) and old and float(old)>0: oi_delta=(oi/float(old)-1)*100
                    if np.isfinite(oi): state[sym]={'oi':oi,'time':time.time()}
                    book=get_book_ratio(sym); time.sleep(.08)
                pump_l,pump_s,pump_lr,pump_sr=score_row(a15,funding,oi_delta,book)
                entry_l,entry_s,lstatus,sstatus,elr,esr,entry,atr5=combine_timeframes(a1h,a15,a5,a1)
                # Separate discovery score from execution score; combined ranking does not hard-gate early alerts.
                total_l=min(100,int(round(.55*pump_l+.45*entry_l)))
                total_s=min(100,int(round(.55*pump_s+.45*entry_s)))
                atr=atr5 if np.isfinite(atr5) and atr5>0 else entry*.005
                stop_pct=1.2*atr/entry*100 if entry else np.nan
                def lev(score,status):
                    if 'دیرهنگام' in status or score<60:return 'عدم ورود / حداکثر 1x'
                    return '1x' if stop_pct>=2.5 or score<75 else ('2x' if stop_pct>=1.5 else '3x حداکثر')
                row={'Symbol':sym.replace('-SWAP-USDT','/USDT'),'Price':a1['price'],'15m %':a15['ret15'],'Long distance %':((a1['price']/a5['resistance']-1)*100) if a5['resistance'] else np.nan,'Short distance %':((a1['price']/a5['support']-1)*100) if a5['support'] else np.nan,'24h Quote Volume':qv,
                  'Pump Score':pump_l,'Dump Score':pump_s,'Entry LONG Score':entry_l,'Entry SHORT Score':entry_s,
                  'Long':total_l,'Short':total_s,'Signal status LONG':lstatus,'Signal status SHORT':sstatus,
                  'Long reasons':'؛ '.join(pump_lr+([elr] if elr else [])),'Short reasons':'؛ '.join(pump_sr+([esr] if esr else [])),
                  '1h Trend':'صعودی' if a1h['trend_up'] else 'نزولی' if a1h['trend_dn'] else 'خنثی',
                  '15m Trend':'صعودی' if a15['trend_up'] else 'نزولی' if a15['trend_dn'] else 'خنثی',
                  '1h EMA Cross':'صعودی' if a1h['ema_cross_up'] else 'نزولی' if a1h['ema_cross_dn'] else '—',
                  '15m EMA Cross':'صعودی' if a15['ema_cross_up'] else 'نزولی' if a15['ema_cross_dn'] else '—',
                  '5m EMA Cross':'صعودی' if a5['ema_cross_up'] else 'نزولی' if a5['ema_cross_dn'] else '—',
                  '1m MACD Cross':'صعودی' if a1['macd_cross_up'] else 'نزولی' if a1['macd_cross_dn'] else '—',
                  '15m MACD Cross':'صعودی' if a15['macd_cross_up'] else 'نزولی' if a15['macd_cross_dn'] else '—',
                  '5m MACD Cross':'صعودی' if a5['macd_cross_up'] else 'نزولی' if a5['macd_cross_dn'] else '—',
                  '1m RSI':a1['rsi'],'5m RSI':a5['rsi'],'15m RSI':a15['rsi'],'1h RSI':a1h['rsi'],
                  'Vol x':a15['volume_ratio'],'5m Vol x':a5['volume_ratio'],'OI Δ %':oi_delta,
                  'Funding %':funding*100 if np.isfinite(funding) else np.nan,'Bid/Ask depth':book,
                  'Bollinger Squeeze':a15['squeeze'],'5m Candle Pattern':a5['candle_pattern'],
                  '5m Pullback LONG':a5['pullback_long'],'5m Pullback SHORT':a5['pullback_short'],
                  'Long trigger':a5['resistance'],'Short trigger':a5['support'],
                  'LONG SL*':entry-1.2*atr,'LONG SL %':stop_pct,'SHORT SL*':entry+1.2*atr,'SHORT SL %':stop_pct,
                  'LONG Leverage':lev(total_l,lstatus),'SHORT Leverage':lev(total_s,sstatus),
                  'LONG TP1*':entry+1.2*atr,'LONG TP1 %':1.2*atr/entry*100,'LONG TP2*':entry+2.4*atr,'LONG TP2 %':2.4*atr/entry*100,
                  'LONG TP3*':entry+3.6*atr,'LONG TP3 %':3.6*atr/entry*100,'LONG TP4*':entry+4.8*atr,'LONG TP4 %':4.8*atr/entry*100,
                  'SHORT TP1*':entry-1.2*atr,'SHORT TP1 %':1.2*atr/entry*100,'SHORT TP2*':entry-2.4*atr,'SHORT TP2 %':2.4*atr/entry*100,
                  'SHORT TP3*':entry-3.6*atr,'SHORT TP3 %':3.6*atr/entry*100,'SHORT TP4*':entry-4.8*atr,'SHORT TP4 %':4.8*atr/entry*100,
                  'Signal candle UTC':datetime.fromtimestamp(a15['candle_time']/1000,timezone.utc).strftime('%H:%M')}
                rows.append(row)
            except Exception as e: errors.append(f'{sym}: {type(e).__name__}: {e}')
        save_state(state)
        rows.sort(key=lambda x:max(x['Pump Score'],x['Dump Score'],x['Long'],x['Short']),reverse=True)
        return {'busy':False,'rows':rows,'errors':errors[:30],'last_scan_utc':datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
          'scanned':len(rows),'universe':len(universe),'long_candidates':sum(1 for x in rows if x['Long']>=70),
          'short_candidates':sum(1 for x in rows if x['Short']>=70),'early_pump':sum(1 for x in rows if x['Pump Score']>=60),
          'early_dump':sum(1 for x in rows if x['Dump Score']>=60),'min_score':min_score}
    except requests.RequestException as e:
        return {'busy':False,'error':f'خطای اتصال به API: {e}','rows':[],'errors':errors[:30]}
    except Exception as e:
        return {'busy':False,'error':f'{type(e).__name__}: {e}','rows':[],'errors':errors[:30]}
    finally: _scan_lock.release()

@app.get("/", response_class=HTMLResponse)
def home():
    return INDEX_HTML

@app.get("/api/health")
def health():
    return {"status": "ok", "version": "9.0.0"}

@app.get("/api/scan")
def scan(min_quote_volume: int = Query(100000, ge=0), top_universe: int = Query(40, ge=15, le=100),
         oi_count: int = Query(20, ge=0, le=40), min_score: int = Query(50, ge=0, le=100),
         force: bool = False):
    key = (min_quote_volume, top_universe, oi_count, min_score)
    now = time.time()
    if not force and _cache["key"] == key and _cache["value"] is not None and now - _cache["at"] < CACHE_TTL:
        return _cache["value"]
    result = clean_json(run_scan(min_quote_volume, top_universe, oi_count, min_score))
    if not result.get("busy") and not result.get("error"):
        _cache.update({"at": now, "key": key, "value": result})
    return result
