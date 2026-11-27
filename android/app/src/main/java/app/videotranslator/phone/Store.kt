package app.videotranslator.phone

import android.content.Context
import android.graphics.Bitmap
import android.net.Uri
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.update
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/** The five steps a video goes through, in order. */
enum class Stage(val title: String, val doing: String) {
    Send("Send to PC", "Sending the video to your PC"),
    Recognise("Recognise", "Finding the dialogue"),
    Translate("Translate", "Translating the lines"),
    Export("Export", "Drawing subtitles on the video"),
    Download("Download", "Bringing the video back to your phone"),
}

data class Picked(val uri: Uri, val name: String, val size: Long, val thumb: Bitmap? = null)

/** What the phone asks the PC to do with the video. A blank model means the PC's usual one. */
data class Choice(val mode: String = "speech", val source: String = "auto", val target: String = "ar", val model: String = "")

/** The languages (name to code) and translation models the PC offers. */
data class Options(val languages: List<Pair<String, String>>, val models: List<String> = emptyList(), val model: String = "") {
    companion object {
        /** Used until the PC answers, and with an older PC app that cannot list its own. */
        val Default = Options(listOf("Auto" to "auto", "English" to "en", "Arabic" to "ar", "Chinese" to "zh", "Chinese (Simplified)" to "zh-cn", "Chinese (Traditional)" to "zh-tw", "Japanese" to "ja", "Korean" to "ko",
            "French" to "fr", "Spanish" to "es", "German" to "de", "Italian" to "it", "Portuguese" to "pt", "Russian" to "ru", "Turkish" to "tr",
            "Hindi" to "hi", "Persian" to "fa", "Urdu" to "ur", "Indonesian" to "id"))
    }
}

/** A newer build of this app that GitHub has ready to download. */
data class Update(val build: Int, val url: String)

/**
 * Asks GitHub for the newest published build. Null when there is none newer than [mine], or there is no internet.
 * One anonymous request; nothing about the user or their videos is sent. Blocking: run it off the main thread.
 */
fun newerBuild(mine: Long): Update? = try {
    val c = URL("https://api.github.com/repos/M7MDSH1/video-translator/releases/tags/android-latest").openConnection() as HttpURLConnection
    c.connectTimeout = 6000
    c.readTimeout = 8000
    c.setRequestProperty("User-Agent", "video-translator")
    val json = try { if (c.responseCode == 200) JSONObject(c.inputStream.bufferedReader().use { it.readText() }) else null } finally { c.disconnect() }
    // The release is titled with its build number; its one file is the APK.
    val build = json?.optString("name")?.let { Regex("\\d+").find(it)?.value?.toIntOrNull() }
    val url = json?.optJSONArray("assets")?.optJSONObject(0)?.optString("browser_download_url")
    if (build != null && build > mine && url != null && url.startsWith("https://github.com/")) Update(build, url) else null
} catch (e: Exception) {
    null
}

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
    val update: Update? = null,
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

    /** The build the user answered Later to, so the popup asks once per build. */
    var skippedBuild: Int
        get() = prefs.getInt("skippedBuild", 0)
        set(value) = prefs.edit().putInt("skippedBuild", value).apply()
    var target: String
        get() = prefs.getString("target", "ar") ?: "ar"
        set(value) = prefs.edit().putString("target", value).apply()
    var model: String
        get() = prefs.getString("model", "") ?: ""
        set(value) = prefs.edit().putString("model", value).apply()

    fun api() = Api(host, token)

    fun paired(host: String, token: String, name: String) {
        prefs.edit().putString("host", host).putString("token", token).putString("name", name).apply()
        state.update { it.copy(phase = Phase.Home, pcName = name, error = null) }
    }

    fun forget() {
        prefs.edit().clear().apply()
        state.value = UiState(update = state.value.update)
    }
}
