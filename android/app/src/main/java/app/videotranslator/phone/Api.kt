package app.videotranslator.phone

import org.json.JSONException
import org.json.JSONObject
import java.io.InputStream
import java.io.OutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

/** A problem the PC reported in words the user can read. */
class ApiException(message: String) : Exception(message)

/** Talks to phone mode on the PC (videotranslator/phone_server.py). Plain blocking calls: run them off the main thread. */
class Api(private val host: String, private val token: String? = null) {
    private fun open(path: String, method: String): HttpURLConnection {
        val c = URL("http://$host$path").openConnection() as HttpURLConnection
        c.requestMethod = method
        c.connectTimeout = 6000
        c.readTimeout = 30000
        token?.let { c.setRequestProperty("Authorization", "Bearer $it") }
        return c
    }

    private fun read(c: HttpURLConnection): JSONObject {
        try {
            val code = c.responseCode
            val text = (if (code in 200..299) c.inputStream else c.errorStream)?.bufferedReader()?.use { it.readText() } ?: ""
            val json = try { JSONObject(text) } catch (e: JSONException) { JSONObject() }
            if (code !in 200..299) throw ApiException(json.optString("error", "The PC answered with error $code."))
            return json
        } finally {
            c.disconnect()
        }
    }

    fun hello(): JSONObject = read(open("/", "GET"))

    fun pair(code: String): JSONObject {
        val c = open("/pair", "POST")
        val body = JSONObject().put("code", code).toString().toByteArray()
        c.doOutput = true
        c.setRequestProperty("Content-Type", "application/json")
        c.setFixedLengthStreamingMode(body.size)
        c.outputStream.use { it.write(body) }
        return read(c)
    }

    fun status(): JSONObject = read(open("/status", "GET"))

    fun options(): Options {
        val json = read(open("/options", "GET"))
        val languages = json.getJSONArray("languages").let { list -> List(list.length()) { list.getJSONObject(it).run { getString("name") to getString("code") } } }
        val models = json.optJSONArray("models")?.let { list -> List(list.length()) { list.getString(it) } } ?: emptyList()
        return Options(languages, models, json.optString("model"))
    }

    fun cancel(): JSONObject {
        val c = open("/cancel", "POST")
        c.doOutput = true
        c.setFixedLengthStreamingMode(0)
        c.outputStream.close()
        return read(c)
    }

    /** Streams the video to the PC without holding it in memory. [progress] gets the bytes sent so far. */
    fun upload(name: String, choice: Choice, size: Long, input: InputStream, keepGoing: () -> Boolean, progress: (Long) -> Unit): JSONObject {
        val model = if (choice.model.isBlank()) "" else "&model=" + URLEncoder.encode(choice.model, "UTF-8")
        val c = open("/upload?name=${URLEncoder.encode(name, "UTF-8")}&mode=${choice.mode}&source=${choice.source}&target=${choice.target}$model", "PUT")
        c.doOutput = true
        c.setFixedLengthStreamingMode(size)
        c.readTimeout = 120000
        try {
            c.outputStream.use { out ->
                val buffer = ByteArray(1 shl 16)
                var sent = 0L
                while (true) {
                    if (!keepGoing()) throw ApiException("Cancelled.")
                    val n = input.read(buffer)
                    if (n < 0) break
                    out.write(buffer, 0, n)
                    sent += n
                    progress(sent)
                }
            }
        } catch (e: Exception) {
            c.disconnect()
            throw e
        }
        return read(c)
    }

    /** Downloads the finished video starting at byte [from], so a dropped transfer continues where it stopped. Returns the total size. */
    fun download(jobId: String, from: Long, out: OutputStream, keepGoing: () -> Boolean, progress: (done: Long, total: Long) -> Unit): Long {
        // The job is named so a retry cannot continue with a different video the PC finished in between.
        val c = open("/result?id=${URLEncoder.encode(jobId, "UTF-8")}", "GET")
        if (from > 0) c.setRequestProperty("Range", "bytes=$from-")
        try {
            val code = c.responseCode
            if (code !in 200..299) return read(c).let { 0L }
            // Asked to continue from a byte: only an answer that starts exactly there may be appended.
            if (from > 0 && (code != 206 || c.getHeaderField("Content-Range")?.startsWith("bytes $from-") != true)) throw ApiException("The PC sent the wrong part of the video. Send it again.")
            val total = from + c.contentLengthLong
            var done = from
            c.inputStream.use { input ->
                val buffer = ByteArray(1 shl 16)
                while (true) {
                    if (!keepGoing()) throw ApiException("Cancelled.")
                    val n = input.read(buffer)
                    if (n < 0) break
                    out.write(buffer, 0, n)
                    done += n
                    progress(done, total)
                }
            }
            return total
        } finally {
            c.disconnect()
        }
    }
}
