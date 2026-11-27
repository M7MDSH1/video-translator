package app.videotranslator.phone

import android.content.Intent
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.animation.shrinkVertically
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.ArrowDropDown
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.IOException

private val ScreenPadding = Modifier.fillMaxSize().padding(horizontal = 24.dp)

// ---------------------------------------------------------------- Connect

@Composable
fun ConnectScreen() {
    val scope = rememberCoroutineScope()
    val focus = LocalFocusManager.current
    var host by rememberSaveable { mutableStateOf(Store.host) }
    var code by rememberSaveable { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val shake = remember { Animatable(0f) }
    val reduced = LocalReducedMotion.current
    val codeFocus = remember { FocusRequester() }

    fun connect() {
        if (busy) return
        val address = host.trim().removePrefix("http://").trimEnd('/').let { if (':' in it) it else "$it:8756" }
        busy = true; error = null; focus.clearFocus()
        scope.launch {
            val result = withContext(Dispatchers.IO) {
                try {
                    val reply = Api(address).pair(code)
                    Result.success(reply.getString("token") to reply.optString("name", "Your PC"))
                } catch (e: ApiException) { Result.failure(e)
                } catch (e: IOException) { Result.failure(ApiException("Could not reach the PC. Check the address, that phone mode is open on the PC, and that both are on the same Wi-Fi."))
                } catch (e: Exception) { Result.failure(ApiException("That address does not look right. It should look like 192.168.1.20:8756.")) }
            }
            busy = false
            result.onSuccess { (token, name) -> Store.paired(address, token, name) }
            result.onFailure {
                error = it.message
                if (!reduced) { // a short sideways shake says "no" before the words are read
                    for (x in listOf(-14f, 12f, -8f, 5f, 0f)) shake.animateTo(x, tween(55))
                }
            }
        }
    }

    Column(ScreenPadding.verticalScroll(rememberScrollState()).padding(top = 40.dp, bottom = 24.dp)) {
        Image(painterResource(R.drawable.logo), null, Modifier.size(64.dp).rise(0))
        Spacer(Modifier.height(20.dp))
        Text("Connect to\nyour PC", style = MaterialTheme.typography.displaySmall, color = Ink.Text, modifier = Modifier.rise(1))
        Spacer(Modifier.height(12.dp))
        Text("On the PC, open Video Translator and choose Translate from your phone. It shows an address and a code.",
            style = MaterialTheme.typography.bodyLarge, color = Ink.Muted, modifier = Modifier.rise(2))
        Spacer(Modifier.height(32.dp))

        Column(Modifier.rise(3)) {
            Text("PC address", style = MaterialTheme.typography.labelMedium, color = Ink.Muted)
            Spacer(Modifier.height(8.dp))
            BasicTextField(
                host, { host = it.take(40) }, singleLine = true,
                textStyle = MaterialTheme.typography.titleMedium.copy(color = Ink.Text), cursorBrush = SolidColor(Ink.Teal),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri, imeAction = ImeAction.Next),
                keyboardActions = KeyboardActions(onNext = { codeFocus.requestFocus() }),
                modifier = Modifier.fillMaxWidth(),
                decorationBox = { inner ->
                    Box(Modifier.fillMaxWidth().clip(FieldShape).background(Ink.Sunken).border(1.5.dp, Ink.Line, FieldShape).padding(horizontal = 18.dp, vertical = 18.dp)) {
                        if (host.isEmpty()) Text("192.168.1.20:8756", style = MaterialTheme.typography.titleMedium, color = Ink.Faint)
                        inner()
                    }
                },
            )
        }
        Spacer(Modifier.height(22.dp))

        Column(Modifier.rise(4)) {
            Text("Code", style = MaterialTheme.typography.labelMedium, color = Ink.Muted)
            Spacer(Modifier.height(8.dp))
            BasicTextField(
                code, { new -> code = new.filter(Char::isDigit).take(6); error = null }, singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword, imeAction = ImeAction.Done),
                keyboardActions = KeyboardActions(onDone = { if (code.length == 6) connect() }),
                modifier = Modifier.fillMaxWidth().focusRequester(codeFocus).graphicsLayer { translationX = shake.value * density },
                decorationBox = { inner ->
                    Box {
                        Box(Modifier.size(1.dp).graphicsLayer { alpha = 0f }) { inner() }
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            repeat(6) { i -> CodeCell(code.getOrNull(i), next = i == code.length, wrong = error != null, modifier = Modifier.weight(1f)) }
                        }
                    }
                },
            )
            AnimatedVisibility(error != null, enter = fadeIn() + expandVertically(), exit = fadeOut() + shrinkVertically()) {
                Text(error ?: "", style = MaterialTheme.typography.bodyMedium, color = Ink.Danger, modifier = Modifier.padding(top = 12.dp))
            }
        }
        Spacer(Modifier.height(32.dp))
        PrimaryButton("Connect", Modifier.rise(5), enabled = host.isNotBlank() && code.length == 6, busy = busy) { connect() }
    }
}

@Composable
private fun CodeCell(digit: Char?, next: Boolean, wrong: Boolean, modifier: Modifier) {
    val reduced = LocalReducedMotion.current
    val line by animateColorAsState(if (wrong) Ink.Danger else if (next || digit != null) Ink.Teal else Ink.Line, tween(200), label = "line")
    // Each digit pops as it lands, so typing the code feels like filling slots.
    val pop by animateFloatAsState(if (digit != null || reduced) 1f else 0.4f, spring(Spring.DampingRatioMediumBouncy, Spring.StiffnessMedium), label = "pop")
    Box(modifier.height(60.dp).clip(FieldShape).background(Ink.Sunken).border(1.5.dp, line, FieldShape), contentAlignment = Alignment.Center) {
        if (digit != null) Text(digit.toString(), style = MaterialTheme.typography.headlineMedium, color = Ink.Text,
            modifier = Modifier.graphicsLayer { scaleX = pop; scaleY = pop })
    }
}

// ---------------------------------------------------------------- Update

// shortcut: the browser downloads the APK and the user opens it; install inside the app (FileProvider + install permission) if that proves clumsy.
fun openUpdate(context: android.content.Context, update: Update) {
    runCatching { context.startActivity(Intent(Intent.ACTION_VIEW, android.net.Uri.parse(update.url))) }
}

/** Asks once per new build: Update or Later. After Later, the Update button on the home screen is still there. */
@Composable
fun UpdatePopup(update: Update) {
    val context = LocalContext.current
    var answered by rememberSaveable { mutableStateOf(Store.skippedBuild) }
    if (answered >= update.build) return
    fun close() { Store.skippedBuild = update.build; answered = update.build }
    AlertDialog(
        onDismissRequest = ::close, containerColor = Ink.Surface, titleContentColor = Ink.Text, textContentColor = Ink.Muted,
        title = { Text("Update available", style = MaterialTheme.typography.titleMedium) },
        text = { Text("A newer version of this app is ready. It downloads in your browser; open the file when it finishes to install it.", style = MaterialTheme.typography.bodyMedium) },
        confirmButton = { TextButton(onClick = { close(); openUpdate(context, update) }) { Text("Update", color = Ink.Teal, style = MaterialTheme.typography.titleMedium) } },
        dismissButton = { TextButton(onClick = ::close) { Text("Later", color = Ink.Muted, style = MaterialTheme.typography.titleMedium) } },
    )
}

// ---------------------------------------------------------------- Home

@Composable
fun HomeScreen(state: UiState, onPick: () -> Unit, onStart: (Choice) -> Unit) {
    var mode by rememberSaveable { mutableStateOf("speech") }
    // The video's language starts on Auto each time: a leftover choice would misread the next video.
    var source by rememberSaveable { mutableStateOf("auto") }
    var target by rememberSaveable { mutableStateOf(Store.target) }
    var picked by rememberSaveable { mutableStateOf(Store.model) }
    val options by produceState(Options.Default) { value = withContext(Dispatchers.IO) { runCatching { Store.api().options() }.getOrDefault(Options.Default) } }
    // A model saved earlier may have been removed from the PC since.
    val needsLanguage = mode == "ocr" && source == "auto"
    val model = picked.takeIf { it in options.models } ?: options.model.takeIf { it in options.models } ?: options.models.firstOrNull() ?: ""
    Column(ScreenPadding.verticalScroll(rememberScrollState()).padding(top = 20.dp, bottom = 24.dp)) {
        Row(Modifier.fillMaxWidth().rise(0), verticalAlignment = Alignment.CenterVertically) {
            Image(painterResource(R.drawable.logo), null, Modifier.size(36.dp))
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text("Connected to", style = MaterialTheme.typography.labelMedium, color = Ink.Muted)
                Text(state.pcName.ifBlank { "Your PC" }, style = MaterialTheme.typography.titleMedium, color = Ink.Text, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            state.update?.let { update ->
                val context = LocalContext.current
                Text("Update", style = MaterialTheme.typography.labelMedium, color = Ink.Sunken,
                    modifier = Modifier.pressable { openUpdate(context, update) }.clip(PillShape).background(Ink.Teal).padding(horizontal = 14.dp, vertical = 10.dp))
            }
            Text("Change PC", style = MaterialTheme.typography.labelMedium, color = Ink.Teal,
                modifier = Modifier.clip(PillShape).pressable { Store.forget() }.padding(horizontal = 12.dp, vertical = 10.dp))
        }
        Spacer(Modifier.height(28.dp))
        Text("Translate\na video", style = MaterialTheme.typography.displaySmall, color = Ink.Text, modifier = Modifier.rise(1))
        Spacer(Modifier.height(20.dp))

        AnimatedVisibility(state.error != null, enter = fadeIn() + expandVertically(), exit = fadeOut() + shrinkVertically()) {
            Column(Modifier.padding(bottom = 16.dp).fillMaxWidth().clip(FieldShape).background(Ink.Danger.copy(alpha = 0.12f)).padding(16.dp)) {
                Text("It did not finish", style = MaterialTheme.typography.titleMedium, color = Ink.Danger)
                Text(state.error ?: "", style = MaterialTheme.typography.bodyMedium, color = Ink.Text, modifier = Modifier.padding(top = 4.dp))
            }
        }

        // The pick area and the chosen video are the same card: the video takes the empty card's place.
        Box(Modifier.rise(2)) {
            AnimatedContent(state.picked, transitionSpec = { (fadeIn(tween(300)) + scaleIn(tween(380, easing = EaseOut), initialScale = 0.94f)) togetherWith fadeOut(tween(150)) },
                contentKey = { it?.uri }, label = "pick") { picked ->
                if (picked == null) EmptyPick(onPick) else PickedCard(picked, onPick)
            }
        }
        Spacer(Modifier.height(24.dp))

        Column(Modifier.rise(3)) {
            Text("Where is the dialogue?", style = MaterialTheme.typography.titleMedium, color = Ink.Text)
            Spacer(Modifier.height(12.dp))
            ModeRow("Spoken", "People talk, and there are no subtitles on screen.", mode == "speech") { mode = "speech" }
            Spacer(Modifier.height(10.dp))
            ModeRow("On screen", "The video already shows subtitles in another language.", mode == "ocr") { mode = "ocr" }
        }
        Spacer(Modifier.height(24.dp))

        Column(Modifier.rise(4)) {
            Text("Languages", style = MaterialTheme.typography.titleMedium, color = Ink.Text)
            Spacer(Modifier.height(12.dp))
            // Speech can be recognised without knowing the language; text on screen cannot, so there it has to be picked.
            if (mode == "ocr") ChoiceRow("Subtitle language", if (needsLanguage) "Choose" else source, options.languages.filter { it.second != "auto" }) { source = it }
            else ChoiceRow("Video language", source, options.languages) { source = it }
            AnimatedVisibility(needsLanguage, enter = fadeIn() + expandVertically(), exit = fadeOut() + shrinkVertically()) {
                Text("Pick the language of the subtitles shown in the video.", style = MaterialTheme.typography.bodyMedium, color = Ink.Teal,
                    modifier = Modifier.padding(top = 8.dp, start = 4.dp))
            }
            Spacer(Modifier.height(10.dp))
            ChoiceRow("Translate to", target, options.languages.filter { it.second != "auto" }) { target = it }
            if (options.models.isNotEmpty()) {
                Spacer(Modifier.height(10.dp))
                ChoiceRow("Translation model", model, options.models.map { it to it }) { picked = it }
            }
        }
        Spacer(Modifier.height(28.dp))
        PrimaryButton("Translate", Modifier.rise(5), enabled = state.picked != null && !needsLanguage) { onStart(Choice(mode, source, target, model)) }
        Text("Your PC must stay on with phone mode open.", style = MaterialTheme.typography.bodyMedium, color = Ink.Muted,
            textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth().padding(top = 14.dp).rise(6))
    }
}

@Composable
private fun EmptyPick(onPick: () -> Unit) {
    Column(
        Modifier.fillMaxWidth().aspectRatio(16f / 10f).pressable(onClick = onPick).clip(CardShape).background(Ink.Surface).border(1.5.dp, Ink.Line, CardShape),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center,
    ) {
        Box(Modifier.size(56.dp).clip(PillShape).background(Ink.Teal), contentAlignment = Alignment.Center) {
            Icon(Icons.Filled.Add, null, tint = Ink.Sunken, modifier = Modifier.size(30.dp))
        }
        Spacer(Modifier.height(14.dp))
        Text("Choose a video", style = MaterialTheme.typography.titleMedium, color = Ink.Text)
        Text("or share one from your gallery", style = MaterialTheme.typography.bodyMedium, color = Ink.Muted)
    }
}

@Composable
private fun PickedCard(picked: Picked, onPick: () -> Unit) {
    Box(Modifier.fillMaxWidth().aspectRatio(16f / 10f).clip(CardShape).background(Ink.Sunken)) {
        // The frame fades in when it has been read from the video; until then the card shows its plain surface.
        AnimatedContent(picked.thumb, transitionSpec = { fadeIn(tween(350)) togetherWith fadeOut(tween(100)) }, label = "thumb") { thumb ->
            if (thumb != null) Image(thumb.asImageBitmap(), null, Modifier.fillMaxSize(), contentScale = ContentScale.Crop)
            else Box(Modifier.fillMaxSize().background(Ink.Surface))
        }
        Box(Modifier.fillMaxSize().background(Brush.verticalGradient(0.45f to Color.Transparent, 1f to Ink.Background.copy(alpha = 0.92f))))
        Row(Modifier.align(Alignment.BottomStart).fillMaxWidth().padding(18.dp), verticalAlignment = Alignment.Bottom) {
            Column(Modifier.weight(1f)) {
                Text(picked.name, style = MaterialTheme.typography.titleMedium, color = Ink.Text, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(readableSize(picked.size), style = MaterialTheme.typography.bodyMedium, color = Ink.Muted)
            }
            Text("Change", style = MaterialTheme.typography.labelMedium, color = Ink.Sunken,
                modifier = Modifier.pressable(onClick = onPick).clip(PillShape).background(Ink.Text).padding(horizontal = 16.dp, vertical = 10.dp))
        }
    }
}

/** One setting on a row; tapping it opens the list of [options] (name to value). */
@Composable
private fun ChoiceRow(label: String, value: String, options: List<Pair<String, String>>, onChoose: (String) -> Unit) {
    var open by remember { mutableStateOf(false) }
    Box {
        Row(Modifier.fillMaxWidth().pressable { open = true }.clip(FieldShape).background(Ink.Surface).border(1.5.dp, Ink.Line, FieldShape)
            .padding(start = 16.dp, end = 8.dp, top = 16.dp, bottom = 16.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(label, style = MaterialTheme.typography.bodyMedium, color = Ink.Muted)
            Spacer(Modifier.width(12.dp))
            Text(options.firstOrNull { it.second == value }?.first ?: value, style = MaterialTheme.typography.titleMedium, color = Ink.Text,
                maxLines = 1, overflow = TextOverflow.Ellipsis, textAlign = TextAlign.End, modifier = Modifier.weight(1f))
            Icon(Icons.Filled.ArrowDropDown, null, tint = Ink.Muted)
        }
        DropdownMenu(open, { open = false }, containerColor = Ink.Surface) {
            options.forEach { (name, code) ->
                DropdownMenuItem(text = { Text(name, style = MaterialTheme.typography.titleMedium, color = if (code == value) Ink.Teal else Ink.Text) },
                    onClick = { onChoose(code); open = false })
            }
        }
    }
}

@Composable
private fun ModeRow(title: String, text: String, selected: Boolean, onClick: () -> Unit) {
    val line by animateColorAsState(if (selected) Ink.Teal else Ink.Line, tween(220), label = "line")
    val fill by animateColorAsState(if (selected) Ink.TealDeep.copy(alpha = 0.45f) else Ink.Surface, tween(220), label = "fill")
    val tick by animateFloatAsState(if (selected) 1f else 0f, spring(Spring.DampingRatioMediumBouncy, Spring.StiffnessMedium), label = "tick")
    Row(Modifier.fillMaxWidth().pressable(onClick = onClick).clip(FieldShape).background(fill).border(1.5.dp, line, FieldShape).padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(title, style = MaterialTheme.typography.titleMedium, color = Ink.Text)
            Text(text, style = MaterialTheme.typography.bodyMedium, color = Ink.Muted)
        }
        Spacer(Modifier.width(12.dp))
        Box(Modifier.size(26.dp).clip(PillShape).border(1.5.dp, line, PillShape), contentAlignment = Alignment.Center) {
            Box(Modifier.size(26.dp).graphicsLayer { scaleX = tick; scaleY = tick }.clip(PillShape).background(Ink.Teal), contentAlignment = Alignment.Center) {
                Icon(Icons.Filled.Check, null, tint = Ink.Sunken, modifier = Modifier.size(16.dp))
            }
        }
    }
}

// ---------------------------------------------------------------- Working

@Composable
fun WorkingScreen(phase: Phase.Working, onCancel: () -> Unit) {
    val shown = rememberCounted(phase.progress)
    Column(ScreenPadding.verticalScroll(rememberScrollState()).padding(top = 28.dp, bottom = 24.dp)) {
        Text(phase.name, style = MaterialTheme.typography.labelMedium, color = Ink.Muted, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.rise(0))
        Spacer(Modifier.height(6.dp))
        // The headline changes with the step; the old line fades up and out as the new one arrives.
        AnimatedContent(phase.stage, transitionSpec = { fadeIn(tween(350)) togetherWith fadeOut(tween(150)) }, label = "doing", modifier = Modifier.rise(1)) { stage ->
            Text(stage.doing, style = MaterialTheme.typography.headlineMedium, color = Ink.Text)
        }
        Spacer(Modifier.height(20.dp))
        Column(Modifier.fillMaxWidth().rise(2).clip(CardShape).background(Ink.Surface).padding(horizontal = 20.dp, vertical = 18.dp)) {
            LinkPicture(phase.stage)
            Row(verticalAlignment = Alignment.Bottom) {
                Text("${(shown * 100).toInt()}", style = MaterialTheme.typography.displaySmall, color = Ink.Teal)
                Text("%", style = MaterialTheme.typography.titleMedium, color = Ink.Teal, modifier = Modifier.padding(start = 2.dp, bottom = 7.dp))
                Spacer(Modifier.weight(1f))
                Text("Step ${phase.stage.ordinal + 1} of ${Stage.entries.size}", style = MaterialTheme.typography.labelMedium, color = Ink.Muted, modifier = Modifier.padding(bottom = 8.dp))
            }
        }
        Spacer(Modifier.height(24.dp))
        Stage.entries.forEachIndexed { index, stage ->
            val done = stage.ordinal < phase.stage.ordinal
            val active = stage == phase.stage
            val ink by animateColorAsState(if (active) Ink.Text else if (done) Ink.Muted else Ink.Faint, tween(300), label = "ink")
            Row(Modifier.fillMaxWidth().rise(3 + index).padding(vertical = 9.dp), verticalAlignment = Alignment.CenterVertically) {
                StageBadge(done, active, phase.progress)
                Spacer(Modifier.width(16.dp))
                Text(stage.title, style = MaterialTheme.typography.titleMedium, color = ink)
            }
        }
        Spacer(Modifier.height(20.dp))
        Text("You can leave the app. A notification shows the progress.", style = MaterialTheme.typography.bodyMedium, color = Ink.Muted, modifier = Modifier.rise(8))
        Spacer(Modifier.height(20.dp))
        SecondaryButton("Cancel", Modifier.fillMaxWidth().rise(9), onCancel)
    }
}

// ---------------------------------------------------------------- Done

@Composable
fun DoneScreen(phase: Phase.Done, thumb: android.graphics.Bitmap?, onAgain: () -> Unit) {
    val context = LocalContext.current
    val reduced = LocalReducedMotion.current
    // The finished video lands with one spring: the single celebratory moment in the app.
    val land = remember { Animatable(if (reduced) 1f else 0.82f) }
    val badge = remember { Animatable(if (reduced) 1f else 0f) }
    LaunchedEffect(Unit) {
        if (!reduced) {
            launch { land.animateTo(1f, spring(Spring.DampingRatioMediumBouncy, Spring.StiffnessLow)) }
            kotlinx.coroutines.delay(220)
            badge.animateTo(1f, spring(Spring.DampingRatioMediumBouncy, Spring.StiffnessMedium))
        }
    }
    fun open(action: String) {
        val intent = if (action == Intent.ACTION_VIEW) Intent(action).setDataAndType(phase.uri, "video/mp4")
        else Intent(action).setType("video/mp4").putExtra(Intent.EXTRA_STREAM, phase.uri)
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        runCatching { context.startActivity(if (action == Intent.ACTION_SEND) Intent.createChooser(intent, null) else intent) }
    }
    Column(ScreenPadding.verticalScroll(rememberScrollState()).padding(top = 28.dp, bottom = 24.dp)) {
        Box(Modifier.fillMaxWidth().aspectRatio(16f / 10f).graphicsLayer { scaleX = land.value; scaleY = land.value; alpha = ((land.value - 0.82f) / 0.12f).coerceIn(0f, 1f) }
            .pressable { open(Intent.ACTION_VIEW) }.clip(CardShape).background(Ink.Surface), contentAlignment = Alignment.Center) {
            if (thumb != null) Image(thumb.asImageBitmap(), null, Modifier.fillMaxSize(), contentScale = ContentScale.Crop)
            Box(Modifier.fillMaxSize().background(Ink.Background.copy(alpha = 0.35f)))
            Box(Modifier.size(72.dp).graphicsLayer { scaleX = badge.value; scaleY = badge.value }.clip(PillShape).background(Ink.Teal), contentAlignment = Alignment.Center) {
                Icon(Icons.Filled.PlayArrow, "Play the translated video", tint = Ink.Sunken, modifier = Modifier.size(40.dp))
            }
        }
        Spacer(Modifier.height(28.dp))
        Text("Your video\nis ready", style = MaterialTheme.typography.displaySmall, color = Ink.Text, modifier = Modifier.rise(2))
        Spacer(Modifier.height(10.dp))
        Text("Saved in your gallery, in Movies, Video Translator.", style = MaterialTheme.typography.bodyLarge, color = Ink.Muted, modifier = Modifier.rise(3))
        Text(phase.name, style = MaterialTheme.typography.bodyMedium, color = Ink.Muted, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(top = 4.dp).rise(3))
        Spacer(Modifier.height(28.dp))
        PrimaryButton("Play", Modifier.rise(4)) { open(Intent.ACTION_VIEW) }
        Spacer(Modifier.height(12.dp))
        Row(Modifier.fillMaxWidth().rise(5), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            SecondaryButton("Share", Modifier.weight(1f)) { open(Intent.ACTION_SEND) }
            SecondaryButton("New video", Modifier.weight(1f), onAgain)
        }
    }
}

fun readableSize(bytes: Long): String = when {
    bytes >= 1L shl 30 -> String.format(java.util.Locale.US, "%.1f GB", bytes / (1L shl 30).toDouble())
    bytes >= 1L shl 20 -> String.format(java.util.Locale.US, "%.0f MB", bytes / (1L shl 20).toDouble())
    else -> String.format(java.util.Locale.US, "%.0f KB", bytes / 1024.0)
}
