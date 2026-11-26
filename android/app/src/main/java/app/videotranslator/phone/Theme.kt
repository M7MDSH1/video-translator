package app.videotranslator.phone

import android.provider.Settings
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.CubicBezierEasing
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.composed
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay

// The desktop app's palette: one dark theme, one accent.
object Ink {
    val Background = Color(0xFF0F151D)
    val Surface = Color(0xFF1D2632)
    val Sunken = Color(0xFF121923)
    val Line = Color(0xFF354153)
    val Teal = Color(0xFF57D6B5)
    val TealDeep = Color(0xFF234D49)
    val Text = Color(0xFFE8EEF4)
    val Muted = Color(0xFF9AA8B8)
    val Faint = Color(0xFF74839A)  // steps not reached yet and field hints: quieter, still readable
    val Danger = Color(0xFFFF9B8F)
}

// One radius rule: buttons are pills, cards 24, fields and small tiles 16.
val CardShape = RoundedCornerShape(24.dp)
val FieldShape = RoundedCornerShape(16.dp)
val PillShape = RoundedCornerShape(percent = 50)

val Almarai = FontFamily(
    Font(R.font.almarai_regular, FontWeight.Normal),
    Font(R.font.almarai_bold, FontWeight.Bold),
    Font(R.font.almarai_extrabold, FontWeight.ExtraBold),
)

val EaseOut = CubicBezierEasing(0.16f, 1f, 0.3f, 1f)

/** True when the user turned animations off in the phone's settings. Everything then appears in its final state. */
val LocalReducedMotion = staticCompositionLocalOf { false }

@Composable
fun AppTheme(content: @Composable () -> Unit) {
    val context = LocalContext.current
    val reduced = remember { Settings.Global.getFloat(context.contentResolver, Settings.Global.ANIMATOR_DURATION_SCALE, 1f) == 0f }
    val base = Typography()
    fun TextStyle.app(weight: FontWeight = FontWeight.Normal) = copy(fontFamily = Almarai, fontWeight = weight)
    val type = Typography(
        displaySmall = base.displaySmall.app(FontWeight.ExtraBold).copy(fontSize = 44.sp, lineHeight = 48.sp, letterSpacing = (-1).sp),
        headlineMedium = base.headlineMedium.app(FontWeight.ExtraBold).copy(fontSize = 28.sp, lineHeight = 34.sp, letterSpacing = (-0.4).sp),
        titleMedium = base.titleMedium.app(FontWeight.Bold).copy(fontSize = 17.sp, lineHeight = 24.sp),
        bodyLarge = base.bodyLarge.app().copy(fontSize = 16.sp, lineHeight = 24.sp),
        bodyMedium = base.bodyMedium.app().copy(fontSize = 14.sp, lineHeight = 21.sp),
        labelLarge = base.labelLarge.app(FontWeight.Bold).copy(fontSize = 16.sp),
        labelMedium = base.labelMedium.app(FontWeight.Bold).copy(fontSize = 13.sp, lineHeight = 18.sp),
    )
    val colors = darkColorScheme(
        primary = Ink.Teal, onPrimary = Ink.Sunken, background = Ink.Background, onBackground = Ink.Text,
        surface = Ink.Surface, onSurface = Ink.Text, onSurfaceVariant = Ink.Muted, outline = Ink.Line, error = Ink.Danger,
    )
    androidx.compose.runtime.CompositionLocalProvider(LocalReducedMotion provides reduced) {
        MaterialTheme(colorScheme = colors, typography = type, content = content)
    }
}

/** Press feedback: the element sinks slightly under the finger and springs back. */
fun Modifier.pressable(enabled: Boolean = true, onClick: () -> Unit): Modifier = composed {
    val source = remember { MutableInteractionSource() }
    val pressed by source.collectIsPressedAsState()
    val reduced = LocalReducedMotion.current
    val scale by animateFloatAsState(
        if (pressed && enabled && !reduced) 0.965f else 1f,
        spring(dampingRatio = Spring.DampingRatioMediumBouncy, stiffness = Spring.StiffnessMedium), label = "press",
    )
    graphicsLayer { scaleX = scale; scaleY = scale }.clickable(source, indication = null, enabled = enabled, onClick = onClick)
}

/** Entrance: fade in while rising a short way. [index] staggers siblings so the eye is led from top to bottom. */
fun Modifier.rise(index: Int = 0): Modifier = composed {
    val reduced = LocalReducedMotion.current
    val progress = remember { Animatable(if (reduced) 1f else 0f) }
    val offset = with(LocalDensity.current) { 22.dp.toPx() }
    LaunchedEffect(Unit) {
        if (!reduced) {
            delay(index * 70L)
            progress.animateTo(1f, tween(520, easing = EaseOut))
        }
    }
    graphicsLayer { alpha = progress.value; translationY = (1f - progress.value) * offset }
}
