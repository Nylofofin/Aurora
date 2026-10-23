package app.aurora.companion

import android.animation.ValueAnimator
import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.RadialGradient
import android.graphics.Shader
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.view.animation.AccelerateDecelerateInterpolator
import android.view.animation.DecelerateInterpolator
import kotlin.math.abs
import kotlin.math.min

/**
 * Bolha flutuante da Aurora em Canvas nativo puro.
 * Sem botões colados na lateral: manuseio limpo e livre.
 * Suporta toque para abrir, arrastar na tela com snap magnético para a borda,
 * e arrastar até o "X" na parte inferior para descartar.
 */
@SuppressLint("ViewConstructor")
class AuroraBubbleView(
    context: Context,
    private val windowManager: WindowManager,
    private val layoutParams: WindowManager.LayoutParams,
    private val onBubbleClick: () -> Unit,
    private val onDragStart: () -> Unit,
    private val onDragMove: (rawX: Float, rawY: Float) -> Boolean,
    private val onDragEnd: (isDroppedOnTarget: Boolean) -> Unit
) : View(context) {

    private val orbPaint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val haloPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 3f
    }
    private val highlightPaint = Paint(Paint.ANTI_ALIAS_FLAG)

    private var pulseScale = 1.0f
    private var haloAlpha = 0.25f
    private var pulseAnimator: ValueAnimator? = null
    private var snapAnimator: ValueAnimator? = null

    // Variáveis de drag
    private var initialX = 0
    private var initialY = 0
    private var initialTouchX = 0f
    private var initialTouchY = 0f
    private var isDragging = false
    private var isOverDismissTarget = false

    init {
        startPulseAnimation()
    }

    private fun startPulseAnimation() {
        pulseAnimator = ValueAnimator.ofFloat(0f, 1f).apply {
            duration = 2200
            repeatMode = ValueAnimator.REVERSE
            repeatCount = ValueAnimator.INFINITE
            interpolator = AccelerateDecelerateInterpolator()
            addUpdateListener { anim ->
                val fraction = anim.animatedValue as Float
                pulseScale = 0.95f + (fraction * 0.08f)
                haloAlpha = 0.12f + (fraction * 0.25f)
                invalidate()
            }
            start()
        }
    }

    override fun onDetachedFromWindow() {
        pulseAnimator?.cancel()
        snapAnimator?.cancel()
        pulseAnimator = null
        snapAnimator = null
        super.onDetachedFromWindow()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)

        val w = width.toFloat()
        val h = height.toFloat()
        if (w <= 0 || h <= 0) return

        val centerX = w / 2f
        val centerY = h / 2f
        val baseRadius = min(w, h) * 0.44f

        // 1. Halo externo pulsante
        haloPaint.color = Color.parseColor("#8A70C4")
        haloPaint.alpha = (haloAlpha * 255).toInt().coerceIn(0, 255)
        canvas.drawCircle(centerX, centerY, baseRadius * 1.12f * pulseScale, haloPaint)

        // 2. Esfera principal com gradiente de luz perolada suave
        val currentRadius = baseRadius * pulseScale
        val sphereShader = LinearGradient(
            centerX - currentRadius, centerY - currentRadius,
            centerX + currentRadius, centerY + currentRadius,
            intArrayOf(
                Color.parseColor("#FFFFFF"),
                Color.parseColor("#F0EAF8"),
                Color.parseColor("#D7C8EF"),
                Color.parseColor("#A9CFE4"),
                Color.parseColor("#8A70C4")
            ),
            floatArrayOf(0.0f, 0.25f, 0.55f, 0.80f, 1.0f),
            Shader.TileMode.CLAMP
        )
        orbPaint.shader = sphereShader
        canvas.drawCircle(centerX, centerY, currentRadius, orbPaint)

        // 3. Brilho radial interno (reflexo de pérola/vidro)
        val glowShader = RadialGradient(
            centerX - (currentRadius * 0.35f),
            centerY - (currentRadius * 0.35f),
            currentRadius * 0.85f,
            intArrayOf(Color.argb(190, 255, 255, 255), Color.argb(40, 255, 255, 255), Color.TRANSPARENT),
            floatArrayOf(0.0f, 0.5f, 1.0f),
            Shader.TileMode.CLAMP
        )
        highlightPaint.shader = glowShader
        canvas.drawCircle(centerX, centerY, currentRadius, highlightPaint)

        // 4. Reflexo elíptico superior suave
        highlightPaint.shader = null
        highlightPaint.color = Color.argb(160, 255, 255, 255)
        canvas.drawOval(
            centerX - (currentRadius * 0.55f),
            centerY - (currentRadius * 0.70f),
            centerX + (currentRadius * 0.25f),
            centerY - (currentRadius * 0.30f),
            highlightPaint
        )
    }

    @SuppressLint("ClickableViewAccessibility")
    override fun onTouchEvent(event: MotionEvent): Boolean {
        when (event.action) {
            MotionEvent.ACTION_DOWN -> {
                snapAnimator?.cancel()
                initialX = layoutParams.x
                initialY = layoutParams.y
                initialTouchX = event.rawX
                initialTouchY = event.rawY
                isDragging = false
                isOverDismissTarget = false
                return true
            }
            MotionEvent.ACTION_MOVE -> {
                val dx = (event.rawX - initialTouchX).toInt()
                val dy = (event.rawY - initialTouchY).toInt()
                if (!isDragging && (abs(dx) > 14 || abs(dy) > 14)) {
                    isDragging = true
                    onDragStart()
                }
                if (isDragging) {
                    layoutParams.x = initialX + dx
                    layoutParams.y = initialY + dy
                    try {
                        windowManager.updateViewLayout(this, layoutParams)
                    } catch (_: Exception) {}

                    isOverDismissTarget = onDragMove(event.rawX, event.rawY)
                }
                return true
            }
            MotionEvent.ACTION_UP -> {
                if (!isDragging) {
                    // Clique simples: traz a Aurora para a frente
                    onBubbleClick()
                } else {
                    onDragEnd(isOverDismissTarget)
                    if (!isOverDismissTarget) {
                        // Snap suave para a lateral mais próxima da tela
                        animateSnapToEdge()
                    }
                }
                isDragging = false
                return true
            }
        }
        return super.onTouchEvent(event)
    }

    /** Anima a bolha para encostar na borda esquerda ou direita mais próxima */
    private fun animateSnapToEdge() {
        val displayWidth = resources.displayMetrics.widthPixels
        val bubbleWidth = width.takeIf { it > 0 } ?: layoutParams.width
        val currentX = layoutParams.x

        val targetX = if (currentX + bubbleWidth / 2 < displayWidth / 2) {
            12 // Borda esquerda
        } else {
            displayWidth - bubbleWidth - 12 // Borda direita
        }

        snapAnimator?.cancel()
        snapAnimator = ValueAnimator.ofInt(currentX, targetX).apply {
            duration = 240
            interpolator = DecelerateInterpolator()
            addUpdateListener { anim ->
                layoutParams.x = anim.animatedValue as Int
                try {
                    windowManager.updateViewLayout(this@AuroraBubbleView, layoutParams)
                } catch (_: Exception) {}
            }
            start()
        }
    }
}
