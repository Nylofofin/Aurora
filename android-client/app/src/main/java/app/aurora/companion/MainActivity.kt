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
    val avatars = listOf("🌌", "⚡", "✨", "🪐", "🐺", "🔮", "🚀")

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
                Text(
                    text = "Aurora AI",
                    fontSize = 28.sp,
                    fontWeight = FontWeight.Bold,
                    color = colors.primary
                )
                Text(
                    text = "Seu assistente pessoal inteligente",
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
                        .padding(horizontal = 16.dp, vertical = 14.dp)
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
                        .padding(horizontal = 16.dp, vertical = 14.dp)
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

    ModalNavigationDrawer(
        drawerState = drawerState,
        drawerContent = {
            ModalDrawerSheet(
                drawerContainerColor = colors.surface,
                drawerContentColor = colors.textPrimary,
                modifier = Modifier.width(300.dp)
            ) {
                Text(
                    "Aurora Companion",
                    fontWeight = FontWeight.Bold,
                    fontSize = 18.sp,
                    color = colors.primary,
                    modifier = Modifier.padding(20.dp)
                )
                NavigationDrawerItem(
                    label = { Text("Nova Conversa") },
                    selected = false,
                    onClick = {
                        viewModel.newConversation()
                        viewModel.activeTab = CompanionTab.CHAT
                        scope.launch { drawerState.close() }
                    },
                    modifier = Modifier.padding(horizontal = 12.dp)
                )
                Spacer(Modifier.height(8.dp))
                Text(
                    "Histórico do PC",
                    fontSize = 12.sp,
                    color = colors.textSecondary,
                    modifier = Modifier.padding(horizontal = 20.dp, vertical = 6.dp)
                )
                LazyColumn(modifier = Modifier.weight(1f)) {
                    items(viewModel.conversations) { conv ->
                        NavigationDrawerItem(
                            label = { Text(conv.title, maxLines = 1, overflow = TextOverflow.Ellipsis) },
                            selected = viewModel.conversationId == conv.id,
                            onClick = {
                                viewModel.openConversation(conv.id)
                                scope.launch { drawerState.close() }
                            },
                            modifier = Modifier.padding(horizontal = 12.dp, vertical = 2.dp)
                        )
                    }
                }
            }
        }
    ) {
        Column(modifier = Modifier.fillMaxSize()) {
            Box(modifier = Modifier.weight(1f)) {
                when (viewModel.activeTab) {
                    CompanionTab.CHAT -> ChatTabContent(viewModel = viewModel, colors = colors, onOpenDrawer = { scope.launch { drawerState.open() } })
                    CompanionTab.LIVE -> LiveTabContent(viewModel = viewModel, colors = colors)
                    CompanionTab.DESKTOP -> DesktopTabContent(viewModel = viewModel, colors = colors)
                    CompanionTab.SETTINGS -> SettingsTabContent(viewModel = viewModel, colors = colors)
                }
            }

            // Bottom Navigation Bar
            NavigationBar(
                containerColor = colors.surface,
                contentColor = colors.textPrimary,
                tonalElevation = 6.dp
            ) {
                NavigationBarItem(
                    selected = viewModel.activeTab == CompanionTab.CHAT,
                    onClick = { viewModel.activeTab = CompanionTab.CHAT },
                    icon = { Text("💬", fontSize = 18.sp) },
                    label = { Text("Chat", fontSize = 11.sp) },
                    colors = NavigationBarItemDefaults.colors(
                        selectedIconColor = colors.primary,
                        selectedTextColor = colors.primary,
                        unselectedIconColor = colors.textSecondary,
                        unselectedTextColor = colors.textSecondary,
                        indicatorColor = colors.primary.copy(alpha = 0.15f)
                    )
                )
                NavigationBarItem(
                    selected = viewModel.activeTab == CompanionTab.LIVE,
                    onClick = {
                        viewModel.activeTab = CompanionTab.LIVE
                        if (!viewModel.liveMode) viewModel.enterLiveMode()
                    },
                    icon = { Text("🎙️", fontSize = 18.sp) },
                    label = { Text("Live", fontSize = 11.sp) },
                    colors = NavigationBarItemDefaults.colors(
                        selectedIconColor = colors.primary,
                        selectedTextColor = colors.primary,
                        unselectedIconColor = colors.textSecondary,
                        unselectedTextColor = colors.textSecondary,
                        indicatorColor = colors.primary.copy(alpha = 0.15f)
                    )
                )
                NavigationBarItem(
                    selected = viewModel.activeTab == CompanionTab.DESKTOP,
                    onClick = {
                        viewModel.activeTab = CompanionTab.DESKTOP
                        if (!viewModel.showScreen) viewModel.startScreenView()
                    },
                    icon = { Text("🖥️", fontSize = 18.sp) },
                    label = { Text("Desktop", fontSize = 11.sp) },
                    colors = NavigationBarItemDefaults.colors(
                        selectedIconColor = colors.primary,
                        selectedTextColor = colors.primary,
                        unselectedIconColor = colors.textSecondary,
                        unselectedTextColor = colors.textSecondary,
                        indicatorColor = colors.primary.copy(alpha = 0.15f)
                    )
                )
                NavigationBarItem(
                    selected = viewModel.activeTab == CompanionTab.SETTINGS,
                    onClick = { viewModel.activeTab = CompanionTab.SETTINGS },
                    icon = { Text("⚙️", fontSize = 18.sp) },
                    label = { Text("Ajustes", fontSize = 11.sp) },
                    colors = NavigationBarItemDefaults.colors(
                        selectedIconColor = colors.primary,
                        selectedTextColor = colors.primary,
                        unselectedIconColor = colors.textSecondary,
                        unselectedTextColor = colors.textSecondary,
                        indicatorColor = colors.primary.copy(alpha = 0.15f)
                    )
                )
            }
        }
    }
}

@Composable
private fun ChatTabContent(viewModel: AuroraViewModel, colors: AuroraColors, onOpenDrawer: () -> Unit) {
    var textDraft by remember { mutableStateOf("") }
    val keyboard = LocalSoftwareKeyboardController.current

    Column(modifier = Modifier.fillMaxSize().padding(horizontal = 16.dp)) {
        Spacer(Modifier.height(12.dp))
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    modifier = Modifier
                        .size(38.dp)
                        .clip(CircleShape)
                        .background(colors.surfaceVariant)
                        .clickable { onOpenDrawer() },
                    contentAlignment = Alignment.Center
                ) {
                    Text("☰", fontSize = 18.sp, color = colors.textPrimary)
                }
                Spacer(Modifier.width(12.dp))
                Column {
                    Text(
                        text = "Aurora",
                        fontWeight = FontWeight.Bold,
                        fontSize = 17.sp,
                        color = colors.textPrimary
                    )
                    Text(
                        text = if (viewModel.connected) "PC Conectado" else "Offline",
                        fontSize = 11.sp,
                        color = if (viewModel.connected) Color(0xFF4CAF50) else colors.textSecondary
                    )
                }
            }

            Text(
                viewModel.userProfile.avatarIcon,
                fontSize = 24.sp
            )
        }

        Spacer(Modifier.height(10.dp))

        // Lista de mensagens
        LazyColumn(
            modifier = Modifier.weight(1f).fillMaxWidth(),
            reverseLayout = true
        ) {
            items(viewModel.lines.reversed()) { line ->
                Row(
                    modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
                    horizontalArrangement = if (line.fromUser) Arrangement.End else Arrangement.Start
                ) {
                    Box(
                        modifier = Modifier
                            .fillMaxWidth(0.82f)
                            .clip(RoundedCornerShape(18.dp))
                            .background(if (line.fromUser) colors.primary else colors.surfaceVariant)
                            .padding(14.dp)
                    ) {
                        Text(
                            text = line.text,
                            color = if (line.fromUser) Color.White else colors.textPrimary,
                            fontSize = 15.sp,
                            lineHeight = 21.sp
                        )
                    }
                }
            }
        }

        if (viewModel.notice.isNotBlank()) {
            Text(
                text = viewModel.notice,
                fontSize = 11.sp,
                color = colors.textSecondary,
                modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
                textAlign = TextAlign.Center
            )
        }

        // Barra de digitação
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(vertical = 10.dp)
                .imePadding(),
            verticalAlignment = Alignment.CenterVertically
        ) {
            BasicTextField(
                value = textDraft,
                onValueChange = { textDraft = it },
                textStyle = TextStyle(color = colors.textPrimary, fontSize = 15.sp),
                cursorBrush = SolidColor(colors.primary),
                modifier = Modifier
                    .weight(1f)
                    .clip(RoundedCornerShape(22.dp))
                    .background(colors.surfaceVariant)
                    .padding(horizontal = 16.dp, vertical = 12.dp),
                decorationBox = { innerTextField ->
                    if (textDraft.isEmpty()) {
                        Text("Pergunte algo à Aurora…", color = colors.textSecondary, fontSize = 14.sp)
                    }
                    innerTextField()
                }
            )
            Spacer(Modifier.width(8.dp))
            Box(
                modifier = Modifier
                    .size(46.dp)
                    .clip(CircleShape)
                    .background(colors.primary)
                    .clickable {
                        if (textDraft.isNotBlank()) {
                            viewModel.sendCurrentMessage(textDraft)
                            textDraft = ""
                            keyboard?.hide()
                        }
                    },
                contentAlignment = Alignment.Center
            ) {
                Text("➤", color = Color.White, fontSize = 18.sp)
            }
        }
    }
}

/**
 * Modo Live Imersivo e 100% Hands-Free.
 * O microfone fica eternamente aberto; sem botões manuais desnecessários de "Falar".
 */
@Composable
private fun LiveTabContent(viewModel: AuroraViewModel, colors: AuroraColors) {
    val transition = rememberInfiniteTransition(label = "live-orb")
    val pulse by transition.animateFloat(
        initialValue = 0.95f,
        targetValue = if (viewModel.remoteState == "speaking") 1.12f else 1.05f,
        animationSpec = infiniteRepeatable(tween(900, easing = FastOutSlowInEasing), RepeatMode.Reverse),
        label = "pulse"
    )

    LaunchedEffect(Unit) {
        if (!viewModel.liveMode) {
            viewModel.enterLiveMode()
        }
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(
                Brush.radialGradient(
                    colors = listOf(colors.surfaceVariant, colors.background),
                    radius = 900f
                )
            ),
        contentAlignment = Alignment.Center
    ) {
        Column(
            modifier = Modifier.fillMaxSize().padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.SpaceBetween
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    "AURORA  ·  LIVE CONTÍNUO",
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Bold,
                    color = colors.primary
                )
                Box(
                    modifier = Modifier
                        .size(36.dp)
                        .clip(CircleShape)
                        .background(colors.surface.copy(alpha = 0.6f))
                        .clickable { viewModel.leaveLiveMode(playExitSound = true) },
                    contentAlignment = Alignment.Center
                ) {
                    Text("✕", fontSize = 16.sp, color = colors.textPrimary)
                }
            }

            // Orbe Cósmica
            Box(
                modifier = Modifier
                    .size(220.dp)
                    .scale(pulse)
                    .clip(CircleShape)
                    .background(
                        Brush.radialGradient(
                            listOf(colors.primary, colors.secondary, Color.Transparent)
                        )
                    )
                    .border(2.dp, colors.accent.copy(alpha = 0.6f), CircleShape),
                contentAlignment = Alignment.Center
            ) {
                Text(
                    text = when (viewModel.remoteState) {
                        "listening" -> "Ouvindo"
                        "transcribing" -> "Entendendo"
                        "preparing" -> "Pensando"
                        "speaking" -> "Falando"
                        else -> "Aurora"
                    },
                    fontWeight = FontWeight.Bold,
                    fontSize = 16.sp,
                    color = Color.White
                )
            }

            // Status e Transcrição Recente
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                val lastResponse = viewModel.lines.lastOrNull { !it.fromUser }?.text
                if (lastResponse != null) {
                    Text(
                        text = lastResponse.take(120),
                        fontSize = 13.sp,
                        color = colors.textSecondary,
                        textAlign = TextAlign.Center,
                        maxLines = 3,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.padding(bottom = 12.dp)
                    )
                }
                Text(
                    text = when {
                        viewModel.live -> "Microfone aberto. Pode falar à vontade."
                        viewModel.remoteState == "speaking" -> "Aurora respondendo…"
                        viewModel.remoteState == "transcribing" -> "Processando áudio…"
                        else -> "Escuta contínua ativa."
                    },
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Medium,
                    color = colors.textPrimary
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
            modifier = Modifier.fillMaxWidth().padding(12.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text("🖥️ Desktop Remoto Touch", fontWeight = FontWeight.Bold, color = colors.textPrimary)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(
                    onClick = { viewModel.toggleScreenView() },
                    shape = RoundedCornerShape(12.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = colors.surfaceVariant),
                    contentPadding = PaddingValues(horizontal = 12.dp, vertical = 6.dp)
                ) {
                    Text(if (viewModel.showScreen) "Pausar" else "Conectar", fontSize = 12.sp, color = colors.textPrimary)
                }
            }
        }

        Box(
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth()
                .background(Color.Black),
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
                Text(
                    "Conectando ao desktop do computador…",
                    color = Color.White.copy(alpha = 0.7f),
                    fontSize = 14.sp
                )
            }
        }

        // Instruções de toque
        Row(
            modifier = Modifier.fillMaxWidth().background(colors.surface).padding(8.dp),
            horizontalArrangement = Arrangement.SpaceAround
        ) {
            Text("Toque: Clique", fontSize = 11.sp, color = colors.textSecondary)
            Text("2 Toques: Duplo clique", fontSize = 11.sp, color = colors.textSecondary)
            Text("Segurar: Botão direito", fontSize = 11.sp, color = colors.textSecondary)
            Text("Arrasto: Cursor", fontSize = 11.sp, color = colors.textSecondary)
        }
    }
}

/**
 * Aba de Configurações, Perfil e Temas.
 */
@Composable
private fun SettingsTabContent(viewModel: AuroraViewModel, colors: AuroraColors) {
    var editName by remember { mutableStateOf(viewModel.userProfile.username) }
    var editAge by remember { mutableStateOf(viewModel.userProfile.age) }

    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        item {
            Text("⚙️ Configurações & Perfil", fontWeight = FontWeight.Bold, fontSize = 22.sp, color = colors.textPrimary)
        }

        // Cartão Perfil
        item {
            Card(
                colors = CardDefaults.cardColors(containerColor = colors.surface),
                shape = RoundedCornerShape(20.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.padding(18.dp)) {
                    Text("Perfil do Usuário", fontWeight = FontWeight.Bold, fontSize = 16.sp, color = colors.primary)
                    Spacer(Modifier.height(10.dp))
                    Text("Nome", fontSize = 12.sp, color = colors.textSecondary)
                    BasicTextField(
                        value = editName,
                        onValueChange = { editName = it },
                        textStyle = TextStyle(color = colors.textPrimary, fontSize = 15.sp),
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(10.dp))
                            .background(colors.surfaceVariant)
                            .padding(12.dp)
                    )
                    Spacer(Modifier.height(10.dp))
                    Text("Idade", fontSize = 12.sp, color = colors.textSecondary)
                    BasicTextField(
                        value = editAge,
                        onValueChange = { editAge = it },
                        textStyle = TextStyle(color = colors.textPrimary, fontSize = 15.sp),
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(10.dp))
                            .background(colors.surfaceVariant)
                            .padding(12.dp)
                    )
                    Spacer(Modifier.height(14.dp))
                    Button(
                        onClick = {
                            viewModel.updateUserProfile(editName, editAge, viewModel.userProfile.avatarIcon)
                        },
                        shape = RoundedCornerShape(12.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = colors.primary)
                    ) {
                        Text("Salvar Perfil no Celular & PC", color = Color.White)
                    }
                }
            }
        }

        // Cartão de Temas
        item {
            Card(
                colors = CardDefaults.cardColors(containerColor = colors.surface),
                shape = RoundedCornerShape(20.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.padding(18.dp)) {
                    Text("Tema Visual", fontWeight = FontWeight.Bold, fontSize = 16.sp, color = colors.primary)
                    Spacer(Modifier.height(12.dp))
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        listOf("aurora" to "Lilás", "dark" to "Escuro", "light" to "Claro", "neon" to "Neon").forEach { (themeKey, label) ->
                            Button(
                                onClick = { viewModel.updateTheme(themeKey) },
                                modifier = Modifier.weight(1f),
                                shape = RoundedCornerShape(12.dp),
                                colors = ButtonDefaults.buttonColors(
                                    containerColor = if (viewModel.currentThemeName == themeKey) colors.primary else colors.surfaceVariant
                                )
                            ) {
                                Text(label, fontSize = 11.sp, color = if (viewModel.currentThemeName == themeKey) Color.White else colors.textPrimary)
                            }
                        }
                    }
                }
            }
        }

        // Cartão Conexão PC
        item {
            Card(
                colors = CardDefaults.cardColors(containerColor = colors.surface),
                shape = RoundedCornerShape(20.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.padding(18.dp)) {
                    Text("Conexão com Computador", fontWeight = FontWeight.Bold, fontSize = 16.sp, color = colors.primary)
                    Spacer(Modifier.height(10.dp))
                    Text("Endereço: ${viewModel.endpoint.ifBlank { "Nenhum" }}", fontSize = 13.sp, color = colors.textSecondary)
                    Text("Status: ${if (viewModel.connected) "Conectado" else "Desconectado"}", fontSize = 13.sp, color = colors.textSecondary)
                    Spacer(Modifier.height(12.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(
                            onClick = { viewModel.findPc() },
                            shape = RoundedCornerShape(12.dp),
                            colors = ButtonDefaults.buttonColors(containerColor = colors.surfaceVariant)
                        ) {
                            Text("Buscar PC", color = colors.textPrimary)
                        }
                        Button(
                            onClick = { if (viewModel.connected) viewModel.disconnectFromPc() else viewModel.connectToPc() },
                            shape = RoundedCornerShape(12.dp),
                            colors = ButtonDefaults.buttonColors(containerColor = colors.primary)
                        ) {
                            Text(if (viewModel.connected) "Desconectar" else "Conectar", color = Color.White)
                        }
                    }
                }
            }
        }

        // Cartão Escuta Permanente & Sessão
        item {
            Card(
                colors = CardDefaults.cardColors(containerColor = colors.surface),
                shape = RoundedCornerShape(20.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.padding(18.dp)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column {
                            Text("Escuta 'Hey Aurora'", fontWeight = FontWeight.Medium, color = colors.textPrimary)
                            Text("Ativação contínua em segundo plano", fontSize = 12.sp, color = colors.textSecondary)
                        }
                        Switch(
                            checked = viewModel.alwaysOnWakeActive,
                            onCheckedChange = { viewModel.toggleAlwaysOnWake() },
                            colors = SwitchDefaults.colors(checkedThumbColor = colors.primary)
                        )
                    }

                    Spacer(Modifier.height(14.dp))
                    TextButton(
                        onClick = { viewModel.logout() },
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Text("Sair da Conta (Logout)", color = Color.Red)
                    }
                }
            }
        }
    }
}
