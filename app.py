import os, time, threading, urllib.parse, urllib.request, json
from datetime import datetime
from flask import Flask, request, jsonify

SERVICE_KEY = os.environ.get("EV_API_KEY", "").strip()
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
DEFAULT_STAT_ID = os.environ.get("STAT_ID", "PI645280")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "120"))
DATA_FILE = os.path.join(os.path.dirname(__file__), "stations.json")

STAT_TEXT = {"1": "통신이상", "2": "충전가능", "3": "충전중",
             "4": "운영중지", "5": "점검중", "9": "상태미확인"}

app = Flask(__name__)
stations = {}      # statId -> {statNm, addr, watching}
last_state = {}    # statId -> {chgerId: stat}
last_check = {}    # statId -> str
last_error = None

def save_stations():
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(stations, f, ensure_ascii=False)
    except Exception as e:
        print("save error:", e)

def load_stations():
    global stations
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, encoding="utf-8") as f:
                stations = json.load(f)
    except Exception as e:
        print("load error:", e)
    if not stations and DEFAULT_STAT_ID:
        stations[DEFAULT_STAT_ID] = {"statNm": "구미시 구미대학교", "addr": "", "watching": True}
        save_stations()

load_stations()

PAGE = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="theme-color" content="#F2F2F7">
<title>충전소</title>
<style>
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
body{font-family:-apple-system,BlinkMacSystemFont,'SF Pro Text','Apple SD Gothic Neo','Malgun Gothic',sans-serif;background:#F2F2F7;color:#1C1C1E;margin:0 auto;max-width:560px;padding:18px 18px 110px}
.date{font-size:13px;font-weight:600;color:#8E8E93;margin-top:8px}
h1{font-size:34px;font-weight:800;margin:2px 0 16px;letter-spacing:-.5px}
.hero{border-radius:24px;color:#fff;padding:22px 22px 0;margin-bottom:26px;overflow:hidden;box-shadow:0 10px 28px rgba(0,0,0,.14);background:linear-gradient(135deg,#34C759,#0A9E88)}
.hero.none{background:linear-gradient(135deg,#8E8E93,#636366)}
.hero .lb{font-size:12px;font-weight:700;opacity:.85;letter-spacing:.5px}
.hero .tt{font-size:30px;font-weight:800;margin:6px 0 2px;line-height:1.15}
.hero .ss{font-size:16px;opacity:.92;margin-bottom:60px}
.hero .bar{margin:0 -22px;padding:14px 22px;background:rgba(255,255,255,.22);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);display:flex;align-items:center;gap:12px}
.hero .ic{width:42px;height:42px;border-radius:10px;background:#fff;display:flex;align-items:center;justify-content:center;font-size:22px}
.hero .bt{flex:1;font-size:14px;font-weight:600;line-height:1.3}
.pill{border:0;border-radius:999px;padding:9px 20px;font-size:15px;font-weight:800;cursor:pointer;background:#fff;color:#007AFF}
.pill.off{background:#E5E5EA;color:#636366}.pill.on{background:#E3F0FF;color:#007AFF}
.sec{display:flex;justify-content:space-between;align-items:baseline;margin:0 4px 10px}
.sec b{font-size:22px;font-weight:800}.sec a{color:#007AFF;font-size:16px;text-decoration:none}
.group{background:#fff;border-radius:20px;padding:4px 16px;margin-bottom:22px;box-shadow:0 1px 3px rgba(0,0,0,.05)}
.item{padding:14px 0;border-top:1px solid #E5E5EA}.item:first-child{border-top:0}
.top{display:flex;align-items:center;gap:13px}
.icon{width:56px;height:56px;border-radius:14px;background:linear-gradient(135deg,#0A84FF,#5E5CE6);color:#fff;font-size:28px;display:flex;align-items:center;justify-content:center;flex:none}
.icon.g{background:linear-gradient(135deg,#34C759,#0A9E88)}
.info{flex:1;min-width:0}.nm{font-size:17px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ad{font-size:13px;color:#8E8E93;margin-top:2px}
.chips{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0 0 69px}
.chip{font-size:13px;font-weight:700;padding:5px 11px;border-radius:999px}
.free{background:#DFF7E5;color:#1E8E3E}.busy{background:#FFE9D9;color:#C2410C}.etc{background:#E5E5EA;color:#636366}
.del{background:none;border:0;color:#FF3B30;font-size:13px;margin:6px 0 0 69px;padding:4px 0;cursor:pointer}
.search{display:flex;gap:8px;margin-bottom:10px}
.search input{flex:1;border:0;border-radius:14px;background:#E3E3E8;padding:14px 16px;font-size:17px;outline:none}
.search button{border:0;border-radius:14px;background:#007AFF;color:#fff;font-size:16px;font-weight:700;padding:0 20px;cursor:pointer}
#msg{color:#8E8E93;font-size:14px;min-height:20px;margin:0 4px 10px}
.big{display:block;width:100%;border:0;border-radius:16px;background:#fff;color:#007AFF;font-size:17px;font-weight:700;padding:16px;margin-bottom:12px;cursor:pointer;box-shadow:0 1px 3px rgba(0,0,0,.05)}
.empty{padding:22px 0;text-align:center;color:#8E8E93}
.meta{color:#FF3B30;font-size:12px;margin:0 4px}
.tabs{position:fixed;left:0;right:0;bottom:0;display:flex;justify-content:center;background:rgba(249,249,249,.85);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);border-top:1px solid rgba(0,0,0,.1);padding:8px 0 calc(8px + env(safe-area-inset-bottom))}
.tabs div{width:560px;max-width:100%;display:flex}
.tab{flex:1;text-align:center;font-size:11px;font-weight:600;color:#8E8E93;cursor:pointer}
.tab span{display:block;font-size:24px;margin-bottom:1px}.tab.act{color:#007AFF}
.page{display:none}.page.act{display:block}
</style></head><body>
<div id="p0" class="page act">
 <div class="date" id="date"></div><h1>충전소</h1>
 <div id="hero"></div>
 <div class="sec"><b>감시 목록</b><a href="#" onclick="refresh();return false">새로고침</a></div>
 <div class="group" id="list"></div>
 <div class="meta" id="meta"></div>
</div>
<div id="p1" class="page">
 <h1 style="margin-top:14px">검색</h1>
 <div class="search"><input id="q" placeholder="충전소 검색 (예: 구미시청, 옥계, 인동)" onkeydown="if(event.key==='Enter')search()"><button onclick="search()">검색</button></div>
 <div id="msg"></div><div class="group" id="results" style="display:none"></div>
</div>
<div id="p2" class="page">
 <h1 style="margin-top:14px">설정</h1>
 <button class="big" onclick="testNoti()">🔔 테스트 알림 보내기</button>
 <div id="tmsg" class="meta" style="color:#8E8E93"></div>
 <div class="ad" style="margin:14px 4px">2분마다 충전소 상태를 확인하고, 빈자리가 생기면 텔레그램으로 알려드립니다.</div>
</div>
<div class="tabs"><div>
 <div class="tab act" onclick="tab(0)"><span>⚡</span>오늘</div>
 <div class="tab" onclick="tab(1)"><span>🔍</span>검색</div>
 <div class="tab" onclick="tab(2)"><span>⚙️</span>설정</div>
</div></div>
<script>
const $=id=>document.getElementById(id);
function tab(n){document.querySelectorAll('.page').forEach((p,i)=>p.classList.toggle('act',i==n));
 document.querySelectorAll('.tab').forEach((t,i)=>t.classList.toggle('act',i==n));window.scrollTo(0,0)}
$('date').textContent=new Date().toLocaleDateString('ko-KR',{month:'long',day:'numeric',weekday:'long'});
async function search(){
 const q=$('q').value.trim();
 if(!q){$('msg').textContent='충전소 이름을 입력하세요';return}
 $('msg').textContent='검색중…';
 const r=await fetch('/api/search?q='+encodeURIComponent(q)); const j=await r.json();
 $('msg').textContent=j.stations?`검색 결과 ${j.stations.length}곳`:(j.error||'검색 실패');
 let h='';
 (j.stations||[]).forEach(s=>{
  h+=`<div class="item"><div class="top"><div class="icon">⚡</div><div class="info"><div class="nm">${s.statNm}</div><div class="ad">${s.addr||''} · 충전기 ${s.count}대</div></div>
  <button class="pill on" onclick="addSt('${s.statId}','${(s.statNm||'').replace(/'/g,'')}')">등록</button></div></div>`;});
 $('results').innerHTML=h;$('results').style.display=h?'block':'none';
}
async function addSt(id,nm){
 const r=await fetch('/api/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({statId:id})});
 const j=await r.json();
 $('msg').textContent=j.ok?`✅ ${nm} 등록됨`:(j.error||'등록 실패');
 refresh();
}
async function setWatch(id,a){await fetch(`/api/watch/${id}/${a}`);refresh()}
async function delSt(id){if(!confirm('이 충전소를 목록에서 삭제할까요?'))return;
 await fetch(`/api/remove/${id}`,{method:'POST'});refresh()}
async function testNoti(){$('tmsg').textContent='전송중…';
 try{const j=await (await fetch('/test')).json();$('tmsg').textContent=j.sent?'✅ 텔레그램으로 전송했습니다':'전송 실패'}catch(e){$('tmsg').textContent='전송 실패'}}
async function refresh(){
 const r=await fetch('/api/state'); const j=await r.json();
 const sts=j.stations||[]; let h='';
 sts.forEach(s=>{
  let chips=''; const ch=s.chargers||[];
  ch.forEach(c=>{const f=c.stat=='2',b=c.stat=='3';
   chips+=`<span class="chip ${f?'free':b?'busy':'etc'}">${c.chgerId}번 ${f?'충전가능':b?'충전중':c.stat_text}</span>`});
  const free=ch.filter(c=>c.stat=='2').length;
  h+=`<div class="item"><div class="top"><div class="icon ${free?'g':''}">⚡</div>
  <div class="info"><div class="nm">${s.statNm}</div><div class="ad">${s.addr||''} · 확인 ${(s.last_check||'-').slice(11,16)||'-'}</div></div>
  <button class="pill ${s.watching?'on':'off'}" onclick="setWatch('${s.statId}','${s.watching?'off':'on'}')">${s.watching?'켜짐':'꺼짐'}</button></div>
  <div class="chips">${chips||'<span class="chip etc">상태 정보 없음</span>'}</div>
  <button class="del" onclick="delSt('${s.statId}')">삭제</button></div>`;});
 $('list').innerHTML=h||'<div class="empty">등록된 충전소가 없습니다<br>검색 탭에서 추가하세요</div>';
 const m=sts.find(s=>s.watching)||sts[0];
 if(m){const ch=m.chargers||[];const free=ch.filter(c=>c.stat=='2').length;
  $('hero').innerHTML=`<div class="hero ${free?'':'none'}"><div class="lb">${free?'지금 빈자리':'현재 만차'}</div>
  <div class="tt">${m.statNm}</div><div class="ss">빈자리 ${free}대 · 전체 ${ch.length}대</div>
  <div class="bar"><div class="ic">⚡</div><div class="bt">${m.watching?'2분마다 감시 중':'감시 꺼짐'}</div>
  <button class="pill" onclick="setWatch('${m.statId}','${m.watching?'off':'on'}')">${m.watching?'알림 켜짐':'알림 꺼짐'}</button></div></div>`;
 }else $('hero').innerHTML='';
 $('meta').textContent=j.last_error?('오류: '+j.last_error):'';
}
refresh(); setInterval(refresh,30000);
</script></body></html>"""

def send_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[telegram skipped]", text)
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": TELEGRAM_CHAT_ID, "text": text}).encode()
        req = urllib.request.Request(url, data=data)
        urllib.request.urlopen(req, timeout=15).read()
        return True
    except Exception as e:
        print("telegram error:", e)
        return False

def api_call(params):
    base = "http://apis.data.go.kr/B552584/EvCharger/getChargerInfo"
    p = {"serviceKey": SERVICE_KEY, "pageNo": "1", "dataType": "JSON"}
    p.update(params)
    url = base + "?" + urllib.parse.urlencode(p)
    raw = urllib.request.urlopen(url, timeout=30).read().decode("utf-8", errors="ignore")
    d = json.loads(raw)
    items = d.get("items", {}).get("item", [])
    if isinstance(items, dict):
        items = [items]
    return items

def fetch_station(stat_id):
    return api_call({"numOfRows": "50", "statId": stat_id})

def search_stations(keyword):
    # 1) statNm 조건 검색 시도
    items = []
    try:
        items = api_call({"numOfRows": "200", "statNm": keyword})
        f = [it for it in items if keyword in it.get("statNm", "")]
        if f:
            items = f
    except Exception:
        pass
    # 2) 조건 검색이 안 먹으면 경북(47) 전체에서 필터 (구미 위주)
    if not items or not any(keyword in it.get("statNm", "") for it in items):
        try:
            items = api_call({"numOfRows": "9999", "zcode": "47"})
            items = [it for it in items if keyword in it.get("statNm", "")
                     or keyword in it.get("addr", "")]
        except Exception:
            pass
    # 충전소 단위로 묶기
    grouped = {}
    for it in items:
        sid = it.get("statId")
        if sid not in grouped:
            grouped[sid] = {"statId": sid, "statNm": it.get("statNm"),
                            "addr": it.get("addr"), "count": 0}
        grouped[sid]["count"] += 1
    return list(grouped.values())[:20]

def watcher():
    global last_state, last_check, last_error
    print(f"watcher start, every {CHECK_INTERVAL}s", flush=True)
    first = {}
    while True:
        try:
            for sid, st in list(stations.items()):
                if not st.get("watching"):
                    continue
                if not SERVICE_KEY:
                    continue
                items = fetch_station(sid)
                cur = {it.get("chgerId"): str(it.get("stat")) for it in items}
                last_check[sid] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                last_error = None
                if sid not in first:
                    first[sid] = True
                if first[sid]:
                    last_state[sid] = cur
                    first[sid] = False
                    avail = sum(1 for s in cur.values() if s == "2")
                    send_telegram(f"🔌 {st.get('statNm')} 감시 시작\n현재 빈자리 {avail}대 / 전체 {len(cur)}대")
                else:
                    prev = last_state.get(sid, {})
                    for cid, stat in cur.items():
                        p = prev.get(cid)
                        if p == "3" and stat == "2":
                            avail = sum(1 for s in cur.values() if s == "2")
                            send_telegram(
                                f"🔌 {st.get('statNm')} 빈자리 발생!\n"
                                f"{cid}번 충전기 충전 종료 → 현재 빈자리 {avail}대\n"
                                f"{last_check[sid]}\n빨리 이동하세요!")
                        elif p == "2" and stat == "3":
                            avail = sum(1 for s in cur.values() if s == "2")
                            if avail == 0:
                                send_telegram(f"⚠️ {st.get('statNm')} 만차됨\n{cid}번 충전 시작 ({last_check[sid]})")
                    last_state[sid] = cur
        except Exception as e:
            last_error = str(e)[:300]
            print("watch error:", e, flush=True)
        time.sleep(CHECK_INTERVAL)

threading.Thread(target=watcher, daemon=True).start()

@app.route("/")
def index():
    return PAGE

@app.route("/api/search")
def api_search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"ok": False, "error": "검색어를 입력하세요"}), 400
    try:
        return jsonify({"ok": True, "stations": search_stations(q)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:200]}), 500

@app.route("/api/add", methods=["POST"])
def api_add():
    d = request.get_json(force=True)
    sid = (d.get("statId") or "").strip()
    if not sid:
        return jsonify({"ok": False, "error": "statId 없음"}), 400
    try:
        items = fetch_station(sid)
        if not items:
            return jsonify({"ok": False, "error": "해당 ID의 충전소를 찾을 수 없습니다"}), 404
        stations[sid] = {"statNm": items[0].get("statNm", sid),
                         "addr": items[0].get("addr", ""),
                         "watching": True}
        save_stations()
        # 즉시 현재 상태 통보
        cur = {it.get("chgerId"): str(it.get("stat")) for it in items}
        last_state[sid] = cur
        avail = sum(1 for s in cur.values() if s == "2")
        send_telegram(f"🔌 {stations[sid]['statNm']} 감시 시작\n현재 빈자리 {avail}대 / 전체 {len(cur)}대")
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:200]}), 500

@app.route("/api/watch/<sid>/<action>")
def api_watch(sid, action):
    if sid in stations:
        if action == "on":
            stations[sid]["watching"] = True
        elif action == "off":
            stations[sid]["watching"] = False
        save_stations()
        return jsonify({"ok": True, "watching": stations[sid]["watching"]})
    return jsonify({"ok": False}), 404

@app.route("/api/remove/<sid>", methods=["POST"])
def api_remove(sid):
    stations.pop(sid, None)
    last_state.pop(sid, None)
    last_check.pop(sid, None)
    save_stations()
    return jsonify({"ok": True})

@app.route("/api/state")
def api_state():
    out = []
    for sid, st in stations.items():
        chargers = []
        try:
            if SERVICE_KEY:
                items = fetch_station(sid)
                chargers = [{"chgerId": it.get("chgerId"), "stat": str(it.get("stat")),
                             "stat_text": STAT_TEXT.get(str(it.get("stat")), "?")}
                            for it in sorted(items, key=lambda x: x.get("chgerId", ""))]
        except Exception as e:
            global last_error
            last_error = str(e)[:300]
        out.append({"statId": sid, "statNm": st.get("statNm"),
                    "addr": st.get("addr"), "watching": st.get("watching"),
                    "last_check": last_check.get(sid), "chargers": chargers})
    return jsonify({"ok": True, "stations": out, "last_error": last_error})

# 하위호환: 예전 단일 URL
@app.route("/status")
def status():
    return api_state()

@app.route("/watch/<action>")
def watch(action):
    for sid in stations:
        if action == "on":
            stations[sid]["watching"] = True
        elif action == "off":
            stations[sid]["watching"] = False
    save_stations()
    return jsonify({"watching": action == "on"})

@app.route("/test")
def test():
    ok = send_telegram("🔔 EV 충전소 알림 테스트입니다. 이 메시지가 오면 연결 성공!")
    return jsonify({"sent": ok})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "10000")))