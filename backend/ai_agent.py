import os
import csv
import time
import re
import requests
import json
import speech_recognition as sr

TWILIO_SID = os.getenv('TWILIO_SID', 'ACff9ab56f6046298714a4b29773ccf932')
TWILIO_TOKEN = os.getenv('TWILIO_TOKEN', '74df57a3673b78e90a87917dc2336fa1')
TWILIO_NUMBER = os.getenv('TWILIO_NUMBER', '+16466998764')

class AIAgent:
    def __init__(self):
        print("[AIAgent] Initialized with Google Speech Recognition")
        self.technicians = self.load_technicians()

    def load_technicians(self):
        techs = []
        try:
            with open('technicians.csv', 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    techs.append(row)
            print(f"[AIAgent] Loaded {len(techs)} technicians")
        except Exception as e:
            print(f"[AIAgent] Error loading technicians: {e}")
        return techs

    def transcribe_audio(self, audio_path):
        try:
            recognizer = sr.Recognizer()
            
            # Works with any audio format (WebM, WAV, MP3, etc.)
            with sr.AudioFile(audio_path) as source:
                # Adjust for ambient noise
                recognizer.adjust_for_ambient_noise(source, duration=0.2)
                audio_data = recognizer.record(source)
                
            # Use Google Speech Recognition (free, no API key)
            text = recognizer.recognize_google(audio_data)
            
            print(f"[Google API] ✅ Transcribed: {text}")
            return text
            
        except sr.UnknownValueError:
            print("[Google API] Could not understand audio")
            return ''
        except sr.RequestError as e:
            print(f"[Google API] Service error: {e}")
            return ''
        except Exception as e:
            print(f"[Google API] Unexpected error: {e}")
            return ''

    def _has_word(self, text: str, words: list[str]) -> bool:
        t = (text or '').lower()
        return any(re.search(rf'\b{re.escape(w.lower())}\b', t) for w in words)

    def infer_problem_type(self, text):
        if self._has_word(text, ['vpn','remote','access']): return 'VPN Problem'
        if self._has_word(text, ['wifi','wi-fi','internet','network','connection','connect']): return 'WiFi Down'
        if self._has_word(text, ['printer','print','printing']): return 'Printer Error'
        if self._has_word(text, ['account','login','password','locked','access denied']): return 'Account Locked'
        if self._has_word(text, ['cloud','aws','azure','storage']): return 'Cloud Failure'
        if self._has_word(text, ['software','application','bug','crash','error']): return 'Software Bug'
        if self._has_word(text, ['billing','payment','invoice','charge']): return 'Billing Issue'
        if self._has_word(text, ['database','db','sql','data']): return 'Database Crash'
        if self._has_word(text, ['security','breach','hack','malware','virus']): return 'Security Breach'
        if self._has_word(text, ['server','overload','slow','performance']): return 'Server Overload'
        if self._has_word(text, ['email','smtp','outlook']): return 'Email Failure'
        if self._has_word(text, ['backup','restore','recovery']): return 'Data Backup Failure'
        if self._has_word(text, ['firewall','port','blocked']): return 'Firewall Error'
        return 'Software Bug'

    def get_diagnostic_questions(self, ptype):
        q = {
            'VPN Problem': ["Can you access the VPN login page?","What error message appears when you try to connect?"],
            'WiFi Down': ["Are other devices unable to connect too?","Have you tried restarting the router?"],
            'Printer Error': ["Is the printer powered on and connected?","Do you see any error lights or messages on the printer?"],
            'Account Locked': ["When did you last successfully log in?","Have you tried resetting your password?"],
            'Cloud Failure': ["Which cloud service is affected?","When did you first notice the issue?"],
            'Software Bug': ["Which application is experiencing the bug?","Can you reproduce the issue consistently?"],
            'Billing Issue': ["What is your account number or invoice ID?","Can you describe the billing discrepancy?"],
            'Database Crash': ["Which database system is affected?","When did the crash occur?"],
            'Security Breach': ["What type of security issue have you noticed?","When did you first detect the breach?"],
            'Server Overload': ["Which server or service is affected?","What is the current CPU or memory usage?"],
            'Email Failure': ["Are you unable to send or receive emails?","What error message do you see?"],
            'Data Backup Failure': ["When was the last successful backup?","What error message appears during backup?"],
            'Firewall Error': ["Which port or service is being blocked?","When did this firewall issue start?"]
        }
        return q.get(ptype, ["Can you describe the issue in more detail?","When did this problem first occur?"])

    def _dispatch_intent(self, text: str) -> bool:
        if not text: return False
        t = text.lower()
        phrases = [
            'call the technician','call technician','call tech','please call technician',
            'send technician','send someone','dispatch','escalate',
            'book appointment','schedule visit','need onsite','need on-site',
            'come now','visit asap','repair now','send engineer'
        ]
        return any(p in t for p in phrases)

    def is_urgent(self, text: str) -> bool:
        if not text: return False
        t = text.lower().strip()
        if any(w in t for w in ['urgent','critical','immediately','asap','now','emergency','high priority']): return True
        if any(w in t for w in ['जरूरी','तुरंत','इमरजेंसी','अभी']): return True
        if any(w in t for w in ['ತುರ್ತು','ತಕ್ಷಣ','அவசரம்','உடனே','అత్యవసరం','ఇప్పుడే']): return True
        if any(w in t for w in ['عاجل','فوراً','فورا','ضروری','فوری']): return True
        return False

    def _normalize_phone(self, s: str) -> str:
        if not s: return ""
        s = s.replace(" ", "")
        if s.startswith("+"): return s
        digits = "".join(ch for ch in s if ch.isdigit())
        if len(digits) == 10: return "+91" + digits
        return "+" + digits if digits else ""

    def _extract_time(self, txt: str) -> str | None:
        if not txt: return None
        t = txt.lower()
        m = re.search(r'\b(\d{1,2}(:\d{2})?\s?(am|pm))\b', t)
        if m: return m.group(1).upper()
        m = re.search(r'\b(\d{1,2}:\d{2})\b', t)
        if m: return m.group(1)
        m = re.search(r'\b(in|after)\s+(\d{1,3})\s+(minute|minutes|min)\b', t)
        if m: return f"in {m.group(2)} minutes"
        return None

    def select_technician(self, problem_type):
        for tech in self.technicians:
            if tech.get('Problem Type','').strip()==problem_type and tech.get('Availability','').strip()=='24x7':
                return tech
        for tech in self.technicians:
            if tech.get('Problem Type','').strip()==problem_type:
                return tech
        for tech in self.technicians:
            if tech.get('Availability','').strip()=='24x7':
                return tech
        return self.technicians[0] if self.technicians else None

    def call_technician(self, technician, user_problem, diag_answers):
        if not technician:
            return {'final': "No technician available at the moment. Please contact support directly.", 'events': ["No technician available right now."]}
        tech_name = technician.get('Name','Unknown')
        tech_phone = self._normalize_phone(technician.get('Contact',''))
        tech_skillset = technician.get('Skillset','General Support')
        if not tech_phone:
            return {'final': f"Selected {tech_name}, but no contact number available.", 'events': [f"Could not call {tech_name}: missing number."]}

        diag_summary = ' '.join(diag_answers) if diag_answers else 'No additional details provided'
        summary = f"New urgent IT support case. User problem: {user_problem}. Additional details: {diag_summary}."
        events = ["Call connected. Awaiting technician response..."]

        try:
            twiml = (
                "<Response>"
                  f"<Say>{summary}</Say>"
                  "<Pause length='1'/>"
                  "<Say>Please say the earliest time you can visit, for example: I can come at 3 PM.</Say>"
                  "<Record maxLength='15' playBeep='true'/>"
                  "<Pause length='1'/>"
                  "<Say>Thanks. Please confirm the appointment by saying yes or no.</Say>"
                  "<Record maxLength='5' playBeep='true'/>"
                "</Response>"
            )
            twiml_url = "https://twimlets.com/echo?Twiml=" + requests.utils.quote(twiml, safe='')
            call_url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Calls.json"
            data = {'To': tech_phone, 'From': TWILIO_NUMBER, 'Url': twiml_url}
            resp = requests.post(call_url, data=data, auth=(TWILIO_SID, TWILIO_TOKEN), timeout=15)

            if resp.status_code not in (200, 201):
                try:
                    j = resp.json()
                    code = j.get('code'); msg = j.get('message') or j.get('more_info') or resp.text
                    events.append(f"Twilio error: code={code}, msg={msg}")
                except Exception:
                    events.append(f"Twilio error: {resp.text}")
                    code = None
                if code in (21219, 21614, 21215, 21217):
                    return {'final': ("Unable to place the call due to Twilio permissions or an unverified destination number. "
                                      "Verify the destination number and Voice Geo Permissions in Twilio, then try again."), 'events': events}
                return {'final': "Unable to reach a technician now. Your urgent ticket is escalated; expect a call within 30 minutes.", 'events': events}

            call_sid = resp.json().get('sid','')
            time.sleep(18)
            recordings_url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Calls/{call_sid}/Recordings.json"
            recs = requests.get(recordings_url, auth=(TWILIO_SID, TWILIO_TOKEN), timeout=15)
            items = []
            if recs.status_code == 200:
                items = recs.json().get('recordings', [])
            if not items:
                time.sleep(6)
                recs2 = requests.get(recordings_url, auth=(TWILIO_SID, TWILIO_TOKEN), timeout=15)
                if recs2.status_code == 200:
                    items = recs2.json().get('recordings', [])
            if not items:
                return {'final': f"Called {tech_name}. Awaiting their confirmation; you will receive a callback shortly.", 'events': ["Technician did not leave a response yet."]}

            def created_key(item): return item.get('date_created') or item.get('sid')
            items = sorted(items, key=created_key)

            def fetch_and_transcribe(sid: str) -> str:
                rurl = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Recordings/{sid}.wav"
                r = requests.get(rurl, auth=(TWILIO_SID, TWILIO_TOKEN), timeout=15)
                if r.status_code != 200: return ""
                tmp = "temp_rec.wav"
                with open(tmp, "wb") as f: f.write(r.content)
                txt = self.transcribe_audio(tmp)
                try: os.unlink(tmp)
                except Exception: pass
                return txt

            time_answer = fetch_and_transcribe(items[0]['sid'])
            confirm_answer = fetch_and_transcribe(items[-1]['sid']) if len(items)>1 else ""

            if time_answer:   events.append(f'Technician time: "{time_answer}"')
            if confirm_answer: events.append(f'Technician confirmation: "{confirm_answer}"')

            appt_time = self._extract_time(time_answer)
            low = (confirm_answer or "").lower()
            confirmed = any(x in low for x in ["yes","ok","okay","sure","confirm"])
            declined  = any(x in low for x in ["no","can't","cannot","busy","decline"])

            if confirmed and not declined:
                when = appt_time or "as soon as possible"
                return {'final': f"Appointment confirmed with {tech_name} ({tech_skillset}) at {when}. You will receive a call or visit shortly.", 'events': events}
            elif declined:
                return {'final': f"{tech_name} is unavailable. Escalating to the next technician; you will receive a callback soon.", 'events': events}
            else:
                maybe = appt_time or "soon"
                return {'final': f"{tech_name} proposed {maybe} but did not clearly confirm. Dispatch will follow up to finalize.", 'events': events}

        except requests.Timeout:
            events.append("Technician call timed out.")
            return {'final': "Technician call timed out. Dispatch will retry shortly.", 'events': events}
        except Exception as e:
            events.append("Unexpected telephony error.")
            return {'final': "Technical error while contacting technician. Your urgent ticket has been logged; support will call you within 30 minutes.", 'events': events}

    def process_conversation(self, step, transcript, diag_qns, diag_idx, diag_answers, user_problem, problem_type):
        if step == 'greet':
            return {'transcript': '', 'agentMessage': 'Hello! Welcome to IT Support. Please describe your problem.',
                    'events': [], 'diagQns': [], 'diagIdx': 0, 'diagAnswers': [],
                    'userProblem': '', 'problemType': '', 'nextStep': 'describe_problem'}

        elif step == 'describe_problem':
            if not transcript:
                return {'transcript': '', 'agentMessage': "I didn't catch that. Please describe your problem again.",
                        'events': [], 'diagQns': [], 'diagIdx': 0, 'diagAnswers': [],
                        'userProblem': '', 'problemType': '', 'nextStep': 'describe_problem'}
            problem_type = self.infer_problem_type(transcript)
            if self._dispatch_intent(transcript) or self.is_urgent(transcript):
                tech = self.select_technician(problem_type)
                tech_name = tech.get('Name','on-call technician') if tech else 'on-call technician'
                return {
                    'transcript': transcript,
                    'agentMessage': f'Calling {tech_name}...',
                    'events': [],
                    'diagQns': [], 'diagIdx': 0, 'diagAnswers': [],
                    'userProblem': transcript, 'problemType': problem_type,
                    'nextStep': 'calling'
                }
            questions = self.get_diagnostic_questions(problem_type)
            return {'transcript': transcript, 'agentMessage': f"I understand you're experiencing a {problem_type}. {questions[0]}",
                    'events': [], 'diagQns': questions, 'diagIdx': 0, 'diagAnswers': [],
                    'userProblem': transcript, 'problemType': problem_type, 'nextStep': 'diagnostic'}

        elif step == 'diagnostic':
            diag_answers.append(transcript)
            if self._dispatch_intent(transcript) or self.is_urgent(transcript):
                tech = self.select_technician(problem_type)
                tech_name = tech.get('Name','on-call technician') if tech else 'on-call technician'
                return {
                    'transcript': transcript,
                    'agentMessage': f'Calling {tech_name}...',
                    'events': [],
                    'diagQns': diag_qns, 'diagIdx': len(diag_answers), 'diagAnswers': diag_answers,
                    'userProblem': user_problem, 'problemType': problem_type,
                    'nextStep': 'calling'
                }
            diag_idx += 1
            if diag_idx < len(diag_qns):
                return {'transcript': transcript, 'agentMessage': diag_qns[diag_idx], 'events': [],
                        'diagQns': diag_qns, 'diagIdx': diag_idx, 'diagAnswers': diag_answers,
                        'userProblem': user_problem, 'problemType': problem_type, 'nextStep': 'diagnostic'}
            return {'transcript': transcript, 'agentMessage': 'Thank you. Is this issue urgent and needs immediate attention?',
                    'events': [], 'diagQns': diag_qns, 'diagIdx': diag_idx, 'diagAnswers': diag_answers,
                    'userProblem': user_problem, 'problemType': problem_type, 'nextStep': 'urgency'}

        elif step == 'urgency':
            t = (transcript or '').lower()
            yes_tokens = ['yes','y','yeah','yep','ok','okay','sure','please do','go ahead','confirm']
            if self._dispatch_intent(transcript) or self.is_urgent(transcript) or any(re.search(rf'\b{re.escape(y)}\b', t) for y in yes_tokens):
                tech = self.select_technician(problem_type)
                tech_name = tech.get('Name','on-call technician') if tech else 'on-call technician'
                return {
                    'transcript': transcript,
                    'agentMessage': f'Calling {tech_name}...',
                    'events': [],
                    'diagQns': diag_qns, 'diagIdx': diag_idx, 'diagAnswers': diag_answers,
                    'userProblem': user_problem, 'problemType': problem_type,
                    'nextStep': 'calling'
                }
            else:
                return {'transcript': transcript, 'agentMessage': 'No problem. A support ticket has been created. Our team will reach out within 24 hours.',
                        'events': [], 'diagQns': diag_qns, 'diagIdx': diag_idx, 'diagAnswers': diag_answers,
                        'userProblem': user_problem, 'problemType': problem_type, 'nextStep': 'complete'}

        elif step == 'calling':
            tech = self.select_technician(problem_type)
            result = self.call_technician(tech, user_problem, diag_answers)
            return {'transcript': transcript, 'agentMessage': result.get('final',''), 'events': result.get('events', []),
                    'diagQns': diag_qns, 'diagIdx': diag_idx, 'diagAnswers': diag_answers,
                    'userProblem': user_problem, 'problemType': problem_type, 'nextStep': 'complete'}

        else:
            return {'transcript': transcript, 'agentMessage': 'This conversation is complete. Please refresh to start a new session.',
                    'events': [], 'diagQns': diag_qns, 'diagIdx': diag_idx, 'diagAnswers': diag_answers,
                    'userProblem': user_problem, 'problemType': problem_type, 'nextStep': 'complete'}
