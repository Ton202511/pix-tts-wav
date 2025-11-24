import os, time, json, threading, hashlib
from flask import Flask, request, jsonify, send_from_directory
from gtts import gTTS
from pydub import AudioSegment

app = Flask(__name__)

AUDIO_DIR = "audios"
os.makedirs(AUDIO_DIR, exist_ok=True)

def frase_pix(nome, valor):
    return f"PIX recebido de {nome}, valor {valor}."

def make_id(nome, valor):
    return hashlib.sha1(f"{nome}|{valor}".encode()).hexdigest()[:8]

def wav_path(audio_id):
    return os.path.join(AUDIO_DIR, f"{audio_id}.wav")

def gerar_audio(nome, valor):
    audio_id = make_id(nome, valor)
    path = wav_path(audio_id)
    if not os.path.exists(path):
        frase = frase_pix(nome, valor)
        temp_mp3 = os.path.join(AUDIO_DIR, f"{audio_id}.mp3")
        gTTS(frase, lang="pt").save(temp_mp3)
        sound = AudioSegment.from_mp3(temp_mp3)
        sound.export(path, format="wav")
        os.remove(temp_mp3)
    return audio_id, f"/audio/{audio_id}.wav"

@app.route("/tts", methods=["POST"])
def tts():
    d = request.get_json(force=True)
    nome, valor = d.get("nome",""), d.get("valor_texto","")
    if not nome or not valor:
        return jsonify({"error":"faltam campos"}), 400
    audio_id, audio_url = gerar_audio(nome, valor)
    return jsonify({"audio_id": audio_id, "audio_url": audio_url})

@app.route("/audio/<audio_id>.wav")
def audio(audio_id):
    path = wav_path(audio_id)
    if not os.path.exists(path):
        return jsonify({"error":"not_found"}), 404
    return send_from_directory(AUDIO_DIR, f"{audio_id}.wav", mimetype="audio/wav")

@app.route("/health")
def health():
    return jsonify({"status":"ok"})
