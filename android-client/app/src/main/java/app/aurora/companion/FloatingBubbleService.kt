package app.aurora.companion

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.graphics.PixelFormat
import android.os.Build
import android.os.IBinder
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.widget.FrameLayout
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
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
import androidx.compose.ui.platform.ComposeView
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.LifecycleRegistry
import androidx.lifecycle.ViewModelStore
import androidx.lifecycle.ViewModelStoreOwner
import androidx.lifecycle.setViewTreeLifecycleOwner
import androidx.lifecycle.setViewTreeViewModelStoreOwner
import androidx.savedstate.SavedStateRegistry
import androidx.savedstate.SavedStateRegistryController
import androidx.savedstate.SavedStateRegistryOwner
import androidx.savedstate.setViewTreeSavedStateRegistryOwner
import kotlin.math.abs

/**
 * Overlay flutuante da Aurora: exibe uma bolha animada acima de todos os apps.
 * Ativado quando o usuário sai do app durante o modo Live.
 *
 * Requer permissão SYSTEM_ALERT_WINDOW (Settings > Exibir sobre outros apps).
 * O usuário é direcionado para conceder a permissão antes de entrar no modo Live
 * pela primeira vez.
 */
class FloatingBubbleService : Service(), LifecycleOwner, ViewModelStoreOwner, SavedStateRegistryOwner {

    private val lifecycleRegistry = LifecycleRegistry(this)
    private val savedStateRegistryController = SavedStateRegistryController.create(this)
    private val viewModelStoreOwner = object : ViewModelStoreOwner {
        override val viewModelStore = ViewModelStore()
    }

    override val lifecycle: Lifecycle get() = lifecycleRegistry
    override val viewModelStore: ViewModelStore get() = viewModelStoreOwner.viewModelStore
    override val savedStateRegistry: SavedStateRegistry get() = savedStateRegistryController.savedStateRegistry

    private var windowManager: WindowManager? = null
    private var bubbleView: View? = null

    // Estado compartilhado (atualizado via Intent)
    var bubbleActivity by mutableStateOf("idle")
        private set

    override fun onCreate() {
        super.onCreate()
        savedStateRegistryController.performAttach()
        savedStateRegistryController.performRestore(null)
        lifecycleRegistry.currentState = Lifecycle.State.CREATED
        windowManager = getSystemService(WINDOW_SERVICE) as WindowManager
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_SHOW -> {
                val activity = intent.getStringExtra(EXTRA_ACTIVITY) ?: "idle"
                val endpoint = intent.getStringExtra(EXTRA_ENDPOINT).orEmpty()
                val fingerprint = intent.getStringExtra(EXTRA_FINGERPRINT).orEmpty()
                val token = intent.getStringExtra(EXTRA_TOKEN).orEmpty()
                bubbleActivity = activity
                showBubble(endpoint, fingerprint, token)
                ensureChannel()
                startForeground(NOTIFICATION_ID, buildNotification())
                lifecycleRegistry.currentState = Lifecycle.State.STARTED
                lifecycleRegistry.currentState = Lifecycle.State.RESUMED
            }
            ACTION_UPDATE_ACTIVITY -> {
                bubbleActivity = intent.getStringExtra(EXTRA_ACTIVITY) ?: "idle"
            }
            ACTION_HIDE -> {
                hideBubble()
                stopForeground(STOP_FOREGROUND_REMOVE)
                stopSelf(startId)
            }
        }
        return START_NOT_STICKY
    }

    private fun showBubble(endpoint: String, fingerprint: String, token: String) {
        if (bubbleView != null) return  // já exibida

        val params = WindowManager.LayoutParams(
            BUBBLE_SIZE_PX, BUBBLE_SIZE_PX,
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
            else
                @Suppress("DEPRECATION") WindowManager.LayoutParams.TYPE_PHONE,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                    WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.BOTTOM or Gravity.END
            x = INITIAL_X_PX
            y = INITIAL_Y_PX
        }

        val container = FrameLayout(this)

        // Configurar o ComposeView para a bolha
        val composeView = ComposeView(this).apply {
            setViewTreeLifecycleOwner(this@FloatingBubbleService)
            setViewTreeViewModelStoreOwner(this@FloatingBubbleService)
            setViewTreeSavedStateRegistryOwner(this@FloatingBubbleService)
            setContent {
                BubbleContent(
                    activity = bubbleActivity,
                    onTap = {
                        // Retornar ao app
                        val launch = packageManager.getLaunchIntentForPackage(packageName)
                            ?.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_REORDER_TO_FRONT)
                        launch?.let { startActivity(it) }
                    },
                    onDismiss = {
                        // Encerrar o overlay
                        sendBroadcast(Intent(ACTION_BUBBLE_DISMISSED).setPackage(packageName))
                        hideBubble()
                        stopForeground(STOP_FOREGROUND_REMOVE)
                        stopSelf()
                    },
                )
            }
        }
        container.addView(composeView)

        // Tornar a bolha draggable
        var lastX = 0f
        var lastY = 0f
        var dragging = false
        var startRawX = 0f
        var startRawY = 0f

        container.setOnTouchListener { _, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    lastX = event.rawX
                    lastY = event.rawY
                    startRawX = event.rawX
                    startRawY = event.rawY
                    dragging = false
                    false
                }
                MotionEvent.ACTION_MOVE -> {
                    val dx = event.rawX - lastX
                    val dy = event.rawY - lastY
                    if (!dragging && (abs(dx) > DRAG_THRESHOLD || abs(dy) > DRAG_THRESHOLD)) {
                        dragging = true
                    }
                    if (dragging) {
                        params.x -= dx.toInt()
                        params.y -= dy.toInt()
                        lastX = event.rawX
                        lastY = event.rawY
                        windowManager?.updateViewLayout(container, params)
                    }
                    dragging
                }
                MotionEvent.ACTION_UP -> {
                    val totalMove = abs(event.rawX - startRawX) + abs(event.rawY - startRawY)
                    dragging = false
                    totalMove > DRAG_THRESHOLD  // consume se foi drag, passa para click se foi tap
                }
                else -> false
            }
        }

        bubbleView = container
        windowManager?.addView(container, params)
    }

    private fun hideBubble() {
        bubbleView?.let { view ->
            lifecycleRegistry.currentState = Lifecycle.State.CREATED
            runCatching { windowManager?.removeView(view) }
        }
        bubbleView = null
    }

    override fun onDestroy() {
        hideBubble()
        lifecycleRegistry.currentState = Lifecycle.State.DESTROYED
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun ensureChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = getSystemService(NotificationManager::class.java)
        if (manager.getNotificationChannel(CHANNEL_ID) != null) return
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL_ID, "Aurora flutuante", NotificationManager.IMPORTANCE_LOW).apply {
                description = "Aurora ativa sobre outros apps. Toque na bolha para voltar."
            }
        )
    }

    private fun buildNotification(): Notification {
        val launch = packageManager.getLaunchIntentForPackage(packageName)?.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        val pending = launch?.let {
            PendingIntent.getActivity(this, 0, it, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        }
        val stop = Intent(ACTION_HIDE).setClass(this, FloatingBubbleService::class.java)
        val stopPending = PendingIntent.getService(this, 1, stop, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)

        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
            Notification.Builder(this, CHANNEL_ID)
        else Notification.Builder(this)

        return builder
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle("Aurora está ouvindo")
            .setContentText("Toque para abrir ou encerrar a sessão.")
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setContentIntent(pending)
            .addAction(android.R.drawable.ic_menu_close_clear_cancel, "Encerrar", stopPending)
            .build()
    }

    companion object {
        const val ACTION_SHOW = "app.aurora.companion.BUBBLE_SHOW"
        const val ACTION_HIDE = "app.aurora.companion.BUBBLE_HIDE"
        const val ACTION_UPDATE_ACTIVITY = "app.aurora.companion.BUBBLE_UPDATE_ACTIVITY"
        const val ACTION_BUBBLE_DISMISSED = "app.aurora.companion.BUBBLE_DISMISSED"

        const val EXTRA_ACTIVITY = "activity"
        const val EXTRA_ENDPOINT = "endpoint"
        const val EXTRA_FINGERPRINT = "fingerprint"
        const val EXTRA_TOKEN = "token"

        private const val CHANNEL_ID = "aurora-floating-bubble"
        private const val NOTIFICATION_ID = 0xA073
        private val BUBBLE_SIZE_PX = 220  // px — tamanho lógico, ajuste via density
        private val INITIAL_X_PX = 48
        private val INITIAL_Y_PX = 160
        private val DRAG_THRESHOLD = 8f  // px de movimento para considerar drag
    }
}

// ─── UI da bolha ───────────────────────────────────────────────────────────────

@Composable
private fun BubbleContent(
    activity: String,
    onTap: () -> Unit,
    onDismiss: () -> Unit,
) {
    val violet = Color(0xFF8A70C4)
    val blue = Color(0xFF579BC2)
    val pearl = Color(0xFF29263A)

    val transition = rememberInfiniteTransition(label = "bubble-orb")
    val pulseMillis = when (activity) {
        "transcribing", "thinking", "preparing" -> 1050
        "searching" -> 1450
        "speaking" -> 720
        "listening" -> 850
        else -> 2500
    }
    val auraColor = when (activity) {
        "searching" -> blue
        "speaking" -> Color(0xFFD9C7FF)
        "thinking", "transcribing", "preparing" -> violet
        else -> violet
    }
    val breathe by transition.animateFloat(
        initialValue = 0.94f,
        targetValue = if (activity != "idle") 1.08f else 1.02f,
        animationSpec = infiniteRepeatable(tween(pulseMillis, easing = FastOutSlowInEasing), RepeatMode.Reverse),
        label = "bubble-breathe",
    )
    val halo by transition.animateFloat(
        initialValue = 1f,
        targetValue = if (activity != "idle") 1.45f else 1.10f,
        animationSpec = infiniteRepeatable(tween(pulseMillis, easing = FastOutSlowInEasing), RepeatMode.Reverse),
        label = "bubble-halo",
    )
    val haloAlpha by transition.animateFloat(
        initialValue = if (activity != "idle") 0.35f else 0.12f,
        targetValue = 0.01f,
        animationSpec = infiniteRepeatable(tween(pulseMillis, easing = FastOutSlowInEasing), RepeatMode.Reverse),
        label = "bubble-halo-alpha",
    )
    val drift by transition.animateFloat(
        initialValue = 0.15f,
        targetValue = 0.85f,
        animationSpec = infiniteRepeatable(tween(4600, easing = FastOutSlowInEasing), RepeatMode.Reverse),
        label = "bubble-drift",
    )

    Box(Modifier.size(80.dp), contentAlignment = Alignment.Center) {
        // Halo externo animado
        Box(
            Modifier.size(80.dp).scale(halo).alpha(haloAlpha)
                .border(1.dp, auraColor, CircleShape)
        )
        // Corpo da bolha
        Box(
            Modifier.size(72.dp).scale(breathe).clip(CircleShape)
                .background(
                    Brush.linearGradient(
                        colors = listOf(
                            Color(0xFFFFFFFF), Color(0xFFF0EAF8),
                            Color(0xFFD7C8EF), Color(0xFFA9CFE4), Color(0xFF927BC9),
                        ),
                        start = Offset(0f, 0f),
                        end = Offset(280f * drift, 380f * (1f - drift)),
                    )
                )
                .border(1.dp, Color.White.copy(alpha = 0.45f), CircleShape)
                .clickable(onClick = onTap),
            contentAlignment = Alignment.Center,
        ) {
            // Reflexo interno
            Box(
                Modifier.size(72.dp).background(
                    Brush.radialGradient(
                        listOf(Color.White.copy(0.68f), Color.White.copy(0.08f), Color.Transparent),
                        radius = 110f,
                    ),
                    CircleShape,
                )
            )
            // Indicador de estado (ícone de waveform quando ativo)
            if (activity == "listening" || activity == "speaking") {
                Canvas(Modifier.size(20.dp)) {
                    val heights = if (activity == "speaking")
                        listOf(.4f, .75f, .55f, .90f, .55f, .75f, .4f)
                    else
                        listOf(.3f, .55f, .85f, .5f, .85f, .55f, .3f)
                    val step = size.width / (heights.size * 1.7f)
                    val gap = step * .7f
                    heights.forEachIndexed { idx, ratio ->
                        val x = step / 2f + idx * (step + gap)
                        val half = size.height * ratio / 2f
                        drawLine(
                            color = pearl.copy(alpha = 0.65f),
                            start = Offset(x, size.height / 2f - half),
                            end = Offset(x, size.height / 2f + half),
                            strokeWidth = 2.dp.toPx(),
                            cap = StrokeCap.Round,
                        )
                    }
                }
            }
        }
        // Botão X pequeno no canto superior direito
        Box(
            Modifier.size(22.dp).align(Alignment.TopEnd)
                .clip(CircleShape)
                .background(Color(0xFFEAE3F5))
                .clickable(onClick = onDismiss),
            contentAlignment = Alignment.Center,
        ) {
            androidx.compose.material3.Text(
                "×",
                color = pearl,
                fontSize = androidx.compose.ui.unit.TextUnit(12f, androidx.compose.ui.unit.TextUnitType.Sp),
            )
        }
    }
}
