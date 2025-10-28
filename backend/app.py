from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import base64, os, re, tempfile, requests, subprocess
from ai_agent import AIAgent
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)
agent = AIAgent()

ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY')
ELEVENLABS_VOICE_ID = os.getenv('ELEVENLABS_VOICE_ID')

def save_base64_audio_to_temp(data_url: str) -> str:
    if not data_url: return ""
    header, b64 = ("", data_url)
    if "," in data_url: header, b64 = data_url.split(",", 1)
    
    audio_bytes = base64.b64decode(b64)
    
    # Save original audio
    with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as tmp:
        tmp.write(audio_bytes)
        webm_path = tmp.name
    
    # Convert to WAV using ffmpeg (if available) or return as-is
    wav_path = webm_path.replace('.webm', '.wav')
    
    try:
        # Try using ffmpeg if installed
        result = subprocess.run(
            ['ffmpeg', '-i', webm_path, '-ar', '16000', '-ac', '1', '-y', wav_path],
            capture_output=True,
            timeout=10
        )
        
        if result.returncode == 0 and os.path.exists(wav_path):
            print(f"[Converted] {wav_path}")
            try:
                os.unlink(webm_path)
            except:
                pass
            return wav_path
        else:
            print("[Conversion] FFmpeg failed, using original")
            return webm_path
            
    except FileNotFoundError:
        print("[Conversion] FFmpeg not found, using WebM directly")
        return webm_path
    except Exception as e:
        print(f"[Conversion Error] {e}")
        return webm_path

@app.route('/conversation', methods=['POST'])
def conversation():
    try:
        data = request.get_json(force=True) or {}
        audio_base64 = data.get('audioBase64', '')
        step         = data.get('step', 'greet')
        diag_qns     = data.get('diagQns', [])
        diag_idx     = data.get('diagIdx', 0)
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
                try: os.unlink(tmp_path)
                except Exception: pass

        resp = agent.process_conversation(
            step=step, transcript=transcript, diag_qns=diag_qns, diag_idx=diag_idx,
            diag_answers=diag_answers, user_problem=user_problem, problem_type=problem_type
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

@app.route('/tts', methods=['POST'])
def tts():
    try:
        text = request.json.get('text', '')
        if not text:
            return jsonify({'error': 'No text provided'}), 400
        
        if not ELEVENLABS_API_KEY:
            return jsonify({'error': 'ELEVENLABS_API_KEY not set'}), 500
        
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
        
        if response.status_code != 200:
            return jsonify({'error': f'ElevenLabs API error: {response.text}'}), response.status_code
        
        tmp_path = tempfile.mktemp(suffix='.mp3')
        with open(tmp_path, 'wb') as f:
            f.write(response.content)
        
        return send_file(tmp_path, mimetype="audio/mpeg", as_attachment=False, download_name="speech.mp3")
    
    except Exception as e:
        print(f"[TTS Error] {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
