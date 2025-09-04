package com.example.adextractauto

import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.UiDevice
import com.example.adextractauto.Devices.AndroidDevice
import com.example.adextractauto.Devices.G20
import com.example.adextractauto.Devices.G23
import com.example.adextractauto.Devices.G24
import com.example.adextractauto.Devices.Pixel8
import org.junit.Test
import org.junit.runner.RunWith


// Global config stuff
private const val LTAG = "AdExtractAuto"

@RunWith(AndroidJUnit4::class)
class AutomationTest {

    /**
     * Main entry point. Depending on the arguments, different tasks are started.
     */
    @Test
    fun entry() {
        // get arguments
        val args = InstrumentationRegistry.getArguments()
        val task = args.getString("task") ?: "disablePersonalization"

        // set up fuel to use the AndroidCA store (only needed with mitmproxy)
        // val keyStore = KeyStore.getInstance("AndroidCAStore")
        // keyStore.load(null as InputStream?, null as CharArray?)
        // FuelManager.instance.keystore = keyStore

        // setup uiDevice to be used
        val uiDevice = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())

        // get device to handle UI differences (default to pixel 8)
        val device = when(args.getString("deviceType") ?: "g23") {
            "pixel_8" -> Pixel8(device = uiDevice)
            "g20" -> G20(device = uiDevice)
            "g23" -> G23(device = uiDevice)
            "g24" -> G24(device = uiDevice)
            else -> throw IllegalArgumentException("Unknown device: ${args.getString("deviceType")}")
            // else -> Pixel8(device = uiDevice)
        }
        Log.i(LTAG, "Using $device for device interaction.")

        try {
            when (task) {
                "measurement" ->
                    device.adExtractExperiment(
                        (args.getString("experimentID")?.toInt() ?: 921)// throw IllegalArgumentException("Missing argument: experimentID.")).toInt()
                    )

                "signalPersona" -> device.signalPersona(
                    args.getString("accountEmail")
                        ?: throw IllegalArgumentException("Missing argument: accountEmail."),
                    // negate expression to get true as default value for, e.g., null
                    !args.getString("openApps").equals("false", ignoreCase = true)
                )

                "installESIM" -> device.installESIM(
                    args.getString("phonenumber")
                        ?: throw IllegalArgumentException("Missing argument: phonenumber."),
                )

                "disableCellular" -> device.disableCellular(
                    args.getString("phonenumber")
                        ?: throw IllegalArgumentException("Missing argument: phonenumber."),
                )

                "removeESIM" -> device.removeESIM(
                    args.getString("phonenumber")
                        ?: throw IllegalArgumentException("Missing argument: phonenumber."),
                )

                "disableUpdates" -> device.disableUpdates()

                "disableScreenTimeout" -> device.disableScreenTimeout()

                "disableSound" -> device.disableSound()

                "setupWifi" -> device.setupWIFI()

                "factoryReset" -> device.factoryReset()

                "disablePersonalization" -> device.disablePersonalization()

                "enablePersonalization" -> device.enablePersonalization()

                "loginAccount" -> device.loginAccount(
                    args.getString("accountEmail") ?: throw IllegalArgumentException("Missing argument: accountEmail."),
                    args.getString("handleCaptcha").equals("true", ignoreCase = true) // false is default if missing
                )

                "logoutAccount" -> device.logoutAccount(
                    args.getString("accountEmail")
                        ?: throw IllegalArgumentException("Missing argument: accountEmail."),
                )

                "retrieveSMSCode" -> device.retrieveSMSCode(AndroidDevice.Platform.valueOf(
                    args.getString("platform") ?: throw IllegalArgumentException("Missing argument: platform.")
                ))

                else -> throw IllegalArgumentException("Unsupported task type: `$task`.")
            }
        } catch(e: RuntimeException) {
            Log.e(LTAG, "Caught exception during task execution: ${e.stackTraceToString()}, aborting.")
            throw e
        }
        Log.i(LTAG, "Finished task `$task`.")
    }
}