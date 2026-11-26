package app.videotranslator.phone

import android.content.Context
import android.graphics.Bitmap
import android.net.Uri
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.update

/** The five steps a video goes through, in order. */
enum class Stage(val title: String, val doing: String) {
    Send("Send to PC", "Sending the video to your PC"),
    Recognise("Recognise", "Finding the dialogue"),
    Translate("Translate", "Translating the lines"),
    Export("Export", "Drawing subtitles on the video"),
    Download("Download", "Bringing the video back to your phone"),
}

data class Picked(val uri: Uri, val name: String, val size: Long, val thumb: Bitmap? = null)

sealed interface Phase {
    data object Connect : Phase
    data object Home : Phase
    data class Working(val stage: Stage, val progress: Float, val name: String) : Phase
    data class Done(val uri: Uri, val name: String) : Phase
}

data class UiState(
    val phase: Phase = Phase.Connect,
    val pcName: String = "",
    val picked: Picked? = null,
    val error: String? = null,
)

/** App state shared by the screens and the transfer service, plus the saved pairing. */
object Store {
    val state = MutableStateFlow(UiState())
    private lateinit var prefs: android.content.SharedPreferences

    fun init(context: Context) {
        if (::prefs.isInitialized) return
        prefs = context.applicationContext.getSharedPreferences("pairing", Context.MODE_PRIVATE)
        if (token.isNotEmpty()) state.update { it.copy(phase = Phase.Home, pcName = prefs.getString("name", "") ?: "") }
    }

    val host: String get() = prefs.getString("host", "") ?: ""
    val token: String get() = prefs.getString("token", "") ?: ""
    var savedJob: String
        get() = prefs.getString("savedJob", "") ?: ""
        set(value) = prefs.edit().putString("savedJob", value).apply()

    fun api() = Api(host, token)

    fun paired(host: String, token: String, name: String) {
        prefs.edit().putString("host", host).putString("token", token).putString("name", name).apply()
        state.update { it.copy(phase = Phase.Home, pcName = name, error = null) }
    }

    fun forget() {
        prefs.edit().clear().apply()
        state.value = UiState()
    }
}
