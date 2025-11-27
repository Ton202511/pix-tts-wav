import os
import hashlib
import logging
import json
import requests
from flask import Flask, request, jsonify, send_from_directory
from gtts import gTTS
from pydub import AudioSegment
import paho.mqtt.client as mqtt

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

AUDIO_DIR = "audios"
os.makedirs(AUDIO_DIR, exist_ok=True)

MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN", "APP_USR-1037853913831408-052223-60fe7c5e6eaa2d8ced682640f5c66216-139586650")
MQTT_BROKER = os.getenv("MQTT_BROKER", "broker.hivemq.com")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "pix/pagamento/notificacao")
BASE_URL = os.getenv("BASE_URL", "https://pix-tts-wav-j9w8.onrender.com")

mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

def conectar_mqtt():
    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_start()
        app.logger.info(f"✅ MQTT: {MQTT_BROKER}:{MQTT_PORT}")
    except Exception as e:
        app.logger.error(f"❌ MQTT: {e}")

def frase_pix(nome, valor):
    valor_str = f"{valor:.2f}".replace(".", ",")
    return f"Pix recebido de {nome}, no valor de {valor_str} reais"

def make_id(nome, valor):
    return hashlib.sha1(f"{nome}|{valor}".encode()).hexdigest()[:12]

def wav_path(audio_id):
    return os.path.join(AUDIO_DIR, f"{audio_id}.wav")

def gerar_audio(nome, valor):
    audio_id = make_id(nome, valor)
    path = wav_path(audio_id)
    
    if os.path.exists(path):
        return audio_id, f"{BASE_URL}/audio/{audio_id}.wav"
    
    try:
        frase = frase_pix(nome, valor)
        app.logger.info(f"🗣️ {frase}")
        
        temp_mp3 = os.path.join(AUDIO_DIR, f"{audio_id}.mp3")
        tts = gTTS(frase, lang="pt", slow=False)
        tts.save(temp_mp3)
        
        sound = AudioSegment.from_mp3(temp_mp3)
        sound = sound.set_frame_rate(44100).set_channels(2).set_sample_width(2)
        sound.export(path, format="wav")
        
        os.remove(temp_mp3)
        
        audio_url = f"{BASE_URL}/audio/{audio_id}.wav"
        app.logger.info(f"✅ {audio_url}")
        return audio_id, audio_url
        
    except Exception as e:
        app.logger.error(f"❌ Áudio: {e}")
        raise

def publicar_mqtt(nome, valor, audio_url):
    try:
        payload = json.dumps({
            "nome": nome,
            "valor": valor,
            "audio_url": audio_url
        })
        
        result = mqtt_client.publish(MQTT_TOPIC, payload, qos=1)
        
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            app.logger.info(f"📡 MQTT OK")
        else:
            app.logger.warning(f"⚠️ MQTT falhou")
            
    except Exception as e:
        app.logger.error(f"❌ MQTT: {e}")

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

@app.route("/webhook/mercadopago", methods=["POST"])
def webhook_mercadopago():
    try:
        data = request.get_json(force=True)
        
        if data.get("action") != "payment.created":
            return jsonify({"status": "ignored"}), 200
        
        payment_id = data.get("data", {}).get("id")
        if not payment_id:
            return jsonify({"error": "missing payment_id"}), 400
        
        headers = {"Authorization": f"Bearer {MP_ACCESS_TOKEN}"}
        url = f"https://api.mercadopago.com/v1/payments/{payment_id}"
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        payment = resp.json()
        
        if payment.get("payment_method_id") != "pix":
            return jsonify({"status": "not_pix"}), 200
        
        if payment.get("status") != "approved":
            return jsonify({"status": "not_approved"}), 200
        
        nome = payment.get("payer", {}).get("first_name", "Cliente")
        valor = float(payment.get("transaction_amount", 0))
        
        app.logger.info(f"💰 PIX: {nome} - R$ {valor:.2f}")
        
        audio_id, audio_url = gerar_audio(nome, valor)
        publicar_mqtt(nome, valor, audio_url)
        
        return jsonify({
            "status": "processed",
            "audio_id": audio_id,
            "audio_url": audio_url
        }), 200
        
    except Exception as e:
        app.logger.error(f"❌ Webhook: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/tts", methods=["POST"])
def tts_manual():
    try:
        data = request.get_json(force=True)
        nome = data.get("nome", "")
        valor = float(data.get("valor", 0))
        
        if not nome or valor <= 0:
            return jsonify({"error": "nome e valor são obrigatórios"}), 400
        
        audio_id, audio_url = gerar_audio(nome, valor)
        publicar_mqtt(nome, valor, audio_url)
        
        return jsonify({
            "audio_id": audio_id,
            "audio_url": audio_url
        })
        
    except Exception as e:
        app.logger.error(f"❌ TTS: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/audio/<audio_id>.wav")
def serve_audio(audio_id):
    path = wav_path(audio_id)
    if not os.path.exists(path):
        return jsonify({"error": "not found"}), 404
    
    return send_from_directory(AUDIO_DIR, f"{audio_id}.wav", mimetype="audio/wav")

@app.route("/test/mqtt", methods=["POST"])
def test_mqtt():
    try:
        data = request.get_json(force=True)
        nome = data.get("nome", "Teste")
        valor = float(data.get("valor", 10.0))
        
        audio_id, audio_url = gerar_audio(nome, valor)
        publicar_mqtt(nome, valor, audio_url)
        
        return jsonify({"status": "ok", "audio_url": audio_url})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    conectar_mqtt()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
