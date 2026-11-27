package app.videotranslator.phone

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.Uri
import android.os.IBinder
import android.provider.MediaStore
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.flow.update
import java.io.IOException

/**
 * Sends the video, waits for the PC, and downloads the result. It is a foreground service so the transfer
 * keeps going when the app is in the background or the screen is off.
 */
class JobService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var job: Job? = null
    private var lastNotified = -1
    @Volatile private var cancelled = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        Store.init(this)
        when (intent?.action) {
            CANCEL -> {
                cancelled = true
                job?.cancel()
                Store.state.update { it.copy(phase = Phase.Home, error = null) }
                // Tell the PC first, then stop: stopping at once would cancel this request too.
                scope.launch { runCatching { Store.api().cancel() }; finish() }
            }
            else -> {
                val uri = intent?.data
                val choice = Choice(intent?.getStringExtra("mode") ?: "speech", intent?.getStringExtra("source") ?: "auto",
                    intent?.getStringExtra("target") ?: "ar", intent?.getStringExtra("model") ?: "")
                val name = intent?.getStringExtra("name") ?: "video.mp4"
                val size = intent?.getLongExtra("size", -1L) ?: -1L
                cancelled = false
                startForeground(1, notification(Stage.Send.doing, 0), ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
                job?.cancel()
                job = scope.launch {
                    try {
                        run(uri, name, size, choice)
                    } catch (e: kotlinx.coroutines.CancellationException) {
                        throw e
                    } catch (e: Exception) {
                        if (cancelled) return@launch  // the user pressed Cancel: that is not a failure to report
                        val reason = when (e) {
                            is ApiException -> e.message ?: "The PC reported a problem."
                            is IOException -> "Lost the connection to your PC. Check that both are on the same Wi-Fi and phone mode is open on the PC."
                            else -> e.message ?: "Something went wrong."
                        }
                        Store.state.update { it.copy(phase = Phase.Home, error = reason) }
                    }
                    finish()
                }
            }
        }
        return START_NOT_STICKY
    }

    private fun finish() {
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    private fun show(stage: Stage, progress: Float, name: String) {
        if (cancelled) return
        Store.state.update { it.copy(phase = Phase.Working(stage, progress, name), error = null) }
        val percent = (progress * 100).toInt()
        val key = stage.ordinal * 1000 + percent
        if (key != lastNotified && !cancelled) {  // at most one notification update per percent
            lastNotified = key
            getSystemService(NotificationManager::class.java).notify(1, notification(stage.doing, percent))
        }
    }

    private suspend fun run(uri: Uri?, pickedName: String, size: Long, choice: Choice) {
        val api = Store.api()
        var name = pickedName
        if (uri != null) {
            if (size <= 0) throw ApiException("This video's size could not be read. Pick it from the gallery instead.")
            // Ask first: a PC that is busy answers in words here, but would just drop a video that is already streaming.
            if (api.status().optString("state") in listOf("receiving", "working")) throw ApiException("Your PC is already translating a video. Wait for it to finish, then send this one.")
            show(Stage.Send, 0f, name)
            val input = contentResolver.openInputStream(uri) ?: throw ApiException("This video could not be opened.")
            input.use { api.upload(name, choice, size, it, { !cancelled }) { sent -> show(Stage.Send, sent.toFloat() / size, name) } }
        }
        // Wait for the PC. A few missed checks are normal on Wi-Fi; a long silence is an error.
        var misses = 0
        var jobId = ""
        while (true) {
            val status = try { api.status().also { misses = 0 } } catch (e: IOException) { if (++misses > 45) throw e; null }
            if (status != null) {
                name = status.optString("name", name)
                jobId = status.optString("id")
                when (status.optString("state")) {
                    "done" -> break
                    "error" -> throw ApiException(status.optString("message", "The PC could not translate this video."))
                    "idle" -> throw ApiException("The PC has no video in progress. Send it again.")
                    else -> {
                        val stage = when (status.optString("stage")) {
                            "translate" -> Stage.Translate
                            "export" -> Stage.Export
                            "receive" -> Stage.Send
                            else -> Stage.Recognise
                        }
                        show(stage, (status.optDouble("progress", 0.0) / 100).toFloat().coerceIn(0f, 1f), name)
                    }
                }
            }
            delay(1000)
        }
        show(Stage.Download, 0f, name)
        val title = name.substringBeforeLast('.') + " - translated.mp4"
        val values = ContentValues().apply {
            put(MediaStore.Video.Media.DISPLAY_NAME, title)
            put(MediaStore.Video.Media.MIME_TYPE, "video/mp4")
            put(MediaStore.Video.Media.RELATIVE_PATH, "Movies/Video Translator")
            put(MediaStore.Video.Media.IS_PENDING, 1)
        }
        val target = contentResolver.insert(MediaStore.Video.Media.EXTERNAL_CONTENT_URI, values) ?: throw ApiException("The phone could not create the video file.")
        try {
            contentResolver.openOutputStream(target)!!.use { out ->
                var done = 0L
                var tries = 0
                while (true) {
                    try {
                        api.download(done, out, { !cancelled }) { d, total -> done = d; show(Stage.Download, if (total > 0) d.toFloat() / total else 0f, name) }
                        break
                    } catch (e: IOException) {
                        if (++tries > 8) throw e  // each retry continues from the bytes already saved
                        delay(2500)
                    }
                }
            }
        } catch (e: Exception) {
            contentResolver.delete(target, null, null)
            throw e
        }
        contentResolver.update(target, ContentValues().apply { put(MediaStore.Video.Media.IS_PENDING, 0) }, null, null)
        Store.savedJob = jobId
        Store.state.update { it.copy(phase = Phase.Done(target, title), error = null) }
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
        getSystemService(NotificationManager::class.java).notify(2, builder().setContentTitle("Your translated video is ready")
            .setContentText(title).setContentIntent(open).setAutoCancel(true).build())
    }

    private fun builder(): Notification.Builder {
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel("job", "Translation progress", NotificationManager.IMPORTANCE_LOW))
        return Notification.Builder(this, "job").setSmallIcon(R.drawable.ic_notification).setColor(0xFF57D6B5.toInt())
    }

    private fun notification(text: String, percent: Int): Notification {
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
        return builder().setContentTitle(text).setProgress(100, percent, false).setOngoing(true).setOnlyAlertOnce(true).setContentIntent(open).build()
    }

    override fun onDestroy() {
        scope.cancel()
        super.onDestroy()
    }

    companion object {
        const val CANCEL = "cancel"

        fun start(context: Context, picked: Picked?, choice: Choice) {
            val intent = Intent(context, JobService::class.java)
            if (picked != null) {
                intent.setDataAndType(picked.uri, "video/*").addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                intent.putExtra("name", picked.name).putExtra("size", picked.size).putExtra("mode", choice.mode)
                    .putExtra("source", choice.source).putExtra("target", choice.target).putExtra("model", choice.model)
            }
            context.startForegroundService(intent)
        }

        fun cancel(context: Context) {
            context.startService(Intent(context, JobService::class.java).setAction(CANCEL))
        }
    }
}
