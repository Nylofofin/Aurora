import http.client
import json
import shutil
import ssl
import tempfile
import unittest
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
    def test_status_pair_chat_and_persisted_history(self):
        with tempfile.TemporaryDirectory() as temporary:
            def answer(message, history):
                text = f"Resposta central: {message}; contexto={len(history)}"
                context = [*history, {"role": "user", "content": message},
                           {"role": "assistant", "content": text + " [evidência interna]"}]
                return {"answer": text, "context_history": context}

            server = CompanionServer(
                Path(temporary), "127.0.0.1", 0,
                answer,
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

                payload = json.dumps({"conversation_id": "alpha1", "message": "E depois?"})
                connection.request("POST", "/v1/chat", payload, {"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
                response = connection.getresponse()
                follow_up = json.loads(response.read())
                self.assertEqual(follow_up["answer"], "Resposta central: E depois?; contexto=2")

                connection.request("GET", "/v1/conversations/alpha1", headers={"Authorization": f"Bearer {token}"})
                response = connection.getresponse()
                history = json.loads(response.read())
                self.assertEqual(response.status, 200)
                self.assertEqual([entry["role"] for entry in history["messages"]], ["user", "assistant", "user", "assistant"])
                self.assertEqual([entry["role"] for entry in history["display_messages"]], ["user", "assistant", "user", "assistant"])
                self.assertNotIn("evidência interna", history["display_messages"][-1]["content"])
                connection.close()
            finally:
                server.close()


if __name__ == "__main__":
    unittest.main()
