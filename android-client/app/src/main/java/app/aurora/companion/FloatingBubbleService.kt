package app.aurora.companion

import android.app.Service
import android.content.Context
import android.content.Intent
import android.graphics.PixelFormat
import android.os.Build
import android.os.IBinder
import android.provider.Settings
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import kotlin.math.hypot

/**
 * Serviço responsável por gerenciar a bolha flutuante da Aurora sobre outros apps.
 *
 * Inclui:
 *  - Bolha fluida com Canvas nativo (sem botão na lateral)
 *  - Zona de descarte "X" no centro inferior da tela (estilo Messenger)
 *  - Feedback visual de descarte (hover/snap vermelho)
 *  - Snap suave para a lateral da tela ao soltar fora do "X"
 */
class FloatingBubbleService : Service() {

    private var windowManager: WindowManager? = null
    private var bubbleView: AuroraBubbleView? = null
    private var dismissTargetView: BubbleDismissTargetView? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        windowManager = getSystemService(Context.WINDOW_SERVICE) as? WindowManager
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_SHOW -> {
                showBubble()
            }
            ACTION_HIDE -> {
                hideBubble()
                stopSelf(startId)
            }
        }
        return START_NOT_STICKY
    }

    private fun showBubble() {
        if (bubbleView != null) return

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && !Settings.canDrawOverlays(this)) {
            return
        }

        val wm = windowManager ?: return
        val displayMetrics = resources.displayMetrics
        val density = displayMetrics.density
        val bubbleSizePx = (80 * density).toInt()
        val targetSizePx = (72 * density).toInt()

        val layoutType = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
        } else {
            @Suppress("DEPRECATION")
            WindowManager.LayoutParams.TYPE_PHONE
        }

        // Layout Params da Bolha
        val bubbleParams = WindowManager.LayoutParams(
            bubbleSizePx, bubbleSizePx,
            layoutType,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                    WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN or
                    WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            x = (displayMetrics.widthPixels - bubbleSizePx - (16 * density).toInt()).coerceAtLeast(0)
            y = (displayMetrics.heightPixels / 3)
        }

        // Layout Params do Alvo de Descarte ("X" no centro inferior)
        val targetParams = WindowManager.LayoutParams(
            targetSizePx, targetSizePx,
            layoutType,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                    WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE or
                    WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL
            y = (56 * density).toInt()
        }

        val target = BubbleDismissTargetView(this).apply {
            visibility = View.GONE
        }

        val bubble = AuroraBubbleView(
            context = this,
            windowManager = wm,
            layoutParams = bubbleParams,
            onBubbleClick = {
                // Traz o app Aurora para frente
                val launchIntent = packageManager.getLaunchIntentForPackage(packageName)?.apply {
                    action = Intent.ACTION_MAIN
                    addCategory(Intent.CATEGORY_LAUNCHER)
                    addFlags(
                        Intent.FLAG_ACTIVITY_NEW_TASK or
                        Intent.FLAG_ACTIVITY_RESET_TASK_IF_NEEDED or
                        Intent.FLAG_ACTIVITY_REORDER_TO_FRONT
                    )
                }
                launchIntent?.let { startActivity(it) }
            },
            onDragStart = {
                target.visibility = View.VISIBLE
            },
            onDragMove = { rawX, rawY ->
                val displayWidth = resources.displayMetrics.widthPixels
                val displayHeight = resources.displayMetrics.heightPixels
                val targetCenterX = displayWidth / 2f
                val targetCenterY = displayHeight - (56 * density) - (targetSizePx / 2f)

                val dist = hypot((rawX - targetCenterX).toDouble(), (rawY - targetCenterY).toDouble()).toFloat()
                val isHovering = dist < (85 * density)
                target.setTargetHovered(isHovering)
                isHovering
            },
            onDragEnd = { isDroppedOnTarget ->
                target.visibility = View.GONE
                target.setTargetHovered(false)
                if (isDroppedOnTarget) {
                    sendBroadcast(Intent(ACTION_BUBBLE_DISMISSED).setPackage(packageName))
                    hideBubble()
                    stopSelf()
                }
            }
        )

        try {
            wm.addView(target, targetParams)
            wm.addView(bubble, bubbleParams)
            dismissTargetView = target
            bubbleView = bubble
        } catch (_: Exception) {
            hideBubble()
        }
    }

    private fun hideBubble() {
        val wm = windowManager
        bubbleView?.let { view ->
            runCatching { wm?.removeView(view) }
        }
        dismissTargetView?.let { view ->
            runCatching { wm?.removeView(view) }
        }
        bubbleView = null
        dismissTargetView = null
    }

    override fun onDestroy() {
        hideBubble()
        super.onDestroy()
    }

    companion object {
        const val ACTION_SHOW = "app.aurora.companion.BUBBLE_SHOW"
        const val ACTION_HIDE = "app.aurora.companion.BUBBLE_HIDE"
        const val ACTION_BUBBLE_DISMISSED = "app.aurora.companion.BUBBLE_DISMISSED"
    }
}
