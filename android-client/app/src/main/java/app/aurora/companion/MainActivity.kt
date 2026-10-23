package app.aurora.companion

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
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
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

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
    var notice by remember { mutableStateOf("") }
    var conversationId by remember { mutableStateOf(CompanionClient.newConversationId()) }
    var conversations by remember { mutableStateOf<List<PcConversation>>(emptyList()) }
    val lines = remember { mutableStateListOf<ChatLine>() }

    LaunchedEffect(saved) {
        if (saved != null) {
            try {
                conversations = withContext(Dispatchers.IO) { CompanionClient(saved.first, saved.second, saved.third).conversations() }
                connected = true
            } catch (_: Exception) {
                // Keep the pairing credentials for temporary Wi-Fi/server outages.
                connected = false
                notice = "PC indisponível. Confira a mesma rede Wi-Fi e tente conectar novamente."
            }
        }
    }

    fun connectToPc() {
        busy = true
        notice = "Validando certificado e pareando com o PC…"
        scope.launch {
            try {
                val cleanFingerprint = fingerprint.filter { it.isLetterOrDigit() }.lowercase()
                val newToken = withContext(Dispatchers.IO) {
                    CompanionClient(endpoint, cleanFingerprint).pair(pairingCode)
                }
                vault.save(endpoint, cleanFingerprint, newToken)
                token = newToken
                fingerprint = cleanFingerprint
                connected = true
                conversationId = CompanionClient.newConversationId()
                lines.clear()
                notice = "Aurora conectada ao computador."
                showConnect = false
            } catch (error: Exception) {
                notice = error.message ?: "Não consegui conectar ao Aurora no PC."
            } finally {
                busy = false
            }
        }
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
                TopBar(connected, onHistory = { showHistory = true; refreshConversations() }, onConnect = { showConnect = true })
                if (lines.isEmpty()) {
                    Welcome(live, onLive = { live = !live }, connected = connected)
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
                        OrbButton(live, Modifier.size(54.dp)) { live = !live }
                    }
                }
                Composer(
                    text = draft,
                    connected = connected,
                    busy = busy,
                    onText = { draft = it },
                    onSend = ::sendCurrentMessage,
                    onNew = { if (!busy) { conversationId = CompanionClient.newConversationId(); lines.clear(); notice = "Nova conversa no PC." } },
                    onLive = { live = !live }
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
                    ConnectField(endpoint, { endpoint = it }, "Endereço do servidor (ex.: https://192.168.1.10:8765)")
                    ConnectField(pairingCode, { pairingCode = it }, "Código de pareamento")
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
private fun TopBar(connected: Boolean, onHistory: () -> Unit, onConnect: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            OrbButton(false, Modifier.size(38.dp)) { }
            Spacer(Modifier.width(11.dp))
            Column {
                Text("Aurora", color = Pearl, fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
                Text(if (connected) "PC conectado" else "Aguardando seu PC", color = Muted, fontSize = 11.sp)
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            SmallAction("Histórico", onHistory)
            SmallAction(if (connected) "PC" else "Conectar", onConnect)
        }
    }
}

@Composable
private fun Welcome(live: Boolean, onLive: () -> Unit, connected: Boolean) {
    Column(
        modifier = Modifier.fillMaxSize().padding(horizontal = 26.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        OrbButton(live, Modifier.size(150.dp), onLive)
        Spacer(Modifier.height(27.dp))
        Text(if (live) "Modo Live — prévia" else "Oi, sou a Aurora", color = Pearl, fontSize = 26.sp, fontWeight = FontWeight.Medium)
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
            Text("A animação está em prévia; o microfone ainda não foi iniciado.", color = Blue, fontSize = 12.sp, textAlign = TextAlign.Center)
        }
    }
}

@Composable
private fun OrbButton(live: Boolean, modifier: Modifier, onClick: () -> Unit) {
    val transition = rememberInfiniteTransition(label = "aurora-orb")
    val breathe by transition.animateFloat(
        initialValue = 0.96f,
        targetValue = if (live) 1.08f else 1.025f,
        animationSpec = infiniteRepeatable(tween(if (live) 800 else 2400, easing = FastOutSlowInEasing), RepeatMode.Reverse),
        label = "orb-breathe"
    )
    val drift by transition.animateFloat(
        initialValue = 0.15f,
        targetValue = 0.85f,
        animationSpec = infiniteRepeatable(tween(4600, easing = FastOutSlowInEasing), RepeatMode.Reverse),
        label = "orb-reflection"
    )
    Box(modifier.scale(breathe).clip(CircleShape).background(
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

@Composable
private fun Composer(text: String, connected: Boolean, busy: Boolean, onText: (String) -> Unit, onSend: () -> Unit, onNew: () -> Unit, onLive: () -> Unit) {
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
            Text("●", color = if (connected) Blue else Muted, fontSize = 11.sp,
                modifier = Modifier.padding(horizontal = 8.dp).clickable(enabled = connected, onClick = onLive))
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

