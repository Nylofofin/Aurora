import http.client
import io
import json
import base64
import shutil
import ssl
import tempfile
import unittest
import wave
from pathlib import Path

from aurora_core.companion.server import CompanionServer, MAX_PAIR_ATTEMPTS, PairingAuth


class PairingAuthTests(unittest.TestCase):
    def test_pair_code_is_single_use_and_issues_random_bearer(self):
        with tempfile.TemporaryDirectory() as temporary:
            auth = PairingAuth(Path(temporary))
            code = auth.code_path.read_text().strip()
            self.assertEqual(auth.code_path.stat().st_mode & 0o777, 0o600)
            token = auth.pair("192.168.1.22", code)
            self.assertIsNotNone(token)
            self.assertTrue(auth.authorized(token))
            token_file = auth.token_path.read_text()
            self.assertNotIn(token, token_file)
            self.assertTrue(PairingAuth(Path(temporary)).authorized(token))
            self.assertIsNone(auth.pair("192.168.1.22", code))
            self.assertNotEqual(auth.code_path.read_text().strip(), code)

    def test_pairing_attempts_are_limited_per_address(self):
        with tempfile.TemporaryDirectory() as temporary:
            now = [0.0]
            auth = PairingAuth(Path(temporary), clock=lambda: now[0])
            for _ in range(MAX_PAIR_ATTEMPTS):
                self.assertIsNone(auth.pair("192.168.1.8", "wrong"))
            code = auth.code_path.read_text().strip()
            self.assertIsNone(auth.pair("192.168.1.8", code))
            now[0] = 301.0
            self.assertIsNotNone(auth.pair("192.168.1.8", code))


@unittest.skipUnless(shutil.which("openssl"), "openssl is required for the HTTPS integration test")
class CompanionHttpsTests(unittest.TestCase):
    def test_failed_mobile_handoff_rolls_back_and_requests_desktop_resume(self):
        with tempfile.TemporaryDirectory() as temporary:
            events = []
            outcomes = iter((False, True))
            server = CompanionServer(
                Path(temporary), "127.0.0.1", 0, lambda *_args: "unused",
                on_control=lambda active: events.append(active) or next(outcomes),
            )
            try:
                token = server.auth.pair("127.0.0.1", server.auth.code_path.read_text().strip())
                acquired, changed = server.acquire_control(token)
                self.assertTrue(acquired)
                self.assertTrue(changed)
                if not server.notify_control(True):
                    server.release_control(token)
                    server.notify_control(False)
                self.assertEqual(events, [True, False])
                self.assertFalse(server.control_active())
                self.assertFalse(server._resume_pending)
            finally:
                server.httpd.server_close()

    def test_status_pair_chat_and_persisted_history(self):
        with tempfile.TemporaryDirectory() as temporary:
            control_events = []
            sound_directory = Path(temporary) / "audio"
            sound_directory.mkdir()
            (sound_directory / "entrada.wav").write_bytes(b"PC entrance sound")

            def answer(message, history):
                text = f"Resposta central: {message}; contexto={len(history)}"
                context = [*history, {"role": "user", "content": message},
                           {"role": "assistant", "content": text + " [evidência interna]"}]
                return {"answer": text, "context_history": context}

            def voice(_audio, history):
                text = "Resposta central para voz"
                context = [*history, {"role": "user", "content": "Pergunta falada"},
                           {"role": "assistant", "content": text}]
                return {"transcript": "Pergunta falada", "answer": text, "context_history": context}

            def on_control(active):
                control_events.append(active)
                return True

            wake_frames = []
            screen_frames = []
            class ScreenStream:
                state = "streaming"
                def start(self): self.state = "starting"; return self.state
                def stop(self): self.state = "stopping"
                def frame_after(self, after, timeout):
                    screen_frames.append((after, timeout))
                    return 7, b"jpeg-frame"

            server = CompanionServer(
                Path(temporary), "127.0.0.1", 0,
                answer, on_voice=voice, on_control=on_control,
                on_speech=lambda text: b"edge-audio:" + text.encode("utf-8"),
                on_wake_audio=lambda token, frame: wake_frames.append((token, frame)) or frame == b"wake frame",
                screen_stream=ScreenStream(),
                sound_directory=sound_directory,
            )
            server.start()
            try:
                port = server.httpd.server_address[1]
                connection = http.client.HTTPSConnection(
                    "127.0.0.1", port, context=ssl._create_unverified_context(), timeout=5
                )
                connection.request("GET", "/v1/status")
                response = connection.getresponse()
                status = json.loads(response.read())
                self.assertEqual(response.status, 200)
                self.assertEqual(status["fingerprint"], server.fingerprint)
                self.assertEqual((Path(temporary) / "server-fingerprint.txt").read_text().strip(), server.fingerprint)

                code = server.auth.code_path.read_text().strip()
                connection.request("POST", "/v1/pair", json.dumps({"code": code}), {"Content-Type": "application/json"})
                response = connection.getresponse()
                token_data = json.loads(response.read())
                self.assertEqual(response.status, 200)
                token = token_data["token"]

                connection.request("POST", "/v1/control", json.dumps({"operation": "acquire"}), {"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
                response = connection.getresponse()
                control = json.loads(response.read())
                self.assertEqual(response.status, 200)
                self.assertTrue(control["mobile_control"])
                self.assertEqual(control_events, [True])

                connection.request("POST", "/v1/wake", b"wake frame", {
                    "Authorization": f"Bearer {token}", "Content-Type": "audio/pcm"})
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertTrue(json.loads(response.read())["wake_detected"])
                self.assertEqual(wake_frames, [(token, b"wake frame")])
                connection.request("POST", "/v1/wake", b"\0\0", {
                    "Authorization": "Bearer invalid", "Content-Type": "audio/pcm"})
                response = connection.getresponse()
                response.read()
                self.assertEqual(response.status, 401)

                connection.request("POST", "/v1/screen/start", "{}", {
                    "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
                response = connection.getresponse()
                screen_start = json.loads(response.read())
                self.assertEqual(response.status, 202)
                self.assertTrue(screen_start["consent_required"])
                connection.request("GET", "/v1/screen/frame?after=6", headers={"Authorization": f"Bearer {token}"})
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(response.getheader("Content-Type"), "image/jpeg")
                self.assertEqual(response.getheader("X-Frame-Number"), "7")
                self.assertEqual(response.read(), b"jpeg-frame")
                self.assertEqual(screen_frames, [(6, 2.0)])
                connection.request("POST", "/v1/screen/stop", "{}", {
                    "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                response.read()

                connection.request("GET", "/v1/conversations", headers={"Authorization": "Bearer invalid"})
                response = connection.getresponse()
                response.read()
                self.assertEqual(response.status, 401)

                payload = json.dumps({"conversation_id": "alpha1", "message": "Oi Aurora"})
                connection.request("POST", "/v1/chat", payload, {"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
                response = connection.getresponse()
                answer = json.loads(response.read())
                self.assertEqual(response.status, 200)
                self.assertEqual(answer["answer"], "Resposta central: Oi Aurora; contexto=0")
                self.assertEqual(
                    base64.b64decode(answer["speech_audio_base64"]),
                    b"edge-audio:Resposta central: Oi Aurora; contexto=0",
                )

                separate_payload = json.dumps({
                    "conversation_id": "alpha2", "message": "Conversa pelo telefone",
                    "speech_delivery": "separate",
                })
                connection.request("POST", "/v1/chat", separate_payload, {
                    "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
                response = connection.getresponse()
                mobile_answer = json.loads(response.read())
                self.assertEqual(response.status, 200)
                self.assertNotIn("speech_audio_base64", mobile_answer)

                connection.request("POST", "/v1/speech", json.dumps({"text": "fala teste"}), {
                    "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(response.getheader("Content-Type"), "audio/mpeg")
                self.assertEqual(response.read(), b"edge-audio:fala teste")
                self.assertEqual(server.remote_state(), "ready")

                server.on_speech = lambda _text: (_ for _ in ()).throw(RuntimeError("TTS failed"))
                connection.request("POST", "/v1/speech", json.dumps({"text": "falha teste"}), {
                    "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
                response = connection.getresponse()
                self.assertEqual(response.status, 503)
                response.read()
                self.assertEqual(server.remote_state(), "ready")
                server.on_speech = lambda text: b"edge-audio:" + text.encode("utf-8")

                connection.request("GET", "/v1/sounds/entrada.wav", headers={"Authorization": f"Bearer {token}"})
                sound = connection.getresponse()
                self.assertEqual(sound.status, 200)
                self.assertEqual(sound.read(), b"PC entrance sound")

                connection.request("POST", "/v1/control", json.dumps({"operation": "release"}), {"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(control_events[-1], False)
                connection.request("POST", "/v1/chat", payload, {"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
                response = connection.getresponse()
                response.read()
                self.assertEqual(response.status, 409)
                connection.request("POST", "/v1/control", json.dumps({"operation": "acquire"}), {"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
                response = connection.getresponse()
                response.read()
                self.assertEqual(response.status, 200)

                payload = json.dumps({"conversation_id": "alpha1", "message": "E depois?"})
                connection.request("POST", "/v1/chat", payload, {"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
                response = connection.getresponse()
                follow_up = json.loads(response.read())
                self.assertEqual(follow_up["answer"], "Resposta central: E depois?; contexto=2")

                buffer = io.BytesIO()
                with wave.open(buffer, "wb") as wav:
                    wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16_000)
                    wav.writeframes(b"\0\0" * 8_000)
                connection.request(
                    "POST", "/v1/voice", buffer.getvalue(),
                    {"Authorization": f"Bearer {token}", "Content-Type": "audio/wav", "X-Conversation-ID": "alpha1", "X-Speech-Delivery": "separate"},
                )
                response = connection.getresponse()
                voice_answer = json.loads(response.read())
                self.assertEqual(response.status, 200)
                self.assertEqual(voice_answer["transcript"], "Pergunta falada")
                self.assertEqual(voice_answer["answer"], "Resposta central para voz")
                self.assertNotIn("speech_audio_base64", voice_answer)

                connection.request("GET", "/v1/conversations/alpha1", headers={"Authorization": f"Bearer {token}"})
                response = connection.getresponse()
                history = json.loads(response.read())
                self.assertEqual(response.status, 200)
                self.assertEqual([entry["role"] for entry in history["messages"]], ["user", "assistant", "user", "assistant", "user", "assistant"])
                self.assertEqual([entry["role"] for entry in history["display_messages"]], ["user", "assistant", "user", "assistant", "user", "assistant"])
                self.assertEqual(history["display_messages"][-2]["content"], "Pergunta falada")
                self.assertNotIn("evidência interna", history["display_messages"][-1]["content"])
                connection.close()
            finally:
                server.close()


if __name__ == "__main__":
    unittest.main()
