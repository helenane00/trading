import os
import telebot
import requests
import time
import threading
from tradingview_ta import TA_Handler

# --- CONFIGURATION ---
API_TOKEN = '8336258649:AAGGw0tLwz8JpWP9hfjgSDx7z3FRZb5lXNE'
bot = telebot.TeleBot(API_TOKEN)

live_btc_id, live_or_id, live_analyse_id = None, None, None
derniere_alerte = {"BTC": 0, "OR": 0}
signaux_actifs = []

def calculer_prudence(prix, conf, rec):
    if 70 <= conf <= 74: marge_pct = 0.001
    elif 75 <= conf <= 79: marge_pct = 0.002
    elif conf >= 80: marge_pct = 0.003
    else: marge_pct = 0.0005
    marge = prix * marge_pct
    return round(prix + marge, 2) if "BUY" in rec else round(prix - marge, 2)

def calculer_confiance(score_buy, score_sell, rsi, rec):
    total = score_buy + score_sell
    if total == 0: return 50.0
    force_score = (score_buy / total if "BUY" in rec else score_sell / total) * 100
    force_rsi = (100 - rsi if "BUY" in rec else rsi)
    return round((force_score * 0.7) + (force_rsi * 0.3), 1)

def verifier_signaux(prix_actuel, symbole, chat_id):
    global signaux_actifs
    maintenant = time.time()
    for s in signaux_actifs[:]:
        if s['symbole'] == symbole:
            if (s['type'] == "BUY" and prix_actuel >= s['cible']) or \
               (s['type'] == "SELL" and prix_actuel <= s['cible']):
                bot.send_message(chat_id, f"Signal {symbole} validé 👏💵")
                signaux_actifs.remove(s)
            elif (maintenant - s['timestamp'] > 18000):
                bot.send_message(chat_id, f"Signal {symbole} perdu 📉")
                signaux_actifs.remove(s)

def get_data():
    try:
        # On vérifie Binance
        res_b = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT", timeout=10).json()
        res_o = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=XAUTUSDT", timeout=10).json()

        # On vérifie TradingView
        b_h = TA_Handler(symbol="BTCUSDT", screener="crypto", exchange="BINANCE", interval="1m")
        o_h = TA_Handler(symbol="XAUTUSDT", screener="crypto", exchange="BINANCE", interval="1m")

        ba = b_h.get_analysis()
        oa = o_h.get_analysis()

        return {
            "btc": {"p": float(res_b['price']), "r": ba.indicators['RSI'], "rec": ba.summary['RECOMMENDATION'], "b": ba.summary['BUY'], "s": ba.summary['SELL']},
            "or": {"p": float(res_o['price']), "r": oa.indicators['RSI'], "rec": oa.summary['RECOMMENDATION'], "b": oa.summary['BUY'], "s": oa.summary['SELL']}
        }
    except Exception as e:
        print(f"ERREUR RÉCUPÉRATION: {e}") # Regarde ton Termux pour voir l'erreur !
        return None

def moteur_principal(chat_id):
    global derniere_alerte, signaux_actifs, live_btc_id, live_or_id, live_analyse_id
    print("Moteur démarré...")
    while True:
        d = get_data()
        if d:
            b_conf = calculer_confiance(d["btc"]["b"], d["btc"]["s"], d["btc"]["r"], d["btc"]["rec"])
            b_prud = calculer_prudence(d["btc"]["p"], b_conf, d["btc"]["rec"])
            o_conf = calculer_confiance(d["or"]["b"], d["or"]["s"], d["or"]["r"], d["or"]["rec"])
            o_prud = calculer_prudence(d["or"]["p"], o_conf, d["or"]["rec"])

            verifier_signaux(d["btc"]["p"], "BTC", chat_id)
            verifier_signaux(d["or"]["p"], "OR", chat_id)

            for key, conf, info, prud in [("BTC", b_conf, d["btc"], b_prud), ("OR", o_conf, d["or"], o_prud)]:
                if conf >= 74 and (time.time() - derniere_alerte[key] > 300):
                    emo = "📈" if "BUY" in info['rec'] else "📉"
                    bot.send_message(chat_id, f"⚠️RADAR {key} : SIGNAL FORT !⚠️\nConfiance : {conf}%📈\nDirection : {info['rec']} {emo}\nPrix actuel : {info['p']}\n🎯Cible (Prudence) : {prud}")
                    signaux_actifs.append({'symbole': key, 'cible': prud, 'type': "BUY" if "BUY" in info['rec'] else "SELL", 'timestamp': time.time()})
                    derniere_alerte[key] = time.time()

            t = time.strftime('%H:%M:%S')
            txt_b = f"BITCOIN LIVE ₿ 📶\n💰Prix actuel : {d['btc']['p']}\nRSI : {d['btc']['r']:.1f}\nConfiance {b_conf}% | {d['btc']['rec']}\n🎯Cible : {b_prud}\n{t}"
            txt_o = f"OR LIVE  🪙\n💰Prix actuel : {d['or']['p']}\nRSI : {d['or']['r']:.1f}\nConfiance {o_conf}% | {d['or']['rec']}\n🎯Cible : {o_prud}\n{t}"
            txt_a = f"Mouvement du marché\nBTC : {d['btc']['b']} Buy | {d['btc']['s']} Sell\nOR : {d['or']['b']} Buy | {d['or']['s']} Sell"

            try:
                bot.edit_message_text(txt_b, chat_id, live_btc_id)
                bot.edit_message_text(txt_o, chat_id, live_or_id)
                bot.edit_message_text(txt_a, chat_id, live_analyse_id)
            except Exception as e:
                print(f"Erreur d'édition : {e}")
        else:
            print("Echec de récupération des données, nouvelle tentative dans 10s...")
            time.sleep(30)
            continue

        time.sleep(60)

@bot.message_handler(commands=['start'])
def start(message):
    global live_btc_id, live_or_id, live_analyse_id

    chat_id = message.chat.id

    bot.send_message(
        chat_id,
        "Bienvenu !\nBot Gold Predictor v3 Activé.\nSuivi en cours... 📡"
    )

    # BTC
    msg_btc = bot.send_message(chat_id, "Connexion BTC...")
    live_btc_id = msg_btc.message_id

    # OR
    msg_or = bot.send_message(chat_id, "Connexion OR...")
    live_or_id = msg_or.message_id

    # ANALYSE
    msg_analyse = bot.send_message(chat_id, "Calcul mouvements...")
    live_analyse_id = msg_analyse.message_id

    # Lancer le moteur sans bloquer le bot
    thread = threading.Thread(
        target=moteur_principal,
        args=(chat_id,)
    )
    thread.daemon = True
    thread.start()


print("Bot en ligne...")
bot.polling(none_stop=True)
