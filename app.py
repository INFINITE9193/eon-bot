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

SHOP_ITEMS = {
    "espada":   {"price": 150, "description": "Trabalho +50 coins", "effect": "work_bonus"},
    "picareta": {"price": 200, "description": "Click de mina x2",   "effect": "click_bonus"},
    "mochila":  {"price": 300, "description": "Capacidade AFK +1000","effect": "afk_capacity"},
    "amuleto":  {"price": 250, "description": "XP x1.5 em tudo",    "effect": "xp_boost"},
}

ZONES = {
    1: {"name": "Carvao",   "emoji": "🪨", "req_level": 1,  "click_value": 1,  "color": "#777"},
    2: {"name": "Ferro",    "emoji": "⚙️", "req_level": 5,  "click_value": 3,  "color": "#aaa"},
    3: {"name": "Ouro",     "emoji": "✨", "req_level": 15, "click_value": 8,  "color": "#f5c400"},
    4: {"name": "Diamante", "emoji": "💎", "req_level": 30, "click_value": 20, "color": "#5cf"},
    5: {"name": "Espacial", "emoji": "🚀", "req_level": 50, "click_value": 60, "color": "#c0f"},
}

MINERS = {
    1: [
        {"id": "coletor",    "name": "Coletor",    "price": 50,    "cps": 0.1, "zone": 1},
        {"id": "mineiro",    "name": "Mineiro",    "price": 200,   "cps": 0.5, "zone": 1},
        {"id": "perfurador", "name": "Perfurador", "price": 800,   "cps": 2,   "zone": 1},
        {"id": "maquina",    "name": "Maquina",    "price": 3000,  "cps": 8,   "zone": 1},
    ],
    2: [
        {"id": "ferreiro",   "name": "Ferreiro",   "price": 500,   "cps": 1,   "zone": 2},
        {"id": "forja",      "name": "Forja",      "price": 2000,  "cps": 4,   "zone": 2},
        {"id": "fundidor",   "name": "Fundidor",   "price": 8000,  "cps": 15,  "zone": 2},
    ],
    3: [
        {"id": "garimpeiro", "name": "Garimpeiro", "price": 2000,  "cps": 3,   "zone": 3},
        {"id": "draga",      "name": "Draga",      "price": 10000, "cps": 12,  "zone": 3},
        {"id": "refinaria",  "name": "Refinaria",  "price": 40000, "cps": 50,  "zone": 3},
    ],
    4: [
        {"id": "laser",      "name": "Laser",      "price": 15000, "cps": 20,  "zone": 4},
        {"id": "robo",       "name": "Robo",       "price": 80000, "cps": 100, "zone": 4},
    ],
    5: [
        {"id": "drone",      "name": "Drone",      "price": 50000, "cps": 50,  "zone": 5},
        {"id": "nave",       "name": "Nave",       "price": 500000,"cps": 500, "zone": 5},
    ],
}

TITLES = [(0,"Novato"),(5,"Aventureiro"),(10,"Mercador"),(20,"Veterano"),(35,"Especialista"),(50,"Lendario"),(75,"Imortal"),(100,"Deus do EON")]
XP_REWARDS = {"work":10,"daily":30,"mine_click":2,"slots_win":25,"buy":10}
QUESTS = [
    {"id":"work3",    "desc":"Trabalhe 3 vezes",          "action":"work",       "target":3,   "reward":150},
    {"id":"mine50",   "desc":"Clique 50x na mina",        "action":"mine_click", "target":50,  "reward":200},
    {"id":"deposit1", "desc":"Deposite 200 coins",        "action":"deposit",    "target":200, "reward":100},
    {"id":"daily1",   "desc":"Colete o daily",            "action":"daily",      "target":1,   "reward":50},
]
MAX_CHAT = 50

def get_conn():
    if DATABASE_URL and USE_POSTGRES:
        return psycopg2.connect(DATABASE_URL, sslmode='require')
    return None

def init_db():
    conn = get_conn()
    if conn:
        cur = conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS players (
            nick TEXT PRIMARY KEY, password TEXT NOT NULL,
            balance FLOAT DEFAULT 0, bank FLOAT DEFAULT 0,
            inventory TEXT DEFAULT '[]', last_work TEXT, last_daily TEXT,
            xp INTEGER DEFAULT 0, level INTEGER DEFAULT 1, quests TEXT DEFAULT '{}',
            zone INTEGER DEFAULT 1, miners TEXT DEFAULT '{}', last_collect TEXT,
            total_clicks INTEGER DEFAULT 0, prestige INTEGER DEFAULT 0,
            created_at TEXT DEFAULT NOW()::TEXT)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS chat (
            id SERIAL PRIMARY KEY, nick TEXT NOT NULL,
            message TEXT NOT NULL, created_at TIMESTAMP DEFAULT NOW())""")
        for col, typ in [("balance","FLOAT DEFAULT 0"),("bank","FLOAT DEFAULT 0"),
            ("xp","INTEGER DEFAULT 0"),("level","INTEGER DEFAULT 1"),
            ("quests","TEXT DEFAULT '{}'"),("zone","INTEGER DEFAULT 1"),
            ("miners","TEXT DEFAULT '{}'"),("last_collect","TEXT"),
            ("total_clicks","INTEGER DEFAULT 0"),("prestige","INTEGER DEFAULT 0"),
            ("inventory","TEXT DEFAULT '[]'")]:
            try: cur.execute(f"ALTER TABLE players ADD COLUMN IF NOT EXISTS {col} {typ}")
            except: conn.rollback()
        conn.commit(); cur.close(); conn.close()

def load_player(nick):
    conn = get_conn()
    if conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("SELECT * FROM players WHERE nick=%s",(nick,))
        row = cur.fetchone(); cur.close(); conn.close()
        if row:
            p = dict(row)
            for f,d in [("inventory","[]"),("quests","{}"),("miners","{}")]:
                p[f] = json.loads(p.get(f) or d)
            return p
        return None
    return load_json().get(nick)

def save_player(p):
    conn = get_conn()
    if conn:
        cur = conn.cursor()
        cur.execute("""INSERT INTO players (nick,password,balance,bank,inventory,last_work,last_daily,
            xp,level,quests,zone,miners,last_collect,total_clicks,prestige)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (nick) DO UPDATE SET
            balance=EXCLUDED.balance,bank=EXCLUDED.bank,inventory=EXCLUDED.inventory,
            last_work=EXCLUDED.last_work,last_daily=EXCLUDED.last_daily,xp=EXCLUDED.xp,
            level=EXCLUDED.level,quests=EXCLUDED.quests,zone=EXCLUDED.zone,
            miners=EXCLUDED.miners,last_collect=EXCLUDED.last_collect,
            total_clicks=EXCLUDED.total_clicks,prestige=EXCLUDED.prestige""",
            (p["nick"],p["password"],p["balance"],p["bank"],
             json.dumps(p.get("inventory",[])),p.get("last_work"),p.get("last_daily"),
             p.get("xp",0),p.get("level",1),json.dumps(p.get("quests",{})),
             p.get("zone",1),json.dumps(p.get("miners",{})),p.get("last_collect"),
             p.get("total_clicks",0),p.get("prestige",0)))
        conn.commit(); cur.close(); conn.close()
    else:
        db = load_json(); db[p["nick"]] = p; save_json(db)

def create_player(nick, pw):
    p = {"nick":nick,"password":hash_pass(pw),"balance":0.0,"bank":0.0,
         "inventory":[],"last_work":None,"last_daily":None,"xp":0,"level":1,
         "quests":{},"zone":1,"miners":{},"last_collect":None,"total_clicks":0,"prestige":0}
    save_player(p); return p

def load_all_players():
    conn = get_conn()
    if conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("SELECT nick,balance,bank,xp,level,prestige FROM players")
        rows = cur.fetchall(); cur.close(); conn.close()
        return [{"nick":r["nick"],"balance":float(r["balance"]),"bank":float(r["bank"]),
                 "xp":r["xp"],"level":r["level"],"prestige":r.get("prestige",0)} for r in rows]
    db = load_json()
    return [{"nick":n,"balance":float(d.get("balance",0)),"bank":float(d.get("bank",0)),
             "xp":d.get("xp",0),"level":d.get("level",1),"prestige":d.get("prestige",0)}
            for n,d in db.items() if isinstance(d,dict)]

def load_json():
    if not os.path.exists(DB_FILE): return {}
    with open(DB_FILE) as f: return json.load(f)

def save_json(data):
    with open(DB_FILE,"w") as f: json.dump(data,f,indent=4)

def hash_pass(p): return hashlib.sha256(p.encode()).hexdigest()

def cooldown_ok(t, mins):
    if not t: return True, None
    try: last = datetime.fromisoformat(t)
    except: return True, None
    diff = datetime.now()-last
    wait = timedelta(minutes=mins)
    if diff >= wait: return True, None
    return False, int((wait-diff).total_seconds())

def now_iso(): return datetime.now().isoformat()

def fmt_time(s):
    h,m,s=s//3600,(s%3600)//60,s%60
    if h>0: return f"{h}h {m}m"
    if m>0: return f"{m}m {s}s"
    return f"{s}s"

def get_title(lv):
    t=TITLES[0][1]
    for l,n in TITLES:
        if lv>=l: t=n
    return t

def add_xp(p, action):
    base = XP_REWARDS.get(action,0)
    mult = 1.5 if "amuleto" in p.get("inventory",[]) else 1.0
    gain = int(base*mult)
    p["xp"] = p.get("xp",0)+gain
    nl = 1+p["xp"]//100
    lv = nl > p.get("level",1)
    p["level"] = nl
    return gain, lv

def update_quest(p, action, amount=1):
    today = datetime.now().strftime("%Y-%m-%d")
    q = p.get("quests",{})
    if q.get("date") != today: q = {"date":today}
    rewards = []
    for quest in QUESTS:
        if quest["action"] != action: continue
        key = quest["id"]; cur = q.get(key,0)
        if cur >= quest["target"]: continue
        q[key] = min(cur+amount, quest["target"])
        if q[key] >= quest["target"] and cur < quest["target"]:
            p["balance"] += quest["reward"]
            rewards.append({"quest":quest["desc"],"reward":quest["reward"]})
    p["quests"] = q; return rewards

def get_quests(p):
    today = datetime.now().strftime("%Y-%m-%d")
    q = p.get("quests",{})
    if q.get("date") != today: q = {}
    return [{"id":quest["id"],"desc":quest["desc"],"current":q.get(quest["id"],0),
             "target":quest["target"],"reward":quest["reward"],
             "done":q.get(quest["id"],0)>=quest["target"]} for quest in QUESTS]

def calc_cps(p):
    miners = p.get("miners",{})
    cps = 0.0
    for mid, qty in miners.items():
        for zms in MINERS.values():
            for m in zms:
                if m["id"] == mid: cps += m["cps"]*qty
    return round(cps, 2)

def calc_afk(p):
    cps = calc_cps(p)
    if cps <= 0: return 0.0, 0
    last = p.get("last_collect")
    if not last: return 0.0, 0
    try: ldt = datetime.fromisoformat(last)
    except: return 0.0, 0
    elapsed = min((datetime.now()-ldt).total_seconds(), 8*3600)
    cap = 5000+(1000 if "mochila" in p.get("inventory",[]) else 0)
    return round(min(cps*elapsed, cap), 2), int(elapsed)

def click_val(p):
    z = p.get("zone",1)
    base = ZONES[z]["click_value"]
    mult = 2 if "picareta" in p.get("inventory",[]) else 1
    return round(base*mult, 2)

def auth(data):
    nick = data.get("nick","").strip().lower()
    pw = data.get("password","")
    if not nick or not pw: return None, jsonify({"error":"Nick e senha obrigatorios."}), 400
    p = load_player(nick)
    if not p: return None, jsonify({"error":"Jogador nao encontrado."}), 404
    if p["password"] != hash_pass(pw): return None, jsonify({"error":"Senha incorreta."}), 401
    return p, None, None

def summary(p):
    afk, _ = calc_afk(p)
    return {
        "nick":p["nick"],"balance":round(float(p["balance"]),2),"bank":round(float(p["bank"]),2),
        "total":round(float(p["balance"])+float(p["bank"]),2),
        "xp":p.get("xp",0),"level":p.get("level",1),"title":get_title(p.get("level",1)),
        "inventory":p.get("inventory",[]),"quests":get_quests(p),
        "zone":p.get("zone",1),"miners":p.get("miners",{}),
        "afk_pending":afk,"cps":calc_cps(p),"click_value":click_val(p),
        "total_clicks":p.get("total_clicks",0),"prestige":p.get("prestige",0),
        "capacity":5000+(1000 if "mochila" in p.get("inventory",[]) else 0),
    }

@app.route("/")
def index():
    f = os.path.join(os.path.dirname(os.path.abspath(__file__)),"economy.html")
    if os.path.exists(f): return send_from_directory(os.path.dirname(os.path.abspath(__file__)),"economy.html")
    return jsonify({"eon":"v6.0"})

@app.route("/register", methods=["POST"])
def register():
    d = request.json or {}
    nick = d.get("nick","").strip().lower(); pw = d.get("password","")
    if not nick or not pw: return jsonify({"error":"Nick e senha obrigatorios."}),400
    if len(nick)<3 or len(nick)>20: return jsonify({"error":"Nick: 3 a 20 chars."}),400
    if len(pw)<4: return jsonify({"error":"Senha: min 4 chars."}),400
    if load_player(nick): return jsonify({"error":"Nick ja em uso."}),409
    create_player(nick,pw)
    return jsonify({"success":True,"nick":nick,"message":f"Bem-vindo ao EON, {nick}!"})

@app.route("/login", methods=["POST"])
def login():
    d = request.json or {}
    p,e,c = auth(d)
    if e: return e,c
    return jsonify({"success":True,**summary(p)})

@app.route("/balance", methods=["POST"])
def balance():
    d = request.json or {}
    p,e,c = auth(d)
    if e: return e,c
    return jsonify(summary(p))

@app.route("/work", methods=["POST"])
def work():
    d = request.json or {}
    p,e,c = auth(d)
    if e: return e,c
    ok,rem = cooldown_ok(p["last_work"],30)
    if not ok: return jsonify({"error":f"Aguarde {fmt_time(rem)} para trabalhar."}),429
    bonus = 50 if "espada" in p.get("inventory",[]) else 0
    earned = random.randint(50,150)+bonus
    p["balance"] = round(float(p["balance"])+earned,2)
    p["last_work"] = now_iso()
    xg,lv = add_xp(p,"work"); qs = update_quest(p,"work")
    save_player(p)
    return jsonify({**summary(p),"earned":earned,"xp_gain":xg,"leveled_up":lv,"quest_rewards":qs})

@app.route("/daily", methods=["POST"])
def daily():
    d = request.json or {}
    p,e,c = auth(d)
    if e: return e,c
    ok,rem = cooldown_ok(p["last_daily"],1440)
    if not ok: return jsonify({"error":f"Daily ja coletado. Volte em {fmt_time(rem)}."}),429
    reward = random.randint(200,500)
    p["balance"] = round(float(p["balance"])+reward,2)
    p["last_daily"] = now_iso()
    xg,lv = add_xp(p,"daily"); qs = update_quest(p,"daily")
    save_player(p)
    return jsonify({**summary(p),"reward":reward,"xp_gain":xg,"leveled_up":lv,"quest_rewards":qs})

@app.route("/mine/click", methods=["POST"])
def mine_click():
    d = request.json or {}
    p,e,c = auth(d)
    if e: return e,c
    clicks = min(int(d.get("clicks",1)),10)
    cv = click_val(p)
    earned = round(cv*clicks,2)
    p["balance"] = round(float(p["balance"])+earned,2)
    p["total_clicks"] = p.get("total_clicks",0)+clicks
    xg,lv = add_xp(p,"mine_click"); qs = update_quest(p,"mine_click",clicks)
    save_player(p)
    return jsonify({"earned":earned,"click_value":cv,"clicks":clicks,
                    "balance":p["balance"],"xp_gain":xg,"total_clicks":p["total_clicks"],
                    "leveled_up":lv,"level":p["level"],"title":get_title(p["level"]),"quest_rewards":qs})

@app.route("/mine/collect", methods=["POST"])
def mine_collect():
    d = request.json or {}
    p,e,c = auth(d)
    if e: return e,c
    earned,elapsed = calc_afk(p)
    if earned<=0: return jsonify({"error":"Nada para coletar. Compre mineradores!"}),400
    p["balance"] = round(float(p["balance"])+earned,2)
    p["last_collect"] = now_iso()
    save_player(p)
    return jsonify({**summary(p),"collected":earned,"elapsed_seconds":elapsed})

@app.route("/mine/buy_miner", methods=["POST"])
def buy_miner():
    d = request.json or {}
    p,e,c = auth(d)
    if e: return e,c
    mid = d.get("miner_id",""); md = None
    for zms in MINERS.values():
        for m in zms:
            if m["id"]==mid: md=m; break
    if not md: return jsonify({"error":"Minerador nao encontrado."}),404
    zi = ZONES[md["zone"]]
    if p.get("level",1)<zi["req_level"]: return jsonify({"error":f"Precisa Lv.{zi['req_level']}."}),400
    if float(p["balance"])<md["price"]: return jsonify({"error":f"Precisa de {md['price']} coins."}),400
    earned,_ = calc_afk(p)
    if earned>0: p["balance"]=round(float(p["balance"])+earned,2)
    p["balance"] = round(float(p["balance"])-md["price"],2)
    miners = p.get("miners",{})
    miners[mid] = miners.get(mid,0)+1
    p["miners"] = miners
    if not p.get("last_collect"): p["last_collect"] = now_iso()
    save_player(p)
    return jsonify({**summary(p),"bought":md["name"],"qty":miners[mid],"miner_cps":md["cps"],"total_cps":calc_cps(p)})

@app.route("/mine/status", methods=["POST"])
def mine_status():
    d = request.json or {}
    p,e,c = auth(d)
    if e: return e,c
    return jsonify(summary(p))

@app.route("/zones", methods=["GET"])
def zones():
    return jsonify({"zones":ZONES,"miners":MINERS})

@app.route("/transfer", methods=["POST"])
def transfer():
    d = request.json or {}
    p,e,c = auth(d)
    if e: return e,c
    tn = d.get("target","").strip().lower(); amount = float(d.get("amount",0))
    if not tn: return jsonify({"error":"Informe o nick."}),400
    if tn==p["nick"]: return jsonify({"error":"Nao pode transferir para si mesmo."}),400
    if amount<=0: return jsonify({"error":"Valor invalido."}),400
    rec = load_player(tn)
    if not rec: return jsonify({"error":"Destinatario nao encontrado."}),404
    if float(p["balance"])<amount: return jsonify({"error":"Saldo insuficiente."}),400
    p["balance"]=round(float(p["balance"])-amount,2); rec["balance"]=round(float(rec["balance"])+amount,2)
    save_player(p); save_player(rec)
    return jsonify({**summary(p),"transferred":amount,"to":tn})

@app.route("/deposit", methods=["POST"])
def deposit():
    d = request.json or {}
    p,e,c = auth(d)
    if e: return e,c
    amount = float(d.get("amount",0))
    if amount<=0: return jsonify({"error":"Valor invalido."}),400
    if float(p["balance"])<amount: return jsonify({"error":"Saldo insuficiente."}),400
    p["balance"]=round(float(p["balance"])-amount,2); p["bank"]=round(float(p["bank"])+amount,2)
    qs = update_quest(p,"deposit",int(amount)); save_player(p)
    return jsonify({**summary(p),"deposited":amount,"quest_rewards":qs})

@app.route("/withdraw", methods=["POST"])
def withdraw():
    d = request.json or {}
    p,e,c = auth(d)
    if e: return e,c
    amount = float(d.get("amount",0))
    if amount<=0: return jsonify({"error":"Valor invalido."}),400
    if float(p["bank"])<amount: return jsonify({"error":"Saldo bancario insuficiente."}),400
    p["bank"]=round(float(p["bank"])-amount,2); p["balance"]=round(float(p["balance"])+amount,2)
    save_player(p)
    return jsonify({**summary(p),"withdrawn":amount})

@app.route("/shop", methods=["GET"])
def shop():
    return jsonify({"items":SHOP_ITEMS})

@app.route("/buy", methods=["POST"])
def buy():
    d = request.json or {}
    p,e,c = auth(d)
    if e: return e,c
    item = d.get("item","")
    if item not in SHOP_ITEMS: return jsonify({"error":"Item nao encontrado."}),404
    price = SHOP_ITEMS[item]["price"]
    if float(p["balance"])<price: return jsonify({"error":f"Precisa de {price} coins."}),400
    if item in p.get("inventory",[]): return jsonify({"error":"Voce ja possui este item."}),400
    p["balance"]=round(float(p["balance"])-price,2); p.setdefault("inventory",[]).append(item)
    xg,lv = add_xp(p,"buy"); save_player(p)
    return jsonify({**summary(p),"bought":item,"xp_gain":xg,"effect":SHOP_ITEMS[item]["description"]})

@app.route("/slots", methods=["POST"])
def slots():
    d = request.json or {}
    p,e,c = auth(d)
    if e: return e,c
    bet = float(d.get("bet",0))
    if bet<=0: return jsonify({"error":"Aposta invalida."}),400
    if float(p["balance"])<bet: return jsonify({"error":"Saldo insuficiente."}),400
    emojis = ["cereja","limao","sino","estrela","diamante"]
    reels = [random.choice(emojis) for _ in range(3)]
    p["balance"] = round(float(p["balance"])-bet,2)
    if reels[0]==reels[1]==reels[2]:
        w=round(bet*(10 if reels[0]=="diamante" else 5),2); r="JACKPOT!"
    elif reels[0]==reels[1] or reels[1]==reels[2]:
        w=round(bet*2,2); r="ganhou!"
    else:
        w=0; r="perdeu"
    p["balance"]=round(float(p["balance"])+w,2)
    xg,lv=(add_xp(p,"slots_win") if w>0 else (0,False)); save_player(p)
    return jsonify({**summary(p),"reels":reels,"result":r,"bet":bet,"winnings":w,"xp_gain":xg,"leveled_up":lv})

@app.route("/quests", methods=["POST"])
def quests():
    d = request.json or {}
    p,e,c = auth(d)
    if e: return e,c
    return jsonify({"nick":p["nick"],"quests":get_quests(p)})

@app.route("/leaderboard", methods=["GET"])
def leaderboard():
    players = load_all_players()
    ranking = sorted(players,key=lambda x:x["balance"]+x["bank"],reverse=True)
    for p in ranking:
        p["total"]=round(p["balance"]+p["bank"],2); p["title"]=get_title(p.get("level",1))
    return jsonify({"leaderboard":ranking[:10]})

@app.route("/chat/send", methods=["POST"])
def chat_send():
    d = request.json or {}
    p,e,c = auth(d)
    if e: return e,c
    msg = d.get("message","").strip()
    if not msg: return jsonify({"error":"Mensagem vazia."}),400
    if len(msg)>200: return jsonify({"error":"Mensagem muito longa."}),400
    conn = get_conn()
    if conn:
        cur=conn.cursor()
        cur.execute("INSERT INTO chat (nick,message) VALUES (%s,%s)",(p["nick"],msg))
        cur.execute(f"DELETE FROM chat WHERE id NOT IN (SELECT id FROM chat ORDER BY id DESC LIMIT {MAX_CHAT})")
        conn.commit(); cur.close(); conn.close()
    else:
        db=load_json(); msgs=db.get("__chat__",[])
        msgs.append({"nick":p["nick"],"message":msg,"time":now_iso()})
        db["__chat__"]=msgs[-MAX_CHAT:]; save_json(db)
    return jsonify({"success":True})

@app.route("/chat/messages", methods=["GET"])
def chat_messages():
    conn = get_conn()
    if conn:
        cur=conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("SELECT nick,message,created_at FROM chat ORDER BY id DESC LIMIT 50")
        rows=cur.fetchall(); cur.close(); conn.close()
        msgs=[{"nick":r["nick"],"message":r["message"],"time":str(r["created_at"])} for r in reversed(rows)]
    else:
        db=load_json(); msgs=db.get("__chat__",[])
    return jsonify({"messages":msgs})

init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT",5000))
    app.run(host="0.0.0.0",port=port,debug=False)
