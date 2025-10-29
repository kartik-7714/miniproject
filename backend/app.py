import os
import tempfile
import base64
import subprocess
import requests
import time
from flask import Flask, request, jsonify, send_file, Response
from flask_cors import CORS
from ai_agent import AIAgent
from dotenv import load_dotenv
from twilio.twiml.voice_response import VoiceResponse

load_dotenv()

app = Flask(__name__)
CORS(app)
agent = AIAgent()

ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY')
ELEVENLABS_VOICE_ID = os.getenv('ELEVENLABS_VOICE_ID')
TWILIO_SID = os.getenv('TWILIO_SID', 'ACff9ab56f6046298714a4b29773ccf932')
TWILIO_TOKEN = os.getenv('TWILIO_TOKEN', '74df57a3673b78e90a87917dc2336fa1')

# Store conversation context per call (use Redis/DB in production)
call_contexts = {}

def save_base64_audio_to_temp(data_url: str) -> str:
    if not data_url:
        return ""
    header, b64 = ("", data_url)
    if "," in data_url:
        header, b64 = data_url.split(",", 1)
    audio_bytes = base64.b64decode(b64)
    with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as tmp:
        tmp.write(audio_bytes)
        webm_path = tmp.name
    wav_path = webm_path.replace('.webm', '.wav')
    try:
        ffmpeg_binary = os.path.join(os.path.dirname(__file__), "ffmpeg.exe")
        result = subprocess.run(
            [ffmpeg_binary, '-i', webm_path, '-ar', '16000', '-ac', '1', '-y', wav_path],
            capture_output=True,
            timeout=10
        )
        if result.returncode == 0 and os.path.exists(wav_path):
            print(f"[Converted] {wav_path}")
            try:
                os.unlink(webm_path)
            except Exception:
                pass
            return wav_path
        else:
            print("[Conversion] FFmpeg failed, using webm directly")
            print(result.stderr.decode())
            return webm_path
    except Exception as e:
        print(f"[Conversion Error] {e}")
        return webm_path

def transcribe_recording(recording_url):
    """Download and transcribe a Twilio recording"""
    try:
        audio_response = requests.get(recording_url, auth=(TWILIO_SID, TWILIO_TOKEN), timeout=10)
        if audio_response.status_code != 200:
            return "unknown"
        
        tmp_path = tempfile.mktemp(suffix='.wav')
        with open(tmp_path, 'wb') as f:
            f.write(audio_response.content)
        
        transcript = agent.transcribe_audio(tmp_path)
        
        try:
            os.unlink(tmp_path)
        except:
            pass
        
        return transcript if transcript else "unknown"
    except Exception as e:
        print(f"[Transcription error] {e}")
        return "unknown"

@app.route('/conversation', methods=['POST'])
def conversation():
    try:
        data = request.get_json(force=True) or {}
        audio_base64 = data.get('audioBase64', '')
        step = data.get('step', 'greet')
        diag_qns = data.get('diagQns', [])
        diag_idx = data.get('diagIdx', 0)
        diag_answers = data.get('diagAnswers', [])
        user_problem = data.get('userProblem', '')
        problem_type = data.get('problemType', '')
        transcript = ''
        tmp_path = ""
        try:
            if audio_base64 and step != 'greet':
                tmp_path = save_base64_audio_to_temp(audio_base64)
                transcript = agent.transcribe_audio(tmp_path)
                print(f"[Transcript] {transcript}")
        except Exception as e:
            print(f"[Transcription Error] {e}")
            transcript = ''
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

        resp = agent.process_conversation(
            step, transcript, diag_qns, diag_idx, diag_answers, user_problem, problem_type
        )
        return jsonify(resp), 200

    except Exception as e:
        print(f"[Error] {e}")
        return jsonify({
            'transcript': '',
            'agentMessage': f'Backend error: {str(e)}',
            'events': [],
            'diagQns': [], 'diagIdx': 0, 'diagAnswers': [],
            'userProblem': '', 'problemType': '', 'nextStep': 'complete'
        }), 200

@app.route('/twilio-ivr', methods=['POST', 'GET'])
def twilio_ivr():
    """Simple IVR using Gather instead of Record for reliability"""
    call_sid = request.values.get('CallSid', 'unknown')
    step = request.values.get('step', 'greet')
    speech_result = request.values.get('SpeechResult', '')
    user_problem = request.values.get('problem', 'a technical issue')
    
    print(f"[IVR] CallSid: {call_sid}, Step: {step}, Speech: {speech_result}, Problem: {user_problem}")
    
    response = VoiceResponse()
    
    # Initialize context
    if call_sid not in call_contexts:
        call_contexts[call_sid] = {
            'user_problem': user_problem,
            'tech_name': '',
            'appointment_time': '',
            'confirmed': False
        }
    
    ctx = call_contexts[call_sid]
    
    if step == 'greet':
        print("[IVR] Greeting step")
        response.say(
            "Hello, this is the AI support agent from IT Support. May I know who I am speaking with?",
            voice='Polly.Joanna',
            language='en-US'
        )
        
        gather = response.gather(
            input='speech',
            timeout=5,
            speech_timeout='auto',
            action=f'/twilio-ivr?step=got_name&problem={requests.utils.quote(user_problem)}',
            method='POST'
        )
        
        # If no input, repeat
        response.say("I didn't hear anything. Please try again.", voice='Polly.Joanna')
        response.redirect(f'/twilio-ivr?step=greet&problem={requests.utils.quote(user_problem)}')
    
    elif step == 'got_name':
        print(f"[IVR] Got name: {speech_result}")
        ctx['tech_name'] = speech_result if speech_result else "technician"
        
        response.say(
            f"Thank you, {ctx['tech_name']}. The user reported: {ctx['user_problem']}. This is urgent.",
            voice='Polly.Joanna',
            language='en-US'
        )
        response.pause(length=1)
        response.say(
            "What is the earliest time you can visit or call the user?",
            voice='Polly.Joanna',
            language='en-US'
        )
        
        gather = response.gather(
            input='speech',
            timeout=5,
            speech_timeout='auto',
            action=f'/twilio-ivr?step=got_time&problem={requests.utils.quote(user_problem)}',
            method='POST'
        )
        
        response.say("I didn't hear a time. Let me try again.", voice='Polly.Joanna')
        response.redirect(f'/twilio-ivr?step=got_name&problem={requests.utils.quote(user_problem)}')
    
    elif step == 'got_time':
        print(f"[IVR] Got time: {speech_result}")
        ctx['appointment_time'] = speech_result if speech_result else "your earliest convenience"
        
        response.say(
            f"Great. So you can visit at {ctx['appointment_time']}.",
            voice='Polly.Joanna',
            language='en-US'
        )
        response.pause(length=1)
        response.say(
            "Please say yes to confirm, or no if you cannot make it.",
            voice='Polly.Joanna',
            language='en-US'
        )
        
        gather = response.gather(
            input='speech',
            timeout=5,
            speech_timeout='auto',
            action=f'/twilio-ivr?step=confirmation&problem={requests.utils.quote(user_problem)}',
            method='POST'
        )
        
        response.say("I didn't hear a response.", voice='Polly.Joanna')
        response.redirect(f'/twilio-ivr?step=got_time&problem={requests.utils.quote(user_problem)}')
    
    elif step == 'confirmation':
        print(f"[IVR] Confirmation: {speech_result}")
        confirmation = speech_result.lower() if speech_result else ""
        ctx['confirmed'] = 'yes' in confirmation or 'confirm' in confirmation or 'sure' in confirmation or 'okay' in confirmation
        
        if ctx['confirmed']:
            response.say(
                f"Perfect! Appointment confirmed for {ctx['appointment_time']}. The user will be notified. Thank you!",
                voice='Polly.Joanna',
                language='en-US'
            )
        else:
            response.say(
                "Understood. We will find another technician. Thank you for your time.",
                voice='Polly.Joanna',
                language='en-US'
            )
        
        response.hangup()
        
        # Clean up
        if call_sid in call_contexts:
            del call_contexts[call_sid]
    
    else:
        print(f"[IVR] Unknown step: {step}")
        response.say(
            "This is IT Support. We will contact you shortly. Thank you.",
            voice='Polly.Joanna',
            language='en-US'
        )
        response.hangup()
    
    print(f"[IVR] Response: {str(response)[:200]}")
    return Response(str(response), mimetype='text/xml')


@app.route('/tts', methods=['POST'])
def tts():
    try:
        text = request.json.get('text', '')
        print("TTS received text:", text)
        if not text:
            return jsonify({'error': 'No text provided'}), 400
        if not ELEVENLABS_API_KEY or not ELEVENLABS_VOICE_ID:
            return jsonify({'error': 'ELEVENLABS API keys not set'}), 500
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
        headers = {
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg"
        }
        payload = {
            "text": text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75
            }
        }
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        print("ElevenLabs status:", response.status_code)
        if response.status_code != 200:
            print("ElevenLabs error:", response.text)
            return jsonify({'error': f'ElevenLabs API error: {response.text}'}), response.status_code

        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp:
            tmp.write(response.content)
            tmp_path = tmp.name

        return send_file(tmp_path, mimetype="audio/mpeg", as_attachment=False, download_name="speech.mp3")
    except Exception as e:
        print(f"[TTS Error] {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
