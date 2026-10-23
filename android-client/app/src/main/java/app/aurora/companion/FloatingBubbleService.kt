package app.aurora.companion

import android.annotation.SuppressLint
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
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
import androidx.compose.material3.Text
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
import androidx.compose.ui.unit.sp
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
 * Overlay flutuante da Aurora: renderiza a bolha animada sobre outros apps.
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
    private var containerView: FrameLayout? = null

    var bubbleActivity by mutableStateOf("idle")
        private set

    override fun onCreate() {
        super.onCreate()
        savedStateRegistryController.performAttach()
        savedStateRegistryController.performRestore(null)
        lifecycleRegistry.currentState = Lifecycle.State.CREATED
        windowManager = getSystemService(Context.WINDOW_SERVICE) as WindowManager
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_SHOW -> {
                bubbleActivity = intent.getStringExtra(EXTRA_ACTIVITY) ?: "idle"
                ensureChannel()
                startForeground(NOTIFICATION_ID, buildNotification())
                showBubble()
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

    @SuppressLint("ClickableViewAccessibility")
    private fun showBubble() {
        if (containerView != null) return

        val density = resources.displayMetrics.density
        val sizePx = (80 * density).toInt()

        val layoutType = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
        } else {
            @Suppress("DEPRECATION")
            WindowManager.LayoutParams.TYPE_PHONE
        }

        val params = WindowManager.LayoutParams(
            sizePx, sizePx,
            layoutType,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                    WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN or
                    WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            x = (resources.displayMetrics.widthPixels - sizePx - (20 * density).toInt())
            y = (resources.displayMetrics.heightPixels / 3)
        }

        val container = FrameLayout(this)
        val composeView = ComposeView(this).apply {
            setViewTreeLifecycleOwner(this@FloatingBubbleService)
            setViewTreeViewModelStoreOwner(this@FloatingBubbleService)
            setViewTreeSavedStateRegistryOwner(this@FloatingBubbleService)
            setContent {
                BubbleContent(
                    activity = bubbleActivity,
                    onTap = {
                        val launch = packageManager.getLaunchIntentForPackage(packageName)?.apply {
                            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_REORDER_TO_FRONT)
                        }
                        launch?.let { startActivity(it) }
                    },
                    onDismiss = {
                        sendBroadcast(Intent(ACTION_BUBBLE_DISMISSED).setPackage(packageName))
                        hideBubble()
                        stopForeground(STOP_FOREGROUND_REMOVE)
                        stopSelf()
                    }
                )
            }
        }
        container.addView(composeView)

        var initialX = 0
        var initialY = 0
        var initialTouchX = 0f
        var initialTouchY = 0f
        var isDragging = false

        container.setOnTouchListener { _, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    initialX = params.x
                    initialY = params.y
                    initialTouchX = event.rawX
                    initialTouchY = event.rawY
                    isDragging = false
                    false
                }
                MotionEvent.ACTION_MOVE -> {
                    val dx = (event.rawX - initialTouchX).toInt()
                    val dy = (event.rawY - initialTouchY).toInt()
                    if (abs(dx) > 10 || abs(dy) > 10) {
                        isDragging = true
                    }
                    if (isDragging) {
                        params.x = initialX + dx
                        params.y = initialY + dy
                        windowManager?.updateViewLayout(container, params)
                    }
                    isDragging
                }
                MotionEvent.ACTION_UP -> {
                    isDragging
                }
                else -> false
            }
        }

        containerView = container
        try {
            windowManager?.addView(container, params)
        } catch (e: Exception) {
            containerView = null
        }
    }

    private fun hideBubble() {
        containerView?.let { view ->
            runCatching { windowManager?.removeView(view) }
        }
        containerView = null
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
            NotificationChannel(CHANNEL_ID, "Aurora Flutuante", NotificationManager.IMPORTANCE_LOW).apply {
                description = "Bolha da Aurora ativa sobre outros apps."
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
            .setContentTitle("Aurora está ativa")
            .setContentText("Toque na bolha para abrir.")
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setContentIntent(pending)
            .addAction(android.R.drawable.ic_menu_close_clear_cancel, "Fechar", stopPending)
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
    }
}

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
        Box(
            Modifier.size(80.dp).scale(halo).alpha(haloAlpha)
                .border(1.dp, auraColor, CircleShape)
        )
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
            Box(
                Modifier.size(72.dp).background(
                    Brush.radialGradient(
                        listOf(Color.White.copy(0.68f), Color.White.copy(0.08f), Color.Transparent),
                        radius = 110f,
                    ),
                    CircleShape,
                )
            )
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
        Box(
            Modifier.size(22.dp).align(Alignment.TopEnd)
                .clip(CircleShape)
                .background(Color(0xFFEAE3F5))
                .clickable(onClick = onDismiss),
            contentAlignment = Alignment.Center,
        ) {
            Text("×", color = pearl, fontSize = 12.sp)
        }
    }
}
