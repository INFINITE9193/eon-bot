from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import os
import random
import hashlib
from datetime import datetime, timedelta

# PostgreSQL
try:
    import psycopg2
    import psycopg2.extras
    USE_POSTGRES = True
except ImportError:
    USE_POSTGRES = False

import json

app = Flask(__name__)
CORS(app)

DATABASE_URL = os.environ.get("DATABASE_URL")

SHOP_ITEMS = {
    "espada":   {"price": 500,  "description": "Aumenta ganhos no trabalho em +50"},
    "escudo":   {"price": 300,  "description": "Protecao contra roubos"},
    "pocao":    {"price": 100,  "description": "Recupera energia"},
    "picareta": {"price": 800,  "description": "Aumenta ganhos na mina em +100"},
}

# ── Database ───────────────────────────────────────────────

def get_conn():
    if DATABASE_URL and USE_POSTGRES:
        return psycopg2.connect(DATABASE_URL, sslmode='require')
    return None

def init_db():
    conn = get_conn()
    if conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS players (
                nick TEXT PRIMARY KEY,
                password TEXT NOT NULL,
                balance INTEGER DEFAULT 0,
                bank INTEGER DEFAULT 0,
                inventory TEXT DEFAULT '[]',
                last_work TEXT,
                last_daily TEXT,
                last_crime TEXT,
                last_mine TEXT,
                created_at TEXT DEFAULT NOW()::TEXT
            )
        """)
        conn.commit()
        cur.close()
        conn.close()
    else:
        # Fallback local JSON
        if not os.path.exists(DB_FILE):
            with open(DB_FILE, "w") as f:
                json.dump({}, f)

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database.json")

def hash_pass(password):
    return hashlib.sha256(password.encode()).hexdigest()

# ── Player helpers ─────────────────────────────────────────

def load_player(nick):
    conn = get_conn()
    if conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("SELECT * FROM players WHERE nick = %s", (nick,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            p = dict(row)
            p["inventory"] = json.loads(p["inventory"])
            return p
        return None
    else:
        db = load_json()
        return db.get(nick)

def save_player(p):
    conn = get_conn()
    nick = p["nick"]
    if conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO players (nick, password, balance, bank, inventory, last_work, last_daily, last_crime, last_mine)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (nick) DO UPDATE SET
                balance = EXCLUDED.balance,
                bank = EXCLUDED.bank,
                inventory = EXCLUDED.inventory,
                last_work = EXCLUDED.last_work,
                last_daily = EXCLUDED.last_daily,
                last_crime = EXCLUDED.last_crime,
                last_mine = EXCLUDED.last_mine
        """, (
            nick, p["password"], p["balance"], p["bank"],
            json.dumps(p["inventory"]),
            p.get("last_work"), p.get("last_daily"),
            p.get("last_crime"), p.get("last_mine")
        ))
        conn.commit()
        cur.close()
        conn.close()
    else:
        db = load_json()
        db[nick] = p
        save_json(db)

def create_player(nick, password):
    p = {
        "nick": nick,
        "password": hash_pass(password),
        "balance": 0,
        "bank": 0,
        "inventory": [],
        "last_work": None,
        "last_daily": None,
        "last_crime": None,
        "last_mine": None,
    }
    save_player(p)
    return p

def load_all_players():
    conn = get_conn()
    if conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("SELECT nick, balance, bank FROM players")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [{"nick": r["nick"], "balance": r["balance"], "bank": r["bank"]} for r in rows]
    else:
        db = load_json()
        result = []
        for nick, data in db.items():
            if isinstance(data, dict):
                result.append({"nick": nick, "balance": data.get("balance", 0), "bank": data.get("bank", 0)})
        return result

def load_json():
    if not os.path.exists(DB_FILE):
        return {}
    with open(DB_FILE, "r") as f:
        return json.load(f)

def save_json(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)

# ── Cooldown ───────────────────────────────────────────────

def cooldown_ok(last_time_str, minutes):
    if not last_time_str:
        return True, None
    try:
        last = datetime.fromisoformat(last_time_str)
    except:
        return True, None
    diff = datetime.now() - last
    wait = timedelta(minutes=minutes)
    if diff >= wait:
        return True, None
    return False, int((wait - diff).total_seconds())

def now_iso():
    return datetime.now().isoformat()

def fmt_time(seconds):
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0: return f"{h}h {m}m"
    if m > 0: return f"{m}m {s}s"
    return f"{s}s"

def auth(data):
    nick = data.get("nick", "").strip().lower()
    password = data.get("password", "")
    if not nick or not password:
        return None, jsonify({"error": "Nick e senha sao obrigatorios."}), 400
    player = load_player(nick)
    if not player:
        return None, jsonify({"error": "Jogador nao encontrado. Crie uma conta primeiro."}), 404
    if player["password"] != hash_pass(password):
        return None, jsonify({"error": "Senha incorreta."}), 401
    return player, None, None

# ── Rotas ──────────────────────────────────────────────────

@app.route("/")
def index():
    html_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "economy.html")
    if os.path.exists(html_file):
        return send_from_directory(os.path.dirname(os.path.abspath(__file__)), "economy.html")
    return jsonify({"eon": "v3.0"})

@app.route("/register", methods=["POST"])
def register():
    data = request.json or {}
    nick = data.get("nick", "").strip().lower()
    password = data.get("password", "")
    if not nick or not password:
        return jsonify({"error": "Nick e senha sao obrigatorios."}), 400
    if len(nick) < 3 or len(nick) > 20:
        return jsonify({"error": "Nick deve ter entre 3 e 20 caracteres."}), 400
    if len(password) < 4:
        return jsonify({"error": "Senha deve ter pelo menos 4 caracteres."}), 400
    if load_player(nick):
        return jsonify({"error": "Nick ja em uso. Escolha outro."}), 409
    p = create_player(nick, password)
    return jsonify({"success": True, "nick": nick, "message": f"Conta criada! Bem-vindo ao EON, {nick}!"})

@app.route("/login", methods=["POST"])
def login():
    data = request.json or {}
    player, err, code = auth(data)
    if err:
        return err, code
    return jsonify({
        "success": True, "nick": player["nick"],
        "balance": player["balance"], "bank": player["bank"],
        "total": player["balance"] + player["bank"],
        "inventory": player["inventory"]
    })

@app.route("/balance", methods=["POST"])
def balance():
    data = request.json or {}
    player, err, code = auth(data)
    if err: return err, code
    return jsonify({
        "nick": player["nick"],
        "balance": player["balance"],
        "bank": player["bank"],
        "total": player["balance"] + player["bank"]
    })

@app.route("/work", methods=["POST"])
def work():
    data = request.json or {}
    player, err, code = auth(data)
    if err: return err, code
    ok, remaining = cooldown_ok(player["last_work"], minutes=30)
    if not ok:
        return jsonify({"error": f"Aguarde {fmt_time(remaining)} para trabalhar novamente."}), 429
    bonus = 50 if "espada" in player["inventory"] else 0
    earned = random.randint(50, 150) + bonus
    player["balance"] += earned
    player["last_work"] = now_iso()
    save_player(player)
    return jsonify({"nick": player["nick"], "earned": earned, "balance": player["balance"]})

@app.route("/daily", methods=["POST"])
def daily():
    data = request.json or {}
    player, err, code = auth(data)
    if err: return err, code
    ok, remaining = cooldown_ok(player["last_daily"], minutes=1440)
    if not ok:
        return jsonify({"error": f"Daily ja coletado. Volte em {fmt_time(remaining)}."}), 429
    reward = random.randint(200, 500)
    player["balance"] += reward
    player["last_daily"] = now_iso()
    save_player(player)
    return jsonify({"nick": player["nick"], "reward": reward, "balance": player["balance"]})

@app.route("/mine", methods=["POST"])
def mine():
    data = request.json or {}
    player, err, code = auth(data)
    if err: return err, code
    ok, remaining = cooldown_ok(player["last_mine"], minutes=60)
    if not ok:
        return jsonify({"error": f"Aguarde {fmt_time(remaining)} para minerar novamente."}), 429
    bonus = 100 if "picareta" in player["inventory"] else 0
    earned = random.randint(30, 120) + bonus
    player["balance"] += earned
    player["last_mine"] = now_iso()
    save_player(player)
    return jsonify({"nick": player["nick"], "earned": earned, "balance": player["balance"]})

@app.route("/crime", methods=["POST"])
def crime():
    data = request.json or {}
    player, err, code = auth(data)
    if err: return err, code
    ok, remaining = cooldown_ok(player["last_crime"], minutes=60)
    if not ok:
        return jsonify({"error": f"Aguarde {fmt_time(remaining)} para cometer um crime."}), 429
    player["last_crime"] = now_iso()
    if random.random() < 0.4:
        fine = random.randint(50, 200)
        player["balance"] = max(0, player["balance"] - fine)
        save_player(player)
        return jsonify({"nick": player["nick"], "result": "preso", "fine": fine, "balance": player["balance"]})
    earned = random.randint(100, 400)
    player["balance"] += earned
    save_player(player)
    return jsonify({"nick": player["nick"], "result": "sucesso", "earned": earned, "balance": player["balance"]})

@app.route("/rob", methods=["POST"])
def rob():
    data = request.json or {}
    player, err, code = auth(data)
    if err: return err, code
    victim_nick = data.get("target", "").strip().lower()
    if not victim_nick:
        return jsonify({"error": "Informe o nick da vitima."}), 400
    if victim_nick == player["nick"]:
        return jsonify({"error": "Nao pode roubar a si mesmo."}), 400
    victim = load_player(victim_nick)
    if not victim:
        return jsonify({"error": "Vitima nao encontrada."}), 404
    if victim["balance"] <= 0:
        return jsonify({"error": "Vitima nao tem coins."}), 400
    protected = "escudo" in victim["inventory"]
    if random.random() < (0.2 if protected else 0.4):
        stolen = random.randint(1, min(200, victim["balance"]))
        victim["balance"] -= stolen
        player["balance"] += stolen
        save_player(victim)
        save_player(player)
        return jsonify({"result": "sucesso", "stolen": stolen, "balance": player["balance"]})
    fine = random.randint(50, 150)
    player["balance"] = max(0, player["balance"] - fine)
    save_player(player)
    return jsonify({"result": "falhou", "fine": fine, "balance": player["balance"]})

@app.route("/transfer", methods=["POST"])
def transfer():
    data = request.json or {}
    player, err, code = auth(data)
    if err: return err, code
    to_nick = data.get("target", "").strip().lower()
    amount = int(data.get("amount", 0))
    if not to_nick:
        return jsonify({"error": "Informe o nick do destinatario."}), 400
    if to_nick == player["nick"]:
        return jsonify({"error": "Nao pode transferir para si mesmo."}), 400
    if amount <= 0:
        return jsonify({"error": "Valor invalido."}), 400
    receiver = load_player(to_nick)
    if not receiver:
        return jsonify({"error": "Destinatario nao encontrado."}), 404
    if player["balance"] < amount:
        return jsonify({"error": "Saldo insuficiente."}), 400
    player["balance"] -= amount
    receiver["balance"] += amount
    save_player(player)
    save_player(receiver)
    return jsonify({"from": player["nick"], "to": to_nick, "amount": amount, "seu_saldo": player["balance"]})

@app.route("/deposit", methods=["POST"])
def deposit():
    data = request.json or {}
    player, err, code = auth(data)
    if err: return err, code
    amount = int(data.get("amount", 0))
    if amount <= 0:
        return jsonify({"error": "Valor invalido."}), 400
    if player["balance"] < amount:
        return jsonify({"error": "Saldo insuficiente."}), 400
    player["balance"] -= amount
    player["bank"] += amount
    save_player(player)
    return jsonify({"nick": player["nick"], "deposited": amount, "balance": player["balance"], "bank": player["bank"]})

@app.route("/withdraw", methods=["POST"])
def withdraw():
    data = request.json or {}
    player, err, code = auth(data)
    if err: return err, code
    amount = int(data.get("amount", 0))
    if amount <= 0:
        return jsonify({"error": "Valor invalido."}), 400
    if player["bank"] < amount:
        return jsonify({"error": "Saldo bancario insuficiente."}), 400
    player["bank"] -= amount
    player["balance"] += amount
    save_player(player)
    return jsonify({"nick": player["nick"], "withdrawn": amount, "balance": player["balance"], "bank": player["bank"]})

@app.route("/shop", methods=["GET"])
def shop():
    return jsonify({"items": SHOP_ITEMS})

@app.route("/buy", methods=["POST"])
def buy():
    data = request.json or {}
    player, err, code = auth(data)
    if err: return err, code
    item = data.get("item", "")
    if item not in SHOP_ITEMS:
        return jsonify({"error": "Item nao encontrado.", "available": list(SHOP_ITEMS.keys())}), 404
    price = SHOP_ITEMS[item]["price"]
    if player["balance"] < price:
        return jsonify({"error": f"Saldo insuficiente. Precisa de {price} coins."}), 400
    if item in player["inventory"]:
        return jsonify({"error": "Voce ja possui este item."}), 400
    player["balance"] -= price
    player["inventory"].append(item)
    save_player(player)
    return jsonify({"nick": player["nick"], "bought": item, "price": price, "balance": player["balance"]})

@app.route("/inventory", methods=["POST"])
def inventory():
    data = request.json or {}
    player, err, code = auth(data)
    if err: return err, code
    items_detail = {i: SHOP_ITEMS[i] for i in player["inventory"] if i in SHOP_ITEMS}
    return jsonify({"nick": player["nick"], "inventory": items_detail})

@app.route("/slots", methods=["POST"])
def slots():
    data = request.json or {}
    player, err, code = auth(data)
    if err: return err, code
    bet = int(data.get("bet", 0))
    if bet <= 0:
        return jsonify({"error": "Aposta invalida."}), 400
    if player["balance"] < bet:
        return jsonify({"error": "Saldo insuficiente."}), 400
    emojis = ["cereja", "limao", "sino", "estrela", "diamante"]
    reels = [random.choice(emojis) for _ in range(3)]
    player["balance"] -= bet
    if reels[0] == reels[1] == reels[2]:
        multiplier = 10 if reels[0] == "diamante" else 5
        winnings = bet * multiplier
        result = "JACKPOT!"
    elif reels[0] == reels[1] or reels[1] == reels[2]:
        winnings = bet * 2
        result = "ganhou!"
    else:
        winnings = 0
        result = "perdeu"
    player["balance"] += winnings
    save_player(player)
    return jsonify({"reels": reels, "result": result, "bet": bet, "winnings": winnings, "balance": player["balance"]})

@app.route("/leaderboard", methods=["GET"])
def leaderboard():
    players = load_all_players()
    ranking = sorted(players, key=lambda x: x["balance"] + x["bank"], reverse=True)
    for p in ranking:
        p["total"] = p["balance"] + p["bank"]
    return jsonify({"leaderboard": ranking[:10]})

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
