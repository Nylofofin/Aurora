package app.aurora.companion

import android.app.Application
import android.content.Intent
import android.graphics.BitmapFactory
import android.os.Build
import android.os.SystemClock
import android.provider.Settings
import android.util.Log
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class AuroraViewModel(application: Application) : AndroidViewModel(application) {

    private val appContext = application.applicationContext
    private val vault = CredentialVault(appContext)
    private val savedCredentials = vault.load()
    private val discovery = LanDiscovery(appContext)
    val audioPlayer = RemoteAudioPlayer(appContext.cacheDir)
    private val soundCache = mutableStateMapOf<String, ByteArray>()

    var connected by mutableStateOf(false)
        private set
    var busy by mutableStateOf(false)
        private set
    var discovering by mutableStateOf(false)
        private set
    var loadingConversations by mutableStateOf(false)
        private set

    var endpoint by mutableStateOf(savedCredentials?.first.orEmpty())
    var fingerprint by mutableStateOf(savedCredentials?.second.orEmpty())
    var token by mutableStateOf(savedCredentials?.third.orEmpty())
    var pairingCode by mutableStateOf("")

    var notice by mutableStateOf("")
    var remoteState by mutableStateOf("idle")

    var liveMode by mutableStateOf(false)
    var live by mutableStateOf(false)
    var liveSessionId by mutableStateOf(0)

    var wakeListening by mutableStateOf(false)
    var wakeFailure by mutableStateOf("")

    var alwaysOnWakeActive by mutableStateOf(false)
    var alwaysOnWakeFailure by mutableStateOf("")

    var showScreen by mutableStateOf(false)
    var screenBitmap by mutableStateOf<ImageBitmap?>(null)

    var voiceStartRequest by mutableStateOf(0)
    var voiceStopRequest by mutableStateOf(0)

    var conversationId by mutableStateOf(CompanionClient.newConversationId())
    var conversations by mutableStateOf<List<PcConversation>>(emptyList())
    val lines = mutableStateListOf<ChatLine>()

    private var heartbeatJob: Job? = null
    private var screenStreamJob: Job? = null

    init {
        if (savedCredentials != null) {
            autoConnectSaved()
        }
    }

    private fun autoConnectSaved() {
        val (savedEndpoint, savedFingerprint, savedToken) = savedCredentials ?: return
        viewModelScope.launch {
            val client = CompanionClient(savedEndpoint, savedFingerprint, savedToken)
            var controlAcquired = false
            try {
                withContext(Dispatchers.IO) { client.acquireControl() }
                controlAcquired = true
                conversations = withContext(Dispatchers.IO) { client.conversations() }
                connected = true
                notice = "PC conectado; controle e áudio transferidos para o celular."
                warmLiveSounds()
                startHeartbeatLoop()
                startWakeListener()
            } catch (_: Exception) {
                if (controlAcquired) withContext(Dispatchers.IO) { runCatching { client.releaseControl() } }
                connected = false
                notice = "PC indisponível. Confira a mesma rede Wi-Fi e tente conectar novamente."
            }
        }
    }

    fun connectToPc() {
        busy = true
        notice = "Validando certificado e pareando com o PC…"
        viewModelScope.launch {
            try {
                val cleanFingerprint = fingerprint.filter { it.isLetterOrDigit() }.lowercase()
                val newToken = if (token.isNotBlank()) token else withContext(Dispatchers.IO) {
                    CompanionClient(endpoint, cleanFingerprint).pair(pairingCode)
                }
                token = newToken
                fingerprint = cleanFingerprint
                if (token.isNotBlank()) vault.save(endpoint, cleanFingerprint, newToken)
                val client = CompanionClient(endpoint, cleanFingerprint, newToken)
                withContext(Dispatchers.IO) { client.acquireControl() }
                conversations = withContext(Dispatchers.IO) { client.conversations() }
                warmLiveSounds()
                connected = true
                conversationId = CompanionClient.newConversationId()
                lines.clear()
                notice = "Controle transferido para o celular. A Aurora do PC dormiu."
                startHeartbeatLoop()
                startWakeListener()
            } catch (error: Exception) {
                notice = error.message ?: "Não consegui conectar ao Aurora no PC."
            } finally {
                busy = false
            }
        }
    }

    fun disconnectFromPc() {
        if (!connected || busy) return
        stopWakeListener()
        val wasLive = liveMode
        if (wasLive) leaveLiveMode(playExitSound = false)
        audioPlayer.stop()
        heartbeatJob?.cancel()
        heartbeatJob = null
        stopScreenView()
        busy = true
        viewModelScope.launch {
            try {
                val exitSound = if (wasLive) loadBundledSound("saida.wav") else null
                withContext(Dispatchers.IO) { CompanionClient(endpoint, fingerprint, token).releaseControl() }
                connected = false
                remoteState = "idle"
                soundCache.clear()
                exitSound?.let { audioPlayer.play(it, fileExtension = ".wav") }
                notice = "Celular desconectado. A Aurora do PC voltou a escutar."
            } catch (error: Exception) {
                notice = "Não confirmei a desconexão: ${error.message ?: "verifique o PC"}."
            } finally {
                busy = false
            }
        }
    }

    private fun startHeartbeatLoop() {
        heartbeatJob?.cancel()
        heartbeatJob = viewModelScope.launch {
            while (connected && token.isNotBlank()) {
                delay(15_000)
                try {
                    val serverState = withContext(Dispatchers.IO) {
                        CompanionClient(endpoint, fingerprint, token).heartbeatControl()
                    }
                    if (remoteState != "preparing" && remoteState != "speaking") {
                        remoteState = serverState
                        updateBubbleActivity(serverState)
                    }
                } catch (_: Exception) {
                    stopWakeListener()
                    if (live) voiceStopRequest += 1
                    live = false
                    liveMode = false
                    liveSessionId += 1
                    audioPlayer.stop()
                    soundCache.clear()
                    remoteState = "idle"
                    connected = false
                    notice = "Conexão com o PC perdida; o controle local será liberado automaticamente."
                    hideFloatingBubble()
                    break
                }
            }
        }
    }

    fun findPc() {
        discovering = true
        notice = "Procurando Aurora PCs nesta rede…"
        discovery.start(
            onFound = { found ->
                endpoint = found
                discovering = false
                notice = "Aurora PC encontrado. Confira o pin do certificado e pareie."
            },
            onError = { message ->
                discovering = false
                notice = message
            },
        )
        viewModelScope.launch {
            delay(12_000)
            if (discovering) {
                discovery.stop()
                discovering = false
                notice = "Nenhum PC Aurora encontrado nesta rede. Confira o Wi-Fi e o serviço do PC."
            }
        }
    }

    fun sendCurrentMessage(message: String) {
        val trimmed = message.trim()
        if (trimmed.isEmpty() || !connected || busy) return
        val currentConv = conversationId
        lines += ChatLine(true, trimmed)
        busy = true
        notice = "Aurora está respondendo pelo computador…"
        viewModelScope.launch {
            try {
                val reply = withContext(Dispatchers.IO) {
                    CompanionClient(endpoint, fingerprint, token).sendMessage(currentConv, trimmed)
                }
                lines += ChatLine(false, reply.answer)
                rememberConversation(currentConv, trimmed)
                notice = "Conversa sincronizada com o PC."
                playPcSpeech(reply.answer)
            } catch (error: Exception) {
                lines += ChatLine(false, "Não consegui falar com o PC: ${error.message ?: "verifique a conexão"}.")
                notice = "A conexão com o PC falhou."
            } finally {
                busy = false
            }
        }
    }

    fun sendVoiceAudio(wav: ByteArray) {
        if (!connected || busy) return
        val currentConv = conversationId
        val requestLiveSession = liveSessionId
        busy = true
        notice = "Transcrevendo no PC e consultando a Aurora…"
        viewModelScope.launch {
            try {
                val result = withContext(Dispatchers.IO) {
                    CompanionClient(endpoint, fingerprint, token).sendVoice(currentConv, wav)
                }
                lines += ChatLine(true, result.transcript)
                lines += ChatLine(false, result.answer)
                rememberConversation(currentConv, result.transcript)
                notice = "Resposta da Thalita recebida do PC."
                if (liveMode && liveSessionId == requestLiveSession) {
                    playPcSpeech(result.answer, requestLiveSession)
                }
            } catch (error: Exception) {
                notice = "Falha na conversa por voz: ${error.message ?: "verifique a conexão"}."
                resumeAlwaysOnWake()
            } finally {
                busy = false
            }
        }
    }

    fun refreshConversations() {
        if (!connected || loadingConversations) return
        loadingConversations = true
        viewModelScope.launch {
            try {
                conversations = withContext(Dispatchers.IO) {
                    CompanionClient(endpoint, fingerprint, token).conversations()
                }
                notice = if (conversations.isEmpty()) "Ainda não há conversas salvas no PC." else "Histórico carregado do PC."
            } catch (error: Exception) {
                notice = error.message ?: "Não consegui carregar o histórico."
            } finally {
                loadingConversations = false
            }
        }
    }

    fun openConversation(id: String) {
        if (!connected || busy) return
        busy = true
        viewModelScope.launch {
            try {
                val selected = withContext(Dispatchers.IO) {
                    CompanionClient(endpoint, fingerprint, token).conversation(id)
                }
                conversationId = selected.id
                lines.clear()
                lines.addAll(selected.messages)
                notice = "Conversa aberta do histórico do PC."
            } catch (error: Exception) {
                notice = error.message ?: "Não consegui abrir essa conversa."
            } finally {
                busy = false
            }
        }
    }

    fun newConversation() {
        if (busy) return
        conversationId = CompanionClient.newConversationId()
        lines.clear()
        notice = "Nova conversa no PC."
    }

    fun rememberConversation(id: String, firstMessage: String) {
        val existing = conversations.firstOrNull { it.id == id }
        val title = existing?.title?.takeIf { it.isNotBlank() } ?: firstMessage.take(72)
        conversations = listOf(PcConversation(id, title, emptyList())) + conversations.filterNot { it.id == id }
    }

    suspend fun loadBundledSound(name: String): ByteArray? {
        soundCache[name]?.let { return it }
        val resource = when (name) {
            "entrada.wav" -> R.raw.aurora_entrada
            "saida.wav" -> R.raw.aurora_saida
            else -> return null
        }
        return runCatching {
            withContext(Dispatchers.IO) { appContext.resources.openRawResource(resource).use { it.readBytes() } }
        }.getOrNull()?.also { soundCache[name] = it }
    }

    fun warmLiveSounds() {
        viewModelScope.launch {
            listOf("entrada.wav", "saida.wav").forEach { loadBundledSound(it) }
        }
    }

    fun playPcSound(name: String) {
        if (!connected) return
        viewModelScope.launch {
            val bytes = loadBundledSound(name)
            if (bytes != null) audioPlayer.play(bytes, fileExtension = ".wav", onFinished = { success ->
                if (!success && connected) notice = "O som $name está no app, mas o celular não conseguiu reproduzi-lo."
            })
            else if (connected) notice = "O som $name embutido no app não pôde ser carregado."
        }
    }

    fun playPcSpeech(text: String, liveSession: Int? = null) {
        if (!connected) return
        remoteState = "preparing"
        updateBubbleActivity("preparing")
        viewModelScope.launch {
            val requestStartedAt = SystemClock.elapsedRealtime()
            try {
                val bytes = withContext(Dispatchers.IO) {
                    CompanionClient(endpoint, fingerprint, token).speech(text)
                }
                val audioReceivedAt = SystemClock.elapsedRealtime()
                if (!connected || (liveSession != null && (!liveMode || liveSessionId != liveSession))) {
                    if (connected && remoteState == "preparing") {
                        remoteState = "ready"
                        updateBubbleActivity("ready")
                    }
                    return@launch
                }
                audioPlayer.play(bytes, fileExtension = ".mp3", onStarted = {
                    Log.i("AuroraCompanion", "Voz pronta: total=${SystemClock.elapsedRealtime() - requestStartedAt}ms; reprodução=${SystemClock.elapsedRealtime() - audioReceivedAt}ms; áudio=${bytes.size} bytes")
                    remoteState = "speaking"
                    updateBubbleActivity("speaking")
                }) { success ->
                    remoteState = "ready"
                    updateBubbleActivity("ready")
                    if (!success) notice = "MP3 da Thalita chegou (${bytes.size} bytes), mas o Android falhou ao reproduzir."
                    resumeAlwaysOnWake()
                    if (connected && !liveMode) {
                        startWakeListener()
                    }
                }
            } catch (error: Exception) {
                remoteState = "ready"
                updateBubbleActivity("ready")
                notice = "Texto recebido; voz do PC falhou: ${error.message ?: "erro de áudio"}."
                resumeAlwaysOnWake()
                if (connected && !liveMode) {
                    startWakeListener()
                }
            }
        }
    }

    fun enterLiveMode() {
        if (!connected) return
        if (liveMode) return
        stopWakeListener()
        pauseAlwaysOnWake()
        audioPlayer.stop()
        liveSessionId += 1
        liveMode = true
        playPcSound("entrada.wav")
    }

    fun leaveLiveMode(playExitSound: Boolean = true) {
        if (!liveMode) return
        audioPlayer.stop()
        if (live) voiceStopRequest += 1
        liveSessionId += 1
        liveMode = false
        hideFloatingBubble()
        if (playExitSound) playPcSound("saida.wav")
        resumeAlwaysOnWake()
        if (connected) {
            startWakeListener()
        }
    }

    fun startVoiceInteraction() {
        if (connected && !busy) {
            pauseAlwaysOnWake()
            voiceStartRequest += 1
        }
    }

    fun startWakeListener() {
        if (!connected) return
        val intent = Intent(appContext, WakeCaptureService::class.java).apply {
            action = WakeCaptureService.ACTION_START
            putExtra(WakeCaptureService.EXTRA_ENDPOINT, endpoint)
            putExtra(WakeCaptureService.EXTRA_FINGERPRINT, fingerprint)
            putExtra(WakeCaptureService.EXTRA_TOKEN, token)
        }
        runCatching {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                appContext.startForegroundService(intent)
            } else {
                appContext.startService(intent)
            }
        }.onSuccess {
            wakeListening = true
            notice = "Ativação por voz ligada. O áudio vai ao PC para detecção local."
        }.onFailure {
            notice = "Não consegui ativar a escuta: ${it.message ?: "verifique a permissão de microfone"}."
        }
    }

    fun stopWakeListener() {
        appContext.stopService(Intent(appContext, WakeCaptureService::class.java).setAction(WakeCaptureService.ACTION_STOP))
        wakeListening = false
    }

    fun toggleWakeListener() {
        if (wakeListening) {
            stopWakeListener()
            notice = "Ativação por voz desligada."
        } else if (connected) {
            startWakeListener()
        }
    }

    fun startAlwaysOnWake() {
        val intent = Intent(appContext, AlwaysOnWakeService::class.java).apply {
            action = AlwaysOnWakeService.ACTION_START
        }
        runCatching {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                appContext.startForegroundService(intent)
            } else {
                appContext.startService(intent)
            }
        }.onSuccess {
            alwaysOnWakeActive = true
            notice = "Escuta permanente ativada. Diga \"Aurora\" a qualquer momento."
        }.onFailure {
            notice = "Falha ao iniciar escuta permanente: ${it.message}"
        }
    }

    fun stopAlwaysOnWake() {
        val intent = Intent(appContext, AlwaysOnWakeService::class.java).apply {
            action = AlwaysOnWakeService.ACTION_STOP
        }
        runCatching { appContext.startService(intent) }
        alwaysOnWakeActive = false
        notice = "Escuta permanente desativada."
    }

    fun pauseAlwaysOnWake() {
        if (!alwaysOnWakeActive) return
        val intent = Intent(appContext, AlwaysOnWakeService::class.java).apply {
            action = AlwaysOnWakeService.ACTION_PAUSE_LISTENING
        }
        runCatching { appContext.startService(intent) }
    }

    fun resumeAlwaysOnWake() {
        if (!alwaysOnWakeActive) return
        val intent = Intent(appContext, AlwaysOnWakeService::class.java).apply {
            action = AlwaysOnWakeService.ACTION_RESUME_LISTENING
        }
        runCatching { appContext.startService(intent) }
    }

    fun toggleAlwaysOnWake() {
        if (alwaysOnWakeActive) {
            stopAlwaysOnWake()
        } else {
            startAlwaysOnWake()
        }
    }

    fun toggleScreenView() {
        if (!connected) return
        if (showScreen) {
            stopScreenView()
        } else {
            startScreenView()
        }
    }

    private fun startScreenView() {
        showScreen = true
        screenBitmap = null
        notice = "Solicitando a tela do PC. Confirme o compartilhamento na janela do computador."
        viewModelScope.launch {
            runCatching {
                withContext(Dispatchers.IO) { CompanionClient(endpoint, fingerprint, token).startScreenStream() }
            }.onFailure {
                notice = "Não consegui iniciar a tela do PC: ${it.message ?: "verifique o desktop"}."
                showScreen = false
            }
        }
        screenStreamJob?.cancel()
        screenStreamJob = viewModelScope.launch {
            var lastFrame = 0
            while (showScreen && connected) {
                try {
                    val next = withContext(Dispatchers.IO) {
                        CompanionClient(endpoint, fingerprint, token).screenFrame(lastFrame)
                    }
                    if (next != null) {
                        lastFrame = next.number
                        val decoded = withContext(Dispatchers.Default) {
                            BitmapFactory.decodeByteArray(next.jpeg, 0, next.jpeg.size)?.asImageBitmap()
                        }
                        if (decoded != null) screenBitmap = decoded
                    } else delay(200)
                } catch (error: Exception) {
                    notice = "A transmissão da tela parou: ${error.message ?: "verifique a conexão"}."
                    showScreen = false
                    screenBitmap = null
                    break
                }
            }
        }
    }

    fun stopScreenView() {
        showScreen = false
        screenBitmap = null
        screenStreamJob?.cancel()
        screenStreamJob = null
        viewModelScope.launch(Dispatchers.IO) {
            runCatching { CompanionClient(endpoint, fingerprint, token).stopScreenStream() }
        }
    }

    fun showFloatingBubble() {
        if (!liveMode) return
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && !Settings.canDrawOverlays(appContext)) return

        val intent = Intent(appContext, FloatingBubbleService::class.java).apply {
            action = FloatingBubbleService.ACTION_SHOW
        }
        runCatching {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                appContext.startForegroundService(intent)
            } else {
                appContext.startService(intent)
            }
        }
    }

    fun hideFloatingBubble() {
        val intent = Intent(appContext, FloatingBubbleService::class.java).apply {
            action = FloatingBubbleService.ACTION_HIDE
        }
        runCatching { appContext.startService(intent) }
    }

    /** A bolha agora é stateless — não precisa de update de atividade. */
    fun updateBubbleActivity(activity: String) = Unit

    override fun onCleared() {
        audioPlayer.release()
        discovery.stop()
        heartbeatJob?.cancel()
        screenStreamJob?.cancel()
        hideFloatingBubble()
        stopWakeListener()
        super.onCleared()
    }
}
