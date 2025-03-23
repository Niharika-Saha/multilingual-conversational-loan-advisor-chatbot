import os 
import requests
import uuid
import socket
import subprocess
import time
import shutil
import base64
from flask import Flask, request, send_from_directory
from dotenv import load_dotenv
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import google.generativeai as genai  # Gemini AI integration
from gemini_chatbot import check_loan_eligibility, gemini_loan_insights
import boto3



load_dotenv()

AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")  # Default to us-east-1
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")  # Your S3 bucket name

# Initialize S3 client
s3_client = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION
)

app = Flask(__name__)
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")  # Gemini API key
NGROK_URL = os.getenv("NGROK_URL", "")  # Optional ngrok URL for local development

# Get the base directory of the application
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Validate environment variables
if not SARVAM_API_KEY:
    raise ValueError("SARVAM_API_KEY is not set.")
if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
    raise ValueError("Twilio credentials are not set.")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY is not set.")

# Configure Gemini API
genai.configure(api_key=GEMINI_API_KEY)
genai.configured = True

# Initialize Twilio client
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Check internet connectivity
try:
    socket.gethostbyname('www.google.com')
    print("Internet connectivity test successful")
except Exception as e:
    print(f"Internet connectivity test failed: {str(e)}")


def download_audio(url, message_sid):
    """Downloads an audio file from the given Twilio media URL."""
    try:
        print(f"Attempting to download audio from: {url}")

        response = requests.get(url, auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN))

        print(f"HTTP Status Code: {response.status_code}")
        if response.status_code != 200:
            print(f"Response Text: {response.text}")
            return None

        # Save the file with a unique name based on the message SID
        temp_dir = os.path.join(BASE_DIR, "temp")
        os.makedirs(temp_dir, exist_ok=True)

        file_path = os.path.join(temp_dir, f"audio_file_{message_sid}_{uuid.uuid4()}.mp4")
        with open(file_path, "wb") as file:
            file.write(response.content)

        print(f"Audio file successfully saved at: {file_path}")
        return file_path

    except Exception as e:
        print(f"Error downloading audio: {str(e)}")
        return None


def convert_audio(input_path):
    """Converts an audio file to WAV format (16kHz, mono)."""
    try:
        output_path = os.path.splitext(input_path)[0] + ".wav"
        print(f"Converting {input_path} to {output_path}")
        
        # Check if ffmpeg is installed and in PATH
        ffmpeg_command = None
        
        # Try standard command first
        if shutil.which("ffmpeg") is not None:
            ffmpeg_command = "ffmpeg"
        else:
            # Common Windows ffmpeg locations
            potential_paths = [
                r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
                r"C:\ffmpeg\bin\ffmpeg.exe",
                r"C:\ProgramData\chocolatey\bin\ffmpeg.exe",
                os.path.join(BASE_DIR, "ffmpeg", "bin", "ffmpeg.exe"),
                os.path.join(BASE_DIR, "ffmpeg.exe")
            ]
            
            for path in potential_paths:
                if os.path.exists(path):
                    ffmpeg_command = f'"{path}"'  # Quote the path in case it contains spaces
                    print(f"Found ffmpeg at: {path}")
                    break
        
        if not ffmpeg_command:
            print("ffmpeg not found. Please install ffmpeg or add it to PATH.")
            print("Download ffmpeg from: https://ffmpeg.org/download.html")
            print("You can also place ffmpeg.exe in the same directory as this script.")
            return None
            
        # Build the complete command with quotes around paths (important for Windows paths with spaces)
        command = f'{ffmpeg_command} -i "{input_path}" -ar 16000 -ac 1 -c:a pcm_s16le "{output_path}"'
        print(f"Running command: {command}")
        
        # Use shell=True for complex command with paths on Windows
        process = subprocess.run(
            command,
            shell=True,  # Using shell to handle paths with spaces properly
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False  # Don't raise exception on non-zero exit
        )
        
        if process.returncode != 0:
            print(f"ffmpeg stderr: {process.stderr.decode('utf-8')}")
            print(f"ffmpeg failed with return code: {process.returncode}")
            return None
            
        # Verify the file was created
        if os.path.exists(output_path):
            print(f"Successfully converted to: {output_path}")
            return output_path
        else:
            print(f"Output file not found after conversion: {output_path}")
            return None
            
    except Exception as e:
        print(f"Exception in convert_audio: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


def transcribe_audio(file_path, language_code="auto"):
    """Calls test_sarvam_api.py to transcribe the audio."""
    try:
        # Ensure we're using absolute paths
        abs_file_path = os.path.abspath(file_path)
        script_path = os.path.join(BASE_DIR, "test_sarvam_api.py")
        
        print(f"Processing file at absolute path: {abs_file_path}")
        print(f"Using script at: {script_path}")
        
        # Check if file exists
        if not os.path.exists(abs_file_path):
            print(f"Error: Audio file does not exist at path: {abs_file_path}")
            return None
            
        # Convert to WAV format if needed
        file_name, file_ext = os.path.splitext(abs_file_path)
        wav_path = f"{file_name}.wav"
        
        # Convert to WAV if it's not already
        if file_ext.lower() != '.wav':
            print(f"Converting {file_ext} file to WAV: {wav_path}")
            wav_path = convert_audio(abs_file_path)
            if not wav_path:
                print("Failed to convert audio to WAV format")
                return None
            
        # Double-check file exists after conversion
        if not os.path.exists(wav_path):
            print(f"Error: WAV file does not exist after conversion: {wav_path}")
            return None
        
        print(f"Starting transcription of file: {wav_path}")
        
        # Create appropriate environment for subprocess
        env = os.environ.copy()
        env["SARVAM_API_KEY"] = SARVAM_API_KEY
        
        # Now pass the file to the script via command line arguments
        result = subprocess.run(
            ["python", script_path, "--file", wav_path, "--language", language_code],
            capture_output=True,
            text=True,
            env=env
        )
        
        print(f"Subprocess return code: {result.returncode}")
        print(f"Subprocess stdout: {result.stdout}")
        print(f"Subprocess stderr: {result.stderr}")
        
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        else:
            print(f"Transcription failed: {result.stderr}")
            return None
    except Exception as e:
        print(f"Error in transcribe_audio: {str(e)}")
        return None


def detect_language(text):
    """Detects the language of the given text using Sarvam API."""
    try:
        url = "https://api.sarvam.ai/translate"
        
        payload = {
            "input": text,  # Changed from "inputs": [text]
            "source_language_code": "auto",
            "target_language_code": "en"     
        }
        
        headers = {
            "Content-Type": "application/json",
            "api-subscription-key": SARVAM_API_KEY
        }
        
        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code == 200:
            response_json = response.json()
            detected_language = response_json.get("source_language_code", "en-IN")
            print(f"Detected language: {detected_language}")
            
            # Map the detected language to appropriate TTS language code
            language_map = {
                "en": "en-IN",
                "hi": "hi-IN",
                "ta": "ta-IN",
                "te": "te-IN",
                "kn": "kn-IN",
                "ml": "ml-IN",
                "bn": "bn-IN",
                "gu": "gu-IN",
                "mr": "mr-IN",
                "pa": "pa-IN"
            }
            
            return language_map.get(detected_language, "en-IN")
        else:
            print(f"Language detection failed: {response.text}")
            return "en-IN"  # Default to English
    except Exception as e:
        print(f"Error in language detection: {str(e)}")
        return "en-IN"  # Default to English

def text_to_speech(text, language_code="en-IN"):
    """Converts text to speech using Sarvam API."""
    try:
        print(f"Converting text to speech: {text}")
        
        url = "https://api.sarvam.ai/text-to-speech"
        
        # Define appropriate speaker based on language
        speaker = "meera"  # Default for Indian English
        
        # Updated language-speaker mapping with more precise matching
        language_speaker_map = {
            "en-IN": "meera",     # Indian English
            "hi-IN": "indic",     # Hindi
            "ta-IN": "indic",     # Tamil
            "kn-IN": "indic",     # Kannada
            "te-IN": "indic",     # Telugu
            "ml-IN": "indic",     # Malayalam
            "bn-IN": "indic",     # Bengali
            "pa-IN": "indic",     # Punjabi
            "gu-IN": "indic",     # Gujarati
            "mr-IN": "indic"      # Marathi
        }
        
        # Handle cases where we might get just the language code without region
        base_language = language_code.split('-')[0] if '-' in language_code else language_code
        
        # Try exact match first, then try base language
        if language_code in language_speaker_map:
            speaker = language_speaker_map[language_code]
        elif f"{base_language}-IN" in language_speaker_map:
            language_code = f"{base_language}-IN"  # Standardize to Indian variant
            speaker = language_speaker_map[language_code]
        speaker_name = "meera"
        print(f"Using language code: {language_code} with speaker: {speaker_name}")

        payload = {
            "inputs": [text],
            "target_language_code": language_code,
            "speaker": speaker_name,
            "speech_sample_rate": 16000,  # Higher quality for WhatsApp
            "enable_preprocessing": True,
            "model": "bulbul:v1"
        }
        
        # ... rest of the function remains the same ...
        
        headers = {
            "Content-Type": "application/json",
            "api-subscription-key": SARVAM_API_KEY
        }
        
        print(f"Sending TTS request with payload: {payload}")
        
        response = requests.post(url, headers=headers, json=payload)
        
        print(f"TTS API Status Code: {response.status_code}")
        
        if response.status_code == 200:
            # Parse the response
            response_json = response.json()
            
            # Extract the base64 audio
            audio_base64 = response_json.get("audios", [None])[0]
            
            if not audio_base64:
                print("No audio data found in the response")
                return None
                
            # Create temp directory if it doesn't exist
            temp_dir = os.path.join(BASE_DIR, "temp")
            os.makedirs(temp_dir, exist_ok=True)
            
            # Generate a unique filename
            output_file = os.path.join(temp_dir, f"tts_output_{uuid.uuid4()}.wav")
            
            # Save the file
            with open(output_file, "wb") as f:
                f.write(base64.b64decode(audio_base64))
                
            print(f"TTS audio saved to: {output_file}")
            return output_file
        else:
            print(f"Error from TTS API: {response.text}")
            return None
            
    except Exception as e:
        print(f"Error in text_to_speech: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


def translate_text(text, source_lang_code="en", target_lang_code="hi-IN"):
    """Translates text from one language to another using Sarvam API."""
    try:
        # Convert target language code format (e.g., "hi-IN" to "hi")
        if "-" in target_lang_code:
            target_lang = target_lang_code.split("-")[0]
        else:
            target_lang = target_lang_code
            
        url = "https://api.sarvam.ai/translate"
        
        payload = {
            "inputs": [text],
            "source_language_code": source_lang_code,
            "target_language_code": target_lang
        }
        
        headers = {
            "Content-Type": "application/json",
            "api-subscription-key": SARVAM_API_KEY
        }
        
        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code == 200:
            response_json = response.json()
            translated_texts = response_json.get("translated_texts", [])
            if translated_texts and len(translated_texts) > 0:
                return translated_texts[0]
            else:
                print("No translation found in response")
                return text  # Return original text if translation fails
        else:
            print(f"Translation failed: {response.text}")
            return text  # Return original text if translation fails
    except Exception as e:
        print(f"Error in translation: {str(e)}")
        return text  # Return original text if translation fails

def process_with_gemini(text, language_code="en-IN"):
    """Process the text with Gemini API and get a response."""
    try:
        print(f"Sending to Gemini: {text}")
        
        if text.lower() == "help" or text.lower() == "commands":
            help_text = """
            Available commands:
            
            - Normal message: I'll respond conversationally
            - tts:[text]: Convert text to speech
            - loan:income,expenses,cibil_score: Check loan eligibility
            - insights:income,expenses,cibil_score,loan_amount,interest_rate,tenure: Get detailed loan insights
            - help: Show this help message
            """
            
            # Translate help text if needed
            if language_code != "en-IN":
                return translate_text(help_text, "en", language_code)
            return help_text
            
        print(f"Sending to Gemini: {text}")
        # Determine language name for better context
        language_names = {
            "en-IN": "English",
            "hi-IN": "Hindi",
            "ta-IN": "Tamil",
            "te-IN": "Telugu",
            "kn-IN": "Kannada",
            "ml-IN": "Malayalam",
            "bn-IN": "Bengali",
            "gu-IN": "Gujarati", 
            "mr-IN": "Marathi",
            "pa-IN": "Punjabi"
        }
        
        language_name = language_names.get(language_code, "the user's language")
        
        # Create a context/system prompt for the model that includes language instructions
        prompt = f"""
        You are an assistant for an Indian language conversational WhatsApp chatbot.
        The user has sent a message in {language_name}.
        
        Original user message: {text}
        
        Respond to the user query in a helpful, conversational manner.
        Keep your response concise (50-70 words) and direct.
        
        IMPORTANT: Please respond in {language_name}. If you're not sure about the language,
        respond in the same language as the user's message.
        """
        
        # Configure Gemini if not already done
        if not hasattr(genai, 'configured') or not genai.configured:
            genai.configure(api_key=GEMINI_API_KEY)
            genai.configured = True
        
        # Send to Gemini
        model = genai.GenerativeModel("gemini-1.5-pro-latest")
        response = model.generate_content(prompt)
        
        # Extract the response text
        if response and hasattr(response, 'text'):
            print(f"Gemini response: {response.text}")
            return response.text
        else:
            print("No valid response from Gemini")
            # Respond in the detected language if possible
            if language_code == "hi-IN":
                return "मैं आपके अनुरोध को संसाधित नहीं कर सका। कृपया पुनः प्रयास करें।"
            elif language_code == "ta-IN":
                return "உங்கள் கோரிக்கையை செயலாக்க முடியவில்லை. தயவுசெய்து மீண்டும் முயற்சிக்கவும்."
            # Add more fallbacks for other languages as needed
            else:
                return "I couldn't process your request. Please try again."
            
    except Exception as e:
        print(f"Error processing with Gemini: {str(e)}")
        return "Sorry, I encountered an error processing your request."

def upload_to_s3(local_file, s3_file_name=None):
    """
    Uploads an audio file to S3 and returns the public URL.

    :param local_file: Path to the local file
    :param s3_file_name: Name to save in S3 (default: same as local file name)
    :return: Public URL of the uploaded file
    """
    try:
        if s3_file_name is None:
            s3_file_name = os.path.basename(local_file)

        s3_client.upload_file(
            local_file,
            S3_BUCKET_NAME,
            s3_file_name,
            ExtraArgs={'ContentType': 'audio/mp3'}
        )


        # Generate the URL
        s3_url = f"https://{S3_BUCKET_NAME}.s3.amazonaws.com/{s3_file_name}"
        print(f"Uploaded to S3: {s3_url}")
        return s3_url

    except Exception as e:
        print(f"Error uploading to S3: {str(e)}")
        return None


def send_audio_via_twilio(audio_file_path, to_number, from_number):
    """
    Uploads the TTS audio file to S3 and sends it via Twilio WhatsApp.

    :param audio_file_path: Local path of the audio file
    :param to_number: WhatsApp recipient number
    :param from_number: Twilio WhatsApp sender number
    :return: Success status (True/False)
    """
    try:
        print(f"Uploading {audio_file_path} to S3...")
        
        # Ensure the file exists
        if not os.path.exists(audio_file_path):
            print(f"File not found: {audio_file_path}")
            return False

        # Convert audio to MP3 if necessary (optional)
        file_name, file_ext = os.path.splitext(audio_file_path)
        mp3_path = f"{file_name}.mp3"
        
        if file_ext.lower() != ".mp3":
            # Convert to MP3 if needed
            os.rename(audio_file_path, mp3_path)  # Simplified conversion step
            audio_file_path = mp3_path

        # Upload to S3
        s3_file_name = f"audio_{os.path.basename(audio_file_path)}"
        public_url = upload_to_s3(audio_file_path, s3_file_name)

        if not public_url:
            print("Failed to upload audio to S3")
            return False

        # Send audio URL via Twilio
        message = twilio_client.messages.create(
            from_=from_number,
            to=to_number,
            media_url=[public_url]
        )

        print(f"WhatsApp message sent with SID: {message.sid}")
        return True

    except Exception as e:
        print(f"Error sending audio via Twilio: {str(e)}")
        return False
    
def cleanup_old_files(max_age_hours=24):
    """Removes audio files older than the specified age."""
    try:
        temp_dir = os.path.join(BASE_DIR, "temp")
        if not os.path.exists(temp_dir):
            return
            
        current_time = time.time()
        for filename in os.listdir(temp_dir):
            file_path = os.path.join(temp_dir, filename)
            # Check if the file is older than max_age_hours
            if os.path.isfile(file_path) and (current_time - os.path.getmtime(file_path)) > (max_age_hours * 3600):
                print(f"Removing old file: {file_path}")
                os.remove(file_path)
    except Exception as e:
        print(f"Error cleaning up old files: {str(e)}")


@app.route('/webhook', methods=['POST'])
def whatsapp_webhook():
    try:
        print("Received request:", request.form)
        
        # Get the Message SID for unique identification
        message_sid = request.values.get('MessageSid', '')
        print(f"Processing message with SID: {message_sid}")
        
        # Get sender and recipient numbers
        from_number = request.values.get('To', '')
        to_number = request.values.get('From', '')
        
        resp = MessagingResponse()
        num_media = int(request.values.get('NumMedia', 0))

        if num_media > 0:
            media_url = request.values.get('MediaUrl0')
            media_type = request.values.get('MediaContentType0')
            print(f"Media received: {media_type} at {media_url}")

            if 'audio' in media_type:
                # Pass the Message SID to ensure unique file names
                file_path = download_audio(media_url, message_sid)
                if file_path:
                    # Convert the MP4 audio to WAV format for the Sarvam API
                    transcription = transcribe_audio(file_path)
                
                    # Clean up old files to prevent disk space issues
                    cleanup_old_files()
                    
                    if transcription:
                        # Extract language code from the transcription output if available
                        language_code = None
                        transcription_text = transcription
                        
                        # Look for the language code in the output
                        if "language_code" in transcription:
                            try:
                                # Try to parse the language code from the output
                                import re
                                lang_match = re.search(r"'language_code':\s*'([^']+)'", transcription)
                                if lang_match:
                                    detected_lang = lang_match.group(1)
                                    print(f"Extracted language code from transcription: {detected_lang}")
                                    
                                    # Clean up the transcription text - remove the JSON part
                                    # Find the last line which is the clean transcript
                                    lines = transcription.strip().split('\n')
                                    transcription_text = lines[-1].strip()
                                    
                                    language_code = detected_lang
                            except Exception as e:
                                print(f"Error extracting language code: {str(e)}")
                        
                        if not language_code:
                            # Fallback to language detection API
                            language_code = detect_language(transcription_text)
                        
                        # Process transcription with Gemini to get a response
                        gemini_response = process_with_gemini(transcription_text, language_code)
                        
                        # Send text response to the user
                        resp.message(f"Received: {transcription_text}\n\nResponse: {gemini_response}")
                        
                        # Convert Gemini's response to speech in the detected language
                        tts_file = text_to_speech(gemini_response, language_code)
                        
                        if tts_file:
                            # Try to send the audio response
                            if send_audio_via_twilio(tts_file, to_number, from_number):
                                print("Sent audio response successfully")
                            else:
                                print("Failed to send audio response")
                    else:
                        resp.message("Sorry, I couldn't transcribe the audio.")
                else:
                    resp.message("Sorry, I couldn't download the audio file.")
            else:
                resp.message("I received your media, but I can only process audio files.")

        else:
            incoming_msg = request.values.get('Body', '').strip()
            if incoming_msg:
                # Process text input with Gemini and TTS
                if incoming_msg.lower().startswith("tts:"):
                    # Extract the text to convert to speech
                    text_for_tts = incoming_msg[4:].strip()
                    
                    if text_for_tts:
                        # Detect language
                        language_code = detect_language(text_for_tts)
                        
                        # Convert to speech
                        tts_file = text_to_speech(text_for_tts, language_code)
                        
                        if tts_file:
                            # Try to send the audio response
                            if send_audio_via_twilio(tts_file, to_number, from_number):
                                resp.message("Here's your text converted to speech.")
                            else:
                                resp.message("Generated speech but couldn't send the audio file.")
                        else:
                            resp.message("Sorry, I couldn't convert your text to speech.")
                    else:
                        resp.message("Please provide some text after 'tts:' to convert to speech.")

                elif incoming_msg.lower().startswith("loan:"):
                    try:
                        # Parse parameters: income, expenses, cibil_score
                        params = incoming_msg[5:].strip().split(',')
                        if len(params) != 3:
                            resp.message("Please provide income, expenses, and CIBIL score in the format: loan:income,expenses,cibil_score")
                        else:
                            income = int(params[0].strip())
                            expenses = int(params[1].strip())
                            cibil_score = int(params[2].strip())
                            
                            # Get eligibility check from gemini_chatbot
                            eligibility_result = check_loan_eligibility(income, expenses, cibil_score)
                            resp.message(f"Loan Eligibility Analysis:\n\n{eligibility_result}")
                    except ValueError:
                        resp.message("Please provide numeric values for income, expenses, and CIBIL score.")
                    except Exception as e:
                        resp.message(f"Error checking loan eligibility: {str(e)}")

                elif incoming_msg.lower().startswith("insights:"):
                    try:
                        # Parse parameters: income, expenses, cibil_score, loan_amount, interest_rate, tenure
                        params = incoming_msg[9:].strip().split(',')
                        if len(params) != 6:
                            resp.message("Please provide all parameters in the format: insights:income,expenses,cibil_score,loan_amount,interest_rate,tenure")
                        else:
                            income = int(params[0].strip())
                            expenses = int(params[1].strip())
                            cibil_score = int(params[2].strip())
                            loan_amount = int(params[3].strip())
                            interest_rate = float(params[4].strip())
                            tenure = int(params[5].strip())
                            
                            # Get loan insights from gemini_chatbot
                            insights_result = gemini_loan_insights(income, expenses, cibil_score, loan_amount, interest_rate, tenure)
                            resp.message(f"Loan Insights Analysis:\n\n{insights_result}")
                    except ValueError:
                        resp.message("Please provide proper numeric values for all parameters.")
                    except Exception as e:
                        resp.message(f"Error generating loan insights: {str(e)}")

                else:
                    # Regular text message - process with Gemini
                    language_code = detect_language(incoming_msg)
                    gemini_response = process_with_gemini(incoming_msg, language_code)
                    
                    # Send text response
                    resp.message(gemini_response)
                    
                    # Also create and send speech response
                    tts_file = text_to_speech(gemini_response, language_code)
                    if tts_file:
                        if send_audio_via_twilio(tts_file, to_number, from_number):
                            print("Sent audio response for text message")
                        else:
                            print("Failed to send audio response for text message")
            else:
                resp.message("I didn't receive any message.")

        return str(resp)

    except Exception as e:
        print(f"Error processing request: {str(e)}")
        resp = MessagingResponse()
        resp.message(f"Error: {str(e)}")
        return str(resp)


# Route to serve audio files (useful for development with ngrok)
@app.route('/audio/<filename>', methods=['GET'])
def serve_audio(filename):
    """Serves audio files from the temp directory."""
    temp_dir = os.path.join(BASE_DIR, "temp")
    return send_from_directory(temp_dir, filename)


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)