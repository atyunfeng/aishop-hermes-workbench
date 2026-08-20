package com.aishop.worker.capture

import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.PixelFormat
import android.hardware.display.DisplayManager
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Handler
import android.os.Looper
import android.util.DisplayMetrics
import java.io.ByteArrayOutputStream
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlin.coroutines.resume

class ScreenCaptureController(private val context: Context) {
    @Volatile
    private var projection: MediaProjection? = null

    val active: Boolean get() = projection != null

    fun consentIntent(): Intent =
        context.getSystemService(MediaProjectionManager::class.java).createScreenCaptureIntent()

    fun start(resultCode: Int, data: Intent) {
        stop()
        projection = context.getSystemService(MediaProjectionManager::class.java)
            .getMediaProjection(resultCode, data)
            .also { activeProjection ->
                activeProjection.registerCallback(object : MediaProjection.Callback() {
                    override fun onStop() {
                        projection = null
                    }
                }, Handler(Looper.getMainLooper()))
            }
    }

    fun stop() {
        projection?.stop()
        projection = null
    }

    suspend fun capturePreviewJpeg(): ByteArray? {
        val current = projection ?: return null
        val metrics = context.resources.displayMetrics
        val scale = (720f / metrics.widthPixels).coerceAtMost(1f)
        val width = (metrics.widthPixels * scale).toInt().coerceAtLeast(1)
        val height = (metrics.heightPixels * scale).toInt().coerceAtLeast(1)
        return suspendCancellableCoroutine { continuation ->
            val reader = ImageReader.newInstance(width, height, PixelFormat.RGBA_8888, 2)
            val display = current.createVirtualDisplay(
                "AIShopPreview",
                width,
                height,
                (metrics.densityDpi * scale).toInt().coerceAtLeast(DisplayMetrics.DENSITY_LOW),
                DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
                reader.surface,
                null,
                null,
            )
            reader.setOnImageAvailableListener({ source ->
                val image = source.acquireLatestImage() ?: return@setOnImageAvailableListener
                val plane = image.planes[0]
                val rowPadding = plane.rowStride - plane.pixelStride * width
                val bitmap = Bitmap.createBitmap(
                    width + rowPadding / plane.pixelStride,
                    height,
                    Bitmap.Config.ARGB_8888,
                )
                bitmap.copyPixelsFromBuffer(plane.buffer)
                val cropped = Bitmap.createBitmap(bitmap, 0, 0, width, height)
                val output = ByteArrayOutputStream()
                cropped.compress(Bitmap.CompressFormat.JPEG, 65, output)
                image.close()
                bitmap.recycle()
                cropped.recycle()
                display.release()
                reader.close()
                if (continuation.isActive) continuation.resume(output.toByteArray())
            }, Handler(Looper.getMainLooper()))
            continuation.invokeOnCancellation {
                display.release()
                reader.close()
            }
        }
    }
}
