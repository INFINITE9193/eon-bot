from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import json
import os
import random
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)

# ── Banco de dados ──────────────────────────────────────────
# Em produção (Railway), usa arquivo em /tmp ou variável de ambiente
# Localmente usa database.json na mesma pasta
if os.environ.get("RAILWAY_ENVIRONMENT"):
    DB_FILE = "/tmp/database.json"
else:
    DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database.json")

SHOP_ITEMS = {
    "espada":   {"price": 500,  "description": "Aumenta ganhos no trabalho em +50"},
    "escudo":   {"price": 300,  "description": "Protecao contra roubos"},
    "pocao":    {"price": 100,  "description": "Recupera energia"},
    "picareta": {"price": 800,  "description": "Aumenta ganhos na mina em +100"},
}

# ── Helpers ────────────────────────────────────────────────

def load_db():
    if not os.path.exists(DB_FILE):
        return {}
    with open(DB_FILE, "r") as f:
        return json.load(f)

def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)

def get_ip():
    if request.headers.get("X-Forwarded-For"):
        return request.headers["X-Forwarded-For"].split(",")[0].strip()
    return request.remote_addr

def get_user(db, user_id):
    if user_id not in db:
        db[user_id] = {
            "balance": 0,
            "bank": 0,
            "inventory": [],
            "last_work": None,
            "last_daily": None,
            "last_crime": None,
            "last_mine": None,
        }
    defaults = {"bank": 0, "inventory": [], "last_work": None,
                "last_daily": None, "last_crime": None, "last_mine": None}
    for k, v in defaults.items():
        db[user_id].setdefault(k, v)
    return db[user_id]

def cooldown_ok(last_time_str, minutes):
    if last_time_str is None:
        return True, None
    last = datetime.fromisoformat(last_time_str)
    diff = datetime.now() - last
    wait = timedelta(minutes=minutes)
    if diff >= wait:
        return True, None
    remaining = int((wait - diff).total_seconds())
    return False, remaining

def now_iso():
    return datetime.now().isoformat()

def fmt_time(seconds):
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}h {m}m"
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"

# ── Rotas ──────────────────────────────────────────────────

@app.route("/")
def index():
    html_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "economy.html")
    if os.path.exists(html_file):
        return send_from_directory(os.path.dirname(os.path.abspath(__file__)), "economy.html")
    return jsonify({"eon": "v2.0", "info": "Coloque economy.html na mesma pasta."})

@app.route("/me")
def me():
    ip = get_ip()
    db = load_db()
    u = get_user(db, ip)
    save_db(db)
    return jsonify({"seu_id": ip, "balance": u["balance"], "bank": u["bank"]})

@app.route("/balance")
def balance():
    ip = get_ip()
    db = load_db()
    u = get_user(db, ip)
    save_db(db)
    return jsonify({"user": ip, "balance": u["balance"], "bank": u["bank"],
                    "total": u["balance"] + u["bank"]})

@app.route("/work")
def work():
    ip = get_ip()
    db = load_db()
    u = get_user(db, ip)
    ok, remaining = cooldown_ok(u["last_work"], minutes=30)
    if not ok:
        return jsonify({"error": f"Aguarde {fmt_time(remaining)} para trabalhar novamente."}), 429
    bonus = 50 if "espada" in u["inventory"] else 0
    earned = random.randint(50, 150) + bonus
    u["balance"] += earned
    u["last_work"] = now_iso()
    save_db(db)
    return jsonify({"user": ip, "earned": earned, "balance": u["balance"]})

@app.route("/daily")
def daily():
    ip = get_ip()
    db = load_db()
    u = get_user(db, ip)
    ok, remaining = cooldown_ok(u["last_daily"], minutes=1440)
    if not ok:
        return jsonify({"error": f"Daily ja coletado. Volte em {fmt_time(remaining)}."}), 429
    reward = random.randint(200, 500)
    u["balance"] += reward
    u["last_daily"] = now_iso()
    save_db(db)
    return jsonify({"user": ip, "reward": reward, "balance": u["balance"]})

@app.route("/mine")
def mine():
    ip = get_ip()
    db = load_db()
    u = get_user(db, ip)
    ok, remaining = cooldown_ok(u["last_mine"], minutes=60)
    if not ok:
        return jsonify({"error": f"Aguarde {fmt_time(remaining)} para minerar novamente."}), 429
    bonus = 100 if "picareta" in u["inventory"] else 0
    earned = random.randint(30, 120) + bonus
    u["balance"] += earned
    u["last_mine"] = now_iso()
    save_db(db)
    return jsonify({"user": ip, "earned": earned, "balance": u["balance"]})

@app.route("/crime")
def crime():
    ip = get_ip()
    db = load_db()
    u = get_user(db, ip)
    ok, remaining = cooldown_ok(u["last_crime"], minutes=60)
    if not ok:
        return jsonify({"error": f"Aguarde {fmt_time(remaining)} para cometer um crime."}), 429
    u["last_crime"] = now_iso()
    if random.random() < 0.4:
        fine = random.randint(50, 200)
        u["balance"] = max(0, u["balance"] - fine)
        save_db(db)
        return jsonify({"user": ip, "result": "preso", "fine": fine, "balance": u["balance"]})
    earned = random.randint(100, 400)
    u["balance"] += earned
    save_db(db)
    return jsonify({"user": ip, "result": "sucesso", "earned": earned, "balance": u["balance"]})

@app.route("/rob/<victim_ip>")
def rob(victim_ip):
    robber_ip = get_ip()
    if robber_ip == victim_ip:
        return jsonify({"error": "Nao pode roubar a si mesmo."}), 400
    db = load_db()
    robber = get_user(db, robber_ip)
    victim = get_user(db, victim_ip)
    if victim["balance"] <= 0:
        return jsonify({"error": "Vitima nao tem coins."}), 400
    protected = "escudo" in victim["inventory"]
    if random.random() < (0.2 if protected else 0.4):
        stolen = random.randint(1, min(200, victim["balance"]))
        victim["balance"] -= stolen
        robber["balance"] += stolen
        save_db(db)
        return jsonify({"result": "sucesso", "stolen": stolen, "balance": robber["balance"]})
    fine = random.randint(50, 150)
    robber["balance"] = max(0, robber["balance"] - fine)
    save_db(db)
    return jsonify({"result": "falhou", "fine": fine, "balance": robber["balance"]})

@app.route("/transfer/<to_ip>/<int:amount>")
def transfer(to_ip, amount):
    from_ip = get_ip()
    if amount <= 0:
        return jsonify({"error": "Valor invalido."}), 400
    if from_ip == to_ip:
        return jsonify({"error": "Nao pode transferir para si mesmo."}), 400
    db = load_db()
    sender = get_user(db, from_ip)
    receiver = get_user(db, to_ip)
    if sender["balance"] < amount:
        return jsonify({"error": "Saldo insuficiente."}), 400
    sender["balance"] -= amount
    receiver["balance"] += amount
    save_db(db)
    return jsonify({"from": from_ip, "to": to_ip, "amount": amount,
                    "seu_saldo": sender["balance"]})

@app.route("/deposit/<int:amount>")
def deposit(amount):
    ip = get_ip()
    if amount <= 0:
        return jsonify({"error": "Valor invalido."}), 400
    db = load_db()
    u = get_user(db, ip)
    if u["balance"] < amount:
        return jsonify({"error": "Saldo insuficiente."}), 400
    u["balance"] -= amount
    u["bank"] += amount
    save_db(db)
    return jsonify({"user": ip, "deposited": amount, "balance": u["balance"], "bank": u["bank"]})

@app.route("/withdraw/<int:amount>")
def withdraw(amount):
    ip = get_ip()
    if amount <= 0:
        return jsonify({"error": "Valor invalido."}), 400
    db = load_db()
    u = get_user(db, ip)
    if u["bank"] < amount:
        return jsonify({"error": "Saldo bancario insuficiente."}), 400
    u["bank"] -= amount
    u["balance"] += amount
    save_db(db)
    return jsonify({"user": ip, "withdrawn": amount, "balance": u["balance"], "bank": u["bank"]})

@app.route("/shop")
def shop():
    return jsonify({"items": SHOP_ITEMS})

@app.route("/buy/<item>")
def buy(item):
    ip = get_ip()
    if item not in SHOP_ITEMS:
        return jsonify({"error": "Item nao encontrado.", "available": list(SHOP_ITEMS.keys())}), 404
    db = load_db()
    u = get_user(db, ip)
    price = SHOP_ITEMS[item]["price"]
    if u["balance"] < price:
        return jsonify({"error": f"Saldo insuficiente. Precisa de {price} coins."}), 400
    if item in u["inventory"]:
        return jsonify({"error": "Voce ja possui este item."}), 400
    u["balance"] -= price
    u["inventory"].append(item)
    save_db(db)
    return jsonify({"user": ip, "bought": item, "price": price, "balance": u["balance"]})

@app.route("/inventory")
def inventory():
    ip = get_ip()
    db = load_db()
    u = get_user(db, ip)
    save_db(db)
    items_detail = {i: SHOP_ITEMS[i] for i in u["inventory"] if i in SHOP_ITEMS}
    return jsonify({"user": ip, "inventory": items_detail})

@app.route("/slots/<int:bet>")
def slots(bet):
    ip = get_ip()
    if bet <= 0:
        return jsonify({"error": "Aposta invalida."}), 400
    db = load_db()
    u = get_user(db, ip)
    if u["balance"] < bet:
        return jsonify({"error": "Saldo insuficiente."}), 400
    emojis = ["cereja", "limao", "sino", "estrela", "diamante"]
    reels = [random.choice(emojis) for _ in range(3)]
    u["balance"] -= bet
    if reels[0] == reels[1] == reels[2]:
        multiplier = 10 if reels[0] == "diamante" else 5
        winnings = bet * multiplier
        u["balance"] += winnings
        result = "JACKPOT!"
    elif reels[0] == reels[1] or reels[1] == reels[2]:
        winnings = bet * 2
        u["balance"] += winnings
        result = "ganhou!"
    else:
        winnings = 0
        result = "perdeu"
    save_db(db)
    return jsonify({"reels": reels, "result": result,
                    "bet": bet, "winnings": winnings, "balance": u["balance"]})

@app.route("/leaderboard")
def leaderboard():
    db = load_db()
    ranking = []
    for uid, data in db.items():
        if not isinstance(data, dict):
            continue
        total = data.get("balance", 0) + data.get("bank", 0)
        ranking.append({"user": uid, "total": total,
                        "balance": data.get("balance", 0),
                        "bank": data.get("bank", 0)})
    ranking.sort(key=lambda x: x["total"], reverse=True)
    return jsonify({"leaderboard": ranking[:10]})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
