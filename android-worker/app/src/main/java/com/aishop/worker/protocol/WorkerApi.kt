package com.aishop.worker.protocol

import com.aishop.worker.BuildConfig
import java.net.URI
import java.util.concurrent.TimeUnit
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody

class WorkerApi(
    private val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .callTimeout(15, TimeUnit.SECONDS)
        .build(),
) {
    private val json = Json {
        explicitNulls = true
        ignoreUnknownKeys = false
    }

    fun pair(baseUrl: String, request: PairDeviceRequest): PairDeviceResponse = post(
        url = "${normalizeGatewayUrl(baseUrl)}/devices/pair",
        payload = json.encodeToString(request),
        token = null,
        decode = json::decodeFromString,
    )

    fun heartbeat(
        baseUrl: String,
        deviceId: String,
        token: String,
        heartbeat: DeviceHeartbeat,
    ): HeartbeatResponse = post(
        url = "${normalizeGatewayUrl(baseUrl)}/devices/$deviceId/heartbeat",
        payload = json.encodeToString(heartbeat),
        token = token,
        decode = json::decodeFromString,
    )

    fun uploadEvidence(
        baseUrl: String,
        deviceId: String,
        token: String,
        upload: EvidenceUpload,
    ): EvidenceResponse = post(
        url = "${normalizeGatewayUrl(baseUrl)}/devices/$deviceId/evidence",
        payload = json.encodeToString(upload),
        token = token,
        decode = json::decodeFromString,
    )

    fun uploadEvent(
        baseUrl: String,
        deviceId: String,
        token: String,
        event: InboundEventPayload,
    ) {
        post<UnitResponse>(
            url = "${normalizeGatewayUrl(baseUrl)}/devices/$deviceId/events",
            payload = json.encodeToString(event),
            token = token,
            decode = { UnitResponse },
        )
    }

    private fun <T> post(
        url: String,
        payload: String,
        token: String?,
        decode: (String) -> T,
    ): T {
        val builder = Request.Builder()
            .url(url)
            .post(payload.toRequestBody(JSON_MEDIA_TYPE))
        if (token != null) {
            builder.header("Authorization", "Bearer $token")
        }
        client.newCall(builder.build()).execute().use { response ->
            if (!response.isSuccessful) {
                throw WorkerApiException(response.code)
            }
            val body = response.body?.string() ?: throw WorkerApiException(response.code)
            return decode(body)
        }
    }

    private companion object {
        val JSON_MEDIA_TYPE = "application/json; charset=utf-8".toMediaType()
    }
}

class WorkerApiException(val statusCode: Int) : RuntimeException("AIShop gateway HTTP $statusCode")

fun normalizeGatewayUrl(input: String): String {
    val normalized = input.trim().trimEnd('/')
    val uri = runCatching { URI(normalized) }.getOrElse {
        throw IllegalArgumentException("Gateway URL is invalid", it)
    }
    require(uri.scheme in setOf("http", "https") && !uri.host.isNullOrBlank()) {
        "Gateway URL must use http or https and include a host"
    }
    require(uri.scheme == "https" || BuildConfig.ALLOW_CLEARTEXT) {
        "Production builds require an HTTPS gateway"
    }
    require(uri.userInfo == null && uri.query == null && uri.fragment == null) {
        "Gateway URL must not contain credentials, query, or fragment"
    }
    return normalized
}

private object UnitResponse
