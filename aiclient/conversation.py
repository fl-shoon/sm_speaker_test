from utils.define import *
from openai import OpenAI, OpenAIError
from typing import List, Dict

import asyncio
import logging
import os
import time

logging.basicConfig(level=logging.INFO)
openai_logger = logging.getLogger(__name__)

class ConversationClient:
    def __init__(self):
        self.client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        self.conversation_history: List[Dict[str, str]] = []
        self.max_retries = 3
        self.retry_delay = 5 
        self.audio_player = None
        self.server = None
        self.tasks = set()
        self.gptContext = {"role": "system", "content": """あなたは役立つアシスタントです。日本語で返答してください。
            ユーザーが薬を飲んだかどうか一度だけぜひ確認してください。確認後は、他の話題に移ってください。
            会話が自然に終了したと判断した場合は、返答の最後に '[END_OF_CONVERSATION]' というタグを付けてください。
            ただし、ユーザーがさらに質問や話題を提供する場合は会話を続けてください。"""
        }

    def setAudioPlayer(self, audioPlayer):
        self.audio_player = audioPlayer

    def set_display(self, display):
        self.display = display

    async def cleanup_tasks(self):
        """Clean up any running tasks"""
        for task in self.tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self.tasks.clear()

    def generate_ai_reply(self, new_message: str) -> str:
        for attempt in range(self.max_retries):
            try:
                if not self.conversation_history:
                    self.conversation_history = [self.gptContext]

                self.conversation_history.append({"role": "user", "content": new_message})

                response = self.client.chat.completions.create(
                    model="gpt-4",
                    messages=self.conversation_history,
                    temperature=0.75,
                    max_tokens=500
                )
                ai_message = response.choices[0].message.content
                self.conversation_history.append({"role": "assistant", "content": ai_message})

                # Limit conversation history to last 10 messages to prevent token limit issues
                if len(self.conversation_history) > 11:  # 11 to keep the system message
                    self.conversation_history = self.conversation_history[:1] + self.conversation_history[-10:]

                return ai_message
            except OpenAIError as e:
                error_code = getattr(getattr(e, 'error', None), 'code', None) or getattr(e, 'type', None)
                if error_code == 'insufficient_quota':
                    openai_logger.error("OpenAI API quota exceeded. Please check your plan and billing details.")
                    return "申し訳ありません。現在システムに問題が発生しています。後でもう一度お試しください。"
                elif error_code == 'rate_limit_exceeded':
                    if attempt < self.max_retries - 1:
                        openai_logger.warning(f"Rate limit exceeded. Retrying in {self.retry_delay} seconds...")
                        time.sleep(self.retry_delay)
                    else:
                        openai_logger.error("Max retries reached. Unable to complete the request.")
                        return "申し訳ありません。しばらくしてからもう一度お試しください。"
                else:
                    openai_logger.error(f"OpenAI API error: {e}")
                    return "申し訳ありません。エラーが発生しました。"

    def speech_to_text(self, audio_file_path: str) -> str:
        try:
            openai_logger.info(f"Processing speech audio file: {audio_file_path}")
            
            with open(audio_file_path, "rb") as audio_file:
                transcript = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="verbose_json",  
                    language="ja",
                    temperature=0.0,
                    prompt=(
                        "これは日常会話の文脈です。一般的な挨拶、仕事、生活、健康などについての会話が含まれています。"
                        "「仕事」「安心」「大丈夫」「はい」「いいえ」などの一般的な言葉が使用される可能性が高いです。"
                    ),
                )

                if hasattr(transcript, 'segments') and transcript.segments:
                    segment = transcript.segments[0]
                    quality_info = {
                        'avg_logprob': segment.avg_logprob,
                        'no_speech_prob': segment.no_speech_prob,
                        'compression_ratio': segment.compression_ratio
                    }
                    # openai_logger.info(f"Transcription quality metrics: {quality_info}")
                    
                    # Evaluate transcription quality
                    if segment.avg_logprob < -1.0:
                        openai_logger.warning(f"Very low confidence transcription detected: {quality_info}")
                        return "申し訳ありません。音声をはっきりと聞き取れませんでした。もう一度お話しいただけますか？"
                    
                    if segment.no_speech_prob > 0.5:
                        openai_logger.warning(f"Possible no speech detected: {quality_info}")
                        return "音声が検出できませんでした。もう一度お話しください。"

                if hasattr(transcript, 'text'):
                    transcribed_text = transcript.text.strip()
                    return transcribed_text
                else:
                    raise ValueError("No text found in transcription response")

        except OpenAIError as e:
            error_msg = f"OpenAI API error during transcription: {str(e)}"
            openai_logger.error(error_msg)
            return "音声の認識に問題が発生しました。もう一度お試しください。"
        except Exception as e:
            error_msg = f"Unexpected error during transcription: {str(e)}"
            openai_logger.error(error_msg)
            return "音声の認識に問題が発生しました。もう一度お試しください。"

    async def handle_error(self, error_message: str):
        """Handle errors with synchronized audio and gif playback"""
        try:
            error_task = asyncio.create_task(
                self.audio_player.sync_audio_and_gif(ErrorAudio, SpeakingGif)
            )
            self.tasks.add(error_task)
            await error_task
        except Exception as e:
            openai_logger.error(f"Error in error handling: {e}")
        finally:
            await self.cleanup_tasks()

    async def text_to_speech(self, text: str, output_file: str):
        try:
            response = self.client.audio.speech.create(
                model="tts-1-hd",
                voice="nova",
                input=text,
                response_format="wav",
            )

            # Write the audio file
            try:
                with open(output_file, "wb") as f:
                    for chunk in response.iter_bytes(chunk_size=4096):
                        f.write(chunk)
                openai_logger.info(f"Successfully wrote audio to {output_file}")
            except Exception as e:
                openai_logger.error(f"Failed to write audio file: {e}")
                await self.handle_error("音声ファイルの作成に失敗しました")
                return

            # Play the audio file
            try:
                sync_task = asyncio.create_task(
                    self.audio_player.sync_audio_and_gif(output_file, SpeakingGif)
                )
                self.tasks.add(sync_task)
                await sync_task
            except Exception as e:
                openai_logger.error(f"Failed to play audio: {e}")
                await self.handle_error("音声の再生に失敗しました")

        except OpenAIError as e:
            openai_logger.error(f"Failed to generate speech: {e}")
            await self.handle_error("音声の生成に失敗しました")
        except Exception as e:
            openai_logger.error(f"Unexpected error in text_to_speech: {e}")
            await self.handle_error("予期せぬエラーが発生しました")
        finally:
            await self.cleanup_tasks()

    async def process_audio(self, input_audio_file: str) -> bool:
        try:
            # Generate output filename
            base, ext = os.path.splitext(input_audio_file)
            output_audio_file = f"{base}_response{ext}"

            # Speech-to-Text
            stt_text = self.speech_to_text(input_audio_file)
            openai_logger.info(f"Transcript: {stt_text}")

            # LLM
            content_response = self.generate_ai_reply(stt_text)
            conversation_ended = '[END_OF_CONVERSATION]' in content_response
            content_response = content_response.replace('[END_OF_CONVERSATION]', '').strip()

            openai_logger.info(f"AI response: {content_response}")
            openai_logger.info(f"Conversation ended: {conversation_ended}")

            # Text-to-Speech
            if content_response:
                # Generate speech (TTS)
                try:
                    await self.text_to_speech(content_response, output_audio_file)
                    openai_logger.info(f'Audio content written to file "{output_audio_file}"')
                except Exception as e:
                    openai_logger.error(f"Text-to-speech failed: {e}")
                    await self.handle_error("音声変換に失敗しました")
                    return False
            else:
                openai_logger.error("No AI response text generated")
                await self.handle_error("応答の生成に失敗しました")
                return False
            
            return conversation_ended

        except OpenAIError as e:
            openai_logger.error(f"Error in process_audio: {e}")
            await self.handle_error("処理中にエラーが発生しました")
            return True
        except Exception as e:
            openai_logger.error(f"Unexpected error in process_audio: {e}")
            await self.handle_error("予期せぬエラーが発生しました")
            return True
        finally:
            await self.cleanup_tasks()
        
    async def process_text(self, auto_text: str) -> tuple[str, bool]:
        try:
            # LLM
            content_response = self.generate_ai_reply(auto_text)
            conversation_ended = '[END_OF_CONVERSATION]' in content_response
            content_response = content_response.replace('[END_OF_CONVERSATION]', '').strip()

            openai_logger.info(f"AI response: {content_response}")
            openai_logger.info(f"Conversation ended: {conversation_ended}")

            # Generate speech (TTS)
            output_audio_file = AIOutputAudio
            await self.text_to_speech(content_response, output_audio_file)

            return conversation_ended, output_audio_file

        except Exception as e:
            openai_logger.error(f"Error in process_text: {e}")
            await self.handle_error("テキスト処理中にエラーが発生しました")
            return True, ErrorAudio
        finally:
            await self.cleanup_tasks()