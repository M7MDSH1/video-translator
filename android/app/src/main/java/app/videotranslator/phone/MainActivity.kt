package app.videotranslator.phone

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.media.MediaMetadataRetriever
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.OpenableColumns
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainActivity : ComponentActivity() {
    private val picker = registerForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri -> uri?.let(::picked) }
    private val askNotifications = registerForActivityResult(ActivityResultContracts.RequestPermission()) { }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        Store.init(this)
        if (savedInstanceState == null) shared(intent)
        lifecycleScope.launch {
            val mine = packageManager.getPackageInfo(packageName, 0).longVersionCode
            val update = withContext(Dispatchers.IO) { newerBuild(mine) }
            if (update != null) Store.state.update { it.copy(update = update) }
        }
        setContent {
            AppTheme {
                val state by Store.state.collectAsStateWithLifecycle()
                val reduced = LocalReducedMotion.current
                Box(Modifier.fillMaxSize().background(Ink.Background).safeDrawingPadding()) {
                    // Moving between screens: the new one rises into place while the old one fades. Progress updates
                    // inside the working screen do not count as a screen change.
                    AnimatedContent(
                        state.phase, contentKey = { it::class },
                        transitionSpec = {
                            if (reduced) fadeIn(tween(0)) togetherWith fadeOut(tween(0))
                            else (fadeIn(tween(320, delayMillis = 90)) + slideInVertically(tween(420, easing = EaseOut)) { it / 14 }) togetherWith fadeOut(tween(140))
                        }, label = "screen",
                    ) { phase ->
                        when (phase) {
                            Phase.Connect -> ConnectScreen()
                            Phase.Home -> HomeScreen(state, onPick = { picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.VideoOnly)) }, onStart = ::start)
                            is Phase.Working -> WorkingScreen(phase) { JobService.cancel(this@MainActivity) }
                            is Phase.Done -> DoneScreen(phase, state.picked?.thumb) { Store.state.update { it.copy(phase = Phase.Home, picked = null, error = null) } }
                        }
                    }
                    // Not while a video is in progress: the question can wait until it is done.
                    if (state.phase !is Phase.Working) state.update?.let { UpdatePopup(it) }
                }
            }
        }
    }

    override fun onStart() {
        super.onStart()
        resume()  // every return to the app: reattach if the PC is still working on our video
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        shared(intent)
    }

    /** A video shared from the gallery or another app. */
    private fun shared(intent: Intent?) {
        if (intent?.action != Intent.ACTION_SEND) return
        val uri = if (Build.VERSION.SDK_INT >= 33) intent.getParcelableExtra(Intent.EXTRA_STREAM, Uri::class.java)
        else @Suppress("DEPRECATION") intent.getParcelableExtra(Intent.EXTRA_STREAM)
        if (uri != null && Store.state.value.phase !is Phase.Working) picked(uri)
    }

    private fun picked(uri: Uri) {
        var name = "video.mp4"
        var size = -1L
        runCatching {
            contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE), null, null, null)?.use { c ->
                if (c.moveToFirst()) { name = c.getString(0) ?: name; size = if (c.isNull(1)) -1L else c.getLong(1) }
            }
        }
        if (size <= 0) size = runCatching { contentResolver.openAssetFileDescriptor(uri, "r")?.use { it.length } }.getOrNull() ?: -1L
        if (size <= 0) {  // no permission to read it, or the other app gave no size: refuse now instead of failing mid-upload
            Store.state.update { it.copy(picked = null, error = "This video could not be read. Choose it with Choose a video instead.") }
            return
        }
        Store.state.update { s -> s.copy(picked = Picked(uri, name, size), error = null, phase = if (s.phase is Phase.Done) Phase.Home else s.phase) }
        lifecycleScope.launch {
            val thumb = withContext(Dispatchers.IO) {
                runCatching {
                    val reader = MediaMetadataRetriever()
                    try { reader.setDataSource(this@MainActivity, uri); reader.getScaledFrameAtTime(1_000_000, MediaMetadataRetriever.OPTION_CLOSEST_SYNC, 960, 600) }
                    finally { reader.release() }
                }.getOrNull()
            }
            Store.state.update { s -> if (s.picked?.uri == uri) s.copy(picked = s.picked.copy(thumb = thumb as Bitmap?)) else s }
        }
    }

    private fun start(choice: Choice) {
        val picked = Store.state.value.picked ?: return
        Store.target = choice.target  // the next video most likely wants the same language and model
        Store.model = choice.model
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            askNotifications.launch(Manifest.permission.POST_NOTIFICATIONS)  // the transfer runs either way; this only shows its progress
        }
        Store.state.update { it.copy(phase = Phase.Working(Stage.Send, 0f, picked.name), error = null) }
        JobService.start(this, picked, choice)
    }

    /** After the app was closed mid-job: if the PC is still working or has a finished video we never saved, pick it up again. */
    private fun resume() {
        if (Store.token.isEmpty() || Store.state.value.phase != Phase.Home) return
        lifecycleScope.launch {
            val status = withContext(Dispatchers.IO) { runCatching { Store.api().status() }.getOrNull() } ?: return@launch
            val state = status.optString("state")
            if (Store.state.value.phase == Phase.Home && (state == "working" || (state == "done" && status.optString("id") != Store.savedJob))) {
                Store.state.update { it.copy(phase = Phase.Working(if (state == "done") Stage.Download else Stage.Recognise, 0f, status.optString("name"))) }
                JobService.start(this@MainActivity, null, Choice())
            }
        }
    }
}
