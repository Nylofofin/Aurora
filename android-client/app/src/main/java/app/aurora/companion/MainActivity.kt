package app.aurora.companion

import android.Manifest
import android.content.Intent
import android.view.SoundEffectConstants
import android.view.View
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.animation.scaleOut
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.asPaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBars
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Divider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.DrawerValue
import androidx.compose.material3.ModalDrawerSheet
import androidx.compose.material3.ModalNavigationDrawer
import androidx.compose.material3.NavigationDrawerItem
import androidx.compose.material3.NavigationDrawerItemDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDrawerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

private val Ink = Color(0xFFF7F5FA)
private val Panel = Color(0xFFFFFFFF)
private val Muted = Color(0xFF777387)
private val Violet = Color(0xFF8A70C4)
private val Blue = Color(0xFF579BC2)
private val Pearl = Color(0xFF29263A)
private val SoftLilac = Color(0xFFEAE3F5)

private fun playPhoneClick(view: View) {
    // Local Android feedback only; companion sounds and speech still arrive from the PC.
    view.playSoundEffect(SoundEffectConstants.CLICK)
}

data class ChatLine(val fromUser: Boolean, val text: String)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = android.graphics.Color.rgb(247, 245, 250)
        window.navigationBarColor = android.graphics.Color.rgb(247, 245, 250)
        window.decorView.systemUiVisibility = View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR or View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR
        setContent { AuroraShell() }
    }
}

@Composable
private fun AuroraShell() {
    val appContext = LocalContext.current
    val rootView = androidx.compose.ui.platform.LocalView.current
    val vault = remember { CredentialVault(appContext) }
    val saved = remember { vault.load() }
    val scope = rememberCoroutineScope()
    val discovery = remember { LanDiscovery(appContext) }
    val audioPlayer = remember { RemoteAudioPlayer(appContext.cacheDir) }
    val drawerState = rememberDrawerState(DrawerValue.Closed)
    val soundCache = remember { mutableStateMapOf<String, ByteArray>() }
    var remoteState by remember { mutableStateOf("idle") }
    DisposableEffect(audioPlayer) { onDispose { audioPlayer.release() } }
    var showConnect by remember { mutableStateOf(false) }
    var connected by remember { mutableStateOf(false) }
    var endpoint by remember { mutableStateOf(saved?.first.orEmpty()) }
    var pairingCode by remember { mutableStateOf("") }
    var fingerprint by remember { mutableStateOf(saved?.second.orEmpty()) }
    var token by remember { mutableStateOf(saved?.third.orEmpty()) }
    var draft by remember { mutableStateOf("") }
    var voiceStartRequest by remember { mutableStateOf(0) }
    var voiceStopRequest by remember { mutableStateOf(0) }
    var live by remember { mutableStateOf(false) }
    var liveMode by remember { mutableStateOf(false) }
    var liveSessionId by remember { mutableStateOf(0) }
    var busy by remember { mutableStateOf(false) }
    var loadingConversations by remember { mutableStateOf(false) }
    var discovering by remember { mutableStateOf(false) }
    var notice by remember { mutableStateOf("") }
    var conversationId by remember { mutableStateOf(CompanionClient.newConversationId()) }
    var conversations by remember { mutableStateOf<List<PcConversation>>(emptyList()) }
    val lines = remember { mutableStateListOf<ChatLine>() }
    val composerFocusRequester = remember { FocusRequester() }
    val keyboardController = LocalSoftwareKeyboardController.current

    suspend fun fetchPcSound(name: String): ByteArray? {
        soundCache[name]?.let { return it }
        return runCatching {
            withContext(Dispatchers.IO) { CompanionClient(endpoint, fingerprint, token).sound(name) }
        }.getOrNull()?.also { soundCache[name] = it }
    }

    fun warmLiveSounds(client: CompanionClient) {
        scope.launch {
            val sounds = withContext(Dispatchers.IO) {
                listOf("entrada.wav", "saida.wav").mapNotNull { name ->
                    runCatching { name to client.sound(name) }.getOrNull()
                }
            }
            sounds.forEach { (name, bytes) -> soundCache[name] = bytes }
        }
    }

    fun playPcSound(name: String) {
        if (!connected) return
        scope.launch {
            val bytes = fetchPcSound(name)
            if (bytes != null) audioPlayer.play(bytes, onFinished = { success ->
                if (!success && connected) notice = "O som $name chegou do PC, mas o celular não conseguiu reproduzi-lo."
            })
            else if (connected) notice = "Não consegui receber o som $name do PC."
        }
    }

    fun playPcSpeech(bytes: ByteArray?) {
        if (!connected) return
        if (bytes == null || bytes.isEmpty()) {
            remoteState = "ready"
            notice = "A resposta chegou em texto, mas o PC não conseguiu gerar o áudio Edge TTS."
            return
        }
        audioPlayer.play(bytes, onStarted = { remoteState = "speaking" }) { success ->
            remoteState = "ready"
            if (!success) notice = "Recebi a resposta, mas não consegui reproduzir o áudio enviado pelo PC."
        }
    }

    fun enterLiveMode() {
        playPhoneClick(rootView)
        if (!connected) {
            showConnect = true
            return
        }
        if (liveMode) return
        audioPlayer.stop()
        liveSessionId += 1
        liveMode = true
        playPcSound("entrada.wav")
    }

    fun leaveLiveMode(playExitSound: Boolean = true) {
        playPhoneClick(rootView)
        if (!liveMode) return
        audioPlayer.stop()
        if (live) voiceStopRequest += 1
        liveSessionId += 1
        liveMode = false
        if (playExitSound) playPcSound("saida.wav")
    }

    BackHandler(enabled = liveMode) { leaveLiveMode() }

    fun startVoiceInteraction() {
        playPhoneClick(rootView)
        if (!connected) {
            showConnect = true
        } else if (!busy) {
            voiceStartRequest += 1
        }
    }

    fun rememberConversation(id: String, firstMessage: String) {
        val existing = conversations.firstOrNull { it.id == id }
        val title = existing?.title?.takeIf { it.isNotBlank() } ?: firstMessage.take(72)
        conversations = listOf(PcConversation(id, title, emptyList())) + conversations.filterNot { it.id == id }
    }

    LaunchedEffect(saved) {
        if (saved != null) {
            val client = CompanionClient(saved.first, saved.second, saved.third)
            var controlAcquired = false
            try {
                withContext(Dispatchers.IO) { client.acquireControl() }
                controlAcquired = true
                conversations = withContext(Dispatchers.IO) { client.conversations() }
                connected = true
                notice = "PC conectado; controle e áudio transferidos para o celular."
                warmLiveSounds(client)
            } catch (_: Exception) {
                if (controlAcquired) withContext(Dispatchers.IO) { runCatching { client.releaseControl() } }
                // Keep the pairing credentials for temporary Wi-Fi/server outages.
                connected = false
                notice = "PC indisponível. Confira a mesma rede Wi-Fi e tente conectar novamente."
            }
        }
    }

    DisposableEffect(discovery) { onDispose { discovery.stop() } }
    LaunchedEffect(discovering) {
        if (discovering) {
            delay(12_000)
            if (discovering) {
                discovery.stop()
                discovering = false
                notice = "Nenhum PC Aurora encontrado nesta rede. Confira o Wi-Fi e o serviço do PC."
            }
        }
    }
    LaunchedEffect(connected, endpoint, fingerprint, token) {
        while (connected && token.isNotBlank()) {
            delay(15_000)
            try {
                remoteState = withContext(Dispatchers.IO) { CompanionClient(endpoint, fingerprint, token).heartbeatControl() }
            } catch (_: Exception) {
                if (live) voiceStopRequest += 1
                live = false
                liveMode = false
                liveSessionId += 1
                audioPlayer.stop()
                soundCache.clear()
                remoteState = "idle"
                connected = false
                notice = "Conexão com o PC perdida; o controle local será liberado automaticamente."
            }
        }
    }

    fun connectToPc() {
        playPhoneClick(rootView)
        busy = true
        notice = "Validando certificado e pareando com o PC…"
        scope.launch {
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
                warmLiveSounds(client)
                token = newToken
                fingerprint = cleanFingerprint
                connected = true
                conversationId = CompanionClient.newConversationId()
                lines.clear()
                notice = "Controle transferido para o celular. A Aurora do PC dormiu."
                showConnect = false
            } catch (error: Exception) {
                notice = error.message ?: "Não consegui conectar ao Aurora no PC."
            } finally {
                busy = false
            }
        }
    }

    fun disconnectFromPc() {
        playPhoneClick(rootView)
        if (!connected || busy) return
        val wasLive = liveMode
        if (wasLive) leaveLiveMode(playExitSound = false)
        audioPlayer.stop()
        busy = true
        scope.launch {
            try {
                // Fetch the PC's exit cue while this phone still owns the lease.
                val exitSound = if (wasLive) fetchPcSound("saida.wav") else null
                withContext(Dispatchers.IO) { CompanionClient(endpoint, fingerprint, token).releaseControl() }
                connected = false
                remoteState = "idle"
                soundCache.clear()
                exitSound?.let { audioPlayer.play(it) }
                notice = "Celular desconectado. A Aurora do PC voltou a escutar."
            } catch (error: Exception) {
                notice = "Não confirmei a desconexão: ${error.message ?: "verifique o PC"}."
            } finally { busy = false }
        }
    }

    fun findPc() {
        playPhoneClick(rootView)
        discovering = true
        notice = "Procurando Aurora PCs nesta rede…"
        discovery.start(
            onFound = { found -> endpoint = found; discovering = false; notice = "Aurora PC encontrado. Confira o pin do certificado e pareie." },
            onError = { message -> discovering = false; notice = message },
        )
    }

    fun sendCurrentMessage() {
        playPhoneClick(rootView)
        val message = draft.trim()
        if (message.isEmpty() || !connected || busy) return
        val selectedConversation = conversationId
        lines += ChatLine(true, message)
        draft = ""
        busy = true
        notice = "Aurora está respondendo pelo computador…"
        scope.launch {
            try {
                val reply = withContext(Dispatchers.IO) {
                    CompanionClient(endpoint, fingerprint, token).sendMessage(selectedConversation, message)
                }
                lines += ChatLine(false, reply.answer)
                rememberConversation(selectedConversation, message)
                notice = "Conversa sincronizada com o PC."
                playPcSpeech(reply.speechAudio)
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
        val selectedConversation = conversationId
        val requestLiveSession = liveSessionId
        busy = true
        notice = "Transcrevendo no PC e consultando a Aurora…"
        scope.launch {
            try {
                val result = withContext(Dispatchers.IO) {
                    CompanionClient(endpoint, fingerprint, token).sendVoice(selectedConversation, wav)
                }
                lines += ChatLine(true, result.transcript)
                lines += ChatLine(false, result.answer)
                rememberConversation(selectedConversation, result.transcript)
                notice = "Resposta da Thalita recebida do PC."
                if (liveMode && liveSessionId == requestLiveSession) playPcSpeech(result.speechAudio)
            } catch (error: Exception) {
                notice = "Falha na conversa por voz: ${error.message ?: "verifique a conexão"}."
            } finally {
                busy = false
            }
        }
    }

    fun refreshConversations() {
        if (!connected || loadingConversations) return
        loadingConversations = true
        scope.launch {
            try {
                conversations = withContext(Dispatchers.IO) { CompanionClient(endpoint, fingerprint, token).conversations() }
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
        scope.launch {
            try {
                val selected = withContext(Dispatchers.IO) { CompanionClient(endpoint, fingerprint, token).conversation(id) }
                conversationId = selected.id
                lines.clear()
                lines.addAll(selected.messages)
                draft = ""
                notice = "Conversa aberta do histórico do PC."
            } catch (error: Exception) {
                notice = error.message ?: "Não consegui abrir essa conversa."
            } finally {
                busy = false
            }
        }
    }

    MaterialTheme {
        ModalNavigationDrawer(
            drawerState = drawerState,
            gesturesEnabled = connected && !liveMode,
            drawerContent = {
                ModalDrawerSheet(drawerContainerColor = Panel, drawerContentColor = Pearl) {
                    Column(Modifier.fillMaxSize().padding(horizontal = 16.dp, vertical = 20.dp)) {
                        Text("Aurora", color = Pearl, fontSize = 24.sp, fontWeight = FontWeight.SemiBold)
                        Text("Conversas no seu PC", color = Muted, fontSize = 13.sp, modifier = Modifier.padding(top = 4.dp, bottom = 18.dp))
                        Button(
                            onClick = {
                                if (!busy) {
                                    conversationId = CompanionClient.newConversationId()
                                    lines.clear()
                                    draft = ""
                                    notice = "Nova conversa. Pode falar ou escrever."
                                    scope.launch { drawerState.close() }
                                }
                            },
                            enabled = connected && !busy,
                            modifier = Modifier.fillMaxWidth().heightIn(min = 50.dp),
                            colors = ButtonDefaults.buttonColors(containerColor = Violet, contentColor = Pearl),
                            shape = RoundedCornerShape(16.dp),
                        ) { Text("＋  Nova conversa", fontWeight = FontWeight.SemiBold) }
                        Row(
                            Modifier.fillMaxWidth().padding(top = 22.dp, bottom = 8.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.SpaceBetween,
                        ) {
                            Text("Recentes", color = Muted, fontSize = 13.sp)
                            TextButton(onClick = ::refreshConversations, enabled = connected && !busy) {
                                Text("Atualizar", color = Blue)
                            }
                        }
                        if (conversations.isEmpty()) {
                            Text("Suas conversas aparecerão aqui.", color = Muted, fontSize = 13.sp, modifier = Modifier.padding(vertical = 12.dp))
                        }
                        LazyColumn(Modifier.weight(1f).fillMaxWidth()) {
                            items(conversations, key = { it.id }) { item ->
                                NavigationDrawerItem(
                                    label = {
                                        Text(item.title.ifBlank { "Conversa" }, maxLines = 2, overflow = TextOverflow.Ellipsis)
                                    },
                                    selected = item.id == conversationId,
                                    onClick = {
                                        openConversation(item.id)
                                        scope.launch { drawerState.close() }
                                    },
                                    modifier = Modifier.padding(NavigationDrawerItemDefaults.ItemPadding),
                                    colors = NavigationDrawerItemDefaults.colors(
                                        selectedContainerColor = Violet.copy(alpha = 0.22f),
                                        selectedTextColor = Pearl,
                                        unselectedTextColor = Muted,
                                    ),
                                )
                            }
                        }
                        TextButton(onClick = { scope.launch { drawerState.close() } }, modifier = Modifier.fillMaxWidth()) {
                            Text("Fechar", color = Muted)
                        }
                    }
                }
            },
        ) {
          Box(Modifier.fillMaxSize()) {
            Surface(color = Ink, modifier = Modifier.fillMaxSize()) {
              Column(
                modifier = Modifier.fillMaxSize().padding(WindowInsets.statusBars.asPaddingValues())
                    .padding(WindowInsets.navigationBars.asPaddingValues()).imePadding()
              ) {
                TopBar(
                    connected,
                    remoteState,
                    onHistory = {
                        if (connected) {
                            refreshConversations()
                            scope.launch { drawerState.open() }
                        } else showConnect = true
                    },
                    onConnect = { showConnect = true },
                    onDisconnect = ::disconnectFromPc,
                    onOrbClick = { if (connected) enterLiveMode() else showConnect = true },
                )
                if (lines.isEmpty()) {
                    Welcome(
                        modifier = Modifier.weight(1f),
                        live = live,
                        working = busy,
                        connected = connected,
                        activity = if (live) "listening" else remoteState,
                        onStartVoice = ::enterLiveMode,
                        onWrite = {
                            if (connected) {
                                composerFocusRequester.requestFocus()
                                keyboardController?.show()
                            } else showConnect = true
                        },
                        onConnect = { showConnect = true },
                    )
                } else {
                    LazyColumn(
                        modifier = Modifier.weight(1f).fillMaxWidth().padding(horizontal = 20.dp),
                        verticalArrangement = Arrangement.spacedBy(18.dp),
                        reverseLayout = false
                    ) {
                        items(lines) { line -> MessageBubble(line) }
                    }
                    Row(Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 10.dp),
                        horizontalArrangement = Arrangement.Center) {
                        OrbButton(live || busy, Modifier.size(54.dp), activity = if (live) "listening" else remoteState, onClick = ::enterLiveMode)
                    }
                }
                Composer(
                    text = draft,
                    connected = connected,
                    busy = busy,
                    liveMode = liveMode,
                    onText = { draft = it },
                    onSend = ::sendCurrentMessage,
                    onNew = { if (!busy) { conversationId = CompanionClient.newConversationId(); lines.clear(); notice = "Nova conversa no PC." } },
                    onToggleLive = { if (liveMode) leaveLiveMode() else enterLiveMode() },
                    focusRequester = composerFocusRequester,
                )
                if (notice.isNotBlank()) Text(notice, color = Muted, fontSize = 11.sp, modifier = Modifier.fillMaxWidth().padding(bottom = 6.dp), textAlign = TextAlign.Center)
              }
            }
            AnimatedVisibility(
                visible = liveMode,
                modifier = Modifier.fillMaxSize(),
                enter = fadeIn(tween(180)) + scaleIn(initialScale = 0.78f, animationSpec = spring(dampingRatio = 0.72f, stiffness = 300f)),
                exit = fadeOut(tween(190)) + scaleOut(targetScale = 0.76f, animationSpec = spring(dampingRatio = 0.82f, stiffness = 330f)),
            ) {
                LiveOverlay(
                    modeActive = liveMode,
                    recording = live,
                    working = busy,
                    activity = remoteState,
                    startRequest = voiceStartRequest,
                    stopRequest = voiceStopRequest,
                    onOrbTap = { if (!live && !busy) startVoiceInteraction() },
                    onExit = ::leaveLiveMode,
                    onRecording = { live = it },
                    onVoice = ::sendVoiceAudio,
                    onVoiceError = { notice = it },
                )
            }
          }
        }
    }

    if (showConnect) {
        AlertDialog(
            onDismissRequest = { showConnect = false },
            containerColor = Panel,
            title = { Text("Conectar ao PC", color = Pearl) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text("O computador é quem executa a Aurora. Primeiro conecte os dois à mesma rede Wi-Fi.", color = Muted)
                    Button(onClick = ::findPc, enabled = !discovering, colors = ButtonDefaults.buttonColors(containerColor = Panel)) {
                        Text(if (discovering) "Procurando na rede…" else "Encontrar meu PC automaticamente", color = Pearl)
                    }
                    ConnectField(endpoint, { endpoint = it }, "Endereço do servidor (ex.: https://192.168.1.10:8765)")
                    if (token.isBlank()) ConnectField(pairingCode, { pairingCode = it }, "Código de pareamento")
                    ConnectField(fingerprint, { fingerprint = it }, "Impressão digital SHA-256 do certificado (64 caracteres)")
                    Text("No PC, obtenha o código e a impressão digital em ~/.config/aurora/companion/. O pareamento usa HTTPS com certificado fixado; não exponha a porta do PC à internet.", color = Muted, fontSize = 12.sp)
                    if (notice.isNotBlank()) Text(notice, color = if (notice.startsWith("Não")) Color(0xFFFFA6AC) else Blue, fontSize = 12.sp)
                }
            },
            confirmButton = {
                Button(onClick = ::connectToPc, enabled = !busy, colors = ButtonDefaults.buttonColors(containerColor = Violet)) {
                    Text(if (busy) "Conectando…" else "Parear com o PC")
                }
            },
            dismissButton = { TextButton(onClick = { showConnect = false }) { Text("Cancelar", color = Muted) } }
        )
    }

}

@Composable
private fun TopBar(
    connected: Boolean,
    remoteState: String,
    onHistory: () -> Unit,
    onConnect: () -> Unit,
    onDisconnect: () -> Unit,
    onOrbClick: () -> Unit,
) {
    Row(
        Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            OrbButton(false, Modifier.size(38.dp), activity = if (connected) remoteState else "idle", onClick = onOrbClick)
            Spacer(Modifier.width(11.dp))
            Column {
                Text("Aurora", color = Pearl, fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
                Text(if (connected) "${remoteStateLabel(remoteState)} · PC em pausa" else "Aguardando seu PC", color = Muted, fontSize = 11.sp)
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            SmallAction("Chats", onHistory)
            SmallAction(if (connected) "Desconectar" else "Conectar", if (connected) onDisconnect else onConnect)
        }
    }
}

private fun remoteStateLabel(state: String): String = when (state) {
    "transcribing" -> "Entendendo sua voz"
    "thinking" -> "Aurora pensando"
    "searching" -> "Aurora pesquisando"
    "speaking" -> "Aurora falando"
    "error" -> "Atenção necessária"
    else -> "Celular conectado"
}

@Composable
private fun Welcome(
    modifier: Modifier = Modifier,
    live: Boolean,
    working: Boolean,
    connected: Boolean,
    activity: String,
    onStartVoice: () -> Unit,
    onWrite: () -> Unit,
    onConnect: () -> Unit,
) {
    Column(
        modifier = modifier.fillMaxWidth().padding(horizontal = 26.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        OrbButton(live, Modifier.size(150.dp), activity, if (connected) onStartVoice else onConnect)
        Spacer(Modifier.height(27.dp))
        Text(
            when {
                live -> "Estou ouvindo você"
                working -> "A Aurora está processando"
                connected -> "Aurora conectada"
                else -> "Oi, sou a Aurora"
            },
            color = Pearl, fontSize = 26.sp, fontWeight = FontWeight.Medium
        )
        Spacer(Modifier.height(9.dp))
        Text(
            if (connected) "Toque em Falar com a Aurora para começar. Você também pode escrever uma mensagem."
            else "Conecte ao computador para conversar com sua assistente.",
            color = Muted, textAlign = TextAlign.Center, fontSize = 15.sp, lineHeight = 22.sp
        )
        Spacer(Modifier.height(22.dp))
        Button(
            onClick = if (connected) onStartVoice else onConnect,
            modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp),
            enabled = !live && !working,
            colors = ButtonDefaults.buttonColors(containerColor = Violet, contentColor = Pearl),
            shape = RoundedCornerShape(18.dp),
        ) {
            Text(
                when {
                    live -> "Gravando sua voz…"
                    working -> "Aguarde a resposta…"
                    connected -> "Falar com a Aurora"
                    else -> "Conectar ao PC"
                },
                fontSize = 15.sp,
                fontWeight = FontWeight.SemiBold,
            )
        }
        if (connected) {
            TextButton(onClick = onWrite, modifier = Modifier.heightIn(min = 48.dp)) {
                Text("Escrever uma mensagem", color = Blue, fontSize = 14.sp)
            }
        }
        if (live) {
            Spacer(Modifier.height(18.dp))
            Text("Toque em “Parar e enviar” no campo abaixo quando terminar.", color = Blue, fontSize = 12.sp, textAlign = TextAlign.Center)
        }
    }
}

@Composable
private fun OrbButton(live: Boolean, modifier: Modifier, activity: String = if (live) "listening" else "idle", onClick: () -> Unit) {
    val transition = rememberInfiniteTransition(label = "aurora-orb")
    val pulseMillis = when (activity) {
        "transcribing", "thinking" -> 1050
        "searching" -> 1450
        "speaking" -> 720
        "listening" -> 850
        else -> 2500
    }
    val auraColor = when (activity) {
        "searching" -> Blue
        "speaking" -> Color(0xFFD9C7FF)
        "thinking", "transcribing" -> Violet
        else -> if (live) Blue else Violet
    }
    val breathe by transition.animateFloat(
        initialValue = 0.96f,
        targetValue = if (activity == "speaking") 1.10f else if (live || activity != "idle") 1.065f else 1.025f,
        animationSpec = infiniteRepeatable(tween(pulseMillis, easing = FastOutSlowInEasing), RepeatMode.Reverse),
        label = "orb-breathe"
    )
    val drift by transition.animateFloat(
        initialValue = 0.15f,
        targetValue = 0.85f,
        animationSpec = infiniteRepeatable(tween(4600, easing = FastOutSlowInEasing), RepeatMode.Reverse),
        label = "orb-reflection"
    )
    val halo by transition.animateFloat(
        initialValue = 1f,
        targetValue = if (activity == "speaking") 1.50f else if (live || activity != "idle") 1.38f else 1.08f,
        animationSpec = infiniteRepeatable(tween(pulseMillis, easing = FastOutSlowInEasing), RepeatMode.Reverse),
        label = "orb-halo-scale"
    )
    val haloAlpha by transition.animateFloat(
        initialValue = if (live || activity != "idle") 0.32f else 0.10f,
        targetValue = 0.01f,
        animationSpec = infiniteRepeatable(tween(pulseMillis, easing = FastOutSlowInEasing), RepeatMode.Reverse),
        label = "orb-halo-alpha"
    )
    Box(modifier, contentAlignment = Alignment.Center) {
    Box(Modifier.fillMaxSize().scale(halo).alpha(haloAlpha)
        .border(1.dp, auraColor, CircleShape))
    Box(Modifier.fillMaxSize().scale(breathe).clip(CircleShape).background(
        Brush.linearGradient(
            colors = listOf(Color(0xFFFFFFFF), Color(0xFFF0EAF8), Color(0xFFD7C8EF), Color(0xFFA9CFE4), Color(0xFF927BC9)),
            start = androidx.compose.ui.geometry.Offset(0f, 0f),
            end = androidx.compose.ui.geometry.Offset(380f * drift, 540f * (1f - drift))
        )
    ).border(1.dp, Color.White.copy(alpha = 0.42f), CircleShape)
        .clickable(onClick = onClick), contentAlignment = Alignment.TopStart) {
        Box(Modifier.fillMaxSize().background(
            Brush.radialGradient(listOf(Color.White.copy(alpha = 0.72f), Color.White.copy(alpha = 0.08f), Color.Transparent), radius = 170f),
            shape = CircleShape
        ))
        Box(Modifier.fillMaxWidth(0.62f).height(40.dp).padding(start = 20.dp, top = 13.dp)
            .clip(CircleShape).alpha(0.7f).background(Brush.horizontalGradient(listOf(Color.White.copy(0.72f), Color.White.copy(0.02f)))))
    }
    }
}

@Composable
private fun VoiceCaptureButton(
    enabled: Boolean,
    startRequest: Int = 0,
    stopRequest: Int = 0,
    label: String = "Voz",
    onRecording: (Boolean) -> Unit,
    onCaptured: (ByteArray) -> Unit,
    onError: (String) -> Unit,
) {
    val appContext = LocalContext.current
    val scope = rememberCoroutineScope()
    var active by remember { mutableStateOf(false) }
    var stopping by remember { mutableStateOf(false) }
    val currentCapture = remember { arrayOfNulls<PcmVoiceCapture>(1) }
    val startCapture: () -> Unit = {
        val serviceIntent = Intent(appContext, MicCaptureService::class.java).setAction(MicCaptureService.ACTION_START)
        val foregroundStarted = try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) appContext.startForegroundService(serviceIntent)
            else appContext.startService(serviceIntent)
            true
        } catch (error: Exception) {
            onError(error.message ?: "Não consegui manter a gravação ativa em segundo plano.")
            false
        }
        if (foregroundStarted) {
            val capture = PcmVoiceCapture()
            currentCapture[0] = capture
            active = true
            onRecording(true)
            scope.launch {
                try {
                    val wav = withContext(Dispatchers.IO) { capture.captureWav() }
                    if (currentCapture[0] === capture) {
                        currentCapture[0] = null
                        active = false
                        stopping = false
                        onRecording(false)
                        onCaptured(wav)
                    }
                } catch (error: Exception) {
                    if (currentCapture[0] === capture) {
                        currentCapture[0] = null
                        active = false
                        stopping = false
                        onRecording(false)
                        onError(error.message ?: "Falha ao capturar o microfone.")
                    }
                } finally {
                    appContext.stopService(Intent(appContext, MicCaptureService::class.java))
                }
            }
        }
    }
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { grants ->
        if (grants[Manifest.permission.RECORD_AUDIO] == true) {
            if (enabled) startCapture()
        } else onError("Permita o microfone para usar a conversa por voz.")
    }
    val requestPermission: () -> Unit = {
        val requested = buildList {
            add(Manifest.permission.RECORD_AUDIO)
            if (Build.VERSION.SDK_INT >= 33) add(Manifest.permission.POST_NOTIFICATIONS)
        }
        permission.launch(requested.toTypedArray())
    }
    var handledStartRequest by remember { mutableStateOf(startRequest) }
    LaunchedEffect(startRequest) {
        if (startRequest != handledStartRequest) {
            handledStartRequest = startRequest
            if (enabled && !active && !stopping) requestPermission()
        }
    }
    LaunchedEffect(stopRequest) {
        if (stopRequest > 0 && active) {
            active = false
            currentCapture[0]?.let { capture ->
                currentCapture[0] = null
                capture.stop()
            }
            onRecording(false)
        }
    }
    DisposableEffect(Unit) { onDispose { currentCapture[0]?.stop() } }
    Button(
        onClick = {
            if (active) {
                stopping = true
                active = false
                onRecording(false)
                currentCapture[0]?.stop()
            } else requestPermission()
        },
        enabled = (enabled || active) && !stopping,
        modifier = Modifier.heightIn(min = 48.dp),
        contentPadding = PaddingValues(horizontal = 10.dp, vertical = 8.dp),
        colors = ButtonDefaults.buttonColors(
            containerColor = if (active) Violet else Panel,
            contentColor = Pearl,
            disabledContainerColor = Panel,
            disabledContentColor = Muted,
        ),
        shape = RoundedCornerShape(16.dp),
    ) {
        Text(
            when { active -> "Parar e enviar"; stopping -> "Enviando…"; else -> label },
            fontSize = 12.sp,
            fontWeight = if (active) FontWeight.SemiBold else FontWeight.Normal,
        )
    }
}

@Composable
private fun Composer(
    text: String,
    connected: Boolean,
    busy: Boolean,
    liveMode: Boolean,
    onText: (String) -> Unit,
    onSend: () -> Unit,
    onNew: () -> Unit,
    onToggleLive: () -> Unit,
    focusRequester: FocusRequester,
) {
    Column(Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 10.dp)) {
        Row(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(28.dp)).background(Panel)
                .border(1.dp, Violet.copy(alpha = 0.14f), RoundedCornerShape(28.dp)).padding(9.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            TextButton(
                onClick = onNew,
                enabled = connected && !busy,
                modifier = Modifier.heightIn(min = 48.dp),
                contentPadding = PaddingValues(horizontal = 8.dp),
            ) { Text("＋", color = Muted, fontSize = 22.sp) }
            BasicTextField(
                value = text,
                onValueChange = onText,
                enabled = connected && !busy,
                modifier = Modifier.weight(1f).focusRequester(focusRequester).padding(vertical = 12.dp),
                textStyle = TextStyle(color = Pearl, fontSize = 15.sp),
                decorationBox = { inner ->
                    Box {
                        if (text.isEmpty()) Text(if (connected) "Mensagem para Aurora" else "Conecte ao PC para começar", color = Muted, fontSize = 14.sp)
                        inner()
                    }
                }
            )
            WaveformButton(liveMode, connected && !busy, onToggleLive)
            Button(
                onClick = onSend,
                enabled = connected && !busy && text.isNotBlank(),
                modifier = Modifier.size(48.dp),
                contentPadding = PaddingValues(0.dp),
                colors = ButtonDefaults.buttonColors(containerColor = Violet, contentColor = Color.White),
                shape = CircleShape,
            ) { Text(if (busy) "…" else "↑", fontSize = 22.sp) }
        }
        Text("O processamento da Aurora acontece no computador pareado.", color = Muted.copy(alpha = 0.72f), fontSize = 10.sp,
            modifier = Modifier.fillMaxWidth().padding(top = 8.dp), textAlign = TextAlign.Center)
    }
}

@Composable
private fun WaveformButton(liveMode: Boolean, enabled: Boolean, onClick: () -> Unit) {
    Button(
        onClick = onClick,
        enabled = enabled || liveMode,
        modifier = Modifier.size(48.dp).semantics {
            contentDescription = if (liveMode) "Sair do modo Live" else "Entrar no modo Live"
        },
        contentPadding = PaddingValues(0.dp),
        colors = ButtonDefaults.buttonColors(
            containerColor = if (liveMode) Violet else Panel,
            contentColor = Pearl,
            disabledContainerColor = Panel,
            disabledContentColor = Muted,
        ),
        shape = CircleShape,
    ) {
        if (liveMode) {
            Text("×", fontSize = 26.sp, fontWeight = FontWeight.Light)
        } else {
            Canvas(Modifier.size(22.dp)) {
                val heights = listOf(.28f, .52f, .82f, .48f, .94f, .56f, .3f)
                val step = size.width / (heights.size * 1.7f)
                val gap = step * .7f
                heights.forEachIndexed { index, ratio ->
                    val x = step / 2f + index * (step + gap)
                    val half = size.height * ratio / 2f
                    drawLine(
                        color = if (enabled) Blue else Muted,
                        start = Offset(x, size.height / 2f - half),
                        end = Offset(x, size.height / 2f + half),
                        strokeWidth = 2.4.dp.toPx(),
                        cap = StrokeCap.Round,
                    )
                }
            }
        }
    }
}

@Composable
private fun LiveOverlay(
    modeActive: Boolean,
    recording: Boolean,
    working: Boolean,
    activity: String,
    startRequest: Int,
    stopRequest: Int,
    onOrbTap: () -> Unit,
    onExit: () -> Unit,
    onRecording: (Boolean) -> Unit,
    onVoice: (ByteArray) -> Unit,
    onVoiceError: (String) -> Unit,
) {
    val interactionSource = remember { MutableInteractionSource() }
    Box(
        Modifier.fillMaxSize()
            .background(
                Brush.radialGradient(
                    colors = listOf(Color(0xFFE8DDF5), Color(0xFFE7F1F7), Ink),
                    radius = 980f,
                )
            )
            .clickable(interactionSource = interactionSource, indication = null, onClick = {}),
        contentAlignment = Alignment.Center,
    ) {
        Column(
            Modifier.fillMaxSize().padding(horizontal = 28.dp, vertical = 22.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.SpaceBetween,
        ) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Text("AURORA  /  LIVE", color = Blue, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                Text("CONECTADA AO PC", color = Muted, fontSize = 10.sp)
            }
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                OrbButton(
                    recording || working || activity == "speaking",
                    Modifier.size(236.dp),
                    activity = if (recording) "listening" else activity,
                    onClick = onOrbTap,
                )
                Spacer(Modifier.height(30.dp))
                Text(
                    when {
                        recording -> "Estou ouvindo você"
                        working -> "A Aurora está pensando"
                        activity == "speaking" -> "A Thalita está falando"
                        else -> "Sua conversa, ao vivo"
                    },
                    color = Pearl,
                    fontSize = 23.sp,
                    fontWeight = FontWeight.Medium,
                    textAlign = TextAlign.Center,
                )
                Spacer(Modifier.height(10.dp))
                Text(
                    when {
                        recording -> "Fale com naturalidade. Toque em Parar e enviar quando terminar."
                        working -> "Sua fala está sendo processada no computador."
                        activity == "speaking" -> "Resposta gerada no PC com Edge TTS · Thalita"
                        else -> "Toque na bolha ou em Falar para iniciar seu próximo turno."
                    },
                    color = Muted,
                    fontSize = 14.sp,
                    lineHeight = 21.sp,
                    textAlign = TextAlign.Center,
                )
                Spacer(Modifier.height(22.dp))
                VoiceCaptureButton(
                    enabled = modeActive && !working,
                    startRequest = startRequest,
                    stopRequest = stopRequest,
                    label = "Falar",
                    onRecording = onRecording,
                    onCaptured = onVoice,
                    onError = onVoiceError,
                )
            }
            Button(
                onClick = onExit,
                modifier = Modifier.size(58.dp).semantics { contentDescription = "Encerrar modo Live" },
                contentPadding = PaddingValues(0.dp),
                colors = ButtonDefaults.buttonColors(containerColor = Panel, contentColor = Pearl),
                shape = CircleShape,
            ) { Text("×", fontSize = 30.sp, fontWeight = FontWeight.Light) }
        }
    }
}

@Composable
private fun MessageBubble(line: ChatLine) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = if (line.fromUser) Arrangement.End else Arrangement.Start) {
        Text(line.text, color = Pearl, fontSize = 15.sp, lineHeight = 22.sp,
            modifier = Modifier.clip(RoundedCornerShape(20.dp)).background(if (line.fromUser) Color(0xFFE9E1F3) else Panel).padding(14.dp))
    }
}

@Composable
private fun ConnectField(value: String, onValue: (String) -> Unit, hint: String) {
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(15.dp)).background(SoftLilac).padding(12.dp)) {
        if (value.isEmpty()) Text(hint, color = Muted, fontSize = 12.sp)
        BasicTextField(value, onValueChange = onValue, singleLine = true,
            textStyle = TextStyle(color = Pearl, fontSize = 14.sp), modifier = Modifier.fillMaxWidth())
    }
}

@Composable
private fun SmallAction(label: String, onClick: () -> Unit) {
    Button(
        onClick = onClick,
        modifier = Modifier.heightIn(min = 48.dp),
        contentPadding = PaddingValues(horizontal = 12.dp, vertical = 8.dp),
        colors = ButtonDefaults.buttonColors(containerColor = Panel, contentColor = Pearl),
        shape = RoundedCornerShape(18.dp),
    ) { Text(label, fontSize = 12.sp) }
}

