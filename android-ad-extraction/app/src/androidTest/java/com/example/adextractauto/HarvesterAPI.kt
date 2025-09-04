package com.example.adextractauto

import android.util.Log
import com.github.kittinunf.fuel.core.Headers
import com.github.kittinunf.fuel.core.extensions.jsonBody
import com.github.kittinunf.fuel.httpGet
import com.github.kittinunf.fuel.httpPost
import com.github.kittinunf.result.Result
import com.github.kittinunf.fuel.core.FuelError
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import java.time.Instant

private const val LTAG = "AdExtractAuto"
private const val API_ENDPOINT = ""
private const val API_TOKEN = ""
private const val RETRIES = 100

fun <T>withRetries(apiFun : () -> T) : T {
    for(t in 0..RETRIES) {
        try {
            return apiFun()
        } catch(e: FuelError) {
            Log.w(LTAG, "Caught error in Harvester API function: '${e.message}'. Attempt $t / $RETRIES, retrying.")
            Thread.sleep(500L)
        }
    }
    throw IllegalArgumentException("HTTP request failed after $RETRIES retries.")
}

/*
 *  Functions that use the REST API ----------------------------------------------------------
 */
fun fetchNextAdID(experimentId: Int): Int {
    Log.i(LTAG, "fetchNextAdID($experimentId)")
    return withRetries {
        val (_, _, result) = "$API_ENDPOINT/ad_data/new_id"
            .httpGet(listOf("experiment_id" to experimentId.toString()))
            .header(Headers.AUTHORIZATION, API_TOKEN)
            .responseString()

        when(result) {
            // Propagate exception upwards
            is Result.Failure -> throw result.getException()
            is Result.Success -> Gson().fromJson(result.get(), ID::class.java).id
        }
    }
}

fun storeAdData(ad: Ad) {
    Log.i(LTAG, "storeAdData(${ad.name})")
    return withRetries {
        val (_, _, result) = "$API_ENDPOINT/ad_data"
            .httpPost()
            .header(Headers.AUTHORIZATION, API_TOKEN)
            .jsonBody(Gson().toJson(ad))
            .responseString()

        when (result) {
            // Propagate exception upwards
            is Result.Failure -> throw result.getException()
            is Result.Success -> {}
        }
    }
}

fun getPersonaApps(email: String): List<App> {
    Log.i(LTAG, "getPersonaApps(${email})")
    return withRetries {

        // get persona of the account
        val (_, _, result) = "$API_ENDPOINT/account"
            .httpGet(listOf("email" to email))
            .header(Headers.AUTHORIZATION, API_TOKEN)
            .responseString()

        val personaId = when (result) {
            // Propagate exception upwards
            is Result.Failure -> throw result.getException()
            is Result.Success -> Gson().fromJson(result.get(), Account::class.java).personaId
        }

        // get apps for this persona
        val (_, _, apps) = "$API_ENDPOINT/persona/apps"
            .httpGet(listOf("id" to personaId))
            .header(Headers.AUTHORIZATION, API_TOKEN)
            .responseString()

        when (apps) {
            // Propagate exception upwards
            is Result.Failure -> throw apps.getException()
            is Result.Success -> Gson().fromJson<List<App>>(
                apps.get(),
                // build a deserialization type with a list containing apps
                object : TypeToken<List<App>>() {}.type
            )
        }
    }
}

fun logAppInstall(email: String, app: App) {
    return withRetries {
        val (_, _, result) = "$API_ENDPOINT/account/app"
            .httpPost()
            .header(Headers.AUTHORIZATION, API_TOKEN)
            .jsonBody(Gson().toJson(AppInstall(email,
                app.id.toString(),
                Instant.now().toString()
            )))
            .responseString()

        when(result) {
            // Propagate exception upwards
            is Result.Failure -> throw result.getException()
            is Result.Success -> {}
        }
    }
}

fun logESIMInstall(phonenumber: String, serial: String, time: String) {
    return withRetries {
        val (_, _, result) = "$API_ENDPOINT/sim/log"
            .httpPost()
            .header(Headers.AUTHORIZATION, API_TOKEN)
            .jsonBody(Gson().toJson(
                mapOf("phonenumber" to phonenumber,
                    "device_serial" to serial,
                    "time" to time)
            ))
            .responseString()

        when(result) {
            // Propagate exception upwards
            is Result.Failure -> throw result.getException()
            is Result.Success -> {}
        }
    }
}

fun logAccountAction(email: String, serial: String, action: String) {
    return withRetries {
        val (_, _, result) = "$API_ENDPOINT/account/log"
            .httpPost()
            .header(Headers.AUTHORIZATION, API_TOKEN)
            .jsonBody(Gson().toJson(
                mapOf("email" to email,
                    "device_serial" to serial,
                    "time" to Instant.now().toString(),
                    "action" to action)
            ))
            .responseString()

        when (result) {
            // Propagate exception upwards
            is Result.Failure -> throw result.getException()
            is Result.Success -> {}
        }
    }
}

fun getAccount(email: String) : Account? {
    return withRetries {
        val (_, _, result) = "$API_ENDPOINT/account"
            .httpGet(listOf("email" to email))
            .header(Headers.AUTHORIZATION, API_TOKEN)
            .responseString()

        when (result) {
            // Propagate exception upwards
            is Result.Failure -> throw result.getException()
            is Result.Success -> Gson().fromJson(result.get(), Account::class.java)
        }
    }
}

 fun getSIMInfo(phonenumber: String): SIM? {
     return withRetries {
         val (_, _, result) = "$API_ENDPOINT/sim"
             .httpGet(listOf("phonenumber" to phonenumber))
             .header(Headers.AUTHORIZATION, API_TOKEN)
             .responseString()

         when (result) {
             // Propagate exception upwards
             is Result.Failure -> throw result.getException()
             is Result.Success -> Gson().fromJson(result.get(), SIM::class.java)
         }
     }
}

 fun releaseESIM(phonenumber: String) {
     return withRetries {
         val (_, _, result) = "$API_ENDPOINT/sim/release"
             .httpGet(listOf("phonenumber" to phonenumber))
             .header(Headers.AUTHORIZATION, API_TOKEN)
             .responseString()

         when (result) {
             // Propagate exception upwards
             is Result.Failure -> throw result.getException()
             is Result.Success -> {}
         }
     }
}

/**
 * Checks if the harvester server is still alive.
 */
 fun checkAlive() : Boolean {
    return withRetries {
        val (_, _, result) = "$API_ENDPOINT/alive"
            .httpGet()
            .timeout(10 * 1000)
            .timeoutRead(10 * 1000)
            .header(Headers.AUTHORIZATION, API_TOKEN)
            .responseString()

        when (result) {
            // Propagate exception upwards
            is Result.Failure -> throw result.getException()
            is Result.Success -> true
        }
    }
}