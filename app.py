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
fail_count = 0      # 연속 실패 횟수 (3회 이상일 때만 화면에 오류 표시)
charger_cache = {}  # statId -> 마지막 성공 조회 결과

def fill_addr(sid, items):
    st = stations.get(sid)
    if st and items and not st.get("addr"):
        st["addr"] = items[0].get("addr", "")
        save_stations()

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

PAGE = r"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#ffffff">
<title>EV 충전소 알림</title>
<style>
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
body{margin:0 auto;max-width:560px;padding:18px 16px 60px;background:#f2f4f8;color:#111827;
font-family:-apple-system,'Pretendard','Malgun Gothic',sans-serif}
header{display:flex;justify-content:space-between;align-items:center;margin:4px 2px 14px}
h1{font-size:24px;margin:0;font-weight:800}
.ref{border:0;background:#e5e7eb;color:#374151;border-radius:999px;padding:9px 14px;font-size:14px;font-weight:700}
.hero{border-radius:22px;padding:22px 20px;margin-bottom:16px;color:#fff;transition:.3s}
.hero.ok{background:#16a34a}.hero.full{background:#475569}.hero.off{background:#9ca3af}
.hero .big{font-size:30px;font-weight:800;line-height:1.25}
.hero .small{font-size:15px;margin-top:6px;opacity:.95}
.card{background:#fff;border-radius:20px;padding:18px;margin-bottom:14px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.top{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}
.nm{font-size:20px;font-weight:800}
.ad{font-size:14px;color:#6b7280;margin-top:3px}
.sw{position:relative;width:62px;height:36px;flex:none;border:0;border-radius:999px;background:#d1d5db;transition:.2s;padding:0}
.sw::after{content:"";position:absolute;top:4px;left:4px;width:28px;height:28px;border-radius:50%;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.3);transition:.2s}
.sw.on{background:#16a34a}.sw.on::after{left:30px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:10px;margin:14px 0 10px}
.tile{border-radius:16px;padding:14px 8px;text-align:center}
.tile .n{font-size:14px;font-weight:700;opacity:.8}
.tile .t{font-size:22px;font-weight:800;margin-top:4px}
.t-free{background:#dcfce7;color:#14532d}.t-busy{background:#fee2e2;color:#7f1d1d}.t-etc{background:#e5e7eb;color:#374151}
.foot{display:flex;justify-content:space-between;align-items:center;font-size:13px;color:#6b7280}
.del{border:0;background:none;color:#dc2626;font-size:14px;font-weight:700;padding:6px 0}
.dim{opacity:.5}
.add{width:100%;border:2px dashed #9ca3af;background:transparent;color:#374151;border-radius:20px;padding:18px;font-size:18px;font-weight:800}
.box{display:none}.box.show{display:block}
.row{display:flex;gap:8px;margin-top:12px}
input{flex:1;min-width:0;border:2px solid #d1d5db;border-radius:14px;padding:14px;font-size:17px;background:#fff;color:#111}
input:focus{outline:none;border-color:#2563eb}
.go{border:0;background:#2563eb;color:#fff;border-radius:14px;padding:0 22px;font-size:17px;font-weight:800}
#msg{min-height:20px;margin-top:10px;font-size:14px;color:#b45309;font-weight:700}
.rs{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:14px 0;border-top:1px solid #e5e7eb}
.rs b{font-size:17px}.rs div div{font-size:13px;color:#6b7280;margin-top:2px}
.pl{border:0;background:#dbeafe;color:#1d4ed8;border-radius:12px;padding:11px 16px;font-size:15px;font-weight:800;flex:none}
.links{text-align:center;margin-top:18px}
.links a{color:#2563eb;font-size:15px;font-weight:700;text-decoration:none}
.err{color:#dc2626;font-size:13px;text-align:center;margin-top:10px}
.empty{text-align:center;color:#6b7280;padding:30px 0;font-size:16px}
</style></head><body>
<header><h1>🔌 EV 충전소 알림</h1><button class="ref" onclick="refresh()">🔄 새로고침</button></header>

<div class="hero off" id="hero"><div class="big">불러오는 중…</div></div>

<div id="list"></div>

<button class="add" id="addBtn" onclick="toggleAdd()">＋ 충전소 추가</button>
<div class="card box" id="addBox" style="margin-top:14px">
 <b style="font-size:17px">충전소 이름으로 검색</b>
 <div class="row">
  <input id="q" placeholder="예: 구미시청, 옥계, 인동" onkeydown="if(event.key==='Enter')search()">
  <button class="go" onclick="search()">검색</button>
 </div>
 <div id="msg"></div><div id="results"></div>
</div>

<div class="links"><a href="/test">🔔 테스트 알림 보내기</a></div>
<div class="err" id="err"></div>

<script>
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
function toggleAdd(){var b=document.getElementById('addBox');b.classList.toggle('show');if(b.classList.contains('show'))document.getElementById('q').focus()}
async function search(){
 var q=document.getElementById('q').value.trim(), m=document.getElementById('msg');
 if(!q){m.textContent='충전소 이름을 입력하세요';return}
 m.textContent='검색중… (최대 10초)';document.getElementById('results').innerHTML='';
 try{
  var j=await (await fetch('/api/search?q='+encodeURIComponent(q))).json();
  if(!j.stations){m.textContent=j.error||'검색 실패';return}
  m.textContent=j.stations.length?('검색 결과 '+j.stations.length+'곳'):'검색 결과가 없습니다';
  document.getElementById('results').innerHTML=j.stations.map(function(s){
   return '<div class="rs"><div><b>'+esc(s.statNm)+'</b><div>'+esc(s.addr)+' · 충전기 '+s.count+'대</div></div>'
   +'<button class="pl" data-id="'+esc(s.statId)+'" data-nm="'+esc(s.statNm)+'" onclick="addSt(this)">등록</button></div>'}).join('');
 }catch(e){m.textContent='검색 실패: '+e}
}
async function addSt(btn){
 var j=await (await fetch('/api/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({statId:btn.dataset.id})})).json();
 document.getElementById('msg').textContent=j.ok?('✅ '+btn.dataset.nm+' 등록됨'):(j.error||'등록 실패');
 if(j.ok){document.getElementById('results').innerHTML='';document.getElementById('q').value=''}
 refresh();
}
async function setWatch(id,on){await fetch('/api/watch/'+id+'/'+(on?'on':'off'));refresh()}
async function delSt(id){if(!confirm('이 충전소를 목록에서 삭제할까요?'))return;await fetch('/api/remove/'+id,{method:'POST'});refresh()}
async function refresh(){
 var j;try{j=await (await fetch('/api/state')).json()}catch(e){return}
 var sts=j.stations||[], free=0, watching=0, html='';
 sts.forEach(function(s){
  var f=(s.chargers||[]).filter(function(c){return c.stat=='2'}).length;
  if(s.watching){watching++;free+=f}
  var tiles=(s.chargers||[]).map(function(c){
   var cls=c.stat=='2'?'t-free':(c.stat=='3'?'t-busy':'t-etc');
   var tx=c.stat=='2'?'빈자리':(c.stat=='3'?'충전중':esc(c.stat_text));
   return '<div class="tile '+cls+'"><div class="n">'+esc(c.chgerId)+'번</div><div class="t">'+tx+'</div></div>'}).join('');
  html+='<div class="card'+(s.watching?'':' dim')+'"><div class="top"><div><div class="nm">'+esc(s.statNm)+'</div>'
   +'<div class="ad">'+esc(s.addr)+'</div></div>'
   +'<button class="sw'+(s.watching?' on':'')+'" aria-label="알림 켜기/끄기" onclick="setWatch(\''+esc(s.statId)+'\','+(!s.watching)+')"></button></div>'
   +'<div class="tiles">'+(tiles||'<div class="ad">상태 정보 없음</div>')+'</div>'
   +'<div class="foot"><span>'+(s.watching?'🔔 알림 켜짐':'🔕 알림 꺼짐')+' · 확인 '+esc((s.last_check||'-').slice(11,16))+'</span>'
   +'<button class="del" onclick="delSt(\''+esc(s.statId)+'\')">삭제</button></div></div>';
 });
 document.getElementById('list').innerHTML=html||'<div class="empty">등록된 충전소가 없습니다<br>아래 버튼으로 추가하세요</div>';
 var h=document.getElementById('hero');
 if(!watching){h.className='hero off';h.innerHTML='<div class="big">알림이 꺼져 있어요</div><div class="small">충전소 오른쪽 스위치를 켜세요</div>'}
 else if(free>0){h.className='hero ok';h.innerHTML='<div class="big">지금 빈자리 '+free+'대</div><div class="small">감시 중인 충전소 '+watching+'곳 · 바로 이용 가능</div>'}
 else{h.className='hero full';h.innerHTML='<div class="big">모두 사용 중</div><div class="small">자리가 나면 텔레그램으로 알려드려요 ('+watching+'곳 감시중)</div>'}
 document.getElementById('err').textContent=j.last_error?('오류: '+j.last_error):'';
}
refresh();setInterval(refresh,30000);
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
    raw = None
    for attempt in range(3):          # 일시적 지연 시 최대 3회 재시도
        try:
            raw = urllib.request.urlopen(url, timeout=20).read().decode("utf-8", errors="ignore")
            break
        except Exception:
            if attempt == 2:
                raise
            time.sleep(3)
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
    global last_state, last_check, last_error, fail_count
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
                fail_count = 0
                fill_addr(sid, items)
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
            fail_count += 1
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
    global last_error, fail_count
    out = []
    for sid, st in stations.items():
        chargers = []
        try:
            if SERVICE_KEY:
                items = fetch_station(sid)
                chargers = [{"chgerId": it.get("chgerId"), "stat": str(it.get("stat")),
                             "stat_text": STAT_TEXT.get(str(it.get("stat")), "?")}
                            for it in sorted(items, key=lambda x: x.get("chgerId", ""))]
            charger_cache[sid] = chargers
            fail_count = 0
            last_error = None
            if chargers:
                fill_addr(sid, items)
        except Exception as e:
            fail_count += 1
            last_error = str(e)[:300]
            chargers = charger_cache.get(sid, [])   # 실패 시 직전 성공값 표시
        out.append({"statId": sid, "statNm": st.get("statNm"),
                    "addr": st.get("addr"), "watching": st.get("watching"),
                    "last_check": last_check.get(sid), "chargers": chargers})
    return jsonify({"ok": True, "stations": out, "last_error": last_error if fail_count >= 3 else None})

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
