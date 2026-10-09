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
                        # 충전중(3) -> 충전가능(2) : 빈자리 발생!
                        if prev == "3" and stat == "2":
                            avail = sum(1 for s in cur.values() if s == "2")
                            send_telegram(
                                f"🔌 구미대 충전소 빈자리 발생!\n"
                                f"{cid}번 충전기 충전 종료 → 현재 빈자리 {avail}대\n"
                                f"{last_check}\n빨리 이동하세요!")
                        # 충전가능 -> 충전중 : 누군가 시작
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
    return jsonify({"ok": True, "station": "구미시 구미대학교 (PI645280)",
                    "watching": watching, "last_check": last_check,
                    "last_state": last_state, "last_error": last_error})

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
    return jsonify({"watching": watching})

@app.route("/test")
def test():
    ok = send_telegram("🔔 구미대 충전소 알림 테스트입니다. 이 메시지가 오면 연결 성공!")
    return jsonify({"sent": ok})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "10000")))
