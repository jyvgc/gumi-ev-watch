import os, time, threading, urllib.parse, urllib.request, json
from datetime import datetime
from flask import Flask, request, jsonify

SERVICE_KEY = os.environ.get("EV_API_KEY", "").strip()
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

STAT_ID = os.environ.get("STAT_ID", "PI645280")  # 구미시 구미대학교 (GS차지비)
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "120"))  # 초

STAT_TEXT = {"1": "통신이상", "2": "충전가능", "3": "충전중",
             "4": "운영중지", "5": "점검중", "9": "상태미확인"}

app = Flask(__name__)
watching = True
last_state = {}   # chgerId -> stat
last_check = None
last_error = None

PAGE = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>구미대 충전소 알림</title>
<style>
*{box-sizing:border-box} body{font-family:-apple-system,'Malgun Gothic',sans-serif;
background:#0f172a;color:#fff;margin:0;padding:20px;max-width:520px;margin:0 auto}
h1{font-size:22px;margin:6px 0 2px} .sub{color:#94a3b8;font-size:13px;margin-bottom:16px}
.card{background:#1e293b;border-radius:16px;padding:18px;margin-bottom:14px}
.big{font-size:44px;font-weight:800;margin:4px 0}
.on{color:#4ade80}.off{color:#f87171}
.row{display:flex;gap:10px}
button{flex:1;border:0;border-radius:14px;padding:18px 0;font-size:19px;font-weight:800;cursor:pointer}
#btnOn{background:#22c55e;color:#06240f} #btnOn.dim{opacity:.35}
#btnOff{background:#334155;color:#fff} #btnOff.dim{opacity:.35}
.chg{display:flex;justify-content:space-between;padding:10px 0;border-top:1px solid #334155;font-size:16px}
.badge{padding:4px 12px;border-radius:999px;font-size:14px;font-weight:700}
.free{background:#14532d;color:#4ade80}.busy{background:#7f1d1d;color:#fca5a5}
.meta{color:#94a3b8;font-size:12px;margin-top:10px}
a{color:#7dd3fc;font-size:13px}
#msg{text-align:center;min-height:22px;color:#fde68a;font-size:14px;margin-top:8px}
</style></head><body>
<h1>🔌 구미대 충전소 알림</h1>
<div class="sub">구미시 구미대학교 (GS차지비) · 2분마다 감시</div>
<div class="card" style="text-align:center">
<div id="state" class="big">확인중…</div>
<div id="avail" style="color:#cbd5e1"></div>
</div>
<div class="card">
<div class="row">
<button id="btnOn" onclick="setWatch('on')">🟢 켜기</button>
<button id="btnOff" onclick="setWatch('off')">🔴 끄기</button>
</div>
<div id="msg"></div>
</div>
<div class="card"><b>충전기 상태</b><div id="list"></div>
<div class="meta" id="meta"></div>
<div style="margin-top:10px"><a href="#" onclick="refresh();return false">🔄 새로고침</a>
&nbsp;·&nbsp;<a href="/test">🔔 테스트 알림 보내기</a></div>
</div>
<script>
async function refresh(){
 const r=await fetch('/api/state'); const j=await r.json();
 const st=document.getElementById('state'), av=document.getElementById('avail');
 if(j.watching){st.innerHTML='<span class="on">● 감시중</span>'}else{st.innerHTML='<span class="off">● 꺼짐</span>'}
 document.getElementById('btnOn').className=j.watching?'':'dim';
 document.getElementById('btnOff').className=j.watching?'dim':'';
 let free=0,html='';
 (j.chargers||[]).forEach(c=>{
   const isFree=c.stat=='2'; if(isFree)free++;
   html+=`<div class="chg"><span>${c.chgerId}번 충전기</span>
   <span class="badge ${isFree?'free':'busy'}">${c.stat_text}</span></div>`;});
 document.getElementById('list').innerHTML=html||'정보 없음';
 av.textContent=`빈자리 ${free}대 / 전체 ${(j.chargers||[]).length}대`;
 document.getElementById('meta').textContent=
  `마지막 확인: ${j.last_check||'-'}`+(j.last_error?` · 오류: ${j.last_error}`:'');
}
async function setWatch(a){
 const r=await fetch('/watch/'+a); const j=await r.json();
 document.getElementById('msg').textContent=j.watching?'✅ 감시 켜짐 — 빈자리 생기면 텔레그램 알림':'⏸️ 감시 꺼짐 — 알림 오지 않음';
 refresh();
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

def fetch_station():
    base = "http://apis.data.go.kr/B552584/EvCharger/getChargerInfo"
    params = {"serviceKey": SERVICE_KEY, "numOfRows": "50", "pageNo": "1",
              "dataType": "JSON", "statId": STAT_ID}
    url = base + "?" + urllib.parse.urlencode(params)
    raw = urllib.request.urlopen(url, timeout=30).read().decode("utf-8", errors="ignore")
    d = json.loads(raw)
    items = d.get("items", {}).get("item", [])
    if isinstance(items, dict):
        items = [items]
    return items

def summarize(items):
    lines = []
    for it in sorted(items, key=lambda x: x.get("chgerId", "")):
        cid = it.get("chgerId", "?")
        stat = str(it.get("stat", "?"))
        upd = it.get("statUpdDt", "")
        lines.append(f"{cid}번: {STAT_TEXT.get(stat, stat)} (갱신 {upd})")
    return lines

def watcher():
    global last_state, last_check, last_error
    print(f"watcher start: {STAT_ID}, every {CHECK_INTERVAL}s", flush=True)
    first = True
    while True:
        try:
            if watching and SERVICE_KEY:
                items = fetch_station()
                cur = {it.get("chgerId"): str(it.get("stat")) for it in items}
                last_check = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                last_error = None
                if first:
                    last_state = cur
                    first = False
                    avail = sum(1 for s in cur.values() if s == "2")
                    send_telegram(f"🔌 구미대 충전소 감시 시작\n현재 빈자리 {avail}대 / 전체 {len(cur)}대\n" + "\n".join(summarize(items)))
                else:
                    for cid, stat in cur.items():
                        prev = last_state.get(cid)
                        if prev == "3" and stat == "2":
                            avail = sum(1 for s in cur.values() if s == "2")
                            send_telegram(
                                f"🔌 구미대 충전소 빈자리 발생!\n"
                                f"{cid}번 충전기 충전 종료 → 현재 빈자리 {avail}대\n"
                                f"{last_check}\n빨리 이동하세요!")
                        elif prev == "2" and stat == "3":
                            avail = sum(1 for s in cur.values() if s == "2")
                            if avail == 0:
                                send_telegram(f"⚠️ 구미대 충전소 만차됨\n{cid}번 충전 시작 ({last_check})")
                    last_state = cur
        except Exception as e:
            last_error = str(e)[:300]
            print("watch error:", e, flush=True)
        time.sleep(CHECK_INTERVAL)

threading.Thread(target=watcher, daemon=True).start()

@app.route("/")
def index():
    return PAGE

@app.route("/api/state")
def api_state():
    try:
        items = fetch_station() if SERVICE_KEY else []
        chargers = [{"chgerId": it.get("chgerId"), "stat": str(it.get("stat")),
                     "stat_text": STAT_TEXT.get(str(it.get("stat")), "?"),
                     "statUpdDt": it.get("statUpdDt")} for it in items]
    except Exception as e:
        chargers = []
        global last_error
        last_error = str(e)[:300]
    return jsonify({"ok": True, "station": "구미시 구미대학교 (PI645280)",
                    "watching": watching, "last_check": last_check,
                    "chargers": chargers, "last_error": last_error})

@app.route("/status")
def status():
    try:
        items = fetch_station()
        return jsonify({"ok": True, "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "chargers": [{"chgerId": it.get("chgerId"),
                                      "stat": it.get("stat"),
                                      "stat_text": STAT_TEXT.get(str(it.get("stat")), "?"),
                                      "statUpdDt": it.get("statUpdDt"),
                                      "output": it.get("output")} for it in items]})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:300]}), 500

@app.route("/watch/<action>", methods=["GET"])
def watch(action):
    global watching
    if action == "on":
        watching = True
    elif action == "off":
        watching = False
    # 텔레그램 켜기/끄기 명령과 연동 시 이 메시지를 활용
    return jsonify({"watching": watching})

@app.route("/test")
def test():
    ok = send_telegram("🔔 구미대 충전소 알림 테스트입니다. 이 메시지가 오면 연결 성공!")
    return jsonify({"sent": ok})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "10000")))
