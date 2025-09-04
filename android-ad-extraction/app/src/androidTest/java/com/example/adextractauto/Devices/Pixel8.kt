package com.example.adextractauto.Devices

import android.content.Context
import android.graphics.Point
import android.net.ConnectivityManager
import android.net.wifi.WifiInfo
import android.net.wifi.WifiManager
import android.util.Log
import android.view.KeyEvent.KEYCODE_ENTER
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.UiScrollable
import androidx.test.uiautomator.UiSelector
import com.example.adextractauto.checkAlive
import com.example.adextractauto.getSIMInfo
import com.example.adextractauto.logAccountAction
import com.example.adextractauto.logESIMInstall
import com.example.adextractauto.releaseESIM
import java.time.Instant

class Pixel8(device: UiDevice) : AndroidDevice(device) {

    /**
     * Helper function to open settings.
     */
    private fun openSettings() {
        // try to clear previous state (partially entered creds, for example)
        device.executeShellCommand("am force-stop com.android.settings")

        device.executeShellCommand("am start -a $SETTINGS_IDENTIFIER")
        device.waitForIdle(IDLE_TIMEOUT)

        // sanity check that we really are in the settings main menu
        // and that nothing is obstructing our user interface
        var iterations = 0
        while(true) {
            if (!detectObject(By.text("Network & internet"))) {
                device.pressBack()
                device.waitForIdle(IDLE_TIMEOUT)
                device.pressBack()
                device.waitForIdle(IDLE_TIMEOUT)
                device.pressBack()
                device.waitForIdle(IDLE_TIMEOUT)
                device.pressBack()
                device.waitForIdle(IDLE_TIMEOUT)


                device.pressHome()
                device.executeShellCommand("am start -a $SETTINGS_IDENTIFIER")
                device.waitForIdle(IDLE_TIMEOUT)
            } else {
                break
            }

            if(iterations++ > 30) {
                throw IllegalStateException("Failed to open settings menu.")
            }
        }
    }

    override fun enterPIN() {
        detectObject(By.desc("PIN"))
                || throw IllegalStateException("Failed to wait for PIN element prompt.")

        // enter pin
        performWithRetry {
            device.findObject(By.desc("PIN")).click()
            device.waitForIdle(IDLE_TIMEOUT)
            device.findObject(By.desc("PIN")).text = DEVICE_PIN
            Thread.sleep(IDLE_TIMEOUT)
            device.pressKeyCode(KEYCODE_ENTER)
            Thread.sleep(IDLE_TIMEOUT)

            // use implicit retry semantic of performRetry by throwing NPE
            if(device.findObject(By.text("Re-enter your PIN")) != null) {
                throw NullPointerException()
            }
        }
    }

    override fun setupWIFI() {
        if(!device.isScreenOn) unlockDevice()

        Log.i(LTAG, "Trying to connect to WIFI $WIFI_NETWORK.")

        val context = InstrumentationRegistry.getInstrumentation().context
        val wManager: WifiManager = context.getSystemService(Context.WIFI_SERVICE) as WifiManager
        assert(wManager.isWifiEnabled)

        openSettings()

        performWithRetry { device.findObject(By.text("Network & internet")).click() }

        performWithRetry { device.findObject(By.text("Internet")).click() }

        // find target network (sometimes takes a few seconds)
        performWithRetry { device.findObject(By.textStartsWith(WIFI_NETWORK)).click() }

        // enter password
        performWithRetry { device.findObject(
            By.clazz("android.widget.EditText").focused(true)).text = WIFI_NETWORK_PASS }

        // click connect
        device.findObject(By.textContains("Connect")).click()

        // wait until connected to wifi
        var iteration = 0
        while(true) {
            val connectivityManager = context.getSystemService(ConnectivityManager::class.java) as ConnectivityManager
            val winfo = connectivityManager.getNetworkCapabilities(connectivityManager.activeNetwork)?.transportInfo
            if(winfo != null && (winfo as WifiInfo).supplicantState.toString() == "COMPLETED") {
                break
            }
            assert(++iteration < 30)
            Thread.sleep(300L)
        }

        // exit settings menu
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
    }

    override fun installESIM(phonenumber: String) {
        Log.i(LTAG, "Initiating eSIM installation.")

        // initial test that the harvester server is reachable
        checkAlive()

        // do this first to ensure that the screen is on before doing anything else
        if(!device.isScreenOn) unlockDevice()
        device.pressHome()

        // assert that we already have a wifi connection (or VPN for account creation purposes)
        checkWIFIConnectivity()

        // retrieve sim information
        val esim = getSIMInfo(phonenumber) ?: throw IllegalStateException("Could not retrieve eSIM with phonenumber $phonenumber")

        // if sim is locked, bail out
        if(esim.locked) {
            Log.e(LTAG, "Could not fetch eSIM details: eSIM is locked! Bailing out.")
            throw IllegalStateException("eSIM is in locked state.")
        }

        openSettings()
        performWithRetry { device.findObject(By.text("Network & internet")).click() }
        performWithRetry { device.findObject(By.text("SIMs")).click() }

        // for some reason, sometimes there is a "Setup an eSIM" button instead?
        // first try 'Download a new eSIM, if that fails, we try the other button.
        // Afterwards, the flow is the same
        try {
            performWithRetry({ device.findObject(By.text("Download a new eSIM")).click() },
                true, MAX_RETRIES)
        } catch (e: IllegalStateException) {
            performWithRetry { device.findObject(By.text("Set up an eSIM")).click() }
        }

        // wait for scan QR code prompt -> handle long delays here
        detectObject(By.textStartsWith("Scan QR code"), timeout=SHORT_WAIT * 180)
                || throw IllegalStateException("Could not find Scan QR code prompt.")

        // sometimes, it is 'Need help' instead
        if(detectObject(By.text("Need help?"))) {
            performWithRetry { device.findObject(By.text("Need help?")).click() }
        } else {
            // text ist not directly clickable
            performWithRetry {
                val obj = device.findObject(By.textContains("Try these troubleshooting steps"))
                device.click(obj.visibleBounds.centerX(), obj.visibleBounds.centerY()+10)
            }
        }

        performWithRetry { device.findObject(By.textContains("Enter it manually")).click(
            Point(40, 820)
        )}

        // build the sim card activation format - check if this is the same for all cards!
        performWithRetry { device.findObject(By.text("Code")).text = "LPA:1$${esim.address}$${esim.activationCode}" }
        performWithRetry { device.findObject(By.text("Continue")).click() }

        Thread.sleep(IDLE_TIMEOUT * 2) // this is required because the download takes some time
        performWithRetry { device.findObject(By.text("Set up")).click() }
        performWithRetry { device.findObject(
            By.clazz("android.widget.EditText")).text = esim.confirmationCode
        }
        performWithRetry { device.findObject(By.text("Continue")).click() }

        // now installing the sim, this can apparently take some time
        Thread.sleep(60 * 1000 )

        // go to settings to active the newly installed SIM
        performWithRetry { device.findObject(By.text("Settings")).click() }
        performWithRetry { device.findObject(By.text("Use this SIM")).click() }
        performWithRetry { device.findObject(By.text("Turn on")).click() }

        // this takes a few seconds (detect by 'mobile data' switch)
        if(!detectObject(By.text("Mobile data"), IDLE_TIMEOUT * 10)) {
            throw IllegalStateException("Something went wrong during eSIM insertion.")
        }

        // log success
        logESIMInstall(phonenumber, getSerial(), Instant.now().toString())

        // exit settings menu
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
    }

    override fun disableCellular(phonenumber: String) {
        Log.i(LTAG, "Initiating eSIM cellular data check.")

        // do this first to ensure that the screen is on before doing anything else
        if(!device.isScreenOn) unlockDevice()
        device.pressHome()

        openSettings()
        performWithRetry { device.findObject(By.text("Network & internet")).click() }
        performWithRetry { device.findObject(By.text("SIMs")).click() }
        performWithRetry { device.findObject(By.textStartsWith(ESIM_IDENTIFIER)).click() }

        // check if data is already disabled, second toggle is the one for mobile data
        if(!detectObject(By.text("Mobile data"))) {
            throw IllegalStateException("Failed to navigate to mobile data menu.")
        }

        if(device.findObjects(By.clazz("android.widget.Switch"))[1].isChecked) {
            // disable mobile data
            performWithRetry { device.findObject(By.text("Mobile data")).click() }
        }

        // it takes some time until the correct value is returned by dumpsys?
        Thread.sleep(5 * 1000)

        // check if data is disabled via dumpsys
        val found  = device.executeShellCommand("dumpsys telephony.registry").split("\n").filter {
            it.trim().startsWith("mDataConnectionState")
        }.map {it.trim()}
        val dataDisabled = (found == listOf("mDataConnectionState=-1", "mDataConnectionState=0"))
        device.waitForIdle(IDLE_TIMEOUT)

        // perform sanity check that mobile date is really disabled.
        if(!dataDisabled || device.findObjects(By.clazz("android.widget.Switch"))[1].isChecked) {
            Log.i(LTAG, "$found, $dataDisabled, dumpsys returned: " + device.executeShellCommand("dumpsys telephony.registry").split("\n").filter {it.trim().startsWith("mDataConnectionState")}.toString())
            Log.e(LTAG, "Failed to disable cellular data. Performing emergency bailout.")
            if(device.executeShellCommand("cmd connectivity airplane-mode enable") != "") {
                Log.e(LTAG, "Failed to enter airplane mode. Performing emergency shutdown.")
                device.executeShellCommand("reboot -p")
            }
            throw IllegalStateException("Failed to disable cellular data. Bailing out.")
        }

        // exit settings menu
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
    }

    override fun removeESIM(phonenumber: String) {
        Log.i(LTAG, "Initiating the removal of the ESIM.")

        // initial test that the harvester server is reachable
        checkAlive()

        checkWIFIConnectivity()

        // do this first to ensure that the screen is on before doing anything else
        if(!device.isScreenOn) unlockDevice()
        device.pressHome()

        fixScreenOrientation()

        // bring up the settings screen
        device.executeShellCommand("am start -a com.android.settings.sim.SIM_SUB_INFO_SETTINGS")
        device.waitForIdle(IDLE_TIMEOUT)

        // select SIM
        performWithRetry { device.findObject(By.textContains(ESIM_IDENTIFIER)).click() }

        // get root scrollable container and scroll to end
        assert(UiScrollable(UiSelector().scrollable(true).className("android.widget.ScrollView")).scrollToEnd(100))
        device.waitForIdle(IDLE_TIMEOUT)

        performWithRetry { device.findObject(By.text("Erase SIM")).click() }

        enterPIN()

        performWithRetry { device.findObject(By.text("Erase")).click() }

        // now removing the sim, this can apparently take some time
        Thread.sleep(30 * 1000)

        // go back to home screen
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)

        // if everything worked, we can mark this sim as released
        releaseESIM(phonenumber)
    }

    override fun factoryReset() {
        Log.i(LTAG, "Initiating factory reset.")

        if(!device.isScreenOn) unlockDevice()

        openSettings()

        // get root scrollable container and scroll to end
        performWithRetry {
            UiScrollable(UiSelector().scrollable(true).className("android.widget.ScrollView")).scrollToEnd(100)
        }

        // open system settings
        Thread.sleep(IDLE_TIMEOUT) // this is required, else the button is not found (for some reason)
        performWithRetry { device.findObject(By.text("System")).click() }

        // get root scrollable container and scroll to end
        performWithRetry {
            UiScrollable(UiSelector().scrollable(true).className("android.widget.ScrollView")).scrollToEnd(100)
        }

        // open reset settings
        Thread.sleep(IDLE_TIMEOUT) // same as above (prevent issue where button is not found)
        performWithRetry { device.findObject(By.text("Reset options")).click() }
        performWithRetry { device.findObject(By.text("Erase all data (factory reset)")).click() }
        performWithRetry { device.findObject(By.text("Erase eSIMs")).click() }
        performWithRetry { device.findObject(By.text("Erase all data")).click() }
        enterPIN()
        logAccountAction("PREV_ACC", getSerial(), "logout")
        performWithRetry { device.findObject(By.text("Erase all data")).click() }
    }

    override fun openGoogleSettings() {
        openSettings()

        // get root scrollable container and scroll to end
        assert(UiScrollable(UiSelector().scrollable(true).className("android.widget.ScrollView")).scrollToEnd(100))
        device.waitForIdle(IDLE_TIMEOUT)
        Thread.sleep(IDLE_TIMEOUT) // same as above (prevent issue where button is not found)

        // open google account settings
        performWithRetry { device.findObject(By.text("Services & preferences")).click() }
    }

    override fun logoutAccount(email: String) {
        Log.i(LTAG, "Initiating account logout.")

        // initial test that the harvester server is reachable
        checkAlive()

        // unlock device (we need to do this first so the device var is initialized)
        if(!device.isScreenOn) unlockDevice()
        device.pressHome()

        openSettings()

        // get root scrollable container and scroll to end
        assert(UiScrollable(UiSelector().scrollable(true).className("android.widget.ScrollView")).scrollToEnd(100))
        device.waitForIdle(IDLE_TIMEOUT)
        Thread.sleep(IDLE_TIMEOUT) // same as above (prevent issue where button is not found)

        // open google account settings
        performWithRetry { device.findObject(By.text("Services & preferences")).click() }

        // click on account
        performWithRetry { device.findObject(By.text(email)).click() }

        // click manage accounts on this device
        performWithRetry { device.findObject(By.text("Manage accounts on this device")).click() }

        // click on account again
        performWithRetry { device.findObject(By.text(email)).click() }

        // click on remove account
        performWithRetry { device.findObject(By.text("Remove account")).click() }

        // confirm account removal
        performWithRetry { device.findObject(By.text("Remove account")).click() }

        // confirm account removal again
        performWithRetry { device.findObject(By.text("OK")).click() }

        enterPIN()

        // go to main screen
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
    }

    override fun disableSound() {
        Log.i(LTAG, "Starting to enable silent mode.")

        if(!device.isScreenOn) unlockDevice()
        device.pressHome()

        openSettings()

        performWithRetry { device.findObject(By.text("Sound & vibration")).click() }
        performWithRetry { device.findObject(By.text("Do Not Disturb")).click() }
        performWithRetry { device.findObject(By.text("Turn on now")).click() }

        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
    }

    override fun disableUpdates() {
        Log.i(LTAG, "Starting to disable updates.")

        if(!device.isScreenOn) unlockDevice()
        device.pressHome()

        openSettings()

        // scroll down to end
        performWithRetry {
            assert(UiScrollable(UiSelector().scrollable(true)
                .className("android.widget.ScrollView"))
                .flingToEnd(100))
        }

        performWithRetry { device.findObject(By.text("System")).click() }

        // scroll down to end
        performWithRetry {
            assert(UiScrollable(UiSelector().scrollable(true)
                .className("android.widget.ScrollView"))
                .flingToEnd(100))
        }

        performWithRetry { device.findObject(By.text("Developer options")).click() }

        // scroll to auto update system
        val ret = UiScrollable(UiSelector()
            .scrollable(true)
            .className("android.widget.ScrollView"))
            .scrollTextIntoView("Automatic system updates")
        if(!ret) {
            Log.e(LTAG, "Could not find 'automatic system updates' element. Aborting.")
            throw IllegalStateException("Failed to find text.")
        }

        performWithRetry { device.findObject(By.text("Automatic system updates")).click() }

        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
    }

    override fun disableScreenTimeout() {
        Log.i(LTAG, "Starting to disable screen timeout.")

        if(!device.isScreenOn) unlockDevice()
        device.pressHome()

        openSettings()

        // scroll down a bit
        UiScrollable(UiSelector().scrollable(true).className("android.widget.ScrollView")).scrollForward(200)
        device.waitForIdle(IDLE_TIMEOUT)

        // click on display settings
        performWithRetry { device.findObject(By.text("Display")).click() }

        // click on screen timeout
        performWithRetry { device.findObject(By.text("Screen timeout")).click() }

        // select 30 minute timeout, aka the highest option
        performWithRetry { device.findObject(By.text("30 minutes")).click() }

        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
    }

}
