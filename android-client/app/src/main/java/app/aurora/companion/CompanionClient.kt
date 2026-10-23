// SPDX-License-Identifier: GPL-3.0-only
package app.aurora.companion

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import org.json.JSONArray
import org.json.JSONObject
import java.net.URI
import java.net.URL
import java.security.KeyStore
import java.security.MessageDigest
import java.security.cert.X509Certificate
import java.util.UUID
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import javax.net.ssl.HostnameVerifier
import javax.net.ssl.HttpsURLConnection
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManager
import javax.net.ssl.X509TrustManager

data class PcConversation(val id: String, val title: String, val messages: List<ChatLine>)
data class CompanionReply(val answer: String)
data class CompanionVoiceReply(val transcript: String, val answer: String)
data class PcScreenFrame(val number: Int, val jpeg: ByteArray)

class CompanionClient(
    endpoint: String,
    fingerprint: String,
    private val token: String? = null,
) {
    private val baseUrl = normalizeEndpoint(endpoint)
    private val expectedFingerprint = normalizeFingerprint(fingerprint)

    fun verifyPc(): String {
        val result = request("GET", "/v1/status")
        val actual = normalizeFingerprint(result.getString("fingerprint"))
        require(actual == expectedFingerprint) { "A impressão digital do certificado do PC não confere." }
        require(result.getInt("protocol") == 1) { "Versão de protocolo incompatível." }
        return result.optString("service", "Aurora")
    }

    fun pair(code: String): String {
        verifyPc()
        val result = request("POST", "/v1/pair", JSONObject().put("code", code.trim()))
        return result.getString("token")
    }

    fun acquireControl() {
        val active = request("POST", "/v1/control", JSONObject().put("operation", "acquire")).optBoolean("mobile_control")
        check(active) { "O PC está ocupado ou não conseguiu transferir o controle." }
    }

    fun heartbeatControl(): String = requestWithRetry("POST", "/v1/control", JSONObject().put("operation", "heartbeat")).optString("state", "ready")

    fun releaseControl() {
        request("POST", "/v1/control", JSONObject().put("operation", "release"))
    }

    fun conversations(): List<PcConversation> {
        val array = requestWithRetry("GET", "/v1/conversations").optJSONArray("conversations") ?: JSONArray()
        return (0 until array.length()).mapNotNull { index ->
            val item = array.optJSONObject(index) ?: return@mapNotNull null
            PcConversation(item.optString("id"), item.optString("title"), emptyList())
        }
    }

    fun conversation(id: String): PcConversation {
        val item = requestWithRetry("GET", "/v1/conversations/${encodePathSegment(id)}")
        val messages = item.optJSONArray("display_messages") ?: item.optJSONArray("messages") ?: JSONArray()
        val lines = (0 until messages.length()).mapNotNull { index ->
            val message = messages.optJSONObject(index) ?: return@mapNotNull null
            val role = message.optString("role")
            if (role != "user" && role != "assistant") return@mapNotNull null
            ChatLine(role == "user", message.optString("content"))
        }
        return PcConversation(item.getString("id"), item.optString("title"), lines)
    }

    fun sendMessage(conversationId: String, message: String): CompanionReply {
        require(!token.isNullOrBlank()) { "Este celular ainda não está pareado com o PC." }
        val result = request(
            "POST", "/v1/chat",
            JSONObject().put("conversation_id", conversationId).put("message", message)
                .put("speech_delivery", "separate"),
        )
        return CompanionReply(result.getString("answer"))
    }

    fun sendVoice(conversationId: String, wav: ByteArray): CompanionVoiceReply {
        require(!token.isNullOrBlank()) { "Este celular ainda não está pareado com o PC." }
        val result = requestAudio("/v1/voice", conversationId, wav)
        return CompanionVoiceReply(result.getString("transcript"), result.getString("answer"))
    }

    fun speech(text: String): ByteArray {
        require(!token.isNullOrBlank()) { "Este celular ainda não está pareado com o PC." }
        require(text.isNotBlank() && text.length <= 1800) { "Texto para voz inválido." }
        val connection = (URL(baseUrl + "/v1/speech").openConnection() as HttpsURLConnection).apply {
            connectTimeout = CONNECT_TIMEOUT_MS
            readTimeout = VOICE_READ_TIMEOUT_MS
            requestMethod = "POST"
            sslSocketFactory = pinnedSslContext(expectedFingerprint).socketFactory
            hostnameVerifier = HostnameVerifier { _, _ -> true }
            setRequestProperty("Accept", "audio/mpeg, application/json")
            setRequestProperty("Content-Type", "application/json")
            setRequestProperty("Cache-Control", "no-store")
            setRequestProperty("Authorization", "Bearer $token")
            doOutput = true
        }
        try {
            connection.outputStream.use {
                it.write(JSONObject().put("text", text).toString().toByteArray(Charsets.UTF_8))
            }
            val code = connection.responseCode
            val stream = if (code in 200..299) connection.inputStream else connection.errorStream
            val bytes = stream?.use { it.readBytes() } ?: ByteArray(0)
            if (code !in 200..299) {
                val error = runCatching { JSONObject(bytes.toString(Charsets.UTF_8)).optString("error") }.getOrNull()
                throw IllegalStateException(error?.takeIf { it.isNotBlank() } ?: "voz HTTP $code")
            }
            require(connection.contentType?.substringBefore(';') == "audio/mpeg" && bytes.size in 4..3_000_000) {
                "O PC respondeu, mas não entregou um MP3 válido."
            }
            require(bytes[0] == 0xff.toByte() || bytes.copyOfRange(0, 3).contentEquals("ID3".toByteArray())) {
                "O áudio recebido do PC não parece ser MP3."
            }
            return bytes
        } finally {
            connection.disconnect()
        }
    }

    fun sound(name: String): ByteArray {
        require(name == "entrada.wav" || name == "saida.wav") { "Som de interface inválido." }
        require(!token.isNullOrBlank()) { "Este celular ainda não está pareado com o PC." }
        return requestBytes("/v1/sounds/$name")
    }

    fun detectWake(pcm: ByteArray): Boolean {
        require(!token.isNullOrBlank()) { "Este celular ainda não está pareado com o PC." }
        require(pcm.size in 2..32_000 && pcm.size % 2 == 0) { "Bloco PCM inválido." }
        val connection = (URL(baseUrl + "/v1/wake").openConnection() as HttpsURLConnection).apply {
            connectTimeout = 2_000
            readTimeout = 2_500
            requestMethod = "POST"
            sslSocketFactory = pinnedSslContext(expectedFingerprint).socketFactory
            hostnameVerifier = HostnameVerifier { _, _ -> true }
            setRequestProperty("Accept", "application/json")
            setRequestProperty("Content-Type", "audio/pcm")
            setRequestProperty("Authorization", "Bearer $token")
            doOutput = true
        }
        try {
            connection.outputStream.use { it.write(pcm) }
            val code = connection.responseCode
            val stream = if (code in 200..299) connection.inputStream else connection.errorStream
            val body = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
            if (code !in 200..299) {
                val reason = runCatching { JSONObject(body).optString("error") }.getOrNull()
                throw IllegalStateException(reason?.takeIf { it.isNotBlank() } ?: "erro HTTP $code")
            }
            return JSONObject(body).optBoolean("wake_detected")
        } finally {
            connection.disconnect()
        }
    }

    fun startScreenStream(): String = request("POST", "/v1/screen/start", JSONObject()).optString("state", "starting")

    fun stopScreenStream() {
        request("POST", "/v1/screen/stop", JSONObject())
    }

    fun sendDesktopInput(action: String, x: Float, y: Float, button: Int = 1, delta: Float = 0f): Boolean {
        return runCatching {
            val payload = JSONObject().apply {
                put("action", action)
                put("x", x.toDouble())
                put("y", y.toDouble())
                put("button", button)
                put("delta", delta.toDouble())
            }
            request("POST", "/v1/desktop/input", payload).optBoolean("success", false)
        }.getOrDefault(false)
    }

    fun sendUserProfile(username: String, age: String, avatar: String = "", theme: String = ""): Boolean {
        return runCatching {
            val payload = JSONObject().apply {
                put("username", username)
                put("age", age)
                put("avatar", avatar)
                put("theme", theme)
            }
            request("POST", "/v1/user/profile", payload).optBoolean("success", false)
        }.getOrDefault(false)
    }

    fun screenFrame(after: Int): PcScreenFrame? {
        require(!token.isNullOrBlank()) { "Este celular ainda não está pareado com o PC." }
        val url = URL(baseUrl + "/v1/screen/frame?after=" + after.coerceAtLeast(0))
        val connection = (url.openConnection() as HttpsURLConnection).apply {
            connectTimeout = CONNECT_TIMEOUT_MS
            readTimeout = SCREEN_READ_TIMEOUT_MS
            sslSocketFactory = pinnedSslContext(expectedFingerprint).socketFactory
            hostnameVerifier = HostnameVerifier { _, _ -> true }
            setRequestProperty("Accept", "image/jpeg, application/json")
            setRequestProperty("Cache-Control", "no-store")
            setRequestProperty("Authorization", "Bearer $token")
        }
        try {
            val code = connection.responseCode
            val stream = if (code in 200..299) connection.inputStream else connection.errorStream
            val bytes = stream?.use { it.readBytes() } ?: ByteArray(0)
            if (code == 202) return null
            if (code !in 200..299) {
                val reason = runCatching { JSONObject(bytes.toString(Charsets.UTF_8)).optString("error") }.getOrNull()
                throw IllegalStateException(reason?.takeIf { it.isNotBlank() } ?: "erro HTTP $code")
            }
            require(connection.contentType?.substringBefore(';') == "image/jpeg" && bytes.size in 1..2_000_000) {
                "O quadro recebido do PC é inválido."
            }
            return PcScreenFrame(connection.getHeaderFieldInt("X-Frame-Number", after + 1), bytes)
        } finally {
            connection.disconnect()
        }
    }

    private fun requestAudio(path: String, conversationId: String, wav: ByteArray): JSONObject {
        val connection = (URL(baseUrl + path).openConnection() as HttpsURLConnection).apply {
            connectTimeout = CONNECT_TIMEOUT_MS
            readTimeout = VOICE_READ_TIMEOUT_MS
            requestMethod = "POST"
            sslSocketFactory = pinnedSslContext(expectedFingerprint).socketFactory
            hostnameVerifier = HostnameVerifier { _, _ -> true }
            setRequestProperty("Accept", "application/json")
            setRequestProperty("Content-Type", "audio/wav")
            setRequestProperty("X-Conversation-ID", conversationId)
            setRequestProperty("X-Speech-Delivery", "separate")
            setRequestProperty("Authorization", "Bearer $token")
            doOutput = true
        }
        try {
            connection.outputStream.use { it.write(wav) }
            val code = connection.responseCode
            val stream = if (code in 200..299) connection.inputStream else connection.errorStream
            val text = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
            if (code !in 200..299) {
                val reason = try { JSONObject(text).optString("error") } catch (_: Exception) { "erro HTTP $code" }
                throw IllegalStateException(reason.ifBlank { "erro HTTP $code" })
            }
            return JSONObject(text)
        } finally {
            connection.disconnect()
        }
    }

    private fun requestBytes(path: String): ByteArray {
        val connection = (URL(baseUrl + path).openConnection() as HttpsURLConnection).apply {
            connectTimeout = 5_000
            readTimeout = 8_000
            requestMethod = "GET"
            sslSocketFactory = pinnedSslContext(expectedFingerprint).socketFactory
            hostnameVerifier = HostnameVerifier { _, _ -> true }
            setRequestProperty("Accept", "audio/wav")
            setRequestProperty("Cache-Control", "no-store")
            setRequestProperty("Authorization", "Bearer $token")
        }
        try {
            val code = connection.responseCode
            if (code !in 200..299) {
                val text = connection.errorStream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
                val reason = runCatching { JSONObject(text).optString("error") }.getOrNull()
                throw IllegalStateException(reason?.takeIf { it.isNotBlank() } ?: "erro HTTP $code")
            }
            require(connection.contentLengthLong in 1..500_000) { "Som da Aurora inválido." }
            return connection.inputStream.use { it.readBytes() }
        } finally {
            connection.disconnect()
        }
    }

    private fun requestWithRetry(method: String, path: String, body: JSONObject? = null): JSONObject {
        val delays = listOf(500L, 1500L)
        var lastError: Exception? = null
        for (attempt in 0..delays.size) {
            try {
                return request(method, path, body)
            } catch (e: java.io.IOException) {
                lastError = e
            } catch (e: java.net.SocketTimeoutException) {
                lastError = e
            } catch (e: Exception) {
                throw e  // HTTP 4xx/5xx or non-IO errors — do not retry
            }
            if (attempt < delays.size) Thread.sleep(delays[attempt])
        }
        throw lastError!!
    }

    private fun request(method: String, path: String, body: JSONObject? = null): JSONObject {
        val url = URL(baseUrl + path)
        val connection = (url.openConnection() as HttpsURLConnection).apply {
            connectTimeout = CONNECT_TIMEOUT_MS
            readTimeout = if (path == "/v1/chat") 185_000 else READ_TIMEOUT_MS
            requestMethod = method
            sslSocketFactory = pinnedSslContext(expectedFingerprint).socketFactory
            hostnameVerifier = HostnameVerifier { _, _ -> true }
            setRequestProperty("Accept", "application/json")
            setRequestProperty("Cache-Control", "no-store")
            token?.let { setRequestProperty("Authorization", "Bearer $it") }
            if (body != null) {
                doOutput = true
                setRequestProperty("Content-Type", "application/json; charset=utf-8")
            }
        }
        try {
            if (body != null) connection.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            val code = connection.responseCode
            val stream = if (code in 200..299) connection.inputStream else connection.errorStream
            val text = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
            if (code !in 200..299) {
                val reason = try { JSONObject(text).optString("error") } catch (_: Exception) { "erro HTTP $code" }
                throw IllegalStateException(reason.ifBlank { "erro HTTP $code" })
            }
            return JSONObject(text)
        } finally {
            connection.disconnect()
        }
    }

    companion object {
        fun newConversationId(): String = UUID.randomUUID().toString()

        private const val CONNECT_TIMEOUT_MS = 5_000
        private const val READ_TIMEOUT_MS = 30_000
        private const val VOICE_READ_TIMEOUT_MS = 60_000
        private const val SCREEN_READ_TIMEOUT_MS = 8_000

        private fun normalizeEndpoint(raw: String): String {
            val uri = URI(raw.trim())
            require(uri.scheme == "https" && !uri.host.isNullOrBlank() && uri.userInfo == null) {
                "Informe o endereço HTTPS do Aurora no computador."
            }
            require(uri.host != "localhost" && uri.host != "127.0.0.1") {
                "O servidor companion deve ser um IP de rede local (192.168.x.x), não localhost."
            }
            require(uri.path.isNullOrEmpty() || uri.path == "/") { "Informe somente o endereço e a porta do servidor." }
            require(uri.rawQuery == null && uri.rawFragment == null) { "O endereço não pode conter query ou fragmento." }
            return uri.toString().trimEnd('/')
        }

        private fun normalizeFingerprint(raw: String): String {
            val normalized = raw.filter { it.isLetterOrDigit() }.lowercase()
            require(normalized.length == 64 && normalized.all { it in '0'..'9' || it in 'a'..'f' }) {
                "Informe a impressão digital SHA-256 de 64 caracteres mostrada pelo Aurora no PC."
            }
            return normalized
        }

        private fun pinnedSslContext(expected: String): SSLContext {
            val manager = object : X509TrustManager {
                override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()
                override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) = Unit
                override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {
                    require(chain.isNotEmpty()) { "O PC não apresentou certificado TLS." }
                    val actual = MessageDigest.getInstance("SHA-256").digest(chain[0].encoded)
                        .joinToString("") { "%02x".format(it) }
                    require(actual == expected) { "Certificado do PC diferente da impressão digital pareada." }
                }
            }
            return SSLContext.getInstance("TLS").apply { init(null, arrayOf<TrustManager>(manager), null) }
        }

        private fun encodePathSegment(value: String): String =
            java.net.URLEncoder.encode(value, Charsets.UTF_8.name()).replace("+", "%20")
    }
}

class CredentialVault(context: Context) {
    private val preferences = context.getSharedPreferences("companion_credentials", Context.MODE_PRIVATE)
    private val alias = "aurora-companion-token-v1"

    fun save(endpoint: String, fingerprint: String, token: String) {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key())
        val encrypted = cipher.doFinal(token.toByteArray(Charsets.UTF_8))
        val payload = cipher.iv + encrypted
        preferences.edit()
            .putString("endpoint", endpoint.trim().trimEnd('/'))
            .putString("fingerprint", fingerprint.filter { it.isLetterOrDigit() }.lowercase())
            .putString("token", Base64.encodeToString(payload, Base64.NO_WRAP))
            .apply()
    }

    fun load(): Triple<String, String, String>? {
        val endpoint = preferences.getString("endpoint", null) ?: return null
        val fingerprint = preferences.getString("fingerprint", null) ?: return null
        val payload = preferences.getString("token", null) ?: return null
        return try {
            val bytes = Base64.decode(payload, Base64.NO_WRAP)
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, bytes.copyOfRange(0, 12)))
            Triple(endpoint, fingerprint, String(cipher.doFinal(bytes.copyOfRange(12, bytes.size)), Charsets.UTF_8))
        } catch (_: Exception) {
            clear()
            null
        }
    }

    fun clear() { preferences.edit().clear().apply() }

    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(alias, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(
            KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setRandomizedEncryptionRequired(true)
                .build(),
        )
        return generator.generateKey()
    }
}
