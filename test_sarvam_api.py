import os
import requests
import base64
import argparse
import sys

# Load API key from environment variable
api_key = os.getenv("SARVAM_API_KEY")  # ✅ Ensure this is set in your environment

def speech_to_text_translate(api_key, file_path, model="saaras:v1", prompt=""):
    """Transcribes and translates speech automatically."""
    
    if not os.path.exists(file_path):
        print(f"Error: File does not exist at path: {file_path}", file=sys.stderr)
        return None
        
    print(f"Processing file: {file_path}")
    
    url = "https://api.sarvam.ai/speech-to-text-translate"
    payload = {
        'model': model,
        'prompt': prompt,
        'language_code': 'auto'  # ✅ Enables automatic language detection
    }
    
    headers = {'api-subscription-key': api_key}
    
    try:
        with open(file_path, 'rb') as audio_file:
            files = {'file': ('audio.wav', audio_file, 'audio/wav')}
            response = requests.post(url, headers=headers, data=payload, files=files)
        
        response.raise_for_status()  # Raise an exception for HTTP errors
        
        data = response.json()
        print("Speech-to-Text-Translate Response:", data)
        
        transcript = data.get("transcript")  # Extract transcription
        translated_text = data.get("translated_text", transcript)  # Use translation if available
        
        return translated_text or "No transcription found"
    except FileNotFoundError:
        print(f"Error: Could not open file: {file_path}", file=sys.stderr)
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error making API request: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Error parsing Speech-to-Text-Translate response: {e}", file=sys.stderr)
        return None

def text_to_speech(api_key, text, target_language_code="en-IN", speaker="meera", speech_sample_rate=8000, enable_preprocessing=True):
    """Converts text to speech and saves it as a WAV file."""
    
    url = "https://api.sarvam.ai/text-to-speech"
    payload = {
        "inputs": [text],
        "target_language_code": target_language_code,  # Ensure this is 'en-IN' for English
        "speaker": speaker,
        "speech_sample_rate": speech_sample_rate,
        "enable_preprocessing": enable_preprocessing,
        "model": "bulbul:v1"
    }
    
    headers = {
        "Content-Type": "application/json",
        "api-subscription-key": api_key
    }

    response = requests.post(url, headers=headers, json=payload)

    if response.status_code == 200:
        # Parse the base64 audio data from the response
        response_json = response.json()
        audio_base64 = response_json.get("audios", [None])[0]
        
        if audio_base64:
            # Decode the base64 string and save it as a WAV file
            output_file = "generated_speech.wav"
            with open(output_file, "wb") as f:
                f.write(base64.b64decode(audio_base64))  # Decode and write to file
            
            print(f"Generated Speech saved as: {output_file}")
            return output_file  # Return the file path instead of raw binary
        else:
            print("Error: No audio data found in the response.")
            return None
    else:
        print(f"Error in Text-to-Speech API: {response.status_code}, {response.text}")
        return None

if __name__ == "__main__":
    # Set up command line argument parsing
    parser = argparse.ArgumentParser(description="Process audio files with Sarvam API")
    parser.add_argument("--file", type=str, required=True, help="Path to the audio file")
    parser.add_argument("--language", type=str, default="auto", help="Language code (default: auto)")
    args = parser.parse_args()
    
    # ✅ Ensure API key is correctly loaded
    if not api_key:
        print("Error: SARVAM_API_KEY is not set in the environment.", file=sys.stderr)
        sys.exit(1)
    
    # Use the file path from command line arguments
    file_path = args.file
    print(f"Processing file: {file_path}")
    
    # Check if the file exists
    if not os.path.isfile(file_path):
        print(f"Error: The file does not exist at path: {file_path}", file=sys.stderr)
        sys.exit(1)
    
    # ✅ Process speech-to-text translation (Transcribe + Translate)
    translated_text = speech_to_text_translate(api_key, file_path)
    if translated_text:
        print(translated_text)  # Just print the result for the subprocess to capture
        sys.exit(0)
    else:
        print("Failed to transcribe the audio", file=sys.stderr)
        sys.exit(1)