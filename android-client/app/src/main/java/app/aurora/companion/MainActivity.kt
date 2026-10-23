package app.aurora.companion

import android.Manifest
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.asPaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
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
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.platform.LocalContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.util.Locale

private val Ink = Color(0xFF090A12)
private val Panel = Color(0xFF151725)
private val Muted = Color(0xFF9DA3B8)
private val Violet = Color(0xFF9A70FF)
private val Blue = Color(0xFF54C7FF)
private val Pearl = Color(0xFFF4F5FF)

data class ChatLine(val fromUser: Boolean, val text: String)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = android.graphics.Color.rgb(9, 10, 18)
        window.navigationBarColor = android.graphics.Color.rgb(9, 10, 18)
        setContent { AuroraShell() }
    }
}

@Composable
private fun AuroraShell() {
    val appContext = LocalContext.current
    val vault = remember { CredentialVault(appContext) }
    val saved = remember { vault.load() }
    val scope = rememberCoroutineScope()
    val discovery = remember { LanDiscovery(appContext) }
    val speech = remember {
        lateinit var engine: TextToSpeech
        engine = TextToSpeech(appContext) { status ->
            if (status == TextToSpeech.SUCCESS) engine.language = Locale("pt", "BR")
        }
        engine
    }
    var remoteState by remember { mutableStateOf("idle") }
    DisposableEffect(speech) {
        speech.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
            override fun onStart(utteranceId: String?) { }
            override fun onDone(utteranceId: String?) { remoteState = "ready" }
            @Deprecated("Deprecated by Android")
            override fun onError(utteranceId: String?) { remoteState = "ready" }
        })
        onDispose { speech.stop(); speech.shutdown() }
    }
    var showConnect by remember { mutableStateOf(false) }
    var showHistory by remember { mutableStateOf(false) }
    var connected by remember { mutableStateOf(false) }
    var endpoint by remember { mutableStateOf(saved?.first.orEmpty()) }
    var pairingCode by remember { mutableStateOf("") }
    var fingerprint by remember { mutableStateOf(saved?.second.orEmpty()) }
    var token by remember { mutableStateOf(saved?.third.orEmpty()) }
    var draft by remember { mutableStateOf("") }
    var live by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var discovering by remember { mutableStateOf(false) }
    var notice by remember { mutableStateOf("") }
    var conversationId by remember { mutableStateOf(CompanionClient.newConversationId()) }
    var conversations by remember { mutableStateOf<List<PcConversation>>(emptyList()) }
    val lines = remember { mutableStateListOf<ChatLine>() }

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
                connected = false
                notice = "Conexão com o PC perdida; o controle local será liberado automaticamente."
            }
        }
    }

    fun connectToPc() {
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
                withContext(Dispatchers.IO) { CompanionClient(endpoint, cleanFingerprint, newToken).acquireControl() }
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
        if (!connected || busy) return
        busy = true
        scope.launch {
            try {
                withContext(Dispatchers.IO) { CompanionClient(endpoint, fingerprint, token).releaseControl() }
                connected = false
                notice = "Celular desconectado. A Aurora do PC voltou a escutar."
            } catch (error: Exception) {
                notice = "Não confirmei a desconexão: ${error.message ?: "verifique o PC"}."
            } finally { busy = false }
        }
    }

    fun findPc() {
        discovering = true
        notice = "Procurando Aurora PCs nesta rede…"
        discovery.start(
            onFound = { found -> endpoint = found; discovering = false; notice = "Aurora PC encontrado. Confira o pin do certificado e pareie." },
            onError = { message -> discovering = false; notice = message },
        )
    }

    fun sendCurrentMessage() {
        val message = draft.trim()
        if (message.isEmpty() || !connected || busy) return
        val selectedConversation = conversationId
        lines += ChatLine(true, message)
        draft = ""
        busy = true
        notice = "Aurora está respondendo pelo computador…"
        scope.launch {
            try {
                val answer = withContext(Dispatchers.IO) {
                    CompanionClient(endpoint, fingerprint, token).sendMessage(selectedConversation, message)
                }
                lines += ChatLine(false, answer)
                notice = "Conversa sincronizada com o PC."
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
        busy = true
        notice = "Transcrevendo no PC e consultando a Aurora…"
        scope.launch {
            try {
                val result = withContext(Dispatchers.IO) {
                    CompanionClient(endpoint, fingerprint, token).sendVoice(selectedConversation, wav)
                }
                lines += ChatLine(true, result.first)
                lines += ChatLine(false, result.second)
                remoteState = "speaking"
                speech.speak(result.second, TextToSpeech.QUEUE_FLUSH, null, "aurora-live-response")
                notice = "Aurora respondeu por voz."
            } catch (error: Exception) {
                notice = "Falha na conversa por voz: ${error.message ?: "verifique a conexão"}."
            } finally {
                busy = false
            }
        }
    }

    fun refreshConversations() {
        if (!connected || busy) return
        busy = true
        scope.launch {
            try {
                conversations = withContext(Dispatchers.IO) { CompanionClient(endpoint, fingerprint, token).conversations() }
                notice = if (conversations.isEmpty()) "Ainda não há conversas salvas no PC." else "Histórico carregado do PC."
            } catch (error: Exception) {
                notice = error.message ?: "Não consegui carregar o histórico."
            } finally {
                busy = false
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
                notice = "Conversa aberta do histórico do PC."
                showHistory = false
            } catch (error: Exception) {
                notice = error.message ?: "Não consegui abrir essa conversa."
            } finally {
                busy = false
            }
        }
    }

    MaterialTheme {
        Surface(color = Ink, modifier = Modifier.fillMaxSize()) {
            Column(
                modifier = Modifier.fillMaxSize().padding(WindowInsets.statusBars.asPaddingValues())
                    .padding(WindowInsets.navigationBars.asPaddingValues()).imePadding()
            ) {
                TopBar(connected, remoteState, onHistory = { showHistory = true; refreshConversations() }, onConnect = { showConnect = true }, onDisconnect = ::disconnectFromPc)
                if (lines.isEmpty()) {
                    Welcome(live || busy, onLive = { }, connected = connected,
                        activity = if (live) "listening" else remoteState)
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
                        OrbButton(live || busy, Modifier.size(54.dp), activity = if (live) "listening" else remoteState) { }
                    }
                }
                Composer(
                    text = draft,
                    connected = connected,
                    busy = busy,
                    onText = { draft = it },
                    onSend = ::sendCurrentMessage,
                    onVoice = ::sendVoiceAudio,
                    onRecording = { live = it },
                    onVoiceError = { notice = it },
                    onNew = { if (!busy) { conversationId = CompanionClient.newConversationId(); lines.clear(); notice = "Nova conversa no PC." } },
                    onLive = { }
                )
                if (notice.isNotBlank()) Text(notice, color = Muted, fontSize = 11.sp, modifier = Modifier.fillMaxWidth().padding(bottom = 6.dp), textAlign = TextAlign.Center)
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

    if (showHistory) {
        AlertDialog(
            onDismissRequest = { showHistory = false },
            containerColor = Panel,
            title = { Text("Conversas", color = Pearl) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (conversations.isEmpty()) Text("Nenhuma conversa carregada. O histórico fica no PC.", color = Muted)
                    conversations.take(12).forEach { item ->
                        Text(item.title.ifBlank { "Conversa" }, color = Pearl, modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(Ink).clickable { openConversation(item.id) }.padding(10.dp))
                    }
                }
            },
            confirmButton = { TextButton(onClick = { refreshConversations() }) { Text(if (busy) "Carregando…" else "Atualizar", color = Blue) } },
            dismissButton = { TextButton(onClick = { showHistory = false }) { Text("Fechar", color = Muted) } }
        )
    }
}

@Composable
private fun TopBar(connected: Boolean, remoteState: String, onHistory: () -> Unit, onConnect: () -> Unit, onDisconnect: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            OrbButton(false, Modifier.size(38.dp), activity = if (connected) remoteState else "idle") { }
            Spacer(Modifier.width(11.dp))
            Column {
                Text("Aurora", color = Pearl, fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
                Text(if (connected) "${remoteStateLabel(remoteState)} · PC em pausa" else "Aguardando seu PC", color = Muted, fontSize = 11.sp)
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            SmallAction("Histórico", onHistory)
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
private fun Welcome(live: Boolean, onLive: () -> Unit, connected: Boolean, activity: String) {
    Column(
        modifier = Modifier.fillMaxSize().padding(horizontal = 26.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        OrbButton(live, Modifier.size(150.dp), activity, onLive)
        Spacer(Modifier.height(27.dp))
        Text(if (live) "Estou ouvindo você" else "Oi, sou a Aurora", color = Pearl, fontSize = 26.sp, fontWeight = FontWeight.Medium)
        Spacer(Modifier.height(9.dp))
        Text(
            if (connected) "Fale comigo ou escreva uma mensagem."
            else "Conecte ao computador para conversar com sua assistente.",
            color = Muted, textAlign = TextAlign.Center, fontSize = 15.sp, lineHeight = 22.sp
        )
        Spacer(Modifier.height(26.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(9.dp)) {
            Suggestion("Pesquisar na web")
            Suggestion("Conversar")
        }
        Spacer(Modifier.height(8.dp))
        Suggestion("Pedir algo ao meu PC")
        if (live) {
            Spacer(Modifier.height(18.dp))
            Text("Toque em Parar para enviar sua fala ao computador.", color = Blue, fontSize = 12.sp, textAlign = TextAlign.Center)
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
            colors = listOf(Color(0xFFF4F6FF), Color(0xFFE8E8FF), Color(0xFFBFAEFF), Color(0xFF698CFF), Color(0xFF7753E8)),
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
private fun VoiceCaptureButton(enabled: Boolean, onRecording: (Boolean) -> Unit, onCaptured: (ByteArray) -> Unit, onError: (String) -> Unit) {
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
        if (grants[Manifest.permission.RECORD_AUDIO] == true) startCapture()
        else onError("Permita o microfone para usar a conversa por voz.")
    }
    DisposableEffect(Unit) { onDispose { currentCapture[0]?.stop() } }
    Text(
        when { active -> "Parar"; stopping -> "Enviando"; else -> "Voz" },
        color = if (enabled || active) Blue else Muted,
        fontSize = 11.sp,
        modifier = Modifier.padding(horizontal = 8.dp).clickable(enabled = (enabled || active) && !stopping) {
            if (active) {
                stopping = true
                active = false
                onRecording(false)
                currentCapture[0]?.stop()
            } else {
                val requested = buildList {
                    add(Manifest.permission.RECORD_AUDIO)
                    if (Build.VERSION.SDK_INT >= 33) add(Manifest.permission.POST_NOTIFICATIONS)
                }
                permission.launch(requested.toTypedArray())
            }
        },
    )
}

@Composable
private fun Composer(text: String, connected: Boolean, busy: Boolean, onText: (String) -> Unit, onSend: () -> Unit, onVoice: (ByteArray) -> Unit, onRecording: (Boolean) -> Unit, onVoiceError: (String) -> Unit, onNew: () -> Unit, onLive: () -> Unit) {
    Column(Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 10.dp)) {
        Row(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(28.dp)).background(Panel)
                .border(1.dp, Color.White.copy(alpha = 0.08f), RoundedCornerShape(28.dp)).padding(9.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text("+", color = Muted, fontSize = 25.sp, modifier = Modifier.clickable(enabled = connected && !busy, onClick = onNew).padding(horizontal = 10.dp))
            BasicTextField(
                value = text,
                onValueChange = onText,
                enabled = connected && !busy,
                modifier = Modifier.weight(1f).padding(vertical = 12.dp),
                textStyle = TextStyle(color = Pearl, fontSize = 15.sp),
                decorationBox = { inner ->
                    Box {
                        if (text.isEmpty()) Text(if (connected) "Mensagem para Aurora" else "Conecte ao PC para começar", color = Muted, fontSize = 14.sp)
                        inner()
                    }
                }
            )
            VoiceCaptureButton(enabled = connected && !busy, onRecording = onRecording, onCaptured = onVoice, onError = onVoiceError)
            Text(if (busy) "…" else "↑", color = if (connected && !busy) Ink else Muted, fontSize = 20.sp,
                modifier = Modifier.clip(CircleShape).background(if (connected && !busy) Pearl else Color(0xFF353747), CircleShape)
                    .clickable(enabled = connected && !busy, onClick = onSend).padding(horizontal = 13.dp, vertical = 7.dp))
        }
        Text("O processamento da Aurora acontece no computador pareado.", color = Muted.copy(alpha = 0.72f), fontSize = 10.sp,
            modifier = Modifier.fillMaxWidth().padding(top = 8.dp), textAlign = TextAlign.Center)
    }
}

@Composable
private fun MessageBubble(line: ChatLine) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = if (line.fromUser) Arrangement.End else Arrangement.Start) {
        Text(line.text, color = Pearl, fontSize = 15.sp, lineHeight = 22.sp,
            modifier = Modifier.clip(RoundedCornerShape(20.dp)).background(if (line.fromUser) Color(0xFF34364B) else Panel).padding(14.dp))
    }
}

@Composable
private fun ConnectField(value: String, onValue: (String) -> Unit, hint: String) {
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(15.dp)).background(Ink).padding(12.dp)) {
        if (value.isEmpty()) Text(hint, color = Muted, fontSize = 12.sp)
        BasicTextField(value, onValueChange = onValue, singleLine = true,
            textStyle = TextStyle(color = Pearl, fontSize = 14.sp), modifier = Modifier.fillMaxWidth())
    }
}

@Composable
private fun SmallAction(label: String, onClick: () -> Unit) {
    Text(label, color = Pearl, fontSize = 12.sp,
        modifier = Modifier.clip(RoundedCornerShape(18.dp)).background(Panel).clickable(onClick = onClick).padding(horizontal = 12.dp, vertical = 9.dp))
}

@Composable
private fun Suggestion(label: String) {
    Text(label, color = Color(0xFFC7C9D6), fontSize = 12.sp,
        modifier = Modifier.clip(RoundedCornerShape(18.dp)).background(Panel).padding(horizontal = 13.dp, vertical = 9.dp))
}

