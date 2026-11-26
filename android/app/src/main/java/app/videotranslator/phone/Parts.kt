package app.videotranslator.phone

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.unit.dp

/** The one primary action on a screen: a teal pill. While [busy] the label is replaced by three pulsing dots. */
@Composable
fun PrimaryButton(text: String, modifier: Modifier = Modifier, enabled: Boolean = true, busy: Boolean = false, onClick: () -> Unit) {
    val fill by animateColorAsState(if (enabled) Ink.Teal else Ink.Line, tween(250), label = "fill")
    val ink by animateColorAsState(if (enabled) Ink.Sunken else Ink.Muted, tween(250), label = "ink")
    Box(
        modifier.fillMaxWidth().height(58.dp).pressable(enabled && !busy, onClick).clip(PillShape).background(fill),
        contentAlignment = Alignment.Center,
    ) {
        AnimatedContent(busy, transitionSpec = { fadeIn(tween(180)) togetherWith fadeOut(tween(120)) }, label = "busy") { waiting ->
            if (waiting) Dots(ink) else Text(text, color = ink, style = MaterialTheme.typography.labelLarge)
        }
    }
}

/** A quiet secondary action: outlined pill. */
@Composable
fun SecondaryButton(text: String, modifier: Modifier = Modifier, onClick: () -> Unit) {
    Box(
        modifier.height(58.dp).pressable(onClick = onClick).clip(PillShape).border(1.5.dp, Ink.Line, PillShape).padding(horizontal = 24.dp),
        contentAlignment = Alignment.Center,
    ) { Text(text, color = Ink.Text, style = MaterialTheme.typography.labelLarge) }
}

@Composable
private fun Dots(color: Color) {
    val reduced = LocalReducedMotion.current
    val phase by rememberInfiniteTransition(label = "dots").animateFloat(0f, 3f, infiniteRepeatable(tween(900, easing = LinearEasing)), label = "phase")
    Row(verticalAlignment = Alignment.CenterVertically) {
        repeat(3) { i ->
            val lit = if (reduced) 1f else (1f - kotlin.math.abs(((phase - i + 3f) % 3f) - 0.5f)).coerceIn(0.3f, 1f)
            Box(Modifier.padding(horizontal = 4.dp).size(8.dp).graphicsLayer { alpha = lit }.clip(PillShape).background(color))
        }
    }
}

/**
 * One step's badge. Waiting: an empty ring. Active: the ring fills clockwise with the step's progress.
 * Finished: a solid teal disc whose tick springs in, so finishing a step is felt, not just read.
 */
@Composable
fun StageBadge(done: Boolean, active: Boolean, progress: Float, modifier: Modifier = Modifier) {
    val reduced = LocalReducedMotion.current
    val sweep by animateFloatAsState(if (done) 1f else if (active) progress else 0f, if (reduced) tween(0) else tween(500, easing = EaseOut), label = "sweep")
    val fill by animateFloatAsState(if (done) 1f else 0f, if (reduced) tween(0) else spring(Spring.DampingRatioMediumBouncy, Spring.StiffnessMediumLow), label = "fill")
    val spin by rememberInfiniteTransition(label = "spin").animateFloat(0f, 360f, infiniteRepeatable(tween(1400, easing = LinearEasing)), label = "angle")
    Box(modifier.size(34.dp), contentAlignment = Alignment.Center) {
        Canvas(Modifier.size(34.dp)) {
            val stroke = 3.dp.toPx()
            val inset = stroke / 2
            val arc = Size(size.width - stroke, size.height - stroke)
            drawArc(if (active || done) Ink.TealDeep else Ink.Line, 0f, 360f, false, Offset(inset, inset), arc, style = Stroke(stroke))
            if (active && sweep < 0.02f && !reduced) {
                // No number from the PC yet: a short arc circles so the step never looks frozen.
                drawArc(Ink.Teal, spin - 90f, 70f, false, Offset(inset, inset), arc, style = Stroke(stroke, cap = StrokeCap.Round))
            } else if (sweep > 0f) {
                drawArc(Ink.Teal, -90f, 360f * sweep, false, Offset(inset, inset), arc, style = Stroke(stroke, cap = StrokeCap.Round))
            }
            if (fill > 0f) drawCircle(Ink.Teal, radius = size.minDimension / 2 * fill.coerceAtMost(1.08f))
        }
        if (done) Icon(Icons.Filled.Check, null, tint = Ink.Sunken, modifier = Modifier.size(20.dp).graphicsLayer { scaleX = fill; scaleY = fill; alpha = fill.coerceIn(0f, 1f) })
    }
}

/**
 * Phone on the left, PC on the right. Dots travel toward the PC while sending and back while downloading;
 * in between the PC glows because that is where the work happens. It shows where the video is right now.
 */
@Composable
fun LinkPicture(stage: Stage, modifier: Modifier = Modifier) {
    val reduced = LocalReducedMotion.current
    val travel by rememberInfiniteTransition(label = "link").animateFloat(0f, 1f, infiniteRepeatable(tween(1500, easing = LinearEasing)), label = "travel")
    val glow by rememberInfiniteTransition(label = "glow").animateFloat(0.35f, 1f, infiniteRepeatable(tween(1100), RepeatMode.Reverse), label = "pulse")
    val moving = stage == Stage.Send || stage == Stage.Download
    val phoneLit by animateFloatAsState(if (moving) 1f else 0.4f, tween(400), label = "phone")
    Canvas(modifier.fillMaxWidth().height(96.dp)) {
        val stroke = 2.5.dp.toPx()
        val mid = size.height / 2
        // Phone
        val pw = 34.dp.toPx(); val ph = 62.dp.toPx(); val px = 8.dp.toPx()
        drawRoundRect(Ink.Teal.copy(alpha = phoneLit), Offset(px, mid - ph / 2), Size(pw, ph), CornerRadius(8.dp.toPx()), style = Stroke(stroke))
        drawLine(Ink.Teal.copy(alpha = phoneLit), Offset(px + pw / 2 - 5.dp.toPx(), mid + ph / 2 - 7.dp.toPx()), Offset(px + pw / 2 + 5.dp.toPx(), mid + ph / 2 - 7.dp.toPx()), stroke, StrokeCap.Round)
        // PC monitor
        val mw = 84.dp.toPx(); val mh = 54.dp.toPx(); val mx = size.width - mw - 8.dp.toPx(); val my = mid - mh / 2 - 6.dp.toPx()
        val pcLit = if (moving || reduced) 1f else glow
        if (!moving) drawRoundRect(Ink.Teal.copy(alpha = 0.16f * pcLit), Offset(mx, my), Size(mw, mh), CornerRadius(8.dp.toPx()))
        drawRoundRect(Ink.Teal.copy(alpha = pcLit), Offset(mx, my), Size(mw, mh), CornerRadius(8.dp.toPx()), style = Stroke(stroke))
        drawLine(Ink.Teal.copy(alpha = pcLit), Offset(mx + mw / 2 - 16.dp.toPx(), my + mh + 10.dp.toPx()), Offset(mx + mw / 2 + 16.dp.toPx(), my + mh + 10.dp.toPx()), stroke, StrokeCap.Round)
        drawLine(Ink.Teal.copy(alpha = pcLit), Offset(mx + mw / 2, my + mh), Offset(mx + mw / 2, my + mh + 10.dp.toPx()), stroke)
        // The path between them
        val from = px + pw + 14.dp.toPx(); val to = mx - 14.dp.toPx(); val count = 7
        for (i in 0 until count) {
            val base = i / count.toFloat()
            val t = if (!moving || reduced) base + 0.5f / count else ((base + travel / count * count) % 1f).let { if (stage == Stage.Download) 1f - it else it }
            // Dots fade in and out at the ends so they appear to leave one device and enter the other.
            val edge = if (moving && !reduced) (kotlin.math.min(t, 1f - t) * 5f).coerceIn(0f, 1f) else 0.35f
            drawCircle(Ink.Teal.copy(alpha = if (moving) edge else 0.25f), 3.2.dp.toPx(), Offset(from + (to - from) * t, mid - 6.dp.toPx()))
        }
    }
}

/** A number that counts toward its target instead of jumping, so progress reads as movement. */
@Composable
fun rememberCounted(target: Float): Float {
    val reduced = LocalReducedMotion.current
    val value = remember { Animatable(target) }
    LaunchedEffect(target) { if (reduced || target < value.value) value.snapTo(target) else value.animateTo(target, tween(600, easing = EaseOut)) }
    return value.value
}
