package com.example.adextractauto.Devices

import android.content.Context
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

/**
 * Handles G23, and also G22+ / G22 ultra.
 */
open class G23(device: UiDevice) : AndroidDevice(device){
    override fun unlockDevice() {
        // wake up screen
        device.executeShellCommand("input keyevent 26")
        device.waitForIdle(IDLE_TIMEOUT)

        device.waitForIdle(IDLE_TIMEOUT)
        device.executeShellCommand("input keyevent 66")
        device.waitForIdle(IDLE_TIMEOUT)
        device.executeShellCommand("input text 0000")
        device.waitForIdle(IDLE_TIMEOUT)
        device.executeShellCommand("input keyevent 66")
        device.waitForIdle(IDLE_TIMEOUT)
        Thread.sleep(IDLE_TIMEOUT) // takes some time for dumpsys to be updated

        assert(device.executeShellCommand("dumpsys deviceidle").contains("mScreenLocked=false\n"))
    }

    override fun enterPIN() {
        // there are different variants of pin prompts
        val descriptor = if(detectObject(By.desc("PIN"))) {
            By.desc("PIN")
        } else if(detectObject(By.res("com.samsung.android.biometrics.app.setting:id/lockPassword"))) {
            By.res("com.samsung.android.biometrics.app.setting:id/lockPassword")
        } else {
            throw IllegalStateException("Failed to wait for PIN element prompt.")
        }

        // enter pin (fails sometimes, therefore retry)
        performWithRetry {
            device.waitForIdle(IDLE_TIMEOUT)
            // set focus
            device.findObject(descriptor).click()
            device.findObject(descriptor).text = DEVICE_PIN
            Thread.sleep(IDLE_TIMEOUT)
            device.pressKeyCode(KEYCODE_ENTER)
            Thread.sleep(IDLE_TIMEOUT)

            // use implicit retry semantic of performRetry by throwing NPE
            if(detectObject(By.text("Confirm PIN"))) {
                throw NullPointerException()
            }
        }
    }

    /**
     * Helper function to deal with issues when opening settings (such as tip overlays).
     */
    fun openSettings() {
        // try to clear previous state (partially entered creds, for example)
        device.executeShellCommand("am force-stop com.android.settings")

        device.executeShellCommand("am start -a $SETTINGS_IDENTIFIER")
        device.waitForIdle(IDLE_TIMEOUT)

        // sanity check that we really are in the settings main menu
        // and that nothing is obstructing our user interface
        var iterations = 0
        while(true) {
            if (!detectObject(By.text("Connections"))) {
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

    override fun setupWIFI() {
        if(!device.isScreenOn) unlockDevice()

        Log.i(LTAG, "Trying to connect to WIFI $WIFI_NETWORK.")

        try {
            checkWIFIConnectivity()
            // if we already have wifi we do not need to try to connect.
            // This can happen if a previous connection attempt crashed.
            return
        } catch(e: IllegalStateException) {
            // we do not have wifi, continue below
        }

        // clear previous state (partially entered creds, for example)
        device.executeShellCommand("am force-stop com.android.settings")

        val context = InstrumentationRegistry.getInstrumentation().context
        val wManager: WifiManager = context.getSystemService(Context.WIFI_SERVICE) as WifiManager
        assert(wManager.isWifiEnabled)

        // open settings -> there is PICK_WIFI_NETWORK, but it is sometimes bugged?
        openSettings()

        performWithRetry { device.findObject(By.text("Connections")).click() }

        performWithRetry { device.findObject(By.text("Wi-Fi")).click() }

        // find target network (sometimes takes a few seconds)
        performWithRetry { device.findObject(By.textStartsWith(WIFI_NETWORK)).click() }

        // enter password
        performWithRetry { device.findObject(
            By.clazz("android.widget.EditText").focused(true)).text = WIFI_NETWORK_PASS }

        // click connect
        performWithRetry { device.findObject(By.text("Connect")).click() }

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
        Log.i(LTAG, "Initiating installation of the ESIM.")

        // do this first to ensure that the screen is on before doing anything else
        if (!device.isScreenOn) unlockDevice()
        device.pressHome()

        // assert that we already have a wifi connection (or VPN for account creation purposes)
        checkWIFIConnectivity()

        // initial test that the harvester server is reachable
        checkAlive()

        // retrieve sim information
        val esim = getSIMInfo(phonenumber)
            ?: throw IllegalStateException("Could not retrieve eSIM with phonenumber $phonenumber")

        // if sim is locked, bail out
        if (esim.locked) {
            Log.e(LTAG, "Could not fetch eSIM details: eSIM is locked! Bailing out.")
            throw IllegalStateException("eSIM is in locked state.")
        }

        openSettings()

        performWithRetry { device.findObject(By.text("Connections")).click() }
        performWithRetry { device.findObject(By.text("SIM manager")).click() }

        // this takes some time usually, and we are close to the 30 iterations limit
        // so we add a manual wait
        performWithRetry {
            device.findObject(By.text("Add eSIM")).click()
        }

        // can take a long time if network is not ready
        detectObject(By.text("Scan QR code"), timeout= SHORT_WAIT * 180)
                || throw IllegalStateException("Failed to wait for QR code prompt.")
        device.waitForIdle(IDLE_TIMEOUT)
        performWithRetry { device.findObject(By.text("Scan QR code")).click() }
        performWithRetry { device.findObject(By.text("Enter activation code")).click() }

        // retry to enter if it fails
        for(i in 0..4) {
            // wait until code field is here
            detectObject(By.text("Enter activation code"), timeout= IDLE_TIMEOUT * 15)
                    || throw IllegalStateException("Failed to wait for activation code prompt.")
            Thread.sleep(IDLE_TIMEOUT) // fix issue where code is not fully entered
            performWithRetry { device.findObject(By.focused(true)).text = "LPA:1$${esim.address}$${esim.activationCode}" }
            Thread.sleep(IDLE_TIMEOUT) // fix issue where code is not fully entered
            performWithRetry { device.findObject(By.text("Done")).click() }
            Thread.sleep(IDLE_TIMEOUT) // fix issue where code is not fully entered

            // check if failed to enter
            if(detectObject(By.text("Enter activation code"))) {
                continue
            }

            break
        }

        // wait until "Enter code from service provider" is here
        if(!detectObject(By.text("Enter code from service provider"), timeout= SHORT_WAIT * 180)) {

            // sometimes, there is just a network or whatever failure and we have to click ok to dismiss the dialogue (else it will prevent subsequent attempts)
            performWithRetry { device.findObject(By.text("OK")).click() }
            throw IllegalStateException("Failed to wait for service provider code prompt.")
        }

        performWithRetry { device.findObject(
            By.clazz("android.widget.EditText")).text = esim.confirmationCode
        }
        performWithRetry { device.findObject(By.text("Done")).click() }

        // wait until esIM has been installed
        detectObject(By.text(ESIM_IDENTIFIER), SHORT_WAIT * 200)
                || throw IllegalStateException("Failed to wait for ESIM_IDENTIFIER text.")

        // log success
        logESIMInstall(phonenumber, getSerial(), Instant.now().toString())

        // go back to home screen
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
    }

    override fun disableCellular(phonenumber: String) {
        Log.i(LTAG, "Initiating disableCellular for $phonenumber.")

        // do this first to ensure that the screen is on before doing anything else
        if (!device.isScreenOn) unlockDevice()
        device.pressHome()

        openSettings()

        performWithRetry { device.findObject(By.text("Connections")).click() }

        // function to abort execution if something went wrong when disabling mobile data
        val bailout = {
            Log.e(LTAG, "Failed to disable  cellular data. Performing emergency bailout.")
            if(device.executeShellCommand("cmd connectivity airplane-mode enable") != "") {
                Log.e(LTAG, "Failed to enter airplane mode. Performing emergency shutdown.")
                device.executeShellCommand("reboot -p")
            }
            Thread.sleep(IDLE_TIMEOUT) // bailout did not work in earlier test?
            throw IllegalStateException("Failed to disable cellular data. Bailing out.")
        }

        // disable data
        val ret = UiScrollable(UiSelector()
            .scrollable(true)
            .className("androidx.recyclerview.widget.RecyclerView"))
            .scrollTextIntoView("Data usage")
        if(!ret) {
            bailout()
        }
        performWithRetry { device.findObject(By.text("Data usage")).click() }

        detectObject(By.text("Mobile data")) || bailout()

        val switches = device.findObjects(By.clazz("android.widget.Switch"))
        if(switches.size !=1) {
            bailout()

        }
        // first switch is mobile data, must not be selected
        else if(switches[0].isChecked) {
            Log.w(LTAG, "Mobile Data is in enabled state, disabling it.")
            try {
                performWithRetry { device.findObject(By.text("Mobile data")).click() }
            } catch(e: IllegalStateException) {
                bailout()
            }
        }
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

        openSettings()

        performWithRetry { device.findObject(By.text("Connections")).click() }
        performWithRetry { device.findObject(By.text("SIM manager")).click() }
        performWithRetry { device.findObject(By.text("eSIM 1")).click() }
        performWithRetry { device.findObject(By.text("Remove")).click() }
        enterPIN()
        performWithRetry { device.findObject(By.text("Remove")).click() }

        // can take some time until sim was removed
        detectObject(By.text("Add eSIM"), IDLE_TIMEOUT * 10)
                || throw IllegalStateException("Failed to wait for screen after removal.")

        // check that it worked
        if(device.findObject(By.text("eSIM 1")) != null) {
            throw IllegalStateException("Failed to eject eSIM.")
        }

        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)

        // if everything worked, we can mark this sim as released
        releaseESIM(phonenumber)
    }

    override fun disableSound() {
        Log.i(LTAG, "Starting to enable silent mode.")

        if(!device.isScreenOn) unlockDevice()
        device.pressHome()

        openSettings()

        // scroll until sounds and vibration text
        val ret = UiScrollable(UiSelector()
            .scrollable(true)
            .className("androidx.recyclerview.widget.RecyclerView"))
            .scrollTextIntoView("Sounds and vibration")
        if(!ret) {
            Log.e(LTAG, "Could not find Sounds and vibration text element. Aborting.")
            throw IllegalStateException("Failed to find Sounds and vibration text.")
        }

        performWithRetry { device.findObject(By.text("Sounds and vibration")).click() }
        performWithRetry { device.findObject(By.text("Mute")).click() }

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

        // scroll down to end, retry to be safe?
        for(i in 0..4) {
            performWithRetry {
                assert(UiScrollable(UiSelector().scrollable(true).className("androidx.recyclerview.widget.RecyclerView")).flingToEnd(100))
            }
        }

        performWithRetry { device.findObject(By.text("Developer options")).click() }

        // scroll to auto update system
        val ret = UiScrollable(UiSelector()
            .scrollable(true)
            .className("androidx.recyclerview.widget.RecyclerView"))
            .scrollTextIntoView("Auto update system")
        if(!ret) {
            Log.e(LTAG, "Could not find 'auto update system' element. Aborting.")
            throw IllegalStateException("Failed to find text.")
        }

        performWithRetry { device.findObject(By.text("Auto update system")).click() }

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
        UiScrollable(UiSelector().scrollable(true).className("androidx.recyclerview.widget.RecyclerView")).scrollForward(200)
        device.waitForIdle(IDLE_TIMEOUT)

        // click on display settings
        performWithRetry { device.findObject(By.text("Display")).click() }

        // scroll down a bit
        UiScrollable(UiSelector().scrollable(true).className("androidx.recyclerview.widget.RecyclerView")).scrollForward(200)
        device.waitForIdle(IDLE_TIMEOUT)

        // click on screen timeout
        performWithRetry { device.findObject(By.text("Screen timeout")).click() }

        // select 10 minute timeout, aka the highest option
        performWithRetry { device.findObject(By.text("10 minutes")).click() }

        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
    }

    override fun factoryReset() {
        Log.i(LTAG, "Initiating factory reset.")

        if(!device.isScreenOn) unlockDevice()
        device.pressHome()

        openSettings()

        // get root scrollable container and scroll to end
        performWithRetry {
            assert(UiScrollable(UiSelector().scrollable(true).className("androidx.recyclerview.widget.RecyclerView")).flingToEnd(100))
        }

        // open general device management
        performWithRetry { device.findObject(By.text("General management")).click() }

        // get root scrollable container and scroll to end
        performWithRetry {
            assert(UiScrollable(UiSelector().scrollable(true).className("androidx.recyclerview.widget.RecyclerView")).scrollToEnd(100))
        }

        performWithRetry { device.findObject(By.text("Reset")).click() }

        // get root scrollable container and scroll to end
        performWithRetry {
            assert(UiScrollable(UiSelector().scrollable(true)).scrollToEnd(100))
        }

        performWithRetry { device.findObject(By.text("Factory data reset")).click() }

        // get root scrollable container and scroll to end (this is for some reason no RecyclerView)
        detectObject(By.textContains("All data will be erased from your phone,"))
                || throw IllegalStateException("Failed to find reset text.")

        // if there was an account logged in, there can be more content and a scroll down is required.
        if(detectObject(By.scrollable(true).clazz("android.widget.ScrollView"), SHORT_WAIT)) {
            performWithRetry {
                assert(UiScrollable(UiSelector().scrollable(true).className("android.widget.ScrollView")).flingToEnd(100))
            }
        }

        // select eSIms for deletion (in case earlier eject has gone wrong, is not always there)
        try {
            performWithRetry({device.findObject(By.text("eSIMs")).click()},
                true, 10)
        } catch(e: IllegalStateException) {
            // It's fine if there is no eSIMs button
        }
        performWithRetry { device.findObject(By.text("Reset")).click() }
        enterPIN()

        performWithRetry { device.findObject(By.text("Delete all")).click() }

        logAccountAction("PREV_ACC", getSerial(), "logout (factory reset)")

        // try to click the "remove esim" thingy (fails sometimes?)
        var iterations = 0
        while(detectObject(By.text("Remove all eSIMs?"))) {
            performWithRetry {device.findObject(By.text("Remove")).click() }
            if(iterations++ > 30)
                throw IllegalStateException("Exceeded 30 iterations when trying to confirm sim removal during reset.")
            // dialogue re-appears sometimes
            Thread.sleep(1000)
        }

        // we want to fail if the devices is not starting to reset now.
        Thread.sleep(5000)
        throw java.lang.IllegalStateException("Device still up, even though it should start resetting!")
    }

    override fun openGoogleSettings() {
        openSettings()

        // scroll until google text
        val ret = UiScrollable(UiSelector()
            .scrollable(true)
            .className("androidx.recyclerview.widget.RecyclerView"))
            .scrollTextIntoView("Google")
        if(!ret) {
            Log.e(LTAG, "Could not find Google text element. Aborting.")
            throw IllegalStateException("Failed to find Google text.")
        }

        performWithRetry { device.findObject(By.text("Google")).click() }
    }

    override fun logoutAccount(email: String) {
        Log.i(LTAG, "Initiating account logout.")

        // initial test that the harvester server is reachable
        checkAlive()

        if(!device.isScreenOn) unlockDevice()
        device.pressHome()

        // check that we have wifi
        checkWIFIConnectivity()

        openSettings()

        // scroll until google text
        val ret = UiScrollable(UiSelector()
            .scrollable(true)
            .className("androidx.recyclerview.widget.RecyclerView"))
            .scrollTextIntoView("Google")
        if(!ret) {
            Log.e(LTAG, "Could not find Google text element. Aborting.")
            throw IllegalStateException("Failed to find Google text.")
        }

        performWithRetry { device.findObject(By.text("Google")).click() }
        performWithRetry { device.findObject(By.text(email)).click() }
        performWithRetry { device.findObject(By.text("Manage accounts on this device")).click() }
        performWithRetry { device.findObject(By.text(email)).click() }
        performWithRetry { device.findObject(By.text("Remove account")).click() }
        performWithRetry { device.findObject(By.text("Remove account")).click() }
        performWithRetry { device.findObject(By.text("OK")).click() }
        enterPIN()

        logAccountAction(email, getSerial(), "logout")

        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
    }
}
