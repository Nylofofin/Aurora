package app.aurora.companion

import android.Manifest
import android.content.Context
import android.content.Intent
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
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
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
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.DrawerValue
import androidx.compose.material3.Icon
import androidx.compose.material3.ModalDrawerSheet
import androidx.compose.material3.ModalNavigationDrawer
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.NavigationDrawerItem
import androidx.compose.material3.NavigationDrawerItemDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
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
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.input.pointer.pointerInput
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
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

data class ChatLine(val fromUser: Boolean, val text: String)

private fun remoteStateLabel(state: String): String = when (state) {
    "transcribing" -> "entendendo sua voz"
    "thinking" -> "pensando"
    "preparing" -> "preparando resposta"
    "speaking" -> "falando"
    "listening" -> "ouvindo"
    else -> "pronta"
}

class MainActivity : ComponentActivity() {

    private val viewModel: AuroraViewModel by viewModels()

    private val micPermLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) {
            if (viewModel.connected) {
                viewModel.startWakeListener()
            }
        } else {
            viewModel.notice = "Permissão de microfone necessária para escuta contínua."
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            val colors = AuroraThemes.getTheme(viewModel.currentThemeName)
            AuroraAppRoot(viewModel = viewModel, colors = colors)
        }

        lifecycleScope.launch {
            delay(800)
            autoStartContinuousWake()
        }
    }

    private fun autoStartContinuousWake() {
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
            if (viewModel.connected) {
                viewModel.startWakeListener()
            }
        } else {
            micPermLauncher.launch(Manifest.permission.RECORD_AUDIO)
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
private fun AuroraAppRoot(viewModel: AuroraViewModel, colors: AuroraColors) {
    Surface(
        modifier = Modifier.fillMaxSize(),
        color = colors.background,
    ) {
        if (!viewModel.userProfile.isLoggedIn) {
            LoginBarrierScreen(viewModel = viewModel, colors = colors)
        } else {
            MainAppScaffold(viewModel = viewModel, colors = colors)
        }
    }
}

@Composable
private fun LoginBarrierScreen(viewModel: AuroraViewModel, colors: AuroraColors) {
    var nameInput by remember { mutableStateOf("") }
    var ageInput by remember { mutableStateOf("") }
    var selectedAvatar by remember { mutableStateOf("🌌") }
    val avatars = listOf("🌌", "✨", "🪐", "🔮", "🚀")

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(
                Brush.verticalGradient(
                    colors = listOf(colors.background, colors.surface, colors.surfaceVariant)
                )
            )
            .padding(24.dp),
        contentAlignment = Alignment.Center
    ) {
        Card(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp),
            colors = CardDefaults.cardColors(containerColor = colors.surface),
            shape = RoundedCornerShape(28.dp),
            elevation = CardDefaults.cardElevation(defaultElevation = 8.dp)
        ) {
            Column(
                modifier = Modifier.padding(28.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                AuroraOrb(82.dp, "idle", colors)
                Spacer(Modifier.height(18.dp))
                Text(
                    text = "Aurora",
                    fontSize = 27.sp,
                    fontWeight = FontWeight.SemiBold,
                    color = colors.primary
                )
                Text(
                    text = "Seu assistente, do seu jeito",
                    fontSize = 13.sp,
                    color = colors.textSecondary,
                    modifier = Modifier.padding(top = 4.dp, bottom = 20.dp)
                )

                Text(
                    text = "Como devemos te chamar?",
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Medium,
                    color = colors.textPrimary,
                    modifier = Modifier.fillMaxWidth()
                )
                Spacer(Modifier.height(8.dp))
                BasicTextField(
                    value = nameInput,
                    onValueChange = { nameInput = it },
                    textStyle = TextStyle(color = colors.textPrimary, fontSize = 16.sp),
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(14.dp))
                        .background(colors.surfaceVariant)
                        .padding(horizontal = 16.dp, vertical = 14.dp),
                    decorationBox = { inner ->
                        if (nameInput.isBlank()) Text("Seu nome", color = colors.textSecondary, fontSize = 15.sp)
                        inner()
                    },
                )

                Spacer(Modifier.height(14.dp))
                Text(
                    text = "Idade (opcional)",
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Medium,
                    color = colors.textPrimary,
                    modifier = Modifier.fillMaxWidth()
                )
                Spacer(Modifier.height(8.dp))
                BasicTextField(
                    value = ageInput,
                    onValueChange = { ageInput = it },
                    textStyle = TextStyle(color = colors.textPrimary, fontSize = 16.sp),
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(14.dp))
                        .background(colors.surfaceVariant)
                        .padding(horizontal = 16.dp, vertical = 14.dp),
                    decorationBox = { inner ->
                        if (ageInput.isBlank()) Text("Opcional", color = colors.textSecondary, fontSize = 15.sp)
                        inner()
                    },
                )

                Spacer(Modifier.height(16.dp))
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceEvenly
                ) {
                    avatars.forEach { av ->
                        Box(
                            modifier = Modifier
                                .size(40.dp)
                                .clip(CircleShape)
                                .background(if (selectedAvatar == av) colors.primary.copy(alpha = 0.35f) else Color.Transparent)
                                .border(1.dp, if (selectedAvatar == av) colors.primary else Color.Transparent, CircleShape)
                                .clickable { selectedAvatar = av },
                            contentAlignment = Alignment.Center
                        ) {
                            Text(av, fontSize = 20.sp)
                        }
                    }
                }

                Spacer(Modifier.height(24.dp))
                Button(
                    onClick = {
                        viewModel.completeLogin("local", nameInput, ageInput, selectedAvatar)
                    },
                    modifier = Modifier.fillMaxWidth().height(52.dp),
                    shape = RoundedCornerShape(16.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = colors.primary)
                ) {
                    Text("Começar com Conta Local", fontWeight = FontWeight.Bold, color = Color.White)
                }

                Spacer(Modifier.height(12.dp))
                Text(
                    "Perfil local neste celular; sem login Google/GitHub e sem conta na nuvem.",
                    fontSize = 11.sp,
                    color = colors.textSecondary,
                    textAlign = TextAlign.Center,
                )
            }
        }
    }
}

@Composable
private fun MainAppScaffold(viewModel: AuroraViewModel, colors: AuroraColors) {
    val drawerState = rememberDrawerState(DrawerValue.Closed)
    val scope = rememberCoroutineScope()
    var showConnect by remember { mutableStateOf(false) }

    BackHandler(enabled = viewModel.activeTab == CompanionTab.LIVE) {
        viewModel.leaveLiveMode(playExitSound = true)
        viewModel.activeTab = CompanionTab.CHAT
    }

    ModalNavigationDrawer(
        drawerState = drawerState,
        drawerContent = {
            ModalDrawerSheet(
                drawerContainerColor = colors.surface,
                drawerContentColor = colors.textPrimary,
                modifier = Modifier.width(304.dp)
            ) {
                Column(Modifier.fillMaxSize().padding(horizontal = 18.dp, vertical = 20.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        AuroraOrb(42.dp, "idle", colors)
                        Spacer(Modifier.width(12.dp))
                        Column {
                            Text("Aurora", fontWeight = FontWeight.SemiBold, fontSize = 19.sp, color = colors.textPrimary)
                            Text("Conversas do computador", fontSize = 12.sp, color = colors.textSecondary)
                        }
                    }
                    Button(
                        onClick = {
                            viewModel.newConversation()
                            viewModel.activeTab = CompanionTab.CHAT
                            scope.launch { drawerState.close() }
                        },
                        enabled = viewModel.connected && !viewModel.busy,
                        modifier = Modifier.fillMaxWidth().padding(top = 22.dp).heightIn(min = 48.dp),
                        shape = RoundedCornerShape(16.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = colors.primary),
                    ) { Text("＋  Nova conversa", color = Color.White, fontWeight = FontWeight.Medium) }
                    Row(
                        Modifier.fillMaxWidth().padding(top = 24.dp, bottom = 8.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween,
                    ) {
                        Text("Recentes", fontSize = 13.sp, color = colors.textSecondary)
                        TextButton(onClick = viewModel::refreshConversations, enabled = viewModel.connected && !viewModel.busy) {
                            Text("Atualizar", color = colors.primary)
                        }
                    }
                    LazyColumn(Modifier.weight(1f)) {
                        items(viewModel.conversations, key = { it.id }) { conv ->
                            NavigationDrawerItem(
                                label = { Text(conv.title.ifBlank { "Conversa" }, maxLines = 2, overflow = TextOverflow.Ellipsis) },
                                selected = viewModel.conversationId == conv.id,
                                onClick = {
                                    viewModel.openConversation(conv.id)
                                    viewModel.activeTab = CompanionTab.CHAT
                                    scope.launch { drawerState.close() }
                                },
                                modifier = Modifier.padding(vertical = 2.dp),
                                colors = NavigationDrawerItemDefaults.colors(
                                    selectedContainerColor = colors.primary.copy(alpha = .12f),
                                    selectedTextColor = colors.textPrimary,
                                    unselectedTextColor = colors.textSecondary,
                                ),
                            )
                        }
                    }
                }
            }
        }
    ) {
        Column(Modifier.fillMaxSize().background(colors.background)) {
            if (viewModel.activeTab != CompanionTab.LIVE) {
                AppTopBar(
                    viewModel = viewModel,
                    colors = colors,
                    onHistory = {
                        if (viewModel.connected) {
                            viewModel.refreshConversations()
                            scope.launch { drawerState.open() }
                        } else viewModel.notice = "Conecte-se ao PC para ver as conversas."
                    },
                    onProfile = { viewModel.activeTab = CompanionTab.SETTINGS },
                    onConnect = { showConnect = true },
                )
                MainTabs(viewModel = viewModel, colors = colors)
            }
            Box(Modifier.weight(1f)) {
                when (viewModel.activeTab) {
                    CompanionTab.CHAT -> ChatTabContent(viewModel = viewModel, colors = colors)
                    CompanionTab.LIVE -> LiveTabContent(viewModel = viewModel, colors = colors)
                    CompanionTab.DESKTOP -> DesktopTabContent(viewModel = viewModel, colors = colors)
                    CompanionTab.SETTINGS -> SettingsTabContent(viewModel = viewModel, colors = colors, onConnect = { showConnect = true })
                }
            }
        }
    }

    if (showConnect) {
        AlertDialog(
            onDismissRequest = { showConnect = false },
            containerColor = colors.surface,
            title = { Text("Conectar ao PC", color = colors.textPrimary, fontWeight = FontWeight.SemiBold) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(11.dp)) {
                    Text("Os modelos e as automações rodam no computador. Use a mesma rede Wi-Fi para encontrá-lo.", color = colors.textSecondary, fontSize = 13.sp)
                    Text("Endereço do computador", color = colors.textSecondary, fontSize = 11.sp)
                    OutlinedConnectField(viewModel.endpoint, { viewModel.endpoint = it }, "Endereço do PC")
                    if (viewModel.token.isBlank()) {
                        Text("Código de pareamento", color = colors.textSecondary, fontSize = 11.sp)
                        OutlinedConnectField(viewModel.pairingCode, { viewModel.pairingCode = it }, "Informe o código mostrado no PC")
                    }
                    Text("Pin do certificado SHA-256", color = colors.textSecondary, fontSize = 11.sp)
                    OutlinedConnectField(viewModel.fingerprint, { viewModel.fingerprint = it }, "Cole o pin SHA-256")
                    TextButton(onClick = viewModel::findPc, enabled = !viewModel.discovering, modifier = Modifier.fillMaxWidth()) {
                        Text(if (viewModel.discovering) "Procurando na rede…" else "Encontrar meu PC", color = colors.primary)
                    }
                    Text("Confira o pin no PC antes de parear. Não encaminhe a porta do servidor para a internet.", color = colors.textSecondary, fontSize = 11.sp)
                    if (viewModel.notice.isNotBlank()) Text(viewModel.notice, color = colors.textSecondary, fontSize = 12.sp)
                }
            },
            confirmButton = {
                Button(
                    onClick = { viewModel.connectToPc(); showConnect = false },
                    enabled = !viewModel.busy,
                    colors = ButtonDefaults.buttonColors(containerColor = colors.primary),
                ) { Text(if (viewModel.busy) "Conectando…" else "Conectar", color = Color.White) }
            },
            dismissButton = { TextButton(onClick = { showConnect = false }) { Text("Agora não", color = colors.textSecondary) } },
        )
    }
}

@Composable
private fun AppTopBar(
    viewModel: AuroraViewModel,
    colors: AuroraColors,
    onHistory: () -> Unit,
    onProfile: () -> Unit,
    onConnect: () -> Unit,
) {
    Row(
        Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 14.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        AuroraOrb(42.dp, if (viewModel.liveMode) viewModel.remoteState else "idle", colors)
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text("Aurora", fontSize = 19.sp, fontWeight = FontWeight.SemiBold, color = colors.textPrimary)
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(6.dp).clip(CircleShape).background(if (viewModel.connected) Color(0xFF58A987) else colors.textSecondary))
                Spacer(Modifier.width(6.dp))
                Text(
                    if (viewModel.connected) "PC conectado · ${remoteStateLabel(viewModel.remoteState)}" else "Conecte seu PC para começar",
                    fontSize = 11.sp,
                    color = colors.textSecondary,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
        HeaderActionChip(
            label = if (viewModel.connected) "PC ativo" else "Conectar",
            colors = colors,
            description = if (viewModel.connected) "Gerenciar conexão com o PC" else "Conectar ao PC",
            onClick = onConnect,
        )
        Spacer(Modifier.width(5.dp))
        HeaderIconButton(colors, onHistory)
        Spacer(Modifier.width(7.dp))
        Box(
            Modifier.size(40.dp).clip(CircleShape).background(colors.surfaceVariant).clickable(onClick = onProfile),
            contentAlignment = Alignment.Center,
        ) { Text(viewModel.userProfile.avatarIcon, fontSize = 19.sp) }
    }
}

@Composable
private fun HeaderActionChip(label: String, colors: AuroraColors, description: String, onClick: () -> Unit) {
    Box(
        Modifier.height(38.dp).clip(RoundedCornerShape(15.dp))
            .background(colors.surfaceVariant).clickable(onClick = onClick)
            .semantics { contentDescription = description }
            .padding(horizontal = 11.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(label, color = colors.primary, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
private fun HeaderIconButton(colors: AuroraColors, onClick: () -> Unit, label: String = "", description: String = "Abrir conversas") {
    Box(Modifier.size(40.dp).clip(CircleShape).background(colors.surface).clickable(onClick = onClick)
        .semantics { contentDescription = description }, contentAlignment = Alignment.Center) {
        if (label.isBlank()) Canvas(Modifier.size(18.dp)) {
            val w = 1.6.dp.toPx()
            drawLine(colors.textSecondary, Offset(size.width * .18f, size.height * .25f), Offset(size.width * .82f, size.height * .25f), w)
            drawLine(colors.textSecondary, Offset(size.width * .18f, size.height * .50f), Offset(size.width * .82f, size.height * .50f), w)
            drawLine(colors.textSecondary, Offset(size.width * .18f, size.height * .75f), Offset(size.width * .82f, size.height * .75f), w)
        } else Text(label, color = colors.primary, fontSize = 20.sp, fontWeight = FontWeight.Medium)
    }
}

@Composable
private fun MainTabs(viewModel: AuroraViewModel, colors: AuroraColors) {
    Row(
        Modifier.fillMaxWidth().padding(horizontal = 18.dp, vertical = 4.dp)
            .clip(RoundedCornerShape(18.dp)).background(colors.surfaceVariant).padding(4.dp),
        horizontalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        MainTabButton("Conversa", viewModel.activeTab == CompanionTab.CHAT, colors, Modifier.weight(1f)) {
            if (viewModel.activeTab == CompanionTab.DESKTOP && viewModel.showScreen) viewModel.stopScreenView()
            viewModel.activeTab = CompanionTab.CHAT
        }
        MainTabButton("Desktop", viewModel.activeTab == CompanionTab.DESKTOP, colors, Modifier.weight(1f)) {
            if (viewModel.connected) {
                viewModel.activeTab = CompanionTab.DESKTOP
                if (!viewModel.showScreen) viewModel.startScreenView()
            } else {
                viewModel.notice = "Conecte o PC antes de abrir o desktop remoto."
                viewModel.activeTab = CompanionTab.SETTINGS
            }
        }
        MainTabButton("Ajustes", viewModel.activeTab == CompanionTab.SETTINGS, colors, Modifier.weight(1f)) {
            if (viewModel.activeTab == CompanionTab.DESKTOP && viewModel.showScreen) viewModel.stopScreenView()
            viewModel.activeTab = CompanionTab.SETTINGS
        }
    }
}

@Composable
private fun MainTabButton(label: String, selected: Boolean, colors: AuroraColors, modifier: Modifier, onClick: () -> Unit) {
    Box(
        modifier.height(40.dp).clip(RoundedCornerShape(14.dp))
            .background(if (selected) colors.surface else Color.Transparent)
            .clickable(onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Text(label, color = if (selected) colors.primary else colors.textSecondary,
            fontSize = 12.sp, fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Medium)
    }
}

@Composable
private fun AuroraOrb(size: androidx.compose.ui.unit.Dp, state: String, colors: AuroraColors) {
    val transition = rememberInfiniteTransition(label = "aurora-orb-$state")
    val pulse by transition.animateFloat(
        initialValue = .96f,
        targetValue = if (state == "speaking") 1.07f else if (state == "listening" || state == "thinking" || state == "preparing") 1.04f else 1f,
        animationSpec = infiniteRepeatable(tween(if (state == "speaking") 650 else 1450, easing = FastOutSlowInEasing), RepeatMode.Reverse),
        label = "orb-pulse",
    )
    val drift by transition.animateFloat(.12f, .82f, infiniteRepeatable(tween(4800), RepeatMode.Reverse), label = "orb-drift")
    Box(Modifier.size(size).scale(pulse), contentAlignment = Alignment.Center) {
        Box(Modifier.fillMaxSize().clip(CircleShape).background(
            Brush.linearGradient(listOf(Color.White, colors.surfaceVariant, colors.secondary.copy(alpha = .74f), colors.primary),
                start = Offset(0f, size.value * 4f), end = Offset(size.value * 4f * drift, size.value * 4f)))
            .border(1.dp, Color.White.copy(alpha = .85f), CircleShape))
        Box(Modifier.fillMaxWidth(.53f).height(size * .22f).align(Alignment.TopStart)
            .padding(start = size * .18f, top = size * .13f).clip(CircleShape)
            .background(Brush.horizontalGradient(listOf(Color.White.copy(alpha = .86f), Color.White.copy(alpha = .02f)))))
    }
}

@Composable
private fun ChatTabContent(viewModel: AuroraViewModel, colors: AuroraColors) {
    var textDraft by remember { mutableStateOf("") }
    val keyboard = LocalSoftwareKeyboardController.current
    val send: () -> Unit = {
        if (viewModel.connected && !viewModel.busy && textDraft.isNotBlank()) {
            viewModel.sendCurrentMessage(textDraft.trim())
            textDraft = ""
            keyboard?.hide()
        }
    }

    Column(Modifier.fillMaxSize().imePadding()) {
        Box(Modifier.weight(1f).fillMaxWidth()) {
            if (viewModel.lines.isEmpty()) {
                Column(
                    Modifier.fillMaxSize().padding(horizontal = 30.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center,
                ) {
                    AuroraOrb(142.dp, if (viewModel.liveMode) viewModel.remoteState else "idle", colors)
                    Spacer(Modifier.height(28.dp))
                    Text(
                        "Oi, ${viewModel.userProfile.username.ifBlank { "aí" }}",
                        color = colors.textPrimary,
                        fontSize = 25.sp,
                        fontWeight = FontWeight.SemiBold,
                        textAlign = TextAlign.Center,
                    )
                    Spacer(Modifier.height(8.dp))
                    Text(
                        if (viewModel.connected) "Estou conectada ao seu computador. O que vamos fazer?"
                        else "Conecte seu computador para conversar, pesquisar e usar o modo Live.",
                        color = colors.textSecondary,
                        fontSize = 14.sp,
                        lineHeight = 21.sp,
                        textAlign = TextAlign.Center,
                    )
                    if (!viewModel.connected) {
                        Spacer(Modifier.height(20.dp))
                        TextButton(onClick = { viewModel.activeTab = CompanionTab.SETTINGS }) {
                            Text("Configurar conexão", color = colors.primary, fontWeight = FontWeight.SemiBold)
                        }
                    } else {
                        Spacer(Modifier.height(20.dp))
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            SuggestionChip("Conversar", colors) { textDraft = "Quero conversar um pouco." }
                            SuggestionChip("Pesquisar", colors) { textDraft = "Pesquise as notícias recentes de hoje." }
                        }
                    }
                }
            } else {
                LazyColumn(
                    modifier = Modifier.fillMaxSize().padding(horizontal = 18.dp, vertical = 14.dp),
                    reverseLayout = true,
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    items(viewModel.lines.reversed()) { line ->
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = if (line.fromUser) Arrangement.End else Arrangement.Start) {
                            Column(Modifier.fillMaxWidth(.88f)) {
                                Text(
                                    if (line.fromUser) viewModel.userProfile.username else "Aurora",
                                    color = colors.textSecondary,
                                    fontSize = 11.sp,
                                    modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                                )
                                Text(
                                    line.text,
                                    color = if (line.fromUser) Color.White else colors.textPrimary,
                                    fontSize = 15.sp,
                                    lineHeight = 22.sp,
                                    modifier = Modifier.clip(RoundedCornerShape(20.dp))
                                        .background(if (line.fromUser) colors.primary else colors.surface)
                                        .padding(horizontal = 15.dp, vertical = 12.dp),
                                )
                            }
                        }
                    }
                }
            }
        }

        if (viewModel.notice.isNotBlank()) {
            Text(
                viewModel.notice,
                color = colors.textSecondary,
                fontSize = 11.sp,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 5.dp),
                textAlign = TextAlign.Center,
            )
        }

        Row(
            Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 10.dp)
                .clip(RoundedCornerShape(26.dp)).background(colors.surface)
                .border(1.dp, colors.primary.copy(alpha = .12f), RoundedCornerShape(26.dp))
                .padding(start = 15.dp, end = 7.dp, top = 7.dp, bottom = 7.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            BasicTextField(
                value = textDraft,
                onValueChange = { textDraft = it },
                enabled = viewModel.connected && !viewModel.busy,
                textStyle = TextStyle(color = colors.textPrimary, fontSize = 15.sp),
                cursorBrush = SolidColor(colors.primary),
                modifier = Modifier.weight(1f).padding(vertical = 11.dp),
                decorationBox = { inner ->
                    if (textDraft.isEmpty()) Text("Mensagem para Aurora…", color = colors.textSecondary, fontSize = 14.sp)
                    inner()
                },
            )
            RoundActionButton("＋", colors, enabled = viewModel.connected && !viewModel.busy, description = "Nova conversa") {
                viewModel.newConversation()
            }
            Spacer(Modifier.width(5.dp))
            RoundActionButton("≋", colors, enabled = viewModel.connected && !viewModel.busy, description = "Iniciar modo Live") {
                viewModel.enterLiveMode()
            }
            Spacer(Modifier.width(5.dp))
            RoundActionButton("↑", colors, enabled = viewModel.connected && !viewModel.busy && textDraft.isNotBlank(), description = "Enviar mensagem", primary = true, onClick = send)
        }
        Text(
            if (viewModel.connected) "Voz, pesquisas e automações são processadas pelo seu PC" else "O PC mantém os modelos e os dados da Aurora",
            color = colors.textSecondary.copy(alpha = .75f),
            fontSize = 10.sp,
            modifier = Modifier.fillMaxWidth().padding(bottom = 9.dp),
            textAlign = TextAlign.Center,
        )
    }
}

@Composable
private fun SuggestionChip(label: String, colors: AuroraColors, onClick: () -> Unit) {
    Text(
        label,
        color = colors.primary,
        fontSize = 12.sp,
        fontWeight = FontWeight.Medium,
        modifier = Modifier.clip(RoundedCornerShape(50)).background(colors.surface)
            .clickable(onClick = onClick).padding(horizontal = 14.dp, vertical = 9.dp),
    )
}

@Composable
private fun RoundActionButton(
    label: String,
    colors: AuroraColors,
    enabled: Boolean,
    description: String,
    primary: Boolean = false,
    onClick: () -> Unit,
) {
    Box(
        Modifier.size(40.dp).clip(CircleShape)
            .background(if (primary) colors.primary else colors.surfaceVariant)
            .alpha(if (enabled) 1f else .48f)
            .clickable(enabled = enabled, onClick = onClick)
            .semantics { contentDescription = description },
        contentAlignment = Alignment.Center,
    ) {
        Text(label, color = if (primary) Color.White else colors.primary, fontSize = if (label == "↑") 22.sp else 19.sp, fontWeight = FontWeight.Medium)
    }
}

/**
 * Modo Live Imersivo e 100% Hands-Free.
 * O microfone fica eternamente aberto; sem botões manuais desnecessários de "Falar".
 */
@Composable
private fun LiveTabContent(viewModel: AuroraViewModel, colors: AuroraColors) {
    LaunchedEffect(Unit) {
        if (!viewModel.liveMode) {
            viewModel.enterLiveMode()
        }
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(
                Brush.radialGradient(colors = listOf(colors.surfaceVariant, colors.background), radius = 900f)
            ),
        contentAlignment = Alignment.Center
    ) {
        Column(
            modifier = Modifier.fillMaxSize().padding(horizontal = 26.dp, vertical = 20.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.SpaceBetween
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    "AURORA   /   LIVE",
                    fontSize = 12.sp,
                    fontWeight = FontWeight.SemiBold,
                    color = colors.primary
                )
                Box(
                    modifier = Modifier
                        .size(42.dp)
                        .clip(CircleShape)
                        .background(colors.surface.copy(alpha = 0.6f))
                        .clickable {
                            viewModel.leaveLiveMode(playExitSound = true)
                            viewModel.activeTab = CompanionTab.CHAT
                        }
                        .semantics { contentDescription = "Encerrar modo Live" },
                    contentAlignment = Alignment.Center
                ) {
                    Text("×", fontSize = 25.sp, color = colors.textPrimary, fontWeight = FontWeight.Light)
                }
            }

            AuroraOrb(236.dp, if (viewModel.live) "listening" else viewModel.remoteState, colors)

            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                val lastResponse = viewModel.lines.lastOrNull { !it.fromUser }?.text
                if (lastResponse != null) {
                    Text(
                        text = lastResponse,
                        fontSize = 13.sp,
                        color = colors.textSecondary,
                        textAlign = TextAlign.Center,
                        maxLines = 4,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.fillMaxWidth().padding(bottom = 18.dp)
                    )
                }
                Text(
                    text = when {
                        viewModel.remoteState == "listening" -> "Estou ouvindo você"
                        viewModel.remoteState == "speaking" -> "Estou falando"
                        viewModel.remoteState == "transcribing" -> "Entendendo sua fala"
                        viewModel.remoteState == "preparing" || viewModel.remoteState == "thinking" -> "Pensando na resposta"
                        else -> "Pode falar comigo"
                    },
                    fontSize = 21.sp,
                    fontWeight = FontWeight.SemiBold,
                    color = colors.textPrimary
                )
                Spacer(Modifier.height(7.dp))
                Text(
                    "A escuta continua depois de cada resposta. Toque no × para encerrar.",
                    fontSize = 13.sp,
                    lineHeight = 19.sp,
                    color = colors.textSecondary,
                    textAlign = TextAlign.Center,
                )
            }
        }
    }
}

/**
 * Desktop Remoto com Controle por Toque no Android.
 */
@Composable
private fun DesktopTabContent(viewModel: AuroraViewModel, colors: AuroraColors) {
    LaunchedEffect(Unit) {
        if (!viewModel.showScreen) {
            viewModel.startScreenView()
        }
    }

    Column(modifier = Modifier.fillMaxSize()) {
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 18.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column {
                Text("Seu computador", fontWeight = FontWeight.SemiBold, fontSize = 18.sp, color = colors.textPrimary)
                Text(
                    if (viewModel.showScreen) "Compartilhamento ativo" else "Controle remoto experimental",
                    fontSize = 12.sp,
                    color = colors.textSecondary,
                )
            }
            Button(
                onClick = { if (viewModel.showScreen) viewModel.stopScreenView() else viewModel.startScreenView() },
                shape = RoundedCornerShape(14.dp),
                colors = ButtonDefaults.buttonColors(containerColor = if (viewModel.showScreen) colors.surfaceVariant else colors.primary),
                contentPadding = PaddingValues(horizontal = 14.dp, vertical = 8.dp),
            ) {
                Text(if (viewModel.showScreen) "Parar" else "Conectar", fontSize = 12.sp,
                    color = if (viewModel.showScreen) colors.textPrimary else Color.White)
            }
        }

        Box(
            modifier = Modifier
                .weight(1f).fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp)
                .clip(RoundedCornerShape(24.dp)).background(Color(0xFF111018)),
            contentAlignment = Alignment.Center
        ) {
            val bitmap = viewModel.screenBitmap
            if (bitmap != null) {
                fun mapToScreen(position: Offset, areaWidth: Int, areaHeight: Int): Pair<Float, Float>? {
                    if (areaWidth <= 0 || areaHeight <= 0) return null
                    val fit = minOf(areaWidth / bitmap.width.toFloat(), areaHeight / bitmap.height.toFloat())
                    val imageWidth = bitmap.width * fit
                    val imageHeight = bitmap.height * fit
                    val left = (areaWidth - imageWidth) / 2f
                    val top = (areaHeight - imageHeight) / 2f
                    if (position.x < left || position.y < top || position.x > left + imageWidth || position.y > top + imageHeight) return null
                    return ((position.x - left) / imageWidth).coerceIn(0f, 1f) to
                        ((position.y - top) / imageHeight).coerceIn(0f, 1f)
                }
                BoxWithConstraints(modifier = Modifier.fillMaxSize()) {
                    Image(
                        bitmap = bitmap,
                        contentDescription = "Desktop Stream",
                        contentScale = ContentScale.Fit,
                        modifier = Modifier
                            .fillMaxSize()
                            .pointerInput(Unit) {
                                detectTapGestures(
                                    onTap = { offset ->
                                        mapToScreen(offset, size.width, size.height)?.let { (x, y) ->
                                            viewModel.sendDesktopInput("click", x, y, button = 1)
                                        }
                                    },
                                    onDoubleTap = { offset ->
                                        mapToScreen(offset, size.width, size.height)?.let { (x, y) ->
                                            viewModel.sendDesktopInput("double_click", x, y, button = 1)
                                        }
                                    },
                                    onLongPress = { offset ->
                                        mapToScreen(offset, size.width, size.height)?.let { (x, y) ->
                                            viewModel.sendDesktopInput("click", x, y, button = 3)
                                        }
                                    }
                                )
                            }
                            .pointerInput(Unit) {
                                var lastPoint: Pair<Float, Float>? = null
                                detectDragGestures(
                                    onDragStart = { position ->
                                        lastPoint = mapToScreen(position, size.width, size.height)
                                        lastPoint?.let { (x, y) -> viewModel.sendDesktopInput("down", x, y) }
                                    },
                                    onDragEnd = {
                                        lastPoint?.let { (x, y) -> viewModel.sendDesktopInput("up", x, y) }
                                        lastPoint = null
                                    },
                                    onDragCancel = {
                                        lastPoint?.let { (x, y) -> viewModel.sendDesktopInput("up", x, y) }
                                        lastPoint = null
                                    },
                                ) { change, _ ->
                                    change.consume()
                                    mapToScreen(change.position, size.width, size.height)?.let { point ->
                                        lastPoint = point
                                        viewModel.sendDesktopInput("move", point.first, point.second)
                                    }
                                }
                            }
                    )
                }
            } else {
                Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.padding(28.dp)) {
                    AuroraOrb(70.dp, if (viewModel.showScreen) "thinking" else "idle", colors)
                    Spacer(Modifier.height(18.dp))
                    Text(
                        when {
                            !viewModel.connected -> "Conecte o computador primeiro"
                            viewModel.showScreen -> "Aguardando autorização no computador…"
                            else -> "Toque em Conectar para compartilhar a tela"
                        },
                        color = Color.White,
                        fontSize = 15.sp,
                        fontWeight = FontWeight.Medium,
                        textAlign = TextAlign.Center,
                    )
                    Spacer(Modifier.height(6.dp))
                    Text(
                        "O GNOME pedirá permissão para compartilhar a tela e aceitar toques.",
                        color = Color.White.copy(alpha = .68f),
                        fontSize = 12.sp,
                        textAlign = TextAlign.Center,
                    )
                }
            }
        }

        Row(
            Modifier.fillMaxWidth().padding(horizontal = 18.dp, vertical = 6.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Text("Toque: clicar", fontSize = 11.sp, color = colors.textSecondary)
            Text("Segure: botão direito", fontSize = 11.sp, color = colors.textSecondary)
            Text("Arraste: mover", fontSize = 11.sp, color = colors.textSecondary)
        }
        Spacer(Modifier.height(8.dp))
    }
}

/** Settings keep profile, theme, connection, and wake controls in one calm page. */
@Composable
private fun SettingsTabContent(viewModel: AuroraViewModel, colors: AuroraColors, onConnect: () -> Unit) {
    var editName by remember { mutableStateOf(viewModel.userProfile.username) }
    var editAge by remember { mutableStateOf(viewModel.userProfile.age) }
    var editAvatar by remember { mutableStateOf(viewModel.userProfile.avatarIcon) }

    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(horizontal = 18.dp),
        contentPadding = PaddingValues(top = 10.dp, bottom = 24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Column(Modifier.padding(bottom = 2.dp)) {
                Text("Seu espaço", fontWeight = FontWeight.SemiBold, fontSize = 23.sp, color = colors.textPrimary)
                Text("Perfil, aparência e conexão", fontSize = 13.sp, color = colors.textSecondary)
            }
        }
        item {
            SettingsCard(colors) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    AuroraOrb(45.dp, "idle", colors)
                    Spacer(Modifier.width(12.dp))
                    Column {
                        Text("Perfil local", fontWeight = FontWeight.SemiBold, fontSize = 16.sp, color = colors.textPrimary)
                        Text("Salvo neste celular; sincronizado ao PC quando conectado", fontSize = 11.sp, color = colors.textSecondary)
                    }
                }
                Spacer(Modifier.height(16.dp))
                Text("Como quer ser chamada?", fontSize = 12.sp, color = colors.textSecondary)
                Spacer(Modifier.height(6.dp))
                ProfileField(editName, { editName = it }, "Seu nome", colors)
                Spacer(Modifier.height(11.dp))
                Text("Idade (opcional)", fontSize = 12.sp, color = colors.textSecondary)
                Spacer(Modifier.height(6.dp))
                ProfileField(editAge, { editAge = it }, "Não precisa preencher", colors)
                Spacer(Modifier.height(13.dp))
                Text("Avatar", fontSize = 12.sp, color = colors.textSecondary)
                Spacer(Modifier.height(6.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(7.dp)) {
                    listOf("🌌", "✨", "🪐", "🔮", "🚀").forEach { avatar ->
                        Box(
                            Modifier.size(40.dp).clip(CircleShape)
                                .background(if (editAvatar == avatar) colors.primary.copy(alpha = .16f) else colors.surfaceVariant)
                                .border(if (editAvatar == avatar) 1.5.dp else 0.dp,
                                    if (editAvatar == avatar) colors.primary else Color.Transparent, CircleShape)
                                .clickable { editAvatar = avatar },
                            contentAlignment = Alignment.Center,
                        ) { Text(avatar, fontSize = 19.sp) }
                    }
                }
                Spacer(Modifier.height(15.dp))
                Button(
                    onClick = { viewModel.updateUserProfile(editName, editAge, editAvatar) },
                    modifier = Modifier.fillMaxWidth().heightIn(min = 46.dp),
                    shape = RoundedCornerShape(14.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = colors.primary),
                ) { Text("Salvar perfil", color = Color.White, fontWeight = FontWeight.Medium) }
            }
        }
        item {
            SettingsCard(colors) {
                Text("Aparência", fontWeight = FontWeight.SemiBold, fontSize = 16.sp, color = colors.textPrimary)
                Text("Escolha as cores do aplicativo", fontSize = 12.sp, color = colors.textSecondary)
                Spacer(Modifier.height(12.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    ThemeOption("aurora", "Aurora", colors, Modifier.weight(1f), viewModel.currentThemeName == "aurora") { viewModel.updateTheme("aurora") }
                    ThemeOption("dark", "Noturno", colors, Modifier.weight(1f), viewModel.currentThemeName == "dark") { viewModel.updateTheme("dark") }
                }
                Spacer(Modifier.height(8.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    ThemeOption("light", "Névoa", colors, Modifier.weight(1f), viewModel.currentThemeName == "light") { viewModel.updateTheme("light") }
                    ThemeOption("neon", "Neon", colors, Modifier.weight(1f), viewModel.currentThemeName == "neon") { viewModel.updateTheme("neon") }
                }
            }
        }
        item {
            SettingsCard(colors) {
                Text("Computador", fontWeight = FontWeight.SemiBold, fontSize = 16.sp, color = colors.textPrimary)
                Spacer(Modifier.height(5.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(7.dp).clip(CircleShape).background(if (viewModel.connected) Color(0xFF58A987) else colors.textSecondary))
                    Spacer(Modifier.width(7.dp))
                    Text(if (viewModel.connected) "Conectado" else "Desconectado", fontSize = 13.sp, color = colors.textSecondary)
                }
                if (viewModel.endpoint.isNotBlank()) {
                    Spacer(Modifier.height(5.dp))
                    Text(viewModel.endpoint, fontSize = 11.sp, color = colors.textSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
                Spacer(Modifier.height(13.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                    Button(
                        onClick = onConnect,
                        modifier = Modifier.weight(1f),
                        shape = RoundedCornerShape(14.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = colors.primary),
                    ) { Text(if (viewModel.connected) "Gerenciar conexão" else "Conectar ao PC", color = Color.White) }
                    if (viewModel.connected) TextButton(onClick = viewModel::disconnectFromPc) {
                        Text("Desconectar", color = colors.textSecondary)
                    }
                }
            }
        }
        item {
            SettingsCard(colors) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Column(Modifier.weight(1f)) {
                        Text("Ativação por voz", fontWeight = FontWeight.SemiBold, color = colors.textPrimary)
                        Text("Escuta por “Aurora” em segundo plano", fontSize = 12.sp, color = colors.textSecondary)
                    }
                    Switch(
                        checked = viewModel.alwaysOnWakeActive,
                        onCheckedChange = { viewModel.toggleAlwaysOnWake() },
                        colors = SwitchDefaults.colors(checkedThumbColor = colors.primary),
                    )
                }
                Spacer(Modifier.height(8.dp))
                Text("Perfil e tema ficam neste aparelho. Dados de conversa e IA permanecem no PC pareado.",
                    fontSize = 11.sp, lineHeight = 16.sp, color = colors.textSecondary)
                TextButton(onClick = viewModel::logout, modifier = Modifier.fillMaxWidth()) {
                    Text("Sair do perfil local", color = colors.textSecondary)
                }
            }
        }
    }
}

@Composable
private fun SettingsCard(colors: AuroraColors, content: @Composable () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(22.dp),
        colors = CardDefaults.cardColors(containerColor = colors.surface),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
    ) {
        Column(Modifier.padding(17.dp)) { content() }
    }
}

@Composable
private fun ProfileField(value: String, onValue: (String) -> Unit, placeholder: String, colors: AuroraColors) {
    BasicTextField(
        value = value,
        onValueChange = onValue,
        singleLine = true,
        textStyle = TextStyle(color = colors.textPrimary, fontSize = 14.sp),
        cursorBrush = SolidColor(colors.primary),
        modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(13.dp))
            .background(colors.surfaceVariant).padding(horizontal = 13.dp, vertical = 12.dp),
        decorationBox = { inner ->
            if (value.isEmpty()) Text(placeholder, color = colors.textSecondary, fontSize = 14.sp)
            inner()
        },
    )
}

@Composable
private fun ThemeOption(key: String, label: String, colors: AuroraColors, modifier: Modifier, selected: Boolean, onClick: () -> Unit) {
    val swatch = when (key) {
        "dark" -> Color(0xFF242034)
        "light" -> Color(0xFFE6EDF2)
        "neon" -> Color(0xFF1D2338)
        else -> Color(0xFFC7B6E8)
    }
    Row(
        modifier.heightIn(min = 48.dp).clip(RoundedCornerShape(14.dp))
            .background(if (selected) colors.primary.copy(alpha = .12f) else colors.surfaceVariant)
            .border(if (selected) 1.dp else 0.dp, if (selected) colors.primary else Color.Transparent, RoundedCornerShape(14.dp))
            .clickable(onClick = onClick).padding(horizontal = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(18.dp).clip(CircleShape).background(swatch))
        Spacer(Modifier.width(8.dp))
        Text(label, color = colors.textPrimary, fontSize = 12.sp, fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal)
    }
}

@Composable
private fun OutlinedConnectField(value: String, onValue: (String) -> Unit, placeholder: String) {
    BasicTextField(
        value = value,
        onValueChange = onValue,
        singleLine = true,
        textStyle = TextStyle(color = Color(0xFF29263A), fontSize = 14.sp),
        modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp))
            .background(Color(0xFFF0EDF5)).padding(horizontal = 12.dp, vertical = 13.dp),
        decorationBox = { inner ->
            if (value.isBlank()) Text(placeholder, color = Color(0xFF777387), fontSize = 13.sp)
            inner()
        },
    )
}
