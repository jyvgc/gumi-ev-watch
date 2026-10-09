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
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>EV 충전소 알림</title>
<style>
*{box-sizing:border-box} body{font-family:-apple-system,'Malgun Gothic',sans-serif;
background:#0f172a;color:#fff;margin:0 auto;padding:20px;max-width:560px}
h1{font-size:22px;margin:6px 0 2px} .sub{color:#94a3b8;font-size:13px;margin-bottom:16px}
.card{background:#1e293b;border-radius:16px;padding:18px;margin-bottom:14px}
.row{display:flex;gap:8px} input{flex:1;border:0;border-radius:12px;padding:14px;font-size:16px}
button{border:0;border-radius:12px;padding:14px 18px;font-size:16px;font-weight:800;cursor:pointer}
.btn{background:#38bdf8;color:#082f49}
.st{border-top:1px solid #334155;padding:12px 0}
.st:first-child{border-top:0}
.nm{font-size:17px;font-weight:700} .ad{color:#94a3b8;font-size:12px;margin:2px 0 8px}
.chips{display:flex;gap:6px;flex-wrap:wrap;margin:6px 0}
.chip{font-size:13px;padding:4px 10px;border-radius:999px;font-weight:700}
.free{background:#14532d;color:#4ade80}.busy{background:#7f1d1d;color:#fca5a5}
.tgl{display:flex;gap:8px;margin-top:8px}
.tgl button{flex:1;padding:12px 0}
.on{background:#22c55e;color:#06240f}.off{background:#334155;color:#fff}.dim{opacity:.35}
.del{background:transparent;color:#f87171;font-size:13px;padding:6px 0}
.rs{padding:10px 0;border-top:1px solid #334155;font-size:15px}
#msg{text-align:center;min-height:22px;color:#fde68a;font-size:14px;margin-top:8px}
.meta{color:#94a3b8;font-size:12px;margin-top:8px}
a{color:#7dd3fc;font-size:13px}
</style></head><body>
<h1>🔌 EV 충전소 알림</h1>
<div class="sub">이름으로 검색 → 등록 → 각각 켜기/끄기 · 2분마다 감시</div>
<div class="card"><b>➕ 충전소 추가</b>
<div class="row" style="margin-top:10px">
<input id="q" placeholder="예: 구미시청, 옥계, 인동" onkeydown="if(event.key==='Enter')search()">
<button class="btn" onclick="search()">검색</button>
</div><div id="msg"></div><div id="results"></div>
</div>
<div class="card"><b>📋 감시 목록</b> <a href="#" onclick="refresh();return false" style="float:right">🔄 새로고침</a>
<div id="list"></div>
<div class="meta" id="meta"></div>
<div style="margin-top:10px"><a href="/test">🔔 테스트 알림 보내기</a></div>
</div>
<script>
async function search(){
 const q=document.getElementById('q').value.trim();
 if(!q){document.getElementById('msg').textContent='충전소 이름을 입력하세요';return}
 document.getElementById('msg').textContent='검색중…';
 const r=await fetch('/api/search?q='+encodeURIComponent(q)); const j=await r.json();
 document.getElementById('msg').textContent=j.stations?`검색 결과 ${j.stations.length}곳`:(j.error||'검색 실패');
 let h='';
 (j.stations||[]).forEach(s=>{
  h+=`<div class="rs"><b>${s.statNm}</b><div style="color:#94a3b8;font-size:12px">${s.addr||''} · 충전기 ${s.count}대</div>
  <button class="btn" style="margin-top:6px;padding:10px 16px" onclick="addSt('${s.statId}','${s.statNm.replace(/'/g,'')}')">+ 등록</button></div>`;});
 document.getElementById('results').innerHTML=h;
}
async function addSt(id,nm){
 const r=await fetch('/api/add',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({statId:id})});
 const j=await r.json();
 document.getElementById('msg').textContent=j.ok?`✅ ${nm} 등록됨`:(j.error||'등록 실패');
 refresh();
}
async function setWatch(id,a){
 await fetch(`/api/watch/${id}/${a}`);
 refresh();
}
async function delSt(id){
 if(!confirm('이 충전소를 목록에서 삭제할까요?'))return;
 await fetch(`/api/remove/${id}`,{method:'POST'});
 refresh();
}
async function refresh(){
 const r=await fetch('/api/state'); const j=await r.json();
 let h='';
 (j.stations||[]).forEach(s=>{
  let chips='';
  (s.chargers||[]).forEach(c=>{
   const f=c.stat=='2';
   chips+=`<span class="chip ${f?'free':'busy'}">${c.chgerId}번 ${f?'빈자리':'충전중'}</span>`;});
  h+=`<div class="st"><div class="nm">${s.watching?'🟢':'🔴'} ${s.statNm}</div>
  <div class="ad">${s.addr||''} · 마지막 확인 ${s.last_check||'-'}</div>
  <div class="chips">${chips||'상태 정보 없음'}</div>
  <div class="tgl">
  <button class="${s.watching?'on':'on dim'}" onclick="setWatch('${s.statId}','on')">켜기</button>
  <button class="${s.watching?'off dim':'off'}" onclick="setWatch('${s.statId}','off')">끄기</button>
  </div><button class="del" onclick="delSt('${s.statId}')">삭제</button></div>`;});
 document.getElementById('list').innerHTML=h||'등록된 충전소가 없습니다';
 document.getElementById('meta').textContent=j.last_error?('오류: '+j.last_error):'';
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
