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

    fun conversations(): List<PcConversation> {
        val array = request("GET", "/v1/conversations").optJSONArray("conversations") ?: JSONArray()
        return (0 until array.length()).mapNotNull { index ->
            val item = array.optJSONObject(index) ?: return@mapNotNull null
            PcConversation(item.optString("id"), item.optString("title"), emptyList())
        }
    }

    fun conversation(id: String): PcConversation {
        val item = request("GET", "/v1/conversations/${encodePathSegment(id)}")
        val messages = item.optJSONArray("display_messages") ?: item.optJSONArray("messages") ?: JSONArray()
        val lines = (0 until messages.length()).mapNotNull { index ->
            val message = messages.optJSONObject(index) ?: return@mapNotNull null
            val role = message.optString("role")
            if (role != "user" && role != "assistant") return@mapNotNull null
            ChatLine(role == "user", message.optString("content"))
        }
        return PcConversation(item.getString("id"), item.optString("title"), lines)
    }

    fun sendMessage(conversationId: String, message: String): String {
        require(!token.isNullOrBlank()) { "Este celular ainda não está pareado com o PC." }
        return request(
            "POST", "/v1/chat",
            JSONObject().put("conversation_id", conversationId).put("message", message),
        ).getString("answer")
    }

    private fun request(method: String, path: String, body: JSONObject? = null): JSONObject {
        val url = URL(baseUrl + path)
        val connection = (url.openConnection() as HttpsURLConnection).apply {
            connectTimeout = 5_000
            readTimeout = if (path == "/v1/chat") 185_000 else 8_000
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

        private fun normalizeEndpoint(raw: String): String {
            val uri = URI(raw.trim())
            require(uri.scheme == "https" && !uri.host.isNullOrBlank() && uri.userInfo == null) {
                "Informe o endereço HTTPS do Aurora no computador."
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
