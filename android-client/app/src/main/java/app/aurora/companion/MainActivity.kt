package app.aurora.companion

import android.Manifest
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.view.SoundEffectConstants
import android.view.View
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.animation.scaleOut
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
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
import androidx.compose.material3.DrawerValue
import androidx.compose.material3.MaterialTheme
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
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

private val Ink = Color(0xFFF7F5FA)
private val Panel = Color(0xFFFFFFFF)
private val Muted = Color(0xFF777387)
private val Violet = Color(0xFF8A70C4)
private val Blue = Color(0xFF579BC2)
private val Pearl = Color(0xFF29263A)
private val SoftLilac = Color(0xFFEAE3F5)
private val SoftBlue = Color(0xFFE0F0F7)

private fun playPhoneClick(view: View) {
    view.playSoundEffect(SoundEffectConstants.CLICK)
}

data class ChatLine(val fromUser: Boolean, val text: String)

class MainActivity : ComponentActivity() {

    private val viewModel: AuroraViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            AuroraShell(viewModel = viewModel)
        }
    }

    override fun onPause() {
        super.onPause()
        if (viewModel.liveMode) {
            viewModel.showFloatingBubble()
        }
    }

    override fun onResume() {
        super.onResume()
        viewModel.hideFloatingBubble()
    }
}

@Composable
private fun AuroraShell(viewModel: AuroraViewModel) {
    val appContext = LocalContext.current
    val rootView = LocalView.current
    val scope = rememberCoroutineScope()
    val drawerState = rememberDrawerState(DrawerValue.Closed)

    var showConnect by remember { mutableStateOf(false) }
    var showOverlayPermissionDialog by remember { mutableStateOf(false) }
    var draft by remember { mutableStateOf("") }
    val composerFocusRequester = remember { FocusRequester() }
    val keyboardController = LocalSoftwareKeyboardController.current

    val overlayPermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && Settings.canDrawOverlays(appContext)) {
            viewModel.notice = "Permissão de bolha flutuante concedida."
        }
    }

    val micPermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) {
            viewModel.startWakeListener()
        } else {
            viewModel.notice = "A ativação por voz precisa da permissão de microfone."
        }
    }

    val alwaysOnWakePermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { grants ->
        if (grants[Manifest.permission.RECORD_AUDIO] == true) {
            viewModel.startAlwaysOnWake()
        } else {
            viewModel.notice = "A escuta permanente precisa de permissão de microfone."
        }
    }

    DisposableEffect(appContext) {
        val receiver = object : BroadcastReceiver() {
            override fun onReceive(context: Context?, intent: Intent?) {
                when (intent?.action) {
                    WakeCaptureService.ACTION_DETECTED -> {
                        viewModel.stopWakeListener()
                        if (viewModel.connected && !viewModel.busy) {
                            playPhoneClick(rootView)
                            viewModel.enterLiveMode()
                            viewModel.startVoiceInteraction()
                            viewModel.notice = "Ouvi Aurora. Pode falar; a detecção aconteceu localmente no PC."
                        } else {
                            viewModel.notice = "Ouvi Aurora. Abra o app e toque em Falar para continuar."
                        }
                    }
                    WakeCaptureService.ACTION_ERROR -> {
                        val msg = intent.getStringExtra(WakeCaptureService.EXTRA_MESSAGE).orEmpty()
                        viewModel.wakeFailure = msg
                        viewModel.wakeListening = false
                        viewModel.notice = "A escuta por voz foi interrompida: $msg"
                    }
                    AlwaysOnWakeService.ACTION_DETECTED -> {
                        playPhoneClick(rootView)
                        viewModel.enterLiveMode()
                        viewModel.startVoiceInteraction()
                        viewModel.notice = "Ouvi você! Pode falar seu comando diretamente."
                    }
                    AlwaysOnWakeService.ACTION_ERROR -> {
                        val msg = intent.getStringExtra(AlwaysOnWakeService.EXTRA_MESSAGE).orEmpty()
                        viewModel.alwaysOnWakeActive = false
                        viewModel.notice = "Escuta permanente: $msg"
                    }
                    FloatingBubbleService.ACTION_BUBBLE_DISMISSED -> {
                        viewModel.leaveLiveMode(playExitSound = true)
                    }
                }
            }
        }
        val filter = IntentFilter().apply {
            addAction(WakeCaptureService.ACTION_DETECTED)
            addAction(WakeCaptureService.ACTION_ERROR)
            addAction(AlwaysOnWakeService.ACTION_DETECTED)
            addAction(AlwaysOnWakeService.ACTION_ERROR)
            addAction(FloatingBubbleService.ACTION_BUBBLE_DISMISSED)
        }
        if (Build.VERSION.SDK_INT >= 33) {
            appContext.registerReceiver(receiver, filter, Context.RECEIVER_NOT_EXPORTED)
        } else {
            @Suppress("DEPRECATION")
            appContext.registerReceiver(receiver, filter)
        }
        onDispose { appContext.unregisterReceiver(receiver) }
    }

    BackHandler(enabled = viewModel.liveMode) {
        viewModel.leaveLiveMode()
    }

    fun handleEnterLiveMode() {
        if (!viewModel.connected) {
            showConnect = true
            return
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && !Settings.canDrawOverlays(appContext)) {
            val prefs = appContext.getSharedPreferences("aurora_ui_prefs", Context.MODE_PRIVATE)
            val alreadyAsked = prefs.getBoolean("overlay_asked", false)
            if (!alreadyAsked) {
                prefs.edit().putBoolean("overlay_asked", true).apply()
                showOverlayPermissionDialog = true
            }
        }
        viewModel.enterLiveMode()
    }

    MaterialTheme {
        ModalNavigationDrawer(
            drawerState = drawerState,
            gesturesEnabled = viewModel.connected && !viewModel.liveMode,
            drawerContent = {
                ModalDrawerSheet(drawerContainerColor = Panel, drawerContentColor = Pearl) {
                    Column(Modifier.fillMaxSize().padding(horizontal = 16.dp, vertical = 20.dp)) {
                        Text("Aurora", color = Pearl, fontSize = 24.sp, fontWeight = FontWeight.SemiBold)
                        Text("Conversas no seu PC", color = Muted, fontSize = 13.sp, modifier = Modifier.padding(top = 4.dp, bottom = 18.dp))
                        Button(
                            onClick = {
                                viewModel.newConversation()
                                scope.launch { drawerState.close() }
                            },
                            enabled = viewModel.connected && !viewModel.busy,
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
                            TextButton(onClick = viewModel::refreshConversations, enabled = viewModel.connected && !viewModel.busy) {
                                Text("Atualizar", color = Blue)
                            }
                        }
                        if (viewModel.conversations.isEmpty()) {
                            Text("Suas conversas aparecerão aqui.", color = Muted, fontSize = 13.sp, modifier = Modifier.padding(vertical = 12.dp))
                        }
                        LazyColumn(Modifier.weight(1f).fillMaxWidth()) {
                            items(viewModel.conversations, key = { it.id }) { item ->
                                NavigationDrawerItem(
                                    label = {
                                        Text(item.title.ifBlank { "Conversa" }, maxLines = 2, overflow = TextOverflow.Ellipsis)
                                    },
                                    selected = item.id == viewModel.conversationId,
                                    onClick = {
                                        viewModel.openConversation(item.id)
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
                            connected = viewModel.connected,
                            remoteState = viewModel.remoteState,
                            alwaysOnActive = viewModel.alwaysOnWakeActive,
                            onHistory = {
                                if (viewModel.connected) {
                                    viewModel.refreshConversations()
                                    scope.launch { drawerState.open() }
                                } else showConnect = true
                            },
                            onConnect = { showConnect = true },
                            onDisconnect = viewModel::disconnectFromPc,
                            onOrbClick = { if (viewModel.connected) handleEnterLiveMode() else showConnect = true },
                            onToggleAlwaysOn = {
                                if (viewModel.alwaysOnWakeActive) {
                                    viewModel.stopAlwaysOnWake()
                                } else if (appContext.checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
                                    viewModel.startAlwaysOnWake()
                                } else {
                                    val req = buildList {
                                        add(Manifest.permission.RECORD_AUDIO)
                                        if (Build.VERSION.SDK_INT >= 33) add(Manifest.permission.POST_NOTIFICATIONS)
                                    }
                                    alwaysOnWakePermissionLauncher.launch(req.toTypedArray())
                                }
                            }
                        )
                        if (viewModel.lines.isEmpty()) {
                            Welcome(
                                modifier = Modifier.weight(1f),
                                live = viewModel.live,
                                working = viewModel.busy,
                                connected = viewModel.connected,
                                activity = if (viewModel.live) "listening" else viewModel.remoteState,
                                onStartVoice = ::handleEnterLiveMode,
                                onWrite = {
                                    if (viewModel.connected) {
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
                                items(viewModel.lines) { line -> MessageBubble(line) }
                            }
                            Row(Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 10.dp),
                                horizontalArrangement = Arrangement.Center) {
                                OrbButton(
                                    viewModel.live || viewModel.busy,
                                    Modifier.size(54.dp),
                                    activity = if (viewModel.live) "listening" else viewModel.remoteState,
                                    onClick = ::handleEnterLiveMode
                                )
                            }
                        }
                        Composer(
                            text = draft,
                            connected = viewModel.connected,
                            busy = viewModel.busy,
                            liveMode = viewModel.liveMode,
                            wakeListening = viewModel.wakeListening,
                            screenActive = viewModel.showScreen,
                            onText = { draft = it },
                            onSend = {
                                val msg = draft
                                draft = ""
                                viewModel.sendCurrentMessage(msg)
                            },
                            onNew = viewModel::newConversation,
                            onToggleLive = {
                                if (viewModel.liveMode) viewModel.leaveLiveMode() else handleEnterLiveMode()
                            },
                            onToggleWake = {
                                playPhoneClick(rootView)
                                if (viewModel.wakeListening) {
                                    viewModel.stopWakeListener()
                                } else if (!viewModel.connected) {
                                    showConnect = true
                                } else if (appContext.checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
                                    viewModel.startWakeListener()
                                } else {
                                    micPermissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
                                }
                            },
                            onToggleScreen = {
                                playPhoneClick(rootView)
                                viewModel.toggleScreenView()
                            },
                            focusRequester = composerFocusRequester,
                        )
                        if (viewModel.notice.isNotBlank()) {
                            Text(
                                viewModel.notice,
                                color = Muted,
                                fontSize = 11.sp,
                                modifier = Modifier.fillMaxWidth().padding(bottom = 6.dp),
                                textAlign = TextAlign.Center
                            )
                        }
                    }
                }
                AnimatedVisibility(
                    visible = viewModel.liveMode,
                    modifier = Modifier.fillMaxSize(),
                    enter = fadeIn(tween(180)) + scaleIn(initialScale = 0.78f, animationSpec = spring(dampingRatio = 0.72f, stiffness = 300f)),
                    exit = fadeOut(tween(190)) + scaleOut(targetScale = 0.76f, animationSpec = spring(dampingRatio = 0.82f, stiffness = 330f)),
                ) {
                    LiveOverlay(
                        modeActive = viewModel.liveMode,
                        recording = viewModel.live,
                        working = viewModel.busy,
                        activity = viewModel.remoteState,
                        startRequest = viewModel.voiceStartRequest,
                        stopRequest = viewModel.voiceStopRequest,
                        onOrbTap = { viewModel.startVoiceInteraction() },
                        onExit = { viewModel.leaveLiveMode(playExitSound = true) },
                        onRecording = { viewModel.live = it },
                        onVoice = viewModel::sendVoiceAudio,
                        onVoiceError = { viewModel.notice = it },
                    )
                }
                AnimatedVisibility(
                    visible = viewModel.showScreen,
                    modifier = Modifier.fillMaxSize(),
                    enter = fadeIn(tween(150)),
                    exit = fadeOut(tween(120)),
                ) {
                    ScreenPreviewOverlay(
                        frame = viewModel.screenBitmap,
                        onClose = viewModel::toggleScreenView,
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
                    Button(onClick = viewModel::findPc, enabled = !viewModel.discovering, colors = ButtonDefaults.buttonColors(containerColor = Panel)) {
                        Text(if (viewModel.discovering) "Procurando na rede…" else "Encontrar meu PC automaticamente", color = Pearl)
                    }
                    ConnectField(viewModel.endpoint, { viewModel.endpoint = it }, "Endereço do servidor (ex.: https://192.168.1.10:8765)")
                    if (viewModel.token.isBlank()) ConnectField(viewModel.pairingCode, { viewModel.pairingCode = it }, "Código de pareamento")
                    ConnectField(viewModel.fingerprint, { viewModel.fingerprint = it }, "Impressão digital SHA-256 do certificado (64 caracteres)")
                    Text("No PC, obtenha o código e a impressão digital em ~/.config/aurora/companion/. O pareamento usa HTTPS com certificado fixado; não exponha a porta do PC à internet.", color = Muted, fontSize = 12.sp)
                    if (viewModel.notice.isNotBlank()) Text(viewModel.notice, color = if (viewModel.notice.startsWith("Não")) Color(0xFFFFA6AC) else Blue, fontSize = 12.sp)
                }
            },
            confirmButton = {
                Button(onClick = {
                    viewModel.connectToPc()
                    showConnect = false
                }, enabled = !viewModel.busy, colors = ButtonDefaults.buttonColors(containerColor = Violet)) {
                    Text(if (viewModel.busy) "Conectando…" else "Parear com o PC")
                }
            },
            dismissButton = { TextButton(onClick = { showConnect = false }) { Text("Cancelar", color = Muted) } }
        )
    }

    if (showOverlayPermissionDialog) {
        AlertDialog(
            onDismissRequest = { showOverlayPermissionDialog = false },
            containerColor = Panel,
            title = { Text("Bolha flutuante da Aurora", color = Pearl) },
            text = {
                Text(
                    "Para continuar ativa como uma bolha flutuante quando você sair do app no modo Live, a Aurora precisa da permissão \"Exibir sobre outros apps\".",
                    color = Muted,
                    fontSize = 14.sp
                )
            },
            confirmButton = {
                Button(
                    onClick = {
                        showOverlayPermissionDialog = false
                        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                            val intent = Intent(
                                Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                                Uri.parse("package:${appContext.packageName}")
                            )
                            overlayPermissionLauncher.launch(intent)
                        }
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = Violet)
                ) { Text("Permitir") }
            },
            dismissButton = {
                TextButton(onClick = { showOverlayPermissionDialog = false }) { Text("Agora não", color = Muted) }
            }
        )
    }
}

@Composable
private fun TopBar(
    connected: Boolean,
    remoteState: String,
    alwaysOnActive: Boolean,
    onHistory: () -> Unit,
    onConnect: () -> Unit,
    onDisconnect: () -> Unit,
    onOrbClick: () -> Unit,
    onToggleAlwaysOn: () -> Unit,
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
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            Button(
                onClick = onToggleAlwaysOn,
                modifier = Modifier.heightIn(min = 40.dp),
                contentPadding = PaddingValues(horizontal = 8.dp, vertical = 4.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = if (alwaysOnActive) Violet else SoftLilac,
                    contentColor = if (alwaysOnActive) Color.White else Pearl,
                ),
                shape = RoundedCornerShape(16.dp),
            ) {
                Text(if (alwaysOnActive) "Sempre ativa" else "Ouvir", fontSize = 11.sp)
            }
            SmallAction("Chats", onHistory)
            SmallAction(if (connected) "Desconectar" else "Conectar", if (connected) onDisconnect else onConnect)
        }
    }
}

private fun remoteStateLabel(state: String): String = when (state) {
    "transcribing" -> "Entendendo sua voz"
    "thinking" -> "Aurora pensando"
    "searching" -> "Aurora pesquisando"
    "preparing" -> "Preparando voz da Aurora"
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
        "transcribing", "thinking", "preparing" -> 1050
        "searching" -> 1450
        "speaking" -> 720
        "listening" -> 850
        else -> 2500
    }
    val auraColor = when (activity) {
        "searching" -> Blue
        "speaking" -> Color(0xFFD9C7FF)
        "thinking", "transcribing", "preparing" -> Violet
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
                start = Offset(0f, 0f),
                end = Offset(380f * drift, 540f * (1f - drift))
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
    wakeListening: Boolean,
    screenActive: Boolean,
    onText: (String) -> Unit,
    onSend: () -> Unit,
    onNew: () -> Unit,
    onToggleLive: () -> Unit,
    onToggleWake: () -> Unit,
    onToggleScreen: () -> Unit,
    focusRequester: FocusRequester,
) {
    Column(Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 10.dp)) {
        Row(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(28.dp)).background(Panel)
                .border(1.dp, Violet.copy(alpha = 0.14f), RoundedCornerShape(28.dp)).padding(9.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Button(
                onClick = onToggleScreen,
                enabled = connected || screenActive,
                modifier = Modifier.size(44.dp).semantics {
                    contentDescription = if (screenActive) "Parar transmissão da tela do PC" else "Mostrar a tela do PC"
                },
                contentPadding = PaddingValues(0.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = if (screenActive) Blue else SoftBlue,
                    contentColor = if (screenActive) Color.White else Blue,
                    disabledContainerColor = SoftBlue,
                    disabledContentColor = Muted,
                ),
                shape = CircleShape,
            ) { Text("PC", fontSize = 10.sp, fontWeight = FontWeight.SemiBold) }
            Button(
                onClick = onToggleWake,
                enabled = connected || wakeListening,
                modifier = Modifier.size(44.dp).semantics {
                    contentDescription = if (wakeListening) "Desativar palavra de ativação" else "Ativar palavra de ativação Aurora"
                },
                contentPadding = PaddingValues(0.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = if (wakeListening) Violet else SoftLilac,
                    contentColor = if (wakeListening) Color.White else Violet,
                    disabledContainerColor = SoftLilac,
                    disabledContentColor = Muted,
                ),
                shape = CircleShape,
            ) { Text(if (wakeListening) "On" else "Mic", fontSize = 10.sp, fontWeight = FontWeight.SemiBold) }
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
private fun ScreenPreviewOverlay(frame: ImageBitmap?, onClose: () -> Unit) {
    Box(
        Modifier.fillMaxSize().background(Color(0xFF171520)),
        contentAlignment = Alignment.Center,
    ) {
        if (frame != null) {
            Image(
                bitmap = frame,
                contentDescription = "Transmissão ao vivo da tela do PC Aurora",
                modifier = Modifier.fillMaxSize().padding(top = 72.dp, bottom = 76.dp, start = 10.dp, end = 10.dp),
                contentScale = ContentScale.Fit,
            )
        } else {
            Text(
                "Aguardando autorização no computador…",
                color = Color.White,
                modifier = Modifier.padding(28.dp),
                textAlign = TextAlign.Center,
            )
        }
        Row(
            Modifier.align(Alignment.TopCenter).fillMaxWidth().background(Color(0xFF252330)).padding(16.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column {
                Text("Tela do computador", color = Color.White, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
                Text("Compartilhamento protegido pelo portal do desktop", color = Color(0xFFD5D0E0), fontSize = 11.sp)
            }
            Button(
                onClick = onClose,
                contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp),
                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFE8DDF5), contentColor = Pearl),
                shape = RoundedCornerShape(18.dp),
            ) { Text("Parar") }
        }
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
                        recording -> "Ouvindo seu comando… Fale agora."
                        working -> "Processando seu pedido…"
                        activity == "preparing" -> "Preparando resposta…"
                        activity == "speaking" -> "Aurora falando"
                        else -> "Sua conversa, ao vivo"
                    },
                    color = Pearl,
                    fontSize = 22.sp,
                    fontWeight = FontWeight.Medium,
                    textAlign = TextAlign.Center,
                )
                Spacer(Modifier.height(8.dp))
                Text(
                    when {
                        recording -> "Basta falar. A Aurora enviará assim que você terminar."
                        working -> "Consultando e pensando no computador…"
                        activity == "preparing" -> "Sintetizando a voz da resposta…"
                        activity == "speaking" -> "Edge TTS · Thalita em execução"
                        else -> "Diga \"Aurora\" ou toque na bolha para falar."
                    },
                    color = Muted,
                    fontSize = 14.sp,
                    lineHeight = 20.sp,
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
