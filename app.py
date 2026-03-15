from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import os, random, hashlib, json
from datetime import datetime, timedelta

try:
    import psycopg2, psycopg2.extras
    USE_POSTGRES = True
except ImportError:
    USE_POSTGRES = False

app = Flask(__name__)
CORS(app)

DATABASE_URL = os.environ.get("DATABASE_URL")
DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database.json")

# ── Constantes ─────────────────────────────────────────────

SHOP_ITEMS = {
    "espada":   {"price": 150, "description": "Aumenta ganhos no trabalho em +50", "effect": "work_bonus", "value": 50},
    "picareta": {"price": 200, "description": "Aumenta ganhos manuais de mineracao em +80", "effect": "mine_bonus", "value": 80},
    "mochila":  {"price": 100, "description": "Aumenta capacidade de armazenamento da mina AFK", "effect": "afk_capacity", "value": 500},
    "amuleto":  {"price": 250, "description": "Aumenta XP ganho em +50% em todas as acoes", "effect": "xp_boost", "value": 1.5},
}

ZONES = {
    1: {"name": "Mina de Carvao",    "emoji": "🪨", "req_level": 1,  "base_rate": 2,  "color": "#555"},
    2: {"name": "Mina de Ferro",     "emoji": "⚙️", "req_level": 5,  "base_rate": 6,  "color": "#aaa"},
    3: {"name": "Mina de Ouro",      "emoji": "✨", "req_level": 15, "base_rate": 15, "color": "#f5c400"},
    4: {"name": "Mina de Diamante",  "emoji": "💎", "req_level": 30, "base_rate": 35, "color": "#5cf"},
    5: {"name": "Mina Espacial",     "emoji": "🚀", "req_level": 50, "base_rate": 80, "color": "#c0f"},
}

MINERS = {
    1: [
        {"id": "minerador_iniciante", "name": "Minerador Iniciante", "price": 100,  "rate": 1,  "zone": 1},
        {"id": "minerador_bronze",    "name": "Minerador Bronze",    "price": 300,  "rate": 3,  "zone": 1},
        {"id": "minerador_prata",     "name": "Minerador Prata",     "price": 700,  "rate": 7,  "zone": 1},
    ],
    2: [
        {"id": "ferreiro_junior",     "name": "Ferreiro Junior",     "price": 500,  "rate": 5,  "zone": 2},
        {"id": "ferreiro_mestre",     "name": "Ferreiro Mestre",     "price": 1200, "rate": 12, "zone": 2},
    ],
    3: [
        {"id": "garimpeiro",          "name": "Garimpeiro",          "price": 1500, "rate": 15, "zone": 3},
        {"id": "garimpeiro_pro",      "name": "Garimpeiro Pro",      "price": 3000, "rate": 30, "zone": 3},
    ],
    4: [
        {"id": "extrator_diamante",   "name": "Extrator de Diamante","price": 5000, "rate": 50, "zone": 4},
    ],
    5: [
        {"id": "drone_espacial",      "name": "Drone Espacial",      "price": 10000,"rate": 100,"zone": 5},
    ],
}

TITLES = [
    (0,  "Novato"), (5, "Aventureiro"), (10, "Mercador"),
    (20, "Veterano"), (35, "Especialista"), (50, "Lendario"),
    (75, "Imortal"), (100, "Deus do EON"),
]

XP_REWARDS = {"work": 10, "daily": 30, "mine": 15, "slots_win": 25, "buy": 10}

QUESTS = [
    {"id": "work3",    "desc": "Trabalhe 3 vezes",           "action": "work",    "target": 3,   "reward": 150},
    {"id": "mine3",    "desc": "Minere 3 vezes",             "action": "mine",    "target": 3,   "reward": 200},
    {"id": "deposit1", "desc": "Deposite 200 coins no banco","action": "deposit", "target": 200, "reward": 100},
    {"id": "daily1",   "desc": "Colete o daily",             "action": "daily",   "target": 1,   "reward": 50},
]

MAX_CHAT = 50

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
                nick TEXT PRIMARY KEY, password TEXT NOT NULL,
                balance INTEGER DEFAULT 0, bank INTEGER DEFAULT 0,
                inventory TEXT DEFAULT '[]',
                last_work TEXT, last_daily TEXT, last_mine TEXT,
                xp INTEGER DEFAULT 0, level INTEGER DEFAULT 1,
                quests TEXT DEFAULT '{}',
                zone INTEGER DEFAULT 1,
                miners TEXT DEFAULT '{}',
                last_collect TEXT,
                created_at TEXT DEFAULT NOW()::TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS chat (
                id SERIAL PRIMARY KEY, nick TEXT NOT NULL,
                message TEXT NOT NULL, created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        for col, typ in [
            ("xp","INTEGER DEFAULT 0"), ("level","INTEGER DEFAULT 1"),
            ("quests","TEXT DEFAULT '{}'"), ("zone","INTEGER DEFAULT 1"),
            ("miners","TEXT DEFAULT '{}'"), ("last_collect","TEXT")
        ]:
            try: cur.execute(f"ALTER TABLE players ADD COLUMN IF NOT EXISTS {col} {typ}")
            except: pass
        conn.commit(); cur.close(); conn.close()

def load_player(nick):
    conn = get_conn()
    if conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("SELECT * FROM players WHERE nick = %s", (nick,))
        row = cur.fetchone(); cur.close(); conn.close()
        if row:
            p = dict(row)
            for f in ["inventory","quests","miners"]:
                p[f] = json.loads(p.get(f) or ("[]" if f=="inventory" else "{}"))
            return p
        return None
    else:
        db = load_json(); return db.get(nick)

def save_player(p):
    conn = get_conn()
    nick = p["nick"]
    if conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO players (nick,password,balance,bank,inventory,last_work,last_daily,last_mine,xp,level,quests,zone,miners,last_collect)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (nick) DO UPDATE SET
                balance=EXCLUDED.balance, bank=EXCLUDED.bank,
                inventory=EXCLUDED.inventory, last_work=EXCLUDED.last_work,
                last_daily=EXCLUDED.last_daily, last_mine=EXCLUDED.last_mine,
                xp=EXCLUDED.xp, level=EXCLUDED.level, quests=EXCLUDED.quests,
                zone=EXCLUDED.zone, miners=EXCLUDED.miners, last_collect=EXCLUDED.last_collect
        """, (
            nick, p["password"], p["balance"], p["bank"],
            json.dumps(p.get("inventory",[])),
            p.get("last_work"), p.get("last_daily"), p.get("last_mine"),
            p.get("xp",0), p.get("level",1),
            json.dumps(p.get("quests",{})),
            p.get("zone",1),
            json.dumps(p.get("miners",{})),
            p.get("last_collect")
        ))
        conn.commit(); cur.close(); conn.close()
    else:
        db = load_json(); db[nick] = p; save_json(db)

def create_player(nick, password):
    p = {
        "nick": nick, "password": hash_pass(password),
        "balance": 0, "bank": 0, "inventory": [],
        "last_work": None, "last_daily": None, "last_mine": None,
        "xp": 0, "level": 1, "quests": {},
        "zone": 1, "miners": {}, "last_collect": None,
    }
    save_player(p); return p

def load_all_players():
    conn = get_conn()
    if conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("SELECT nick,balance,bank,xp,level FROM players")
        rows = cur.fetchall(); cur.close(); conn.close()
        return [{"nick":r["nick"],"balance":r["balance"],"bank":r["bank"],
                 "xp":r.get("xp",0),"level":r.get("level",1)} for r in rows]
    else:
        db = load_json()
        return [{"nick":n,"balance":d.get("balance",0),"bank":d.get("bank",0),
                 "xp":d.get("xp",0),"level":d.get("level",1)}
                for n,d in db.items() if isinstance(d,dict)]

def load_json():
    if not os.path.exists(DB_FILE): return {}
    with open(DB_FILE) as f: return json.load(f)

def save_json(data):
    with open(DB_FILE,"w") as f: json.dump(data,f,indent=4)

def hash_pass(p): return hashlib.sha256(p.encode()).hexdigest()

# ── Helpers ────────────────────────────────────────────────

def cooldown_ok(t, minutes):
    if not t: return True, None
    try: last = datetime.fromisoformat(t)
    except: return True, None
    diff = datetime.now() - last
    wait = timedelta(minutes=minutes)
    if diff >= wait: return True, None
    return False, int((wait-diff).total_seconds())

def now_iso(): return datetime.now().isoformat()

def fmt_time(s):
    h,m,s = s//3600,(s%3600)//60,s%60
    if h>0: return f"{h}h {m}m"
    if m>0: return f"{m}m {s}s"
    return f"{s}s"

def get_title(level):
    t = TITLES[0][1]
    for lvl,name in TITLES:
        if level >= lvl: t = name
    return t

def add_xp(player, action):
    base = XP_REWARDS.get(action, 0)
    mult = 1.5 if "amuleto" in player.get("inventory",[]) else 1.0
    gain = int(base * mult)
    player["xp"] = player.get("xp",0) + gain
    new_level = 1 + player["xp"] // 100
    leveled = new_level > player.get("level",1)
    player["level"] = new_level
    return gain, leveled

def update_quest(player, action, amount=1):
    today = datetime.now().strftime("%Y-%m-%d")
    q = player.get("quests",{})
    if q.get("date") != today: q = {"date": today}
    rewards = []
    for quest in QUESTS:
        if quest["action"] != action: continue
        key = quest["id"]
        cur = q.get(key,0)
        if cur >= quest["target"]: continue
        q[key] = min(cur+amount, quest["target"])
        if q[key] >= quest["target"] and cur < quest["target"]:
            player["balance"] += quest["reward"]
            rewards.append({"quest": quest["desc"], "reward": quest["reward"]})
    player["quests"] = q
    return rewards

def get_quest_progress(player):
    today = datetime.now().strftime("%Y-%m-%d")
    q = player.get("quests",{})
    if q.get("date") != today: q = {}
    return [{"id":quest["id"],"desc":quest["desc"],
             "current":q.get(quest["id"],0),"target":quest["target"],
             "reward":quest["reward"],"done":q.get(quest["id"],0)>=quest["target"]}
            for quest in QUESTS]

def calc_afk(player):
    """Calcula coins acumulados AFK desde último collect."""
    miners = player.get("miners",{})
    if not miners: return 0, 0
    last = player.get("last_collect")
    if not last:
        return 0, 0
    try: last_dt = datetime.fromisoformat(last)
    except: return 0, 0
    elapsed = (datetime.now() - last_dt).total_seconds()
    elapsed = min(elapsed, 8 * 3600)  # máx 8h acumuladas

    # taxa total de coins/segundo
    rate_per_sec = 0
    for miner_id, qty in miners.items():
        for zone_miners in MINERS.values():
            for m in zone_miners:
                if m["id"] == miner_id:
                    rate_per_sec += (m["rate"] / 60.0) * qty

    # bonus mochila
    capacity = 2000 + (500 if "mochila" in player.get("inventory",[]) else 0)
    earned = int(rate_per_sec * elapsed)
    earned = min(earned, capacity)
    return earned, int(elapsed)

def auth(data):
    nick = data.get("nick","").strip().lower()
    pw = data.get("password","")
    if not nick or not pw:
        return None, jsonify({"error":"Nick e senha sao obrigatorios."}), 400
    player = load_player(nick)
    if not player:
        return None, jsonify({"error":"Jogador nao encontrado."}), 404
    if player["password"] != hash_pass(pw):
        return None, jsonify({"error":"Senha incorreta."}), 401
    return player, None, None

# ── Rotas ──────────────────────────────────────────────────

@app.route("/")
def index():
    html = os.path.join(os.path.dirname(os.path.abspath(__file__)), "economy.html")
    if os.path.exists(html):
        return send_from_directory(os.path.dirname(os.path.abspath(__file__)), "economy.html")
    return jsonify({"eon": "v5.0"})

@app.route("/register", methods=["POST"])
def register():
    data = request.json or {}
    nick = data.get("nick","").strip().lower()
    pw = data.get("password","")
    if not nick or not pw: return jsonify({"error":"Nick e senha sao obrigatorios."}), 400
    if len(nick)<3 or len(nick)>20: return jsonify({"error":"Nick: 3 a 20 caracteres."}), 400
    if len(pw)<4: return jsonify({"error":"Senha: minimo 4 caracteres."}), 400
    if load_player(nick): return jsonify({"error":"Nick ja em uso."}), 409
    create_player(nick, pw)
    return jsonify({"success":True,"nick":nick,"message":f"Bem-vindo ao EON, {nick}!"})

@app.route("/login", methods=["POST"])
def login():
    data = request.json or {}
    player, err, code = auth(data)
    if err: return err, code
    afk_coins, _ = calc_afk(player)
    return jsonify({
        "success":True,"nick":player["nick"],
        "balance":player["balance"],"bank":player["bank"],
        "total":player["balance"]+player["bank"],
        "inventory":player.get("inventory",[]),
        "xp":player.get("xp",0),"level":player.get("level",1),
        "title":get_title(player.get("level",1)),
        "quests":get_quest_progress(player),
        "zone":player.get("zone",1),
        "miners":player.get("miners",{}),
        "afk_pending":afk_coins,
    })

@app.route("/balance", methods=["POST"])
def balance():
    data = request.json or {}
    player, err, code = auth(data)
    if err: return err, code
    afk_coins, _ = calc_afk(player)
    return jsonify({
        "nick":player["nick"],"balance":player["balance"],
        "bank":player["bank"],"total":player["balance"]+player["bank"],
        "xp":player.get("xp",0),"level":player.get("level",1),
        "title":get_title(player.get("level",1)),
        "afk_pending":afk_coins,
    })

@app.route("/work", methods=["POST"])
def work():
    data = request.json or {}
    player, err, code = auth(data)
    if err: return err, code
    ok, remaining = cooldown_ok(player["last_work"], minutes=30)
    if not ok: return jsonify({"error":f"Aguarde {fmt_time(remaining)} para trabalhar novamente."}), 429
    bonus = 50 if "espada" in player.get("inventory",[]) else 0
    earned = random.randint(50,150) + bonus
    player["balance"] += earned
    player["last_work"] = now_iso()
    xp_gain, leveled = add_xp(player,"work")
    quests = update_quest(player,"work")
    save_player(player)
    return jsonify({"nick":player["nick"],"earned":earned,"balance":player["balance"],
                    "xp_gain":xp_gain,"xp":player["xp"],"level":player["level"],
                    "leveled_up":leveled,"title":get_title(player["level"]),"quest_rewards":quests})

@app.route("/daily", methods=["POST"])
def daily():
    data = request.json or {}
    player, err, code = auth(data)
    if err: return err, code
    ok, remaining = cooldown_ok(player["last_daily"], minutes=1440)
    if not ok: return jsonify({"error":f"Daily ja coletado. Volte em {fmt_time(remaining)}."}), 429
    reward = random.randint(200,500)
    player["balance"] += reward
    player["last_daily"] = now_iso()
    xp_gain, leveled = add_xp(player,"daily")
    quests = update_quest(player,"daily")
    save_player(player)
    return jsonify({"nick":player["nick"],"reward":reward,"balance":player["balance"],
                    "xp_gain":xp_gain,"xp":player["xp"],"level":player["level"],
                    "leveled_up":leveled,"title":get_title(player["level"]),"quest_rewards":quests})

@app.route("/mine", methods=["POST"])
def mine():
    data = request.json or {}
    player, err, code = auth(data)
    if err: return err, code
    ok, remaining = cooldown_ok(player["last_mine"], minutes=60)
    if not ok: return jsonify({"error":f"Aguarde {fmt_time(remaining)} para minerar novamente."}), 429
    bonus = 80 if "picareta" in player.get("inventory",[]) else 0
    earned = random.randint(30,120) + bonus
    player["balance"] += earned
    player["last_mine"] = now_iso()
    xp_gain, leveled = add_xp(player,"mine")
    quests = update_quest(player,"mine")
    save_player(player)
    return jsonify({"nick":player["nick"],"earned":earned,"balance":player["balance"],
                    "xp_gain":xp_gain,"xp":player["xp"],"level":player["level"],
                    "leveled_up":leveled,"title":get_title(player["level"]),"quest_rewards":quests})

@app.route("/transfer", methods=["POST"])
def transfer():
    data = request.json or {}
    player, err, code = auth(data)
    if err: return err, code
    to_nick = data.get("target","").strip().lower()
    amount = int(data.get("amount",0))
    if not to_nick: return jsonify({"error":"Informe o nick do destinatario."}), 400
    if to_nick == player["nick"]: return jsonify({"error":"Nao pode transferir para si mesmo."}), 400
    if amount <= 0: return jsonify({"error":"Valor invalido."}), 400
    receiver = load_player(to_nick)
    if not receiver: return jsonify({"error":"Destinatario nao encontrado."}), 404
    if player["balance"] < amount: return jsonify({"error":"Saldo insuficiente."}), 400
    player["balance"] -= amount
    receiver["balance"] += amount
    save_player(player); save_player(receiver)
    return jsonify({"from":player["nick"],"to":to_nick,"amount":amount,"seu_saldo":player["balance"]})

@app.route("/deposit", methods=["POST"])
def deposit():
    data = request.json or {}
    player, err, code = auth(data)
    if err: return err, code
    amount = int(data.get("amount",0))
    if amount <= 0: return jsonify({"error":"Valor invalido."}), 400
    if player["balance"] < amount: return jsonify({"error":"Saldo insuficiente."}), 400
    player["balance"] -= amount
    player["bank"] += amount
    quests = update_quest(player,"deposit",amount)
    save_player(player)
    return jsonify({"nick":player["nick"],"deposited":amount,
                    "balance":player["balance"],"bank":player["bank"],"quest_rewards":quests})

@app.route("/withdraw", methods=["POST"])
def withdraw():
    data = request.json or {}
    player, err, code = auth(data)
    if err: return err, code
    amount = int(data.get("amount",0))
    if amount <= 0: return jsonify({"error":"Valor invalido."}), 400
    if player["bank"] < amount: return jsonify({"error":"Saldo bancario insuficiente."}), 400
    player["bank"] -= amount
    player["balance"] += amount
    save_player(player)
    return jsonify({"nick":player["nick"],"withdrawn":amount,"balance":player["balance"],"bank":player["bank"]})

@app.route("/shop", methods=["GET"])
def shop():
    return jsonify({"items":SHOP_ITEMS})

@app.route("/buy", methods=["POST"])
def buy():
    data = request.json or {}
    player, err, code = auth(data)
    if err: return err, code
    item = data.get("item","")
    if item not in SHOP_ITEMS: return jsonify({"error":"Item nao encontrado."}), 404
    price = SHOP_ITEMS[item]["price"]
    if player["balance"] < price: return jsonify({"error":f"Precisa de {price} coins."}), 400
    if item in player.get("inventory",[]): return jsonify({"error":"Voce ja possui este item."}), 400
    player["balance"] -= price
    player.setdefault("inventory",[]).append(item)
    xp_gain, leveled = add_xp(player,"buy")
    save_player(player)
    return jsonify({"nick":player["nick"],"bought":item,"price":price,
                    "balance":player["balance"],"xp_gain":xp_gain,
                    "effect":SHOP_ITEMS[item]["description"]})

@app.route("/inventory", methods=["POST"])
def inventory():
    data = request.json or {}
    player, err, code = auth(data)
    if err: return err, code
    items = {i:SHOP_ITEMS[i] for i in player.get("inventory",[]) if i in SHOP_ITEMS}
    return jsonify({"nick":player["nick"],"inventory":items})

@app.route("/slots", methods=["POST"])
def slots():
    data = request.json or {}
    player, err, code = auth(data)
    if err: return err, code
    bet = int(data.get("bet",0))
    if bet <= 0: return jsonify({"error":"Aposta invalida."}), 400
    if player["balance"] < bet: return jsonify({"error":"Saldo insuficiente."}), 400
    emojis = ["cereja","limao","sino","estrela","diamante"]
    reels = [random.choice(emojis) for _ in range(3)]
    player["balance"] -= bet
    if reels[0]==reels[1]==reels[2]:
        mult = 10 if reels[0]=="diamante" else 5
        winnings = bet*mult; result = "JACKPOT!"
    elif reels[0]==reels[1] or reels[1]==reels[2]:
        winnings = bet*2; result = "ganhou!"
    else:
        winnings = 0; result = "perdeu"
    player["balance"] += winnings
    xp_gain, leveled = (add_xp(player,"slots_win") if winnings>0 else (0,False))
    save_player(player)
    return jsonify({"reels":reels,"result":result,"bet":bet,"winnings":winnings,
                    "balance":player["balance"],"xp_gain":xp_gain,
                    "level":player["level"],"leveled_up":leveled})

# ── Zonas e Mineração AFK ──────────────────────────────────

@app.route("/zones", methods=["GET"])
def zones():
    return jsonify({"zones":ZONES,"miners":MINERS})

@app.route("/mine/status", methods=["POST"])
def mine_status():
    data = request.json or {}
    player, err, code = auth(data)
    if err: return err, code
    afk_coins, elapsed = calc_afk(player)
    capacity = 2000 + (500 if "mochila" in player.get("inventory",[]) else 0)
    total_rate = 0
    miners = player.get("miners",{})
    for miner_id, qty in miners.items():
        for zone_ms in MINERS.values():
            for m in zone_ms:
                if m["id"] == miner_id:
                    total_rate += m["rate"] * qty
    return jsonify({
        "zone": player.get("zone",1),
        "zone_info": ZONES.get(player.get("zone",1)),
        "miners": miners,
        "afk_pending": afk_coins,
        "rate_per_min": total_rate,
        "capacity": capacity,
        "elapsed_seconds": elapsed,
    })

@app.route("/mine/collect", methods=["POST"])
def mine_collect():
    data = request.json or {}
    player, err, code = auth(data)
    if err: return err, code
    earned, elapsed = calc_afk(player)
    if earned <= 0:
        return jsonify({"error":"Nada para coletar ainda. Compre mineradores!"}), 400
    player["balance"] += earned
    player["last_collect"] = now_iso()
    save_player(player)
    return jsonify({"nick":player["nick"],"collected":earned,
                    "balance":player["balance"],"elapsed_seconds":elapsed})

@app.route("/mine/buy_miner", methods=["POST"])
def buy_miner():
    data = request.json or {}
    player, err, code = auth(data)
    if err: return err, code
    miner_id = data.get("miner_id","")
    miner_data = None
    for zone_ms in MINERS.values():
        for m in zone_ms:
            if m["id"] == miner_id:
                miner_data = m; break

    if not miner_data: return jsonify({"error":"Minerador nao encontrado."}), 404
    zone_req = miner_data["zone"]
    zone_info = ZONES[zone_req]
    if player.get("level",1) < zone_info["req_level"]:
        return jsonify({"error":f"Precisa Lv.{zone_info['req_level']} para comprar este minerador."}), 400
    if player["balance"] < miner_data["price"]:
        return jsonify({"error":f"Precisa de {miner_data['price']} coins."}), 400

    # Coleta AFK antes de mudar mineradores
    earned, _ = calc_afk(player)
    if earned > 0:
        player["balance"] += earned
        player["last_collect"] = now_iso()

    player["balance"] -= miner_data["price"]
    miners = player.get("miners",{})
    miners[miner_id] = miners.get(miner_id,0) + 1
    player["miners"] = miners
    if not player.get("last_collect"):
        player["last_collect"] = now_iso()
    save_player(player)
    return jsonify({
        "nick":player["nick"],"bought":miner_data["name"],
        "price":miner_data["price"],"balance":player["balance"],
        "miners":miners,"rate":miner_data["rate"],
        "qty":miners[miner_id]
    })

@app.route("/mine/unlock_zone", methods=["POST"])
def unlock_zone():
    data = request.json or {}
    player, err, code = auth(data)
    if err: return err, code
    zone_id = int(data.get("zone",0))
    if zone_id not in ZONES: return jsonify({"error":"Zona invalida."}), 400
    zone = ZONES[zone_id]
    if player.get("level",1) < zone["req_level"]:
        return jsonify({"error":f"Precisa Lv.{zone['req_level']} para desbloquear esta zona."}), 400
    player["zone"] = max(player.get("zone",1), zone_id)
    save_player(player)
    return jsonify({"nick":player["nick"],"zone":player["zone"],"zone_info":zone})

# ── Quests ────────────────────────────────────────────────

@app.route("/quests", methods=["POST"])
def quests():
    data = request.json or {}
    player, err, code = auth(data)
    if err: return err, code
    return jsonify({"nick":player["nick"],"quests":get_quest_progress(player)})

@app.route("/profile", methods=["POST"])
def profile():
    data = request.json or {}
    player, err, code = auth(data)
    if err: return err, code
    afk_coins, _ = calc_afk(player)
    return jsonify({
        "nick":player["nick"],"level":player.get("level",1),
        "xp":player.get("xp",0),"title":get_title(player.get("level",1)),
        "balance":player["balance"],"bank":player["bank"],
        "inventory":player.get("inventory",[]),
        "quests":get_quest_progress(player),
        "zone":player.get("zone",1),"miners":player.get("miners",{}),
        "afk_pending":afk_coins,
    })

@app.route("/leaderboard", methods=["GET"])
def leaderboard():
    players = load_all_players()
    ranking = sorted(players, key=lambda x:x["balance"]+x["bank"], reverse=True)
    for p in ranking:
        p["total"] = p["balance"]+p["bank"]
        p["title"] = get_title(p.get("level",1))
    return jsonify({"leaderboard":ranking[:10]})

# ── Chat ──────────────────────────────────────────────────

@app.route("/chat/send", methods=["POST"])
def chat_send():
    data = request.json or {}
    player, err, code = auth(data)
    if err: return err, code
    message = data.get("message","").strip()
    if not message: return jsonify({"error":"Mensagem vazia."}), 400
    if len(message)>200: return jsonify({"error":"Mensagem muito longa."}), 400
    conn = get_conn()
    if conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO chat (nick,message) VALUES (%s,%s)", (player["nick"],message))
        cur.execute(f"DELETE FROM chat WHERE id NOT IN (SELECT id FROM chat ORDER BY id DESC LIMIT {MAX_CHAT})")
        conn.commit(); cur.close(); conn.close()
    else:
        db = load_json()
        msgs = db.get("__chat__",[])
        msgs.append({"nick":player["nick"],"message":message,"time":now_iso()})
        db["__chat__"] = msgs[-MAX_CHAT:]
        save_json(db)
    return jsonify({"success":True})

@app.route("/chat/messages", methods=["GET"])
def chat_messages():
    conn = get_conn()
    if conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("SELECT nick,message,created_at FROM chat ORDER BY id DESC LIMIT 50")
        rows = cur.fetchall(); cur.close(); conn.close()
        msgs = [{"nick":r["nick"],"message":r["message"],"time":str(r["created_at"])} for r in reversed(rows)]
    else:
        db = load_json(); msgs = db.get("__chat__",[])
    return jsonify({"messages":msgs})

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT",5000))
    app.run(host="0.0.0.0", port=port, debug=False)
