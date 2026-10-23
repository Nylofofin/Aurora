// SPDX-License-Identifier: GPL-3.0-only
package app.aurora.companion

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
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
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat

private enum class AppDestination { CHAT, DESKTOP, SETTINGS }
data class ChatLine(val fromUser: Boolean, val text: String)

class MainActivity : ComponentActivity() {
    private val viewModel: AuroraViewModel by viewModels()
    private var pendingMicrophoneAction: (() -> Unit)? = null

    private val microphonePermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        val action = pendingMicrophoneAction
        pendingMicrophoneAction = null
        if (granted) action?.invoke() else viewModel.notice = "O Android não liberou o microfone. Confira a permissão do app nas configurações."
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            val colors = AuroraThemes.getTheme(viewModel.currentThemeName)
            AuroraMaterialApp(
                viewModel = viewModel,
                colors = colors,
                requestMicrophone = { action ->
                    if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
                        action()
                    } else {
                        pendingMicrophoneAction = action
                        microphonePermission.launch(Manifest.permission.RECORD_AUDIO)
                    }
                },
            )
        }
    }

    override fun onPause() {
        super.onPause()
        if (viewModel.liveMode) viewModel.showFloatingBubble()
    }

    override fun onResume() {
        super.onResume()
        viewModel.hideFloatingBubble()
    }
}

@Composable
private fun AuroraMaterialApp(
    viewModel: AuroraViewModel,
    colors: AuroraColors,
    requestMicrophone: (() -> Unit) -> Unit,
) {
    MaterialTheme {
        Surface(Modifier.fillMaxSize(), color = colors.background) {
            if (!viewModel.userProfile.isLoggedIn) {
                LocalProfileScreen(viewModel, colors)
            } else if (viewModel.liveMode) {
                BackHandler { viewModel.leaveLiveMode() }
                LiveScreen(viewModel, colors)
            } else {
                MainShell(viewModel, colors, requestMicrophone)
            }
        }
    }
}

@Composable
private fun MainShell(
    viewModel: AuroraViewModel,
    colors: AuroraColors,
    requestMicrophone: (() -> Unit) -> Unit,
) {
    var destination by remember(viewModel.activeTab) {
        mutableStateOf(
            when (viewModel.activeTab) {
                CompanionTab.DESKTOP -> AppDestination.DESKTOP
                CompanionTab.SETTINGS -> AppDestination.SETTINGS
                else -> AppDestination.CHAT
            },
        )
    }
    var showConnect by remember { mutableStateOf(false) }
    var showHistory by remember { mutableStateOf(false) }

    BackHandler(enabled = showHistory || showConnect) {
        if (showConnect) showConnect = false else showHistory = false
    }

    Scaffold(
        contentWindowInsets = WindowInsets.statusBars,
        containerColor = colors.background,
        bottomBar = {
            NavigationBar(
                windowInsets = WindowInsets.navigationBars,
                containerColor = colors.surface,
                tonalElevation = 0.dp,
            ) {
                listOf(
                    Triple(AppDestination.CHAT, "Conversa", "○"),
                    Triple(AppDestination.DESKTOP, "PC", "▣"),
                    Triple(AppDestination.SETTINGS, "Ajustes", "⚙"),
                ).forEach { (target, label, mark) ->
                    NavigationBarItem(
                        selected = destination == target,
                        onClick = {
                            if (target == AppDestination.DESKTOP && !viewModel.connected) {
                                viewModel.notice = "Conecte o PC antes de abrir o desktop remoto."
                                showConnect = true
                            } else {
                                if (destination == AppDestination.DESKTOP && target != destination) viewModel.stopScreenView()
                                destination = target
                                viewModel.activeTab = when (target) {
                                    AppDestination.CHAT -> CompanionTab.CHAT
                                    AppDestination.DESKTOP -> CompanionTab.DESKTOP
                                    AppDestination.SETTINGS -> CompanionTab.SETTINGS
                                }
                                if (target == AppDestination.DESKTOP && !viewModel.showScreen) viewModel.startScreenView()
                            }
                        },
                        icon = { Text(mark, fontSize = 19.sp, fontWeight = FontWeight.Medium) },
                        label = { Text(label, maxLines = 1) },
                        colors = NavigationBarItemDefaults.colors(
                            selectedIconColor = colors.primary,
                            selectedTextColor = colors.primary,
                            indicatorColor = colors.primary.copy(alpha = .12f),
                            unselectedIconColor = colors.textSecondary,
                            unselectedTextColor = colors.textSecondary,
                        ),
                    )
                }
            }
        },
    ) { insets ->
        Column(Modifier.fillMaxSize().padding(insets)) {
            AppHeader(viewModel, colors, onHistory = { showHistory = true }, onConnect = { showConnect = true })
            Box(Modifier.weight(1f).fillMaxWidth()) {
                AnimatedContent(targetState = destination, label = "main-destination") { target ->
                    when (target) {
                        AppDestination.CHAT -> ChatScreen(viewModel, colors, requestMicrophone)
                        AppDestination.DESKTOP -> DesktopScreen(viewModel, colors)
                        AppDestination.SETTINGS -> SettingsScreen(viewModel, colors, requestMicrophone) { showConnect = true }
                    }
                }
            }
        }
    }

    if (showConnect) PairingDialog(viewModel, colors, onDismiss = { showConnect = false })
    if (showHistory) HistoryDialog(viewModel, colors, onDismiss = { showHistory = false })
}

@Composable
private fun AppHeader(viewModel: AuroraViewModel, colors: AuroraColors, onHistory: () -> Unit, onConnect: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().padding(start = 18.dp, end = 14.dp, top = 8.dp, bottom = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Image(
            painter = painterResource(R.drawable.ic_aurora_foreground),
            contentDescription = "Orb Aurora",
            modifier = Modifier.size(42.dp),
        )
        Spacer(Modifier.width(10.dp))
        Column(Modifier.weight(1f)) {
            Text("Aurora", color = colors.textPrimary, fontSize = 19.sp, fontWeight = FontWeight.SemiBold)
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(7.dp).clip(CircleShape).background(if (viewModel.connected) Color(0xFF438C72) else colors.textSecondary.copy(alpha = .6f)))
                Spacer(Modifier.width(6.dp))
                Text(
                    if (viewModel.connected) "PC conectado" else "Seu assistente no computador",
                    color = colors.textSecondary,
                    fontSize = 11.sp,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
        HeaderButton(if (viewModel.connected) "PC ✓" else "Conectar", colors, onConnect)
        Spacer(Modifier.width(5.dp))
        HeaderButton("☰", colors, onHistory, "Abrir histórico")
        Spacer(Modifier.width(5.dp))
        Box(
            Modifier.size(40.dp).clip(CircleShape).background(colors.surfaceVariant).clickable {
                viewModel.activeTab = CompanionTab.SETTINGS
            },
            contentAlignment = Alignment.Center,
        ) { Text(viewModel.userProfile.avatarIcon, fontSize = 18.sp) }
    }
}

@Composable
private fun HeaderButton(label: String, colors: AuroraColors, onClick: () -> Unit, description: String = label) {
    Surface(
        onClick = onClick,
        shape = RoundedCornerShape(18.dp),
        color = colors.surfaceVariant,
        modifier = Modifier.semantics { contentDescription = description },
    ) {
        Box(Modifier.heightIn(min = 38.dp).padding(horizontal = 11.dp), contentAlignment = Alignment.Center) {
            Text(label, color = colors.primary, fontSize = 11.sp, fontWeight = FontWeight.SemiBold, maxLines = 1)
        }
    }
}

@Composable
private fun ChatScreen(
    viewModel: AuroraViewModel,
    colors: AuroraColors,
    requestMicrophone: (() -> Unit) -> Unit,
) {
    var draft by remember { mutableStateOf("") }
    val keyboard = LocalSoftwareKeyboardController.current
    val send = {
        if (viewModel.connected && !viewModel.busy && draft.isNotBlank()) {
            viewModel.sendCurrentMessage(draft.trim())
            draft = ""
            keyboard?.hide()
        }
    }

    Column(Modifier.fillMaxSize().imePadding()) {
        BoxWithConstraints(Modifier.weight(1f).fillMaxWidth()) {
            if (viewModel.lines.isEmpty()) {
                val orbSize = minOf(maxWidth * .34f, maxHeight * .22f, 126.dp)
                Column(
                    Modifier.fillMaxWidth().widthIn(max = 560.dp).align(Alignment.Center).padding(horizontal = 24.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    AuroraOrb(orbSize, viewModel.remoteState, colors)
                    Spacer(Modifier.height(19.dp))
                    Text("Oi, ${viewModel.userProfile.username.ifBlank { "por aí" }}", color = colors.textPrimary, fontSize = 24.sp, fontWeight = FontWeight.SemiBold, textAlign = TextAlign.Center)
                    Spacer(Modifier.height(8.dp))
                    Text(
                        if (viewModel.connected) "Sua Aurora está pronta. Converse, pesquise ou peça para controlar o computador."
                        else "Conecte seu computador para conversar com a Aurora e acessar os recursos dele.",
                        color = colors.textSecondary,
                        fontSize = 14.sp,
                        lineHeight = 21.sp,
                        textAlign = TextAlign.Center,
                    )
                    if (!viewModel.connected) {
                        Spacer(Modifier.height(17.dp))
                        Button(onClick = { viewModel.activeTab = CompanionTab.SETTINGS }, colors = ButtonDefaults.buttonColors(containerColor = colors.primary)) {
                            Text("Configurar conexão", color = Color.White)
                        }
                    }
                }
            } else {
                LazyColumn(
                    modifier = Modifier.fillMaxSize().padding(horizontal = 16.dp),
                    reverseLayout = true,
                    contentPadding = PaddingValues(top = 14.dp, bottom = 12.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    items(viewModel.lines.reversed()) { line -> MessageBubble(line, viewModel.userProfile.username, colors) }
                }
            }
        }
        if (viewModel.notice.isNotBlank()) {
            Text(viewModel.notice, color = colors.textSecondary, fontSize = 11.sp, maxLines = 2, overflow = TextOverflow.Ellipsis,
                modifier = Modifier.fillMaxWidth().padding(horizontal = 18.dp, vertical = 4.dp), textAlign = TextAlign.Center)
        }
        MessageComposer(
            value = draft,
            onValueChange = { draft = it },
            colors = colors,
            enabled = viewModel.connected && !viewModel.busy,
            canSend = draft.isNotBlank(),
            onNew = viewModel::newConversation,
            onLive = { requestMicrophone { viewModel.enterLiveMode() } },
            onSend = send,
        )
        Text(
            if (viewModel.connected) "A IA e a voz são processadas pelo seu PC" else "Perfil local • os modelos ficam no seu PC",
            color = colors.textSecondary.copy(alpha = .8f),
            fontSize = 10.sp,
            modifier = Modifier.fillMaxWidth().padding(bottom = 4.dp),
            textAlign = TextAlign.Center,
        )
    }
}

@Composable
private fun MessageBubble(line: ChatLine, username: String, colors: AuroraColors) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = if (line.fromUser) Arrangement.End else Arrangement.Start) {
        Column(Modifier.fillMaxWidth(.88f)) {
            Text(if (line.fromUser) username else "Aurora", color = colors.textSecondary, fontSize = 11.sp, modifier = Modifier.padding(horizontal = 7.dp, vertical = 3.dp))
            Surface(
                shape = RoundedCornerShape(20.dp, 20.dp, if (line.fromUser) 5.dp else 20.dp, if (line.fromUser) 20.dp else 5.dp),
                color = if (line.fromUser) colors.primary else colors.surface,
            ) {
                Text(line.text, color = if (line.fromUser) Color.White else colors.textPrimary, fontSize = 15.sp, lineHeight = 22.sp,
                    modifier = Modifier.padding(horizontal = 15.dp, vertical = 12.dp))
            }
        }
    }
}

@Composable
private fun MessageComposer(
    value: String,
    onValueChange: (String) -> Unit,
    colors: AuroraColors,
    enabled: Boolean,
    canSend: Boolean,
    onNew: () -> Unit,
    onLive: () -> Unit,
    onSend: () -> Unit,
) {
    Row(
        Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 8.dp)
            .clip(RoundedCornerShape(28.dp)).background(colors.surface)
            .border(1.dp, colors.primary.copy(alpha = .12f), RoundedCornerShape(28.dp))
            .padding(start = 15.dp, end = 7.dp, top = 7.dp, bottom = 7.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        OutlinedTextField(
            value = value,
            onValueChange = onValueChange,
            enabled = enabled,
            modifier = Modifier.weight(1f),
            placeholder = { Text("Mensagem…", fontSize = 14.sp, color = colors.textSecondary) },
            maxLines = 4,
            shape = RoundedCornerShape(20.dp),
            colors = AuroraFieldColors(colors),
        )
        Spacer(Modifier.width(4.dp))
        RoundButton("+", "Nova conversa", colors, enabled, onNew)
        Spacer(Modifier.width(4.dp))
        RoundButton("≋", "Iniciar modo Live", colors, enabled, onLive)
        Spacer(Modifier.width(4.dp))
        RoundButton("↑", "Enviar mensagem", colors, enabled && canSend, onSend, primary = true)
    }
}

@Composable
private fun RoundButton(label: String, description: String, colors: AuroraColors, enabled: Boolean, onClick: () -> Unit, primary: Boolean = false) {
    Surface(
        onClick = onClick,
        enabled = enabled,
        shape = CircleShape,
        color = if (primary) colors.primary else colors.surfaceVariant,
        modifier = Modifier.size(42.dp).alpha(if (enabled) 1f else .45f).semantics { contentDescription = description },
    ) {
        Box(contentAlignment = Alignment.Center) {
            Text(label, color = if (primary) Color.White else colors.primary, fontSize = if (label == "↑") 23.sp else 19.sp, fontWeight = FontWeight.Medium)
        }
    }
}

@Composable
private fun LiveScreen(viewModel: AuroraViewModel, colors: AuroraColors) {
    BoxWithConstraints(
        Modifier.fillMaxSize().background(Brush.verticalGradient(listOf(colors.background, colors.surfaceVariant.copy(alpha = .62f)))),
    ) {
        val orbSize = minOf(maxWidth * .62f, maxHeight * .4f, 250.dp)
        Column(
            Modifier.fillMaxSize().padding(horizontal = 22.dp, vertical = 14.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.SpaceBetween,
        ) {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("MODO LIVE", color = colors.primary, fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.5.sp)
                    Text("Conversa por voz", color = colors.textPrimary, fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
                }
                Surface(onClick = { viewModel.leaveLiveMode() }, shape = CircleShape, color = colors.surface, modifier = Modifier.size(44.dp).semantics { contentDescription = "Encerrar modo Live" }) {
                    Box(contentAlignment = Alignment.Center) { Text("×", color = colors.textPrimary, fontSize = 27.sp, fontWeight = FontWeight.Light) }
                }
            }
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                AuroraOrb(orbSize, viewModel.remoteState, colors)
                Spacer(Modifier.height(22.dp))
                Text(
                    when (viewModel.remoteState) {
                        "listening" -> "Estou ouvindo você"
                        "speaking" -> "Estou falando"
                        "transcribing" -> "Entendendo sua fala"
                        "preparing", "thinking" -> "Pensando na resposta"
                        else -> "Pode falar comigo"
                    },
                    color = colors.textPrimary,
                    fontSize = 21.sp,
                    fontWeight = FontWeight.SemiBold,
                    textAlign = TextAlign.Center,
                )
                Spacer(Modifier.height(6.dp))
                Text("A escuta continua entre as respostas. Toque no X para encerrar.", color = colors.textSecondary, fontSize = 13.sp, textAlign = TextAlign.Center)
                viewModel.lines.lastOrNull { !it.fromUser }?.let { answer ->
                    Spacer(Modifier.height(14.dp))
                    Text(answer.text, color = colors.textSecondary, fontSize = 14.sp, lineHeight = 20.sp, textAlign = TextAlign.Center,
                        maxLines = 5, overflow = TextOverflow.Ellipsis, modifier = Modifier.fillMaxWidth().widthIn(max = 560.dp))
                }
            }
            Surface(
                shape = RoundedCornerShape(22.dp),
                color = colors.surface.copy(alpha = .88f),
                modifier = Modifier.fillMaxWidth().widthIn(max = 560.dp),
            ) {
                Row(Modifier.padding(horizontal = 15.dp, vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(9.dp).clip(CircleShape).background(if (viewModel.live) colors.primary else colors.textSecondary.copy(alpha = .5f)))
                    Spacer(Modifier.width(9.dp))
                    Text(if (viewModel.live) "Microfone ativo" else "Conectando ao PC…", color = colors.textSecondary, fontSize = 12.sp)
                    Spacer(Modifier.weight(1f))
                    Text("Áudio no celular", color = colors.primary, fontSize = 12.sp, fontWeight = FontWeight.Medium)
                }
            }
        }
    }
}

@Composable
private fun AuroraOrb(size: Dp, state: String, colors: AuroraColors) {
    val active = state in setOf("listening", "speaking", "thinking", "preparing", "transcribing")
    val transition = rememberInfiniteTransition(label = "aurora-pulse-$state")
    val pulse by transition.animateFloat(
        initialValue = 1f,
        targetValue = if (active) 1.045f else 1.015f,
        animationSpec = infiniteRepeatable(tween(if (state == "speaking") 720 else 1700, easing = FastOutSlowInEasing), RepeatMode.Reverse),
        label = "orb-scale",
    )
    Box(Modifier.size(size).scale(pulse), contentAlignment = Alignment.Center) {
        Image(
            painter = painterResource(R.drawable.ic_aurora_foreground),
            contentDescription = null,
            contentScale = ContentScale.Fit,
            modifier = Modifier.fillMaxSize(),
        )
    }
}

@Composable
private fun DesktopScreen(viewModel: AuroraViewModel, colors: AuroraColors) {
    Column(Modifier.fillMaxSize().padding(horizontal = 14.dp, vertical = 8.dp)) {
        Row(Modifier.fillMaxWidth().padding(bottom = 9.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("Computador", color = colors.textPrimary, fontSize = 19.sp, fontWeight = FontWeight.SemiBold)
                Text(if (viewModel.showScreen) "Tela compartilhada" else "Controle remoto", color = colors.textSecondary, fontSize = 12.sp)
            }
            Button(
                onClick = { viewModel.toggleScreenView() },
                colors = ButtonDefaults.buttonColors(containerColor = if (viewModel.showScreen) colors.surfaceVariant else colors.primary),
                contentPadding = PaddingValues(horizontal = 14.dp, vertical = 9.dp),
            ) { Text(if (viewModel.showScreen) "Parar" else "Mostrar tela", color = if (viewModel.showScreen) colors.textPrimary else Color.White) }
        }
        Box(Modifier.weight(1f).fillMaxWidth().clip(RoundedCornerShape(24.dp)).background(Color(0xFF17151D)), contentAlignment = Alignment.Center) {
            val bitmap = viewModel.screenBitmap
            if (bitmap != null) DesktopImage(bitmap, viewModel) else Column(Modifier.padding(25.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                Image(painterResource(R.drawable.ic_aurora_foreground), null, Modifier.size(66.dp))
                Spacer(Modifier.height(15.dp))
                Text(if (viewModel.showScreen) "Aguardando autorização no computador…" else "Toque em Mostrar tela para começar", color = Color.White, fontSize = 15.sp, textAlign = TextAlign.Center)
                Spacer(Modifier.height(7.dp))
                Text("O GNOME exibirá a solicitação de compartilhamento e controle.", color = Color.White.copy(alpha = .68f), fontSize = 12.sp, textAlign = TextAlign.Center)
            }
        }
        Text("Toque: clicar • toque duplo: abrir • segure: botão direito • arraste: mover", color = colors.textSecondary, fontSize = 11.sp, textAlign = TextAlign.Center,
            modifier = Modifier.fillMaxWidth().padding(vertical = 10.dp))
    }
}

@Composable
private fun DesktopImage(bitmap: ImageBitmap, viewModel: AuroraViewModel) {
    fun mapToScreen(point: Offset, width: Int, height: Int): Pair<Float, Float>? {
        if (width <= 0 || height <= 0) return null
        val fit = minOf(width / bitmap.width.toFloat(), height / bitmap.height.toFloat())
        val imageWidth = bitmap.width * fit
        val imageHeight = bitmap.height * fit
        val left = (width - imageWidth) / 2f
        val top = (height - imageHeight) / 2f
        if (point.x < left || point.y < top || point.x > left + imageWidth || point.y > top + imageHeight) return null
        return ((point.x - left) / imageWidth).coerceIn(0f, 1f) to ((point.y - top) / imageHeight).coerceIn(0f, 1f)
    }
    Image(
        bitmap = bitmap,
        contentDescription = "Tela do computador; toque para controlar",
        contentScale = ContentScale.Fit,
        modifier = Modifier.fillMaxSize()
            .pointerInput(bitmap) {
                detectTapGestures(
                    onTap = { mapToScreen(it, size.width, size.height)?.let { (x, y) -> viewModel.sendDesktopInput("click", x, y) } },
                    onDoubleTap = { mapToScreen(it, size.width, size.height)?.let { (x, y) -> viewModel.sendDesktopInput("double_click", x, y) } },
                    onLongPress = { mapToScreen(it, size.width, size.height)?.let { (x, y) -> viewModel.sendDesktopInput("click", x, y, button = 3) } },
                )
            }
            .pointerInput(bitmap) {
                var last: Pair<Float, Float>? = null
                detectDragGestures(
                    onDragStart = { mapToScreen(it, size.width, size.height)?.also { point -> last = point; viewModel.sendDesktopInput("down", point.first, point.second) } },
                    onDragEnd = { last?.let { viewModel.sendDesktopInput("up", it.first, it.second) }; last = null },
                    onDragCancel = { last?.let { viewModel.sendDesktopInput("up", it.first, it.second) }; last = null },
                ) { change, _ ->
                    change.consume()
                    mapToScreen(change.position, size.width, size.height)?.let { last = it; viewModel.sendDesktopInput("move", it.first, it.second) }
                }
            },
    )
}

@Composable
private fun SettingsScreen(viewModel: AuroraViewModel, colors: AuroraColors, requestMicrophone: (() -> Unit) -> Unit, onConnect: () -> Unit) {
    var name by remember(viewModel.userProfile.username) { mutableStateOf(viewModel.userProfile.username) }
    var age by remember(viewModel.userProfile.age) { mutableStateOf(viewModel.userProfile.age) }
    var avatar by remember(viewModel.userProfile.avatarIcon) { mutableStateOf(viewModel.userProfile.avatarIcon) }
    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(horizontal = 17.dp),
        contentPadding = PaddingValues(top = 8.dp, bottom = 20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Column(Modifier.padding(bottom = 2.dp)) {
                Text("Ajustes", color = colors.textPrimary, fontSize = 24.sp, fontWeight = FontWeight.SemiBold)
                Text("Seu perfil, aparência e conexão", color = colors.textSecondary, fontSize = 13.sp)
            }
        }
        item {
            SettingsCard(colors) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Image(painterResource(R.drawable.ic_aurora_foreground), null, Modifier.size(44.dp))
                    Spacer(Modifier.width(11.dp))
                    Column {
                        Text("Perfil local", color = colors.textPrimary, fontWeight = FontWeight.SemiBold)
                        Text("Salvo neste celular", color = colors.textSecondary, fontSize = 12.sp)
                    }
                }
                Spacer(Modifier.height(12.dp))
                OutlinedTextField(name, { name = it }, label = { Text("Nome") }, modifier = Modifier.fillMaxWidth(), singleLine = true, colors = AuroraFieldColors(colors))
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(age, { age = it }, label = { Text("Idade (opcional)") }, modifier = Modifier.fillMaxWidth(), singleLine = true, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), colors = AuroraFieldColors(colors))
                Spacer(Modifier.height(10.dp))
                Text("Avatar", color = colors.textSecondary, fontSize = 12.sp)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 6.dp)) {
                    listOf("🌌", "✨", "🪐", "🔮", "🚀").forEach { option ->
                        Surface(onClick = { avatar = option }, shape = CircleShape, color = if (avatar == option) colors.primary.copy(alpha = .16f) else colors.surfaceVariant,
                            modifier = Modifier.size(42.dp).border(if (avatar == option) 1.dp else 0.dp, if (avatar == option) colors.primary else Color.Transparent, CircleShape)) {
                            Box(contentAlignment = Alignment.Center) { Text(option, fontSize = 18.sp) }
                        }
                    }
                }
                Spacer(Modifier.height(12.dp))
                Button(onClick = { viewModel.updateUserProfile(name, age, avatar) }, modifier = Modifier.fillMaxWidth(), colors = ButtonDefaults.buttonColors(containerColor = colors.primary)) {
                    Text("Salvar perfil", color = Color.White)
                }
            }
        }
        item {
            SettingsCard(colors) {
                Text("Aparência", color = colors.textPrimary, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
                Text("Escolha o tema do cliente", color = colors.textSecondary, fontSize = 12.sp)
                Spacer(Modifier.height(10.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    ThemeChoice("aurora", "Aurora", viewModel, colors, Modifier.weight(1f))
                    ThemeChoice("dark", "Noturno", viewModel, colors, Modifier.weight(1f))
                }
                Spacer(Modifier.height(8.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    ThemeChoice("light", "Névoa", viewModel, colors, Modifier.weight(1f))
                    ThemeChoice("neon", "Neon", viewModel, colors, Modifier.weight(1f))
                }
            }
        }
        item {
            SettingsCard(colors) {
                Text("Computador", color = colors.textPrimary, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.height(4.dp))
                Text(if (viewModel.connected) "Conectado • ${viewModel.endpoint}" else "Desconectado", color = colors.textSecondary, fontSize = 12.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
                Spacer(Modifier.height(10.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = onConnect, modifier = Modifier.weight(1f), colors = ButtonDefaults.buttonColors(containerColor = colors.primary)) {
                        Text(if (viewModel.connected) "Gerenciar conexão" else "Conectar ao PC", color = Color.White, maxLines = 1)
                    }
                    if (viewModel.connected) TextButton(onClick = viewModel::disconnectFromPc) { Text("Sair", color = colors.textSecondary) }
                }
            }
        }
        item {
            SettingsCard(colors) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("Palavra de ativação", color = colors.textPrimary, fontWeight = FontWeight.SemiBold)
                        Text("O Android mantém uma notificação enquanto escuta", color = colors.textSecondary, fontSize = 12.sp, lineHeight = 17.sp)
                    }
                    Switch(checked = viewModel.alwaysOnWakeActive, onCheckedChange = { requestMicrophone { viewModel.toggleAlwaysOnWake() } }, colors = SwitchDefaults.colors(checkedThumbColor = colors.primary))
                }
                HorizontalDivider(Modifier.padding(vertical = 10.dp), color = colors.surfaceVariant)
                Text("O microfone é controlado pelo Android. Live e ativação em segundo plano usam uma notificação visível; não há captura oculta.", color = colors.textSecondary, fontSize = 11.sp, lineHeight = 16.sp)
                TextButton(onClick = viewModel::logout, modifier = Modifier.fillMaxWidth()) { Text("Sair do perfil local", color = colors.textSecondary) }
            }
        }
    }
}

@Composable
private fun ThemeChoice(key: String, label: String, viewModel: AuroraViewModel, colors: AuroraColors, modifier: Modifier) {
    val selected = viewModel.currentThemeName == key
    Surface(onClick = { viewModel.updateTheme(key) }, shape = RoundedCornerShape(14.dp),
        color = if (selected) colors.primary.copy(alpha = .12f) else colors.surfaceVariant,
        modifier = modifier.heightIn(min = 45.dp).border(if (selected) 1.dp else 0.dp, if (selected) colors.primary else Color.Transparent, RoundedCornerShape(14.dp))) {
        Box(contentAlignment = Alignment.Center) { Text(label, color = colors.textPrimary, fontSize = 12.sp, fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal) }
    }
}

@Composable
private fun LocalProfileScreen(viewModel: AuroraViewModel, colors: AuroraColors) {
    var name by remember { mutableStateOf("") }
    var age by remember { mutableStateOf("") }
    var avatar by remember { mutableStateOf("🌌") }
    BoxWithConstraints(Modifier.fillMaxSize().background(Brush.verticalGradient(listOf(colors.background, colors.surfaceVariant))), contentAlignment = Alignment.Center) {
        val availableWidth = maxWidth
        Card(
            modifier = Modifier.fillMaxWidth().widthIn(max = 480.dp).padding(horizontal = 20.dp),
            shape = RoundedCornerShape(28.dp),
            colors = CardDefaults.cardColors(containerColor = colors.surface),
            elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
        ) {
            Column(Modifier.padding(22.dp).verticalScroll(rememberScrollState()), horizontalAlignment = Alignment.CenterHorizontally) {
                Image(painterResource(R.drawable.ic_aurora_foreground), null, Modifier.size(minOf(availableWidth * .27f, 96.dp)))
                Spacer(Modifier.height(12.dp))
                Text("Aurora", color = colors.textPrimary, fontSize = 25.sp, fontWeight = FontWeight.SemiBold)
                Text("Seu espaço pessoal", color = colors.textSecondary, fontSize = 13.sp)
                Spacer(Modifier.height(20.dp))
                OutlinedTextField(name, { name = it }, label = { Text("Como quer ser chamada?") }, modifier = Modifier.fillMaxWidth(), singleLine = true, colors = AuroraFieldColors(colors))
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(age, { age = it }, label = { Text("Idade (opcional)") }, modifier = Modifier.fillMaxWidth(), singleLine = true, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), colors = AuroraFieldColors(colors))
                Spacer(Modifier.height(10.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf("🌌", "✨", "🪐", "🔮", "🚀").forEach { option ->
                        Surface(onClick = { avatar = option }, shape = CircleShape, color = if (avatar == option) colors.primary.copy(alpha = .15f) else colors.surfaceVariant,
                            modifier = Modifier.size(40.dp)) { Box(contentAlignment = Alignment.Center) { Text(option, fontSize = 17.sp) } }
                    }
                }
                Spacer(Modifier.height(16.dp))
                Button(onClick = { viewModel.completeLogin("local", name, age, avatar) }, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp), colors = ButtonDefaults.buttonColors(containerColor = colors.primary)) {
                    Text("Continuar com perfil local", color = Color.White, fontWeight = FontWeight.SemiBold)
                }
                Spacer(Modifier.height(8.dp))
                Text("Sem conta na nuvem. Seus dados de perfil ficam neste aparelho.", color = colors.textSecondary, fontSize = 11.sp, textAlign = TextAlign.Center)
            }
        }
    }
}

@Composable
private fun PairingDialog(viewModel: AuroraViewModel, colors: AuroraColors, onDismiss: () -> Unit) {
    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = colors.surface,
        title = { Text("Conectar ao computador", color = colors.textPrimary, fontWeight = FontWeight.SemiBold) },
        text = {
            Column(Modifier.heightIn(max = 420.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(9.dp)) {
                Text("Use a mesma rede local. Os modelos e as automações continuam no PC.", color = colors.textSecondary, fontSize = 13.sp)
                OutlinedTextField(viewModel.endpoint, { viewModel.endpoint = it }, label = { Text("Endereço do PC") }, modifier = Modifier.fillMaxWidth(), singleLine = true, colors = AuroraFieldColors(colors))
                if (viewModel.token.isBlank()) OutlinedTextField(viewModel.pairingCode, { viewModel.pairingCode = it }, label = { Text("Código exibido no PC") }, modifier = Modifier.fillMaxWidth(), singleLine = true, colors = AuroraFieldColors(colors))
                OutlinedTextField(viewModel.fingerprint, { viewModel.fingerprint = it }, label = { Text("Pin SHA-256 do certificado") }, modifier = Modifier.fillMaxWidth(), singleLine = true, colors = AuroraFieldColors(colors))
                TextButton(onClick = viewModel::findPc, enabled = !viewModel.discovering, modifier = Modifier.fillMaxWidth()) {
                    Text(if (viewModel.discovering) "Procurando na rede…" else "Encontrar meu PC", color = colors.primary)
                }
                Text("Confirme o pin mostrado no PC. Não exponha a conexão à internet pública.", color = colors.textSecondary, fontSize = 11.sp, lineHeight = 16.sp)
                if (viewModel.notice.isNotBlank()) Text(viewModel.notice, color = colors.textSecondary, fontSize = 12.sp)
            }
        },
        confirmButton = {
            Button(onClick = { viewModel.connectToPc(); onDismiss() }, enabled = !viewModel.busy, colors = ButtonDefaults.buttonColors(containerColor = colors.primary)) {
                Text(if (viewModel.busy) "Conectando…" else "Conectar", color = Color.White)
            }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Agora não", color = colors.textSecondary) } },
    )
}

@Composable
private fun HistoryDialog(viewModel: AuroraViewModel, colors: AuroraColors, onDismiss: () -> Unit) {
    androidx.compose.material3.AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = colors.surface,
        title = { Text("Conversas", color = colors.textPrimary, fontWeight = FontWeight.SemiBold) },
        text = {
            Column(Modifier.heightIn(max = 420.dp)) {
                TextButton(onClick = { viewModel.refreshConversations() }, enabled = viewModel.connected && !viewModel.loadingConversations) {
                    Text(if (viewModel.loadingConversations) "Atualizando…" else "Atualizar histórico", color = colors.primary)
                }
                if (!viewModel.connected) Text("Conecte o PC para abrir o histórico.", color = colors.textSecondary)
                LazyColumn {
                    items(viewModel.conversations, key = { it.id }) { conversation ->
                        Surface(onClick = { viewModel.openConversation(conversation.id); onDismiss() }, color = Color.Transparent) {
                            Text(conversation.title.ifBlank { "Conversa" }, color = colors.textPrimary, maxLines = 2, overflow = TextOverflow.Ellipsis,
                                modifier = Modifier.fillMaxWidth().padding(vertical = 10.dp))
                        }
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("Fechar", color = colors.primary) } },
    )
}

@Composable
private fun SettingsCard(colors: AuroraColors, content: @Composable () -> Unit) {
    Card(Modifier.fillMaxWidth(), shape = RoundedCornerShape(22.dp), colors = CardDefaults.cardColors(containerColor = colors.surface), elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)) {
        Column(Modifier.padding(16.dp)) { content() }
    }
}

@Composable
private fun AuroraFieldColors(colors: AuroraColors) = androidx.compose.material3.OutlinedTextFieldDefaults.colors(
    focusedBorderColor = colors.primary,
    unfocusedBorderColor = colors.textSecondary.copy(alpha = .25f),
    focusedLabelColor = colors.primary,
    cursorColor = colors.primary,
    focusedTextColor = colors.textPrimary,
    unfocusedTextColor = colors.textPrimary,
    focusedContainerColor = colors.surface,
    unfocusedContainerColor = colors.surface,
)
